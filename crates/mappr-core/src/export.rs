//! Saving the map: the frontend hands over its SVG, which is written as is,
//! converted to PDF, or rasterised at a print width and resolution (PNG,
//! JPEG, TIFF, WebP), following PyMappr's save rules.

use std::path::Path;
use std::sync::OnceLock;

pub use resvg::{tiny_skia, usvg};
use serde::Deserialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Format {
    Svg,
    Pdf,
    Png,
    Jpeg,
    Tiff,
    Webp,
}

#[derive(Debug, thiserror::Error)]
pub enum ExportError {
    #[error("the map could not be read as SVG: {0}")]
    Svg(String),
    #[error("an image {0} × {1} pixels is too large")]
    TooLarge(u32, u32),
    #[error("could not write {path}: {message}")]
    Write { path: String, message: String },
}

/// Pixel width of a print `width_cm` wide at `dpi`.
pub fn pixel_width(width_cm: f64, dpi: f64) -> u32 {
    (width_cm / 2.54 * dpi).round().max(1.0) as u32
}

/// DejaVu Sans, matplotlib's default font (and so PyMappr's), compiled in so
/// exports render map text exactly as the screen does on any machine.
const MAP_FONTS: [&[u8]; 4] = [
    include_bytes!("../fonts/DejaVuSans.ttf"),
    include_bytes!("../fonts/DejaVuSans-Bold.ttf"),
    include_bytes!("../fonts/DejaVuSans-Oblique.ttf"),
    include_bytes!("../fonts/DejaVuSans-BoldOblique.ttf"),
];

fn load_map_fonts(db: &mut usvg::fontdb::Database) {
    for font in MAP_FONTS {
        db.load_font_data(font.to_vec());
    }
}

fn options() -> &'static usvg::Options<'static> {
    static OPTIONS: OnceLock<usvg::Options<'static>> = OnceLock::new();
    OPTIONS.get_or_init(|| {
        let mut opt = usvg::Options::default();
        let db = opt.fontdb_mut();
        load_map_fonts(db);
        db.load_system_fonts();
        db.set_sans_serif_family("DejaVu Sans");
        opt
    })
}

/// Rasterise `svg` onto a white canvas `width_px` wide.
pub fn render_pixmap(svg: &str, width_px: u32) -> Result<tiny_skia::Pixmap, ExportError> {
    let tree = usvg::Tree::from_str(svg, options()).map_err(|e| ExportError::Svg(e.to_string()))?;
    let size = tree.size();
    let scale = width_px as f32 / size.width();
    let height_px = (size.height() * scale).round().max(1.0) as u32;
    if u64::from(width_px) * u64::from(height_px) > 400_000_000 {
        return Err(ExportError::TooLarge(width_px, height_px));
    }
    let mut pixmap = tiny_skia::Pixmap::new(width_px, height_px).ok_or(ExportError::TooLarge(width_px, height_px))?;
    pixmap.fill(tiny_skia::Color::WHITE);
    resvg::render(&tree, tiny_skia::Transform::from_scale(scale, scale), &mut pixmap.as_mut());
    Ok(pixmap)
}

/// Rasterise `svg` to PNG bytes `width_px` wide, tagged with `dpi`.
pub fn render_png(svg: &str, width_px: u32, dpi: f64) -> Result<Vec<u8>, ExportError> {
    let pixmap = render_pixmap(svg, width_px)?;
    let png = pixmap.encode_png().map_err(|e| ExportError::Svg(e.to_string()))?;
    Ok(with_dpi(png, dpi))
}

pub fn export(svg: &str, format: Format, width_px: u32, dpi: f64, path: &Path) -> Result<(), ExportError> {
    let bytes = match format {
        Format::Svg => svg.as_bytes().to_vec(),
        Format::Pdf => render_pdf(svg)?,
        Format::Png => render_png(svg, width_px, dpi)?,
        Format::Jpeg => render_jpeg(svg, width_px, dpi)?,
        Format::Tiff => render_tiff(svg, width_px, dpi)?,
        Format::Webp => render_webp(svg, width_px)?,
    };
    std::fs::write(path, bytes).map_err(|e| ExportError::Write {
        path: path.display().to_string(),
        message: e.to_string(),
    })
}

fn rgb_bytes(pixmap: &tiny_skia::Pixmap) -> Vec<u8> {
    // The canvas is opaque white underneath, so dropping alpha is exact.
    pixmap.data().chunks_exact(4).flat_map(|p| [p[0], p[1], p[2]]).collect()
}

fn encode_err(e: impl std::fmt::Display) -> ExportError {
    ExportError::Svg(e.to_string())
}

/// JPEG on white (no alpha), quality 95, with the DPI in its JFIF header.
pub fn render_jpeg(svg: &str, width_px: u32, dpi: f64) -> Result<Vec<u8>, ExportError> {
    let pixmap = render_pixmap(svg, width_px)?;
    let mut out = Vec::new();
    let mut enc = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut out, 95);
    let d = dpi.round().clamp(1.0, 65535.0) as u16;
    enc.set_pixel_density(image::codecs::jpeg::PixelDensity::dpi(d));
    enc.encode(&rgb_bytes(&pixmap), pixmap.width(), pixmap.height(), image::ExtendedColorType::Rgb8)
        .map_err(encode_err)?;
    Ok(out)
}

/// TIFF with LZW compression and the DPI tag, saved as greyscale when every
/// pixel is grey (PyMappr's journal-ready rule).
pub fn render_tiff(svg: &str, width_px: u32, dpi: f64) -> Result<Vec<u8>, ExportError> {
    use tiff::encoder::{Compression, Rational, TiffEncoder, colortype};
    use tiff::tags::ResolutionUnit;

    let pixmap = render_pixmap(svg, width_px)?;
    let (w, h) = (pixmap.width(), pixmap.height());
    let rgb = rgb_bytes(&pixmap);
    let grey = rgb.chunks_exact(3).all(|p| p[0] == p[1] && p[1] == p[2]);
    let mut out = std::io::Cursor::new(Vec::new());
    let mut enc = TiffEncoder::new(&mut out).map_err(encode_err)?.with_compression(Compression::Lzw);
    let res = Rational { n: dpi.round().max(1.0) as u32, d: 1 };
    if grey {
        let luma: Vec<u8> = rgb.chunks_exact(3).map(|p| p[0]).collect();
        let mut img = enc.new_image::<colortype::Gray8>(w, h).map_err(encode_err)?;
        img.resolution(ResolutionUnit::Inch, res);
        img.write_data(&luma).map_err(encode_err)?;
    } else {
        let mut img = enc.new_image::<colortype::RGB8>(w, h).map_err(encode_err)?;
        img.resolution(ResolutionUnit::Inch, res);
        img.write_data(&rgb).map_err(encode_err)?;
    }
    Ok(out.into_inner())
}

/// Lossless WebP on white.
pub fn render_webp(svg: &str, width_px: u32) -> Result<Vec<u8>, ExportError> {
    let pixmap = render_pixmap(svg, width_px)?;
    let mut out = Vec::new();
    image::codecs::webp::WebPEncoder::new_lossless(&mut out)
        .encode(&rgb_bytes(&pixmap), pixmap.width(), pixmap.height(), image::ExtendedColorType::Rgb8)
        .map_err(encode_err)?;
    Ok(out)
}

/// Vector PDF with real (embedded, editable) text.
pub fn render_pdf(svg: &str) -> Result<Vec<u8>, ExportError> {
    use svg2pdf::usvg as pdf_usvg;
    static FONTS: OnceLock<std::sync::Arc<pdf_usvg::fontdb::Database>> = OnceLock::new();
    let fontdb = FONTS.get_or_init(|| {
        let mut db = pdf_usvg::fontdb::Database::new();
        for font in MAP_FONTS {
            db.load_font_data(font.to_vec());
        }
        db.load_system_fonts();
        db.set_sans_serif_family("DejaVu Sans");
        std::sync::Arc::new(db)
    });
    let opt = pdf_usvg::Options { fontdb: fontdb.clone(), ..Default::default() };
    let tree = pdf_usvg::Tree::from_str(svg, &opt).map_err(|e| ExportError::Svg(e.to_string()))?;
    svg2pdf::to_pdf(&tree, svg2pdf::ConversionOptions::default(), svg2pdf::PageOptions::default())
        .map_err(|e| ExportError::Svg(format!("{e:?}")))
}

/// Insert a pHYs chunk after IHDR so print software sees the DPI.
fn with_dpi(png: Vec<u8>, dpi: f64) -> Vec<u8> {
    const IHDR_END: usize = 8 + 25; // signature + IHDR chunk (length, type, 13 bytes, crc)
    if png.len() < IHDR_END {
        return png;
    }
    let ppm = (dpi / 0.0254).round() as u32;
    let mut body = Vec::with_capacity(13);
    body.extend_from_slice(b"pHYs");
    body.extend_from_slice(&ppm.to_be_bytes());
    body.extend_from_slice(&ppm.to_be_bytes());
    body.push(1); // unit: metre
    let mut chunk = Vec::with_capacity(21);
    chunk.extend_from_slice(&9u32.to_be_bytes());
    chunk.extend_from_slice(&body);
    chunk.extend_from_slice(&crc32(&body).to_be_bytes());

    let mut out = Vec::with_capacity(png.len() + chunk.len());
    out.extend_from_slice(&png[..IHDR_END]);
    out.extend_from_slice(&chunk);
    out.extend_from_slice(&png[IHDR_END..]);
    out
}

fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = 0xFFFF_FFFFu32;
    for &b in bytes {
        crc ^= u32::from(b);
        for _ in 0..8 {
            crc = if crc & 1 != 0 { (crc >> 1) ^ 0xEDB8_8320 } else { crc >> 1 };
        }
    }
    !crc
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crc_matches_known_value() {
        assert_eq!(crc32(b"IEND"), 0xAE42_6082);
    }

    #[test]
    fn png_has_requested_size_and_dpi() {
        let svg = r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100" width="200" height="100"><rect width="200" height="100" fill="#d62728"/></svg>"##;
        let width = pixel_width(17.0, 600.0);
        assert_eq!(width, 4016);
        let png = render_png(svg, 400, 600.0).unwrap();
        assert_eq!(&png[12..16], b"IHDR");
        assert_eq!(u32::from_be_bytes(png[16..20].try_into().unwrap()), 400);
        assert_eq!(u32::from_be_bytes(png[20..24].try_into().unwrap()), 200);
        assert_eq!(&png[37..41], b"pHYs");
        assert_eq!(u32::from_be_bytes(png[41..45].try_into().unwrap()), 23622);
    }

    const COLOUR: &str = r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10" width="20pt" height="10pt"><rect width="10" height="10" fill="#d62728"/><text x="11" y="8" font-family="DejaVu Sans" font-size="6">A</text></svg>"##;
    const GREY: &str = r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10" width="20" height="10"><rect width="10" height="10" fill="#808080"/></svg>"##;

    #[test]
    fn every_format_encodes() {
        assert_eq!(&render_jpeg(COLOUR, 40, 300.0).unwrap()[..2], &[0xFF, 0xD8]);
        assert_eq!(&render_webp(COLOUR, 40).unwrap()[8..12], b"WEBP");
        let pdf = render_pdf(COLOUR).unwrap();
        assert_eq!(&pdf[..5], b"%PDF-");
        let tiff = render_tiff(COLOUR, 40, 600.0).unwrap();
        assert!(&tiff[..4] == b"II*\0" || &tiff[..4] == b"MM\0*");
    }

    #[test]
    fn tiff_is_greyscale_only_when_the_map_is() {
        let decode = |bytes: Vec<u8>| {
            let mut d = tiff::decoder::Decoder::new(std::io::Cursor::new(bytes)).unwrap();
            d.colortype().unwrap()
        };
        assert_eq!(decode(render_tiff(GREY, 20, 300.0).unwrap()), tiff::ColorType::Gray(8));
        assert_eq!(decode(render_tiff(COLOUR, 20, 300.0).unwrap()), tiff::ColorType::RGB(8));
    }

    #[test]
    fn draws_use_markers_and_text() {
        // The frontend draws markers as <use href> and the legend as <text>.
        let svg = r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50" width="100" height="50">
            <defs><path id="m" d="M-1 -1H1V1H-1Z"/></defs>
            <use href="#m" transform="translate(20 25) scale(10)" fill="#000000"/>
            <text x="50" y="35" font-family="DejaVu Sans" font-size="30" font-style="italic">Ab</text>
        </svg>"##;
        let png = render_png(svg, 100, 96.0).unwrap();
        let tree = usvg::Tree::from_str(svg, options()).unwrap();
        let mut pixmap = tiny_skia::Pixmap::new(100, 50).unwrap();
        resvg::render(&tree, tiny_skia::Transform::default(), &mut pixmap.as_mut());
        let alpha = |x: u32, y: u32| pixmap.pixel(x, y).unwrap().alpha();
        assert_eq!(alpha(20, 25), 255, "the <use> marker is drawn");
        let text_ink = (50..100).flat_map(|x| (10..45).map(move |y| (x, y))).filter(|&(x, y)| alpha(x, y) > 0).count();
        assert!(text_ink > 50, "the legend text is drawn ({text_ink} px)");
        assert!(png.len() > 100);
    }
}
