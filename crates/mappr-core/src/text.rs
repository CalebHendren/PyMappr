//! Text measured and outlined the way matplotlib 3.11 does it, so map text
//! lands where PyMappr puts it.
//!
//! matplotlib's Agg renderer measures and draws text through FreeType and
//! libraqm (HarfBuzz): `FT_Set_Char_Size(size * 64, dpi)` with the face's
//! integer-ppem flag set (all DejaVu faces), so the em is rounded to whole
//! pixels; glyphs are loaded with `FT_LOAD_DEFAULT`, which runs the TrueType
//! bytecode (v40 interpreter); advances are the hinted, whole-pixel ones
//! and kerning comes from GPOS scaled to 26.6. A string's width is the pen
//! advance and its height and descent come from the union of the hinted
//! glyphs' control boxes (`FT2Font::set_text`). skrifa's interpreter is a
//! port of FreeType's and harfrust is a port of HarfBuzz, so both give the
//! same numbers.
//!
//! Text with a path effect (the labels' white halo) is drawn instead as
//! unhinted outlines laid out at 100 pt and 72 dpi and scaled
//! (`TextToPath`), which `Mode::Path` reproduces.

use std::collections::HashMap;

use harfrust::font::{BuiltinFontFuncs, FontFuncs};
use harfrust::{ShapeOptions, ShaperData, UnicodeBuffer};
use skrifa::instance::{LocationRef, Size};
use skrifa::outline::{DrawSettings, HintingInstance, HintingOptions, OutlinePen};
use skrifa::raw::TableProvider;
use skrifa::{FontRef, GlyphId, MetadataProvider, OutlineGlyphCollection};

use crate::export::MAP_FONTS;

/// How the text will be drawn, which decides how it is measured.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Mode {
    /// Agg's own text: hinted at the rounded ppem.
    Agg,
    /// matplotlib's TextToPath (text with path effects): unhinted.
    Path,
}

/// The faces in `export::MAP_FONTS`: family 0 Sans, 1 Serif, 2 Sans Mono.
pub fn face_index(family: usize, bold: bool, italic: bool) -> usize {
    family.min(2) * 4 + usize::from(bold) + 2 * usize::from(italic)
}

/// A shaped string in pixels at the requested dpi.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Shaped {
    /// The pen advance (matplotlib's text width).
    pub width: f64,
    /// Ink height: top of the highest control box to the bottom of the lowest.
    pub height: f64,
    /// Depth of the ink below the baseline.
    pub descent: f64,
    /// The glyph outlines as SVG path data, y down, with the origin at the
    /// start of the baseline.
    pub path: String,
}

/// The requested em in 26.6 pixels for `FT_Set_Char_Size(face, size * 64, 0,
/// dpi, dpi)` (FT_REQUEST_WIDTH).
pub fn em_26_6(size_pt: f64, dpi: f64) -> i64 {
    let char_size = (size_pt * 64.0) as i64;
    let res = dpi as i64;
    (char_size * res + 36) / 72
}

/// FreeType's ppem for that request: the em rounded to whole pixels, which
/// is what a face with the integer-ppem flag is hinted at.
pub fn ppem(size_pt: f64, dpi: f64) -> i64 {
    ((em_26_6(size_pt, dpi) + 32) >> 6).max(1)
}

/// matplotlib's TextToPath lays text out at this size and 72 dpi.
const PATH_FONT_SCALE: f64 = 100.0;

/// Measures and outlines `text` in face `face` (see `face_index`) at
/// `size_pt` points and `dpi`.
pub fn shape(text: &str, face: usize, size_pt: f64, dpi: f64, mode: Mode) -> Shaped {
    let data = MAP_FONTS[face.min(MAP_FONTS.len() - 1)];
    let Ok(font) = FontRef::new(data) else {
        return Shaped::default();
    };
    let outlines = font.outline_glyphs();
    let upem = i64::from(font.head().map(|h| h.units_per_em()).unwrap_or(2048));
    let (ppem, out_scale) = match mode {
        Mode::Agg => (ppem(size_pt, dpi), 1.0),
        Mode::Path => (PATH_FONT_SCALE as i64, size_pt * dpi / 72.0 / PATH_FONT_SCALE),
    };
    let hinting = match mode {
        Mode::Agg => HintingInstance::new(&outlines, Size::new(ppem as f32), LocationRef::default(), HintingOptions::default()).ok(),
        Mode::Path => None,
    };
    let metrics = font.glyph_metrics(Size::unscaled(), LocationRef::default());
    let mut glyphs = GlyphSource { outlines: &outlines, metrics, hinting: hinting.as_ref(), ppem, upem, cache: HashMap::new() };

    let shaper_data = ShaperData::new(&font);
    let shaper = shaper_data.shaper(&font).build();
    let mut buffer = UnicodeBuffer::new();
    buffer.push_str(text);
    buffer.guess_segment_properties();
    // HarfBuzz's scale through FreeType (hb_ft) is x_scale * upem >> 16: the
    // requested em in 26.6, not the rounded ppem the hinter uses. It scales
    // the kerning; the advances are the hinted ones.
    let hb_scale = match mode {
        Mode::Agg => em_26_6(size_pt, dpi),
        Mode::Path => ppem * 64,
    };
    let mut funcs = Advances { glyphs: &mut glyphs };
    let shaped = shaper.shape(buffer, ShapeOptions::new().scale(Some(hb_scale as i32)).font_funcs(Some(&mut funcs)));

    let mut pen_x: i64 = 0;
    let mut pen_y: i64 = 0;
    let (mut x0, mut y0, mut x1, mut y1) = (i64::MAX, i64::MAX, i64::MIN, i64::MIN);
    let mut path = PathWriter { out: String::new(), scale: out_scale / 64.0, dx: 0, dy: 0 };
    for (info, pos) in shaped.glyph_infos().iter().zip(shaped.glyph_positions()) {
        // FT2Font::set_text skips missing glyphs without advancing.
        if info.glyph_id == 0 {
            continue;
        }
        pen_x += i64::from(pos.x_offset);
        pen_y += i64::from(pos.y_offset);
        let glyph = glyphs.get(GlyphId::new(info.glyph_id));
        // An empty outline's box is all zeros and is not moved by the pen.
        let cbox = match glyph.cbox {
            Some([a, b, c, d]) => [a + pen_x, b + pen_y, c + pen_x, d + pen_y],
            None => [0, 0, 0, 0],
        };
        x0 = x0.min(cbox[0]);
        y0 = y0.min(cbox[1]);
        x1 = x1.max(cbox[2]);
        y1 = y1.max(cbox[3]);
        path.dx = pen_x;
        path.dy = pen_y;
        path.replay(&glyph.commands);
        pen_x += i64::from(pos.x_advance) - i64::from(pos.x_offset);
        pen_y += i64::from(pos.y_advance) - i64::from(pos.y_offset);
    }
    if x0 > x1 {
        (y0, y1) = (0, 0);
    }
    let k = out_scale / 64.0;
    Shaped { width: pen_x as f64 * k, height: (y1 - y0) as f64 * k, descent: -y0 as f64 * k, path: path.out }
}

/// One glyph's outline in 26.6 units (y up), its control box and advance.
struct Glyph {
    commands: Vec<Command>,
    cbox: Option<[i64; 4]>,
    advance: i64,
}

#[derive(Clone, Copy)]
enum Command {
    Move(i64, i64),
    Line(i64, i64),
    Quad(i64, i64, i64, i64),
    Cubic(i64, i64, i64, i64, i64, i64),
    Close,
}

struct GlyphSource<'a> {
    outlines: &'a OutlineGlyphCollection<'a>,
    metrics: skrifa::metrics::GlyphMetrics<'a>,
    hinting: Option<&'a HintingInstance>,
    ppem: i64,
    upem: i64,
    cache: HashMap<u32, std::rc::Rc<Glyph>>,
}

impl GlyphSource<'_> {
    fn get(&mut self, gid: GlyphId) -> std::rc::Rc<Glyph> {
        if let Some(g) = self.cache.get(&gid.to_u32()) {
            return g.clone();
        }
        let mut pen = Recorder::default();
        let mut advance = 0;
        if let Some(outline) = self.outlines.get(gid) {
            match self.hinting {
                Some(instance) => {
                    if let Ok(metrics) = outline.draw(DrawSettings::hinted(instance, false), &mut pen) {
                        advance = metrics.advance_width.map(|a| (f64::from(a) * 64.0).round() as i64).unwrap_or(0);
                    }
                }
                None => {
                    let _ = outline.draw(DrawSettings::unhinted(Size::new(self.ppem as f32), LocationRef::default()), &mut pen);
                }
            }
        }
        if self.hinting.is_none() {
            advance = self.unhinted_advance(gid);
        }
        let glyph = std::rc::Rc::new(Glyph { cbox: pen.cbox(), commands: pen.commands, advance });
        self.cache.insert(gid.to_u32(), glyph.clone());
        glyph
    }

    /// FT_Get_Advance's unhinted fast path through hb_ft: the 16.16 advance
    /// `FT_MulDiv(aw, x_scale, 64)`, rounded to 26.6.
    fn unhinted_advance(&self, gid: GlyphId) -> i64 {
        let aw = i64::from(self.metrics.advance_width(gid).unwrap_or(0.0).round() as i32);
        let x_scale = ((self.ppem << 6 << 16) + self.upem / 2) / self.upem;
        let v = (aw * x_scale + 32) / 64;
        (v + 512) >> 10
    }
}

/// Hinted (or unhinted) advances for harfrust, in its 26.6 scale.
struct Advances<'a, 'b> {
    glyphs: &'a mut GlyphSource<'b>,
}

impl FontFuncs for Advances<'_, '_> {
    fn advance_width(&mut self, _builtin: &BuiltinFontFuncs, glyph: GlyphId) -> i32 {
        self.glyphs.get(glyph).advance as i32
    }
}

/// Collects an outline in 26.6 units.
#[derive(Default)]
struct Recorder {
    commands: Vec<Command>,
    points: Vec<(i64, i64)>,
}

fn f26(v: f32) -> i64 {
    (f64::from(v) * 64.0).round() as i64
}

impl Recorder {
    fn cbox(&self) -> Option<[i64; 4]> {
        let mut it = self.points.iter();
        let &(x, y) = it.next()?;
        let mut b = [x, y, x, y];
        for &(x, y) in it {
            b = [b[0].min(x), b[1].min(y), b[2].max(x), b[3].max(y)];
        }
        Some(b)
    }
}

impl OutlinePen for Recorder {
    fn move_to(&mut self, x: f32, y: f32) {
        let (x, y) = (f26(x), f26(y));
        self.points.push((x, y));
        self.commands.push(Command::Move(x, y));
    }
    fn line_to(&mut self, x: f32, y: f32) {
        let (x, y) = (f26(x), f26(y));
        self.points.push((x, y));
        self.commands.push(Command::Line(x, y));
    }
    fn quad_to(&mut self, cx: f32, cy: f32, x: f32, y: f32) {
        let (cx, cy, x, y) = (f26(cx), f26(cy), f26(x), f26(y));
        self.points.extend([(cx, cy), (x, y)]);
        self.commands.push(Command::Quad(cx, cy, x, y));
    }
    fn curve_to(&mut self, cx0: f32, cy0: f32, cx1: f32, cy1: f32, x: f32, y: f32) {
        let c = [f26(cx0), f26(cy0), f26(cx1), f26(cy1), f26(x), f26(y)];
        self.points.extend([(c[0], c[1]), (c[2], c[3]), (c[4], c[5])]);
        self.commands.push(Command::Cubic(c[0], c[1], c[2], c[3], c[4], c[5]));
    }
    fn close(&mut self) {
        self.commands.push(Command::Close);
    }
}

/// Writes outlines as SVG path data, y flipped to point down.
struct PathWriter {
    out: String,
    scale: f64,
    dx: i64,
    dy: i64,
}

impl PathWriter {
    fn pt(&mut self, x: i64, y: i64) {
        use std::fmt::Write;
        let fx = (x + self.dx) as f64 * self.scale;
        let fy = -((y + self.dy) as f64) * self.scale;
        let _ = write!(self.out, "{} {}", num(fx), num(fy));
    }

    fn replay(&mut self, commands: &[Command]) {
        for c in commands {
            match *c {
                Command::Move(x, y) => {
                    self.out.push('M');
                    self.pt(x, y);
                }
                Command::Line(x, y) => {
                    self.out.push('L');
                    self.pt(x, y);
                }
                Command::Quad(cx, cy, x, y) => {
                    self.out.push('Q');
                    self.pt(cx, cy);
                    self.out.push(' ');
                    self.pt(x, y);
                }
                Command::Cubic(a, b, c, d, x, y) => {
                    self.out.push('C');
                    self.pt(a, b);
                    self.out.push(' ');
                    self.pt(c, d);
                    self.out.push(' ');
                    self.pt(x, y);
                }
                Command::Close => self.out.push('Z'),
            }
        }
    }
}

/// A coordinate with up to 6 decimals (26.6 values are exact at 6) and no
/// trailing zeros.
fn num(v: f64) -> String {
    let s = format!("{v:.6}");
    let s = s.trim_end_matches('0').trim_end_matches('.');
    if s == "-0" { "0".to_string() } else { s.to_string() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ppem_rounds_like_freetype() {
        assert_eq!(ppem(9.0, 100.0), 13);
        assert_eq!(ppem(8.0, 100.0), 11);
        assert_eq!(ppem(10.0, 72.0), 10);
        assert_eq!(ppem(9.0, 600.0), 75);
    }

    /// Numbers from matplotlib 3.11.1 (FT2Font.set_text with
    /// LoadFlags.DEFAULT, then get_width_height / get_descent, in 26.6).
    #[test]
    fn agg_metrics_match_matplotlib() {
        let sans = face_index(0, false, false);
        let cases = [
            ("lp", 9.0, 100.0, 768, 896, 192),
            ("Eleusis", 9.0, 100.0, 2944, 704, 0),
            ("Xanthopygus", 9.0, 100.0, 5440, 896, 192),
            ("lp", 8.0, 100.0, 640, 704, 128),
            ("Plociopterus", 9.0, 600.0, 29504, 4672, 1024),
        ];
        for (text, size, dpi, w, h, d) in cases {
            let s = shape(text, sans, size, dpi, Mode::Agg);
            assert_eq!((s.width * 64.0, s.height * 64.0, s.descent * 64.0), (f64::from(w), f64::from(h), f64::from(d)), "{text} {size} {dpi}");
        }
    }

    /// The dump written by the parity notes' `dump_metrics.py`, when given.
    #[test]
    fn agg_metrics_match_dump() {
        let Some(path) = std::env::var_os("MPL_METRICS") else { return };
        let rows: Vec<serde_json::Value> = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
        let mut bad = 0;
        let mut total = 0;
        for r in &rows {
            let fam = match r[0].as_str().unwrap() {
                "DejaVu Sans" => 0,
                "DejaVu Serif" => 1,
                _ => 2,
            };
            let face = face_index(fam, r[1] == "bold", r[2] == "italic");
            let size = r[3].as_f64().unwrap();
            let dpi = r[4].as_f64().unwrap();
            let text = r[5].as_str().unwrap();
            let want = [r[6].as_i64().unwrap(), r[7].as_i64().unwrap(), r[8].as_i64().unwrap()];
            let mode = if r.get(9).is_some() { Mode::Path } else { Mode::Agg };
            let s = shape(text, face, size, dpi, mode);
            let k = 64.0;
            let got = [(s.width * k).round() as i64, (s.height * k).round() as i64, (s.descent * k).round() as i64];
            total += 1;
            if got != want {
                bad += 1;
                if bad <= 40 {
                    eprintln!("{r} -> {got:?}");
                }
            }
        }
        eprintln!("{bad} of {total} differ");
        assert_eq!(bad, 0);
    }
}
