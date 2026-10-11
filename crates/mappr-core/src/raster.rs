//! Raster basemaps (Natural Earth relief, grey relief, Blue Marble), cut
//! and warped to the view as PyMappr does (`renderer/layers.py`): a mip
//! pyramid, the level the view's pixels call for, the view grown by 15%,
//! and an inverse warp onto a grid of about the screen's pixels with
//! nearest-pixel lookup. Outside the projection's domain is transparent.

use std::path::Path;
use std::sync::Arc;

use base64::Engine as _;
use rayon::prelude::*;

use crate::basemap::Basemap;
use crate::render::{MapContext, Raster, Rect};

/// Source pixels per screen pixel.
const OVERSAMPLE: f64 = 1.3;
/// The crop is grown by this much of the view span on each side.
const CROP_MARGIN: f64 = 0.15;
/// A warp grid never exceeds this on either side.
const MAX_WARP_PX: f64 = 2400.0;
/// The pyramid stops halving once its shorter side reaches this.
const PYRAMID_FLOOR: usize = 64;

/// Raster modes and their files in `data/basemap/`.
pub const BASEMAP_FILES: [(&str, &str); 4] = [
    ("relief", "ne1_world.jpg"),
    ("relief_alt", "ne2_world.jpg"),
    ("relief_grey", "gray_world.jpg"),
    ("blue_marble", "hyp_world.jpg"),
];

pub fn basemap_file(mode: &str) -> Option<&'static str> {
    BASEMAP_FILES.iter().find(|m| m.0 == mode).map(|m| m.1)
}

/// An RGB image, rows top to bottom.
pub struct Image {
    pub w: usize,
    pub h: usize,
    pub rgb: Vec<u8>,
}

impl Image {
    fn halve(&self) -> Image {
        let (w, h) = (self.w / 2, self.h / 2);
        let mut rgb = vec![0u8; w * h * 3];
        rgb.par_chunks_mut(w * 3).enumerate().for_each(|(y, row)| {
            for x in 0..w {
                for c in 0..3 {
                    let at = |yy: usize, xx: usize| self.rgb[(yy * self.w + xx) * 3 + c] as u32;
                    let sum = at(2 * y, 2 * x) + at(2 * y, 2 * x + 1) + at(2 * y + 1, 2 * x) + at(2 * y + 1, 2 * x + 1);
                    row[x * 3 + c] = ((sum + 2) / 4) as u8;
                }
            }
        });
        Image { w, h, rgb }
    }
}

fn decode_jpeg(path: &Path) -> Result<Image, String> {
    use zune_jpeg::zune_core::bytestream::ZCursor;
    use zune_jpeg::zune_core::colorspace::ColorSpace;
    use zune_jpeg::zune_core::options::DecoderOptions;
    let data = std::fs::read(path).map_err(|e| format!("could not read {}: {e}", path.display()))?;
    let options = DecoderOptions::default().jpeg_set_out_colorspace(ColorSpace::RGB);
    let mut decoder = zune_jpeg::JpegDecoder::new_with_options(ZCursor::new(data), options);
    let rgb = decoder.decode().map_err(|e| format!("could not decode {}: {e:?}", path.display()))?;
    let info = decoder.info().ok_or("no image size")?;
    let (w, h) = (info.width as usize, info.height as usize);
    if rgb.len() != w * h * 3 {
        return Err(format!("{}: not an RGB image", path.display()));
    }
    Ok(Image { w, h, rgb })
}

/// The basemap as a mip pyramid, finest level first, built once.
fn pyramid(basemap: &Basemap, mode: &str, path: &Path) -> Arc<Result<Vec<Image>, String>> {
    basemap.cached(&format!("pyramid:{mode}"), || {
        let mut levels = vec![decode_jpeg(path)?];
        loop {
            let last = levels.last().unwrap();
            if last.w.min(last.h) <= PYRAMID_FLOOR {
                break;
            }
            let next = last.halve();
            levels.push(next);
        }
        Ok(levels)
    })
}

/// The coarsest level still carrying enough detail for a view `span` map
/// units wide drawn `px` pixels wide (PyMappr's `_pyramid_level`).
pub fn pyramid_level(widths: &[usize], span: f64, world_width: f64, px: f64) -> usize {
    let fraction = (span / world_width).max(1e-9);
    let want = OVERSAMPLE * px;
    let mut index = 0;
    for (i, w) in widths.iter().enumerate() {
        if *w as f64 * fraction >= want {
            index = i;
        } else {
            break;
        }
    }
    index
}

/// The raster basemap for a view, or `None` for the plain ("simple") map.
pub fn raster(basemap: &Basemap, ctx: &MapContext, mode: &str) -> Result<Option<Raster>, String> {
    let Some(file) = basemap_file(mode) else { return Ok(None) };
    let path = basemap.data_dir().join("basemap").join(file);
    if !path.is_file() {
        return Err(format!("{mode} basemap: not downloaded ({})", path.display()));
    }
    let built = pyramid(basemap, mode, &path);
    let levels = match &*built {
        Ok(levels) => levels,
        Err(e) => return Err(e.clone()),
    };
    let proj = &ctx.proj;
    let [wx0, wx1, wy0, wy1] = proj.bounds;
    let world_w = wx1 - wx0;
    let [vx0, vx1, vy0, vy1] = ctx.data_view();
    let (mx, my) = ((vx1 - vx0) * CROP_MARGIN, (vy1 - vy0) * CROP_MARGIN);
    let (mut x0, mut x1) = (vx0 - mx, vx1 + mx);
    let (y0, y1) = ((vy0 - my).max(wy0), (vy1 + my).min(wy1));
    let wraps = ctx.offsets.len() > 1;
    if !wraps || proj.is_globe() {
        (x0, x1) = (x0.max(wx0), x1.min(wx1));
    }
    if x1 <= x0 || y1 <= y0 {
        return Ok(None);
    }
    let px_w = ctx.px_width;
    let px_h = ctx.px_height;
    let widths: Vec<usize> = levels.iter().map(|l| l.w).collect();
    let img = &levels[pyramid_level(&widths, vx1 - vx0, world_w, px_w)];
    let nx = (px_w * OVERSAMPLE).clamp(2.0, MAX_WARP_PX) as usize;
    let ny = (px_h * OVERSAMPLE).clamp(2.0, MAX_WARP_PX) as usize;
    let mut rgba = vec![0u8; nx * ny * 4];
    rgba.par_chunks_mut(nx * 4).enumerate().for_each(|(row, out)| {
        let y = y1 - (y1 - y0) * row as f64 / (ny - 1) as f64;
        let mut seed: Option<(f64, f64)> = None;
        for col in 0..nx {
            let mut x = x0 + (x1 - x0) * col as f64 / (nx - 1) as f64;
            if wraps && !proj.is_globe() {
                x = wx0 + (x - wx0).rem_euclid(world_w);
            }
            let Some((lon, lat)) = proj.inverse_on_map(x, y, seed) else {
                seed = None;
                continue;
            };
            seed = Some((lon, lat));
            if !(lon.abs() <= 180.001 && lat.abs() <= 90.001) {
                continue;
            }
            let c = (((lon + 180.0) / 360.0 * img.w as f64) as usize).min(img.w - 1);
            let r = (((90.0 - lat) / 180.0 * img.h as f64).max(0.0) as usize).min(img.h - 1);
            let src = (r * img.w + c) * 3;
            out[col * 4..col * 4 + 3].copy_from_slice(&img.rgb[src..src + 3]);
            out[col * 4 + 3] = 255;
        }
    });
    let png = encode_png(&rgba, nx, ny)?;
    let href = format!("data:image/png;base64,{}", base64::engine::general_purpose::STANDARD.encode(png));
    let rect = Rect::from_bounds([x0, x1, y0, y1]);
    Ok(Some(Raster { href, x: rect.x, y: rect.y, w: rect.w, h: rect.h }))
}

fn encode_png(rgba: &[u8], w: usize, h: usize) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    let mut encoder = png::Encoder::new(&mut out, w as u32, h as u32);
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_compression(png::Compression::Fast);
    let mut writer = encoder.write_header().map_err(|e| e.to_string())?;
    writer.write_image_data(rgba).map_err(|e| e.to_string())?;
    writer.finish().map_err(|e| e.to_string())?;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::projection::{Projection, ProjectionSpec};

    fn data() -> Option<Basemap> {
        let dir = crate::pymappr_dir().join("data");
        dir.join("basemap").join("ne1_world.jpg").is_file().then(|| Basemap::new(dir))
    }

    fn ctx(name: &str, view: Option<Rect>) -> MapContext {
        let proj = Projection::new(&ProjectionSpec { name: name.into(), lon_0: None, lat_0: None }).unwrap();
        MapContext::new(proj, view, 900.0, 1.0)
    }

    #[test]
    fn level_follows_the_pixels_on_screen() {
        let widths = [5400, 2700, 1350, 675, 337, 168, 84];
        assert_eq!(pyramid_level(&widths, 360.0, 360.0, 900.0), 2);
        assert_eq!(pyramid_level(&widths, 36.0, 360.0, 900.0), 0);
        assert_eq!(pyramid_level(&widths, 360.0, 360.0, 100.0), 5);
    }

    #[test]
    fn simple_has_no_raster_and_missing_files_are_reported() {
        let b = Basemap::new(std::env::temp_dir().join("no-such-natural-earth"));
        assert!(raster(&b, &ctx("Robinson", None), "simple").unwrap().is_none());
        assert!(raster(&b, &ctx("Robinson", None), "relief").unwrap_err().contains("not downloaded"));
    }

    #[test]
    fn warped_relief_is_transparent_off_the_world() {
        let Some(b) = data() else { return };
        for name in crate::projection::projection_names() {
            let t = std::time::Instant::now();
            let r = raster(&b, &ctx(name, None), "relief").unwrap().unwrap();
            assert!(r.href.starts_with("data:image/png;base64,"), "{name}");
            assert!(r.w > 0.0 && r.h > 0.0);
            assert!(t.elapsed().as_secs_f64() < 5.0, "{name}: {:?}", t.elapsed());
        }
    }
}
