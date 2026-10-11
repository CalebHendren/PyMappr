//! Saving the map: the frontend hands over its SVG, which is written as is
//! or rasterised to a PNG at a print width and resolution.

use std::path::Path;
use std::sync::OnceLock;

use resvg::{tiny_skia, usvg};
use serde::Deserialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Format {
    Svg,
    Png,
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

fn options() -> &'static usvg::Options<'static> {
    static OPTIONS: OnceLock<usvg::Options<'static>> = OnceLock::new();
    OPTIONS.get_or_init(|| {
        let mut opt = usvg::Options::default();
        opt.fontdb_mut().load_system_fonts();
        opt
    })
}

/// Rasterise `svg` to PNG bytes `width_px` wide, tagged with `dpi`.
pub fn render_png(svg: &str, width_px: u32, dpi: f64) -> Result<Vec<u8>, ExportError> {
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
    let png = pixmap.encode_png().map_err(|e| ExportError::Svg(e.to_string()))?;
    Ok(with_dpi(png, dpi))
}

pub fn export(svg: &str, format: Format, width_px: u32, dpi: f64, path: &Path) -> Result<(), ExportError> {
    let bytes = match format {
        Format::Svg => svg.as_bytes().to_vec(),
        Format::Png => render_png(svg, width_px, dpi)?,
    };
    std::fs::write(path, bytes).map_err(|e| ExportError::Write {
        path: path.display().to_string(),
        message: e.to_string(),
    })
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

    #[test]
    fn draws_use_markers_and_text() {
        // The frontend draws markers as <use href> and the legend as <text>.
        let svg = r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50" width="100" height="50">
            <defs><path id="m" d="M-1 -1H1V1H-1Z"/></defs>
            <use href="#m" transform="translate(20 25) scale(10)" fill="#000000"/>
            <text x="50" y="35" font-family="Arial, Helvetica, sans-serif" font-size="30" font-style="italic">Ab</text>
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
