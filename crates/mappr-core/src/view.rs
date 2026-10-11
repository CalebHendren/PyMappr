//! Framing: the view that shows a lon/lat box (PyMappr's `set_extent`),
//! the lon/lat area a view shows, and ground distances between map points.

use geographiclib_rs::{Geodesic, InverseGeodesic};

use crate::projection::Projection;
use crate::render::Rect;

/// Fraction of the box's shorter side the globe's disk spans.
const GLOBE_FILL: f64 = 0.88;

/// A lon/lat box (lon0, lon1, lat0, lat1) projected to a box in map
/// coordinates (x0, x1, y0, y1, y up), its edges sampled 40 times
/// (PyMappr's `project_extent`). An east edge past the antimeridian lands
/// on the wrap copy one world-width east.
pub fn project_extent(proj: &Projection, extent: [f64; 4]) -> [f64; 4] {
    let [x0, x1, y0, y1] = extent;
    if proj.is_geographic() {
        return [x0, x1, y0, y1];
    }
    let seam = proj.lon_0 + 180.0;
    if !proj.is_globe() && proj.lon_halfspan >= 180.0 && x1 > seam {
        let west = project_extent(proj, [x0, seam - 1e-9, y0, y1]);
        let east = project_extent(proj, [seam - 360.0 + 1e-9, x1 - 360.0, y0, y1]);
        return [west[0], east[1] + proj.world_width(), west[2].min(east[2]), west[3].max(east[3])];
    }
    let (y0, y1) = (y0.max(proj.min_lat), y1.min(proj.max_lat));
    let n = 40;
    let t = |i: usize| i as f64 / (n - 1) as f64;
    let mut samples = Vec::new();
    if proj.is_globe() {
        for i in 0..n {
            for j in 0..n {
                samples.push([x0 + (x1 - x0) * t(j), y0 + (y1 - y0) * t(i)]);
            }
        }
    } else {
        for i in 0..n {
            let lon = x0 + (x1 - x0) * t(i);
            let lat = y0 + (y1 - y0) * t(i);
            samples.extend([[lon, y0], [lon, y1], [x0, lat], [x1, lat]]);
        }
    }
    let mut b = [f64::MAX, f64::MIN, f64::MAX, f64::MIN];
    for [lon, lat] in samples {
        if let Some((x, y)) = proj.forward_clamped(lon, lat) {
            b = [b[0].min(x), b[1].max(x), b[2].min(y), b[3].max(y)];
        }
    }
    if b[0] > b[1] { proj.bounds } else { b }
}

/// The view (SVG coordinates) showing a lon/lat box in a map box of
/// `aspect` (height / width): padded to the box so map units stay square,
/// kept inside the world unless the box crosses the antimeridian on
/// purpose. The globe always frames its whole disk.
pub fn extent_view(proj: &Projection, lonlat: [f64; 4], aspect: f64) -> Rect {
    let box_ratio = (1.0 / aspect.max(1e-6)).max(1e-6);
    let [wx0, wx1, wy0, wy1] = proj.bounds;
    if proj.is_globe() {
        let (cx, cy) = ((wx0 + wx1) / 2.0, (wy0 + wy1) / 2.0);
        let radius = (wx1 - wx0).max(wy1 - wy0) / 2.0;
        let short = radius / GLOBE_FILL;
        let half_h = if box_ratio >= 1.0 { short } else { short / box_ratio };
        let half_w = half_h * box_ratio;
        return Rect::from_bounds([cx - half_w, cx + half_w, cy - half_h, cy + half_h]);
    }
    let [mut x0, mut x1, mut y0, mut y1] = project_extent(proj, lonlat);
    let (world_w, world_h) = (wx1 - wx0, wy1 - wy0);
    let (width, height) = (x1 - x0, (y1 - y0).max(1e-12));
    if width / height < box_ratio {
        let new_w = height * box_ratio;
        if new_w <= world_w {
            let mut cx = (x0 + x1) / 2.0;
            if wx0 <= x0 && x1 <= wx1 {
                cx = cx.max(wx0 + new_w / 2.0).min(wx1 - new_w / 2.0);
            }
            (x0, x1) = (cx - new_w / 2.0, cx + new_w / 2.0);
        }
    } else {
        let new_h = width / box_ratio;
        if new_h <= world_h {
            let cy = ((y0 + y1) / 2.0).max(wy0 + new_h / 2.0).min(wy1 - new_h / 2.0);
            (y0, y1) = (cy - new_h / 2.0, cy + new_h / 2.0);
        }
    }
    Rect::from_bounds([x0, x1, y0, y1])
}

/// The lon/lat extent a view shows and its centre, sampled on a 25 x 25
/// grid (PyMappr's `view_lonlat`). A view spanning more than 300° of
/// longitude counts as the whole way round.
pub fn view_lonlat(proj: &Projection, view: Rect) -> ([f64; 4], [f64; 2]) {
    let [x0, x1, y0, y1] = view.bounds();
    let mut lons = Vec::new();
    let mut lats = Vec::new();
    for i in 0..25 {
        for j in 0..25 {
            let x = x0 + (x1 - x0) * j as f64 / 24.0;
            let y = y0 + (y1 - y0) * i as f64 / 24.0;
            if let Some((lon, lat)) = proj.inverse_raw(x, y) {
                lons.push(lon);
                lats.push(lat);
            }
        }
    }
    if lons.is_empty() {
        return ([-180.0, 180.0, -90.0, 90.0], [0.0, 0.0]);
    }
    let min = |v: &[f64]| v.iter().copied().fold(f64::INFINITY, f64::min);
    let max = |v: &[f64]| v.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let mut extent = [min(&lons), max(&lons), min(&lats), max(&lats)];
    if extent[1] - extent[0] > 300.0 {
        extent = [-180.0, 180.0, extent[2], extent[3]];
    }
    let centre = proj.inverse_raw((x0 + x1) / 2.0, (y0 + y1) / 2.0).unwrap_or_else(|| {
        (lons.iter().sum::<f64>() / lons.len() as f64, lats.iter().sum::<f64>() / lats.len() as f64)
    });
    (extent, [(centre.0 + 180.0).rem_euclid(360.0) - 180.0, centre.1])
}

/// Metres on the WGS84 ellipsoid between two map points (projected, y
/// up), or NaN where either has no lon/lat (PyMappr's `ground_distance`).
pub fn ground_distance(proj: &Projection, a: [f64; 2], b: [f64; 2]) -> f64 {
    let (Some(p), Some(q)) = (proj.inverse_raw(a[0], a[1]), proj.inverse_raw(b[0], b[1])) else {
        return f64::NAN;
    };
    let s12: f64 = Geodesic::wgs84().inverse(p.1, p.0, q.1, q.0);
    s12.abs()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::projection::ProjectionSpec;

    fn proj(name: &str) -> Projection {
        Projection::new(&ProjectionSpec { name: name.into(), lon_0: None, lat_0: None }).unwrap()
    }

    /// PyMappr's 9 x 6.5 in test figure with the plain margins.
    const ASPECT: f64 = (6.5 * (0.988 - 0.012)) / (9.0 * (0.99 - 0.01));

    #[test]
    fn a_continent_is_padded_to_the_box() {
        let p = proj("Equirectangular");
        let v = extent_view(&p, [-20.0, 55.0, -38.0, 40.0], ASPECT);
        assert!((v.h / v.w - ASPECT).abs() < 1e-9);
        assert!((v.h - 78.0).abs() < 1e-9, "Africa keeps its height");
        let world = extent_view(&p, [-180.0, 180.0, -90.0, 90.0], ASPECT);
        assert_eq!((world.w, world.h), (360.0, 180.0), "too wide to pad: fills the box");
    }

    #[test]
    fn a_padded_view_stays_inside_the_world() {
        let p = proj("Equirectangular");
        let v = extent_view(&p, [160.0, 180.0, -50.0, 50.0], ASPECT);
        assert!(v.x + v.w <= 180.0 + 1e-9);
    }

    #[test]
    fn an_extent_across_the_antimeridian_frames_just_that() {
        for name in ["Equirectangular", "Robinson", "Mercator"] {
            let p = proj(name);
            let v = extent_view(&p, [175.0, 191.0, -23.5, -11.0], ASPECT);
            assert!(v.w < p.world_width() / 8.0, "{name}");
            assert!(v.x + v.w > p.bounds[1], "{name}: runs onto the copy east");
        }
    }

    #[test]
    fn the_globe_frames_its_disk() {
        let p = proj("Globe (Orthographic)");
        let v = extent_view(&p, [-20.0, 55.0, -38.0, 40.0], 0.5);
        assert!((v.h - 2.0 * 6378127.2855 / GLOBE_FILL).abs() < 10.0);
        assert!((v.w - 2.0 * v.h).abs() < 1e-6);
    }

    #[test]
    fn view_lonlat_of_a_zoomed_view() {
        let p = proj("Robinson");
        let (x0, y0) = p.forward(-97.3, 40.5).unwrap();
        let (x1, y1) = p.forward(-96.2, 41.4).unwrap();
        let (ext, centre) = view_lonlat(&p, Rect::from_bounds([x0, x1, y0, y1]));
        assert!((ext[2] - 40.5).abs() < 0.01 && (ext[3] - 41.4).abs() < 0.01, "{ext:?}");
        assert!((centre[0] + 96.75).abs() < 0.2, "{centre:?}");
    }

    #[test]
    fn one_degree_of_longitude_at_the_equator() {
        for name in ["Equirectangular", "Mercator", "Robinson", "Mollweide", "Globe (Orthographic)"] {
            let p = proj(name);
            let (x0, y0) = p.forward(0.0, 0.0).unwrap();
            let (x1, y1) = p.forward(1.0, 0.0).unwrap();
            let km = ground_distance(&p, [x0, y0], [x1, y1]) / 1000.0;
            assert!((km - 111.319).abs() < 0.01, "{name}: {km}");
        }
    }

    #[test]
    fn distances_are_ellipsoidal_not_spherical() {
        let p = proj("Lambert: N. America");
        let at = |lon, lat| {
            let (x, y) = p.forward(lon, lat).unwrap();
            [x, y]
        };
        let east = ground_distance(&p, at(-100.0, 40.0), at(-99.0, 40.0)) / 1000.0;
        let north = ground_distance(&p, at(-100.0, 40.0), at(-100.0, 41.0)) / 1000.0;
        assert!((east - 85.4).abs() < 0.5 && (north - 111.0).abs() < 0.5);
        let clamped = |lon, lat| {
            let (x, y) = p.forward_clamped(lon, lat).unwrap();
            [x, y]
        };
        assert_eq!(ground_distance(&p, clamped(0.0, 0.0), clamped(1.0, 0.0)), 0.0);
        assert!(ground_distance(&proj("Globe (Orthographic)"), [f64::NAN, 0.0], [1.0, 1.0]).is_nan());
    }
}
