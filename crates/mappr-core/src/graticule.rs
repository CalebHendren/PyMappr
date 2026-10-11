//! The graticule and its degree labels, as PyMappr draws them
//! (`renderer/view.py`, `renderer/grid_labels.py`).
//!
//! On the plain lon/lat map the grid lines are the axis ticks. On a
//! projected map they are curves, ticked where each meridian meets the
//! bottom of the view and each parallel the left. Labels that would run
//! into their neighbours are thinned to every second, third, ... line.

use crate::projection::Projection;
use crate::render::{Graticule, MapContext, PathWriter, Tick, clip_line_rect};

/// Every n-th grid line keeps its label, n from this list.
const STRIDES: [usize; 9] = [1, 2, 3, 4, 6, 9, 12, 18, 36];
/// A label's footprint along its axis in ems of the 7 pt tick font.
const WIDTH_EMS: f64 = 5.0 * 0.62 + 1.0;
const HEIGHT_EMS: f64 = 1.2 + 0.6;
const TICK_FONT_PT: f64 = 7.0;
/// The globe's outline sits just inside the horizon.
const HORIZON: f64 = 89.9;

/// Python's `%g` for the round numbers degree labels carry.
fn fmt_g(v: f64) -> String {
    if v.fract() == 0.0 && v.abs() < 1e15 { format!("{}", v as i64) } else { format!("{v}") }
}

fn norm_lon(v: f64) -> f64 {
    (v + 180.0).rem_euclid(360.0) - 180.0
}

/// "30°W", "0°", "180°" (PyMappr's `format_lon`).
pub fn format_lon(value: f64) -> String {
    let v = norm_lon(value);
    if v == 0.0 || v.abs() == 180.0 {
        return format!("{}°", fmt_g(v.abs()));
    }
    format!("{}°{}", fmt_g(v.abs()), if v < 0.0 { "W" } else { "E" })
}

/// "20°S", "0°" (PyMappr's `format_lat`).
pub fn format_lat(value: f64) -> String {
    if value == 0.0 {
        return "0°".into();
    }
    format!("{}°{}", fmt_g(value.abs()), if value < 0.0 { "S" } else { "N" })
}

/// How many grid lines apart labels must be so that labels `label_pts`
/// long, on lines `spacing_pts` apart, do not touch.
pub fn label_stride(spacing_pts: f64, label_pts: f64) -> usize {
    if spacing_pts <= 0.0 {
        return STRIDES[8];
    }
    let need = label_pts / spacing_pts;
    STRIDES.iter().copied().find(|&s| s as f64 >= need).unwrap_or(STRIDES[8])
}

/// `start, start + step, ...` below `stop` (numpy's `arange`).
fn arange(start: f64, stop: f64, step: f64) -> Vec<f64> {
    let n = ((stop - start) / step).ceil().max(0.0) as usize;
    (0..n).map(|i| start + step * i as f64).collect()
}

fn linspace(a: f64, b: f64, n: usize) -> Vec<f64> {
    (0..n).map(|i| a + (b - a) * i as f64 / (n - 1) as f64).collect()
}

/// Where a polyline crosses a frame edge: `along` 'x' finds crossings of
/// the line y = `edge` and returns their x; 'y' crossings of x = `edge`,
/// returning y. NaN gaps are never bridged.
pub fn edge_crossings(xs: &[f64], ys: &[f64], edge: f64, along: char) -> Vec<f64> {
    let (cut, other) = if along == 'x' { (ys, xs) } else { (xs, ys) };
    let mut found = Vec::new();
    // A sample landing on the edge counts as on it, as it does in PyMappr
    // where the edge and the samples come from the same pyproj call (the
    // crossing is then found twice, which PyMappr's crowding rule uses).
    let eps = 1e-9 * edge.abs().max(1.0);
    let off = |v: f64| if (v - edge).abs() <= eps { 0.0 } else { v - edge };
    for i in 0..cut.len().saturating_sub(1) {
        let (a, b) = (off(cut[i]), off(cut[i + 1]));
        if !(a.is_finite() && b.is_finite()) || a * b > 0.0 || a == b {
            continue;
        }
        if !(other[i].is_finite() && other[i + 1].is_finite()) {
            continue;
        }
        let t = a / (a - b);
        found.push(other[i] + t * (other[i + 1] - other[i]));
    }
    found
}

/// Where a grid line meets the bottom ('x') or left ('y') edge of `view`
/// (x0, x1, y0, y1, y up). A line stopping short of the edge is continued
/// straight on from its end when that lands close by (PyMappr's
/// `edge_ticks`).
pub fn edge_ticks(xs: &[f64], ys: &[f64], view: [f64; 4], along: char) -> Vec<f64> {
    let [x0, x1, y0, y1] = view;
    let ticks: Vec<f64> = if along == 'x' {
        edge_crossings(xs, ys, y0, 'x').into_iter().filter(|x| (x0..=x1).contains(x)).collect()
    } else {
        edge_crossings(xs, ys, x0, 'y').into_iter().filter(|y| (y0..=y1).contains(y)).collect()
    };
    if !ticks.is_empty() {
        return ticks;
    }
    let good: Vec<(f64, f64)> =
        xs.iter().zip(ys).filter(|(x, y)| x.is_finite() && y.is_finite()).map(|(x, y)| (*x, *y)).collect();
    if good.len() < 4 {
        return Vec::new();
    }
    let key = |p: &(f64, f64)| if along == 'x' { p.1 } else { p.0 };
    let mut end = 0;
    for (i, p) in good.iter().enumerate() {
        if key(p) < key(&good[end]) {
            end = i;
        }
    }
    if 0 < end && end < good.len() - 1 {
        return Vec::new();
    }
    let inner = if end == 0 { 3 } else { good.len() - 4 };
    let (x, y) = good[end];
    if !(x0 <= x && x <= x1 && y0 <= y && y <= y1) {
        return Vec::new();
    }
    let (dx, dy) = (x - good[inner].0, y - good[inner].1);
    let (tick, ok, drift) = if along == 'x' {
        if dy >= 0.0 {
            return Vec::new();
        }
        let t = (y0 - y) / dy;
        let tick = x + t * dx;
        (tick, (x0..=x1).contains(&tick), ((t * dx).abs(), x1 - x0))
    } else {
        if dx >= 0.0 {
            return Vec::new();
        }
        let t = (x0 - x) / dx;
        let tick = y + t * dy;
        (tick, (y0..=y1).contains(&tick), ((t * dy).abs(), y1 - y0))
    };
    if ok && drift.0 <= 0.03 * drift.1 { vec![tick] } else { Vec::new() }
}

/// The graticule for a view: lines, the globe's horizon, and the labelled
/// ticks along the bottom and left edges.
pub fn graticule(ctx: &MapContext, step: f64, labels_on: bool) -> Graticule {
    let proj = &ctx.proj;
    let mut writer = PathWriter::new(ctx);
    let mut d = String::new();
    let clip = writer.clip;
    let mut line = |d: &mut String, pts: &[Option<[f64; 2]>]| {
        for run in pts.split(|p| p.is_none()) {
            let run: Vec<[f64; 2]> = run.iter().flatten().copied().collect();
            if run.len() < 2 {
                continue;
            }
            for &off in &ctx.offsets {
                let c = clip.shift(-off);
                for piece in clip_line_rect(&run, c.x, c.x + c.w, c.y, c.y + c.h) {
                    let shifted: Vec<[f64; 2]> = piece.iter().map(|p| [p[0] + off, p[1]]).collect();
                    writer.write(d, &shifted, false);
                }
            }
        }
    };
    if proj.is_geographic() {
        // The grid lines are the axis ticks, across the whole view.
        let [x0, x1, y0, y1] = ctx.data_view();
        for x in multiples(x0, x1, step) {
            line(&mut d, &[Some([x, -y1]), Some([x, -y0])]);
        }
        for y in multiples(y0, y1, step) {
            line(&mut d, &[Some([x0, -y]), Some([x1, -y])]);
        }
    } else {
        let svg = |p: Option<(f64, f64)>| p.map(|(x, y)| [x, -y]);
        for lon in arange(-180.0, 180.0 + step / 2.0, step) {
            let pts: Vec<_> =
                linspace(-proj.max_lat, proj.max_lat, 91).into_iter().map(|lat| svg(proj.forward_clamped(lon, lat))).collect();
            line(&mut d, &pts);
        }
        for lat in arange(-90.0, 90.0 + step / 2.0, step) {
            if lat.abs() > proj.max_lat {
                continue;
            }
            let span = proj.lon_halfspan;
            let pts: Vec<_> = linspace(-span, span, 181)
                .into_iter()
                .map(|rel| svg(proj.forward_clamped(proj.lon_0 + rel, lat)))
                .collect();
            line(&mut d, &pts);
        }
    }
    let horizon = proj.is_globe().then(|| {
        let ring = crate::projection::cap_ring(proj.lon_0, proj.lat_0, HORIZON, 361);
        let pts: Vec<[f64; 2]> = ring.iter().filter_map(|p| proj.forward(p[0], p[1])).map(|(x, y)| [x, -y]).collect();
        let mut h = String::new();
        PathWriter::new(ctx).write(&mut h, &pts, true);
        h
    });
    let (x_ticks, y_ticks) = if labels_on && !proj.is_globe() { ticks(ctx, step) } else { (Vec::new(), Vec::new()) };
    Graticule { d, horizon, x_ticks, y_ticks }
}

/// Multiples of `step` within [a, b].
fn multiples(a: f64, b: f64, step: f64) -> Vec<f64> {
    let first = (a / step).ceil() as i64;
    let last = (b / step).floor() as i64;
    (first..=last).map(|k| k as f64 * step).collect()
}

/// (position, degree) pairs along one axis.
type Ticks = Vec<(f64, f64)>;

/// Tick (position, degree) pairs for each axis, before thinning, and the
/// positions the label spacing is judged from.
fn locate(ctx: &MapContext, step: f64) -> (Ticks, Ticks, Vec<f64>, Vec<f64>) {
    let proj = &ctx.proj;
    let view = ctx.data_view();
    let [x0, x1, y0, y1] = view;
    if proj.is_geographic() {
        // matplotlib's MultipleLocator: the multiples in view, plus one
        // beyond each end (which count for the spacing only).
        let xs = multiples(x0, x1, step);
        let ys = multiples(y0, y1, step);
        let around = |v: &[f64]| -> Vec<f64> {
            let mut all = v.to_vec();
            if let (Some(a), Some(b)) = (v.first(), v.last()) {
                all.insert(0, a - step);
                all.push(b + step);
            }
            all
        };
        let (ax, ay) = (around(&xs), around(&ys));
        return (xs.iter().map(|&x| (x, x)).collect(), ys.iter().map(|&y| (y, y)).collect(), ax, ay);
    }
    let nan = |p: Option<(f64, f64)>| p.unwrap_or((f64::NAN, f64::NAN));
    // Meridians along the bottom edge.
    let lats = linspace(proj.min_lat, proj.max_lat, 361);
    let mut ticks: Vec<(f64, f64, f64)> = Vec::new();
    for lon in arange(-180.0, 180.0, step) {
        let (xs, ys): (Vec<f64>, Vec<f64>) = lats.iter().map(|&lat| nan(proj.forward_unclamped(lon, lat))).unzip();
        for off in ctx.all_offsets() {
            let shifted: Vec<f64> = xs.iter().map(|x| x + off).collect();
            for x in edge_ticks(&shifted, &ys, view, 'x') {
                ticks.push((x, lon, off));
            }
        }
    }
    let mut x_found = meridian_ticks(proj, &ticks, view);
    // Parallels along the left edge.
    let span = proj.lon_halfspan;
    let lons: Vec<f64> = linspace(-span, span, 721).into_iter().map(|r| proj.lon_0 + r).collect();
    let first = (proj.min_lat / step).ceil() * step;
    let mut y_found: Vec<(f64, f64)> = Vec::new();
    for lat in arange(first, proj.max_lat + step / 2.0, step) {
        if lat.abs() > 90.0 {
            continue;
        }
        let (xs, ys): (Vec<f64>, Vec<f64>) = lons.iter().map(|&lon| nan(proj.forward_unclamped(lon, lat))).unzip();
        for off in ctx.all_offsets() {
            let shifted: Vec<f64> = xs.iter().map(|x| x + off).collect();
            for y in edge_ticks(&shifted, &ys, view, 'y') {
                upsert(&mut y_found, y, lat);
            }
        }
    }
    x_found.sort_by(|a, b| a.0.total_cmp(&b.0));
    y_found.sort_by(|a, b| a.0.total_cmp(&b.0));
    let xv = x_found.iter().map(|t| t.0).collect();
    let yv = y_found.iter().map(|t| t.0).collect();
    (x_found, y_found, xv, yv)
}

/// A dict assignment: a later degree at the same position wins.
fn upsert(found: &mut Vec<(f64, f64)>, pos: f64, degree: f64) {
    match found.iter_mut().find(|t| t.0 == pos) {
        Some(t) => t.1 = degree,
        None => found.push((pos, degree)),
    }
}

/// Meridians that meet the bottom edge at one point (a pointed pole) are
/// ticked below where they cross the equator instead.
fn meridian_ticks(proj: &Projection, ticks: &[(f64, f64, f64)], view: [f64; 4]) -> Vec<(f64, f64)> {
    let [x0, x1, y0, y1] = view;
    let close = 0.005 * (x1 - x0);
    let mut xs: Vec<f64> = ticks.iter().map(|t| t.0).collect();
    xs.sort_by(f64::total_cmp);
    let mut crowded = Vec::new();
    for w in xs.windows(2) {
        if w[1] - w[0] <= close {
            crowded.push(w[0]);
            crowded.push(w[1]);
        }
    }
    let mut found = Vec::new();
    for &(x, lon, off) in ticks {
        let mut x = x;
        if crowded.contains(&x) {
            let Some((ex, ey)) = proj.forward_unclamped(lon, 0.0) else { continue };
            let ex = ex + off;
            if !(x0 <= ex && ex <= x1 && y0 <= ey && ey <= y1) {
                continue;
            }
            x = ex;
        }
        upsert(&mut found, x, lon);
    }
    found
}

/// The ticks for both axes, thinned so neighbouring labels never touch.
fn ticks(ctx: &MapContext, step: f64) -> (Vec<Tick>, Vec<Tick>) {
    let (xt, yt, xv, yv) = locate(ctx, step);
    let stride = |values: &[f64], ems: f64, ppu: f64| -> usize {
        if values.len() < 2 {
            return 1;
        }
        let mut px: Vec<f64> = values.iter().map(|v| v * ppu).collect();
        px.sort_by(f64::total_cmp);
        let gap = px.windows(2).map(|w| w[1] - w[0]).filter(|g| *g > 0.0).fold(f64::INFINITY, f64::min);
        if !gap.is_finite() {
            return 1;
        }
        label_stride(gap / ctx.px_per_pt, ems * TICK_FONT_PT)
    };
    let keep = |degree: f64, stride: usize| (degree / step).round() as i64 % stride as i64 == 0;
    let sx = stride(&xv, WIDTH_EMS, ctx.px_per_unit());
    let sy = stride(&yv, HEIGHT_EMS, ctx.px_per_unit_y());
    let x_ticks =
        xt.iter().filter(|t| keep(t.1, sx)).map(|&(pos, deg)| Tick { pos, text: format_lon(deg) }).collect();
    let y_ticks =
        yt.iter().filter(|t| keep(t.1, sy)).map(|&(pos, deg)| Tick { pos: -pos, text: format_lat(deg) }).collect();
    (x_ticks, y_ticks)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::projection::ProjectionSpec;
    use crate::render::Rect;

    /// PyMappr's test figure: 9.29 x 6.59 in at 100 dpi with tick margins.
    fn ctx(name: &str, origin: Option<(f64, f64)>, lonlat: Option<[f64; 4]>) -> MapContext {
        let spec = ProjectionSpec { name: name.into(), lon_0: origin.map(|o| o.0), lat_0: origin.map(|o| o.1) };
        let proj = Projection::new(&spec).unwrap();
        let (w, h) = (9.29 * (0.99 - 0.055) * 100.0, 6.59 * (0.99 - 0.045) * 100.0);
        let view = lonlat.map(|e| crate::view::extent_view(&proj, e, h / w));
        let view = view.unwrap_or_else(|| crate::view::extent_view(&proj, [-180.0, 180.0, -90.0, 90.0], h / w));
        MapContext::new(proj, Some(view), w, 100.0 / 72.0)
    }

    fn texts(t: &[Tick]) -> Vec<String> {
        t.iter().map(|t| t.text.clone()).collect()
    }

    #[test]
    fn edge_crossings_interpolate_and_skip_gaps() {
        let xs = [0.0, 2.0, f64::NAN, 4.0, 6.0];
        let ys = [-1.0, 1.0, 0.0, -1.0, 1.0];
        assert_eq!(edge_crossings(&xs, &ys, 0.0, 'x'), vec![1.0, 5.0]);
    }

    #[test]
    fn a_short_straight_line_is_continued_to_the_edge() {
        let view = [0.0, 10.0, 0.0, 10.0];
        let xs = linspace(9.0, 0.2, 20);
        let ys = vec![4.0; 20];
        let got = edge_ticks(&xs, &ys, view, 'y');
        assert_eq!(got.len(), 1);
        assert!((got[0] - 4.0).abs() < 1e-9);
        let ys: Vec<f64> = xs.iter().map(|x| 4.0 + (9.0 - x) * (9.0 - x) / 4.0).collect();
        assert!(edge_ticks(&xs, &ys, view, 'y').is_empty());
    }

    #[test]
    fn label_stride_table() {
        for (spacing, length, stride) in [(40.0, 20.0, 1), (15.0, 20.0, 2), (5.0, 20.0, 4), (0.1, 20.0, 36)] {
            assert_eq!(label_stride(spacing, length), stride);
        }
    }

    #[test]
    fn labels_read_as_pymappr_writes_them() {
        assert_eq!(format_lon(-30.0), "30°W");
        assert_eq!(format_lon(190.0), "170°W");
        assert_eq!(format_lon(180.0), "180°");
        assert_eq!(format_lon(0.0), "0°");
        assert_eq!(format_lat(-20.0), "20°S");
        assert_eq!(format_lat(2.5), "2.5°N");
    }

    #[test]
    fn a_dense_world_grid_is_thinned_to_readable_labels() {
        let g = graticule(&ctx("Equirectangular", None, None), 5.0, true);
        let xs = texts(&g.x_ticks);
        assert!(!xs.is_empty() && xs.len() < 36, "{xs:?}");
        for t in &xs {
            let n: i64 = t.trim_end_matches(['E', 'W']).trim_end_matches('°').parse().unwrap();
            assert_eq!(n % 10, 0, "{t}");
        }
    }

    #[test]
    fn a_zoomed_grid_keeps_every_label() {
        let g = graticule(&ctx("Equirectangular", None, Some([-100.0, -77.0, 6.0, 21.0])), 5.0, true);
        let degrees: Vec<i64> =
            g.x_ticks.iter().map(|t| t.text.trim_end_matches('W').trim_end_matches('°').parse().unwrap()).collect();
        assert!(degrees.len() >= 5, "{degrees:?}");
        assert!(degrees.windows(2).all(|w| w[0] - w[1] == 5));
    }

    #[test]
    fn a_lambert_map_is_labelled_where_the_grid_meets_the_frame() {
        let c = ctx("Lambert Azimuthal (custom)", Some((-178.0, -17.0)), Some([175.0, 191.0, -23.5, -11.0]));
        let g = graticule(&c, 5.0, true);
        let (xs, ys) = (texts(&g.x_ticks), texts(&g.y_ticks));
        assert!(xs.contains(&"180°".into()) && xs.contains(&"175°W".into()), "{xs:?}");
        assert!(ys.contains(&"15°S".into()) && ys.contains(&"20°S".into()), "{ys:?}");
    }

    #[test]
    fn a_pointed_pole_world_labels_its_meridians_at_the_equator() {
        let c = ctx("Mollweide", None, None);
        let g = graticule(&c, 30.0, true);
        let xs = texts(&g.x_ticks);
        for want in ["120°W", "60°W", "0°", "60°E", "120°E"] {
            assert!(xs.contains(&want.into()), "{xs:?}");
        }
        for lon in [-60.0, 0.0, 60.0] {
            let (ex, _) = c.proj.forward(lon, 0.0).unwrap();
            assert!(g.x_ticks.iter().any(|t| (t.pos - ex).abs() < 1.0), "{lon}");
        }
    }

    #[test]
    fn a_flat_pole_world_keeps_its_labels_on_the_edge() {
        let c = ctx("Robinson", None, None);
        let (xt, _, _, _) = locate(&c, 30.0);
        let g = graticule(&c, 30.0, true);
        assert!(g.x_ticks.len() >= 6, "{:?}", texts(&g.x_ticks));
        let at = xt.iter().find(|t| t.1 == 60.0).unwrap().0;
        let (eq, _) = c.proj.forward(60.0, 0.0).unwrap();
        assert!(at < 0.9 * eq);
    }

    #[test]
    fn the_globe_and_hidden_labels_stay_unlabelled() {
        let g = graticule(&ctx("Globe (Orthographic)", None, None), 10.0, true);
        assert!(g.x_ticks.is_empty() && g.y_ticks.is_empty());
        assert!(g.horizon.is_some());
        let g = graticule(&ctx("Robinson", None, None), 10.0, false);
        assert!(g.x_ticks.is_empty() && g.y_ticks.is_empty());
        assert!(g.d.contains('M') && g.horizon.is_none());
        let _ = Rect { x: 0.0, y: 0.0, w: 1.0, h: 1.0 };
    }
}
