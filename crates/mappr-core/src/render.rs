//! Turns base layers into SVG path data for one view of the map.
//!
//! Geometry is clipped to the part of the world the projection draws (a
//! longitude/latitude box, or a cap of the sphere for the globe), projected,
//! thinned to the screen resolution and culled to the view. SVG has y down,
//! so every y is negated.

use std::fmt::Write as _;

use serde::{Deserialize, Serialize};

use crate::basemap::{Basemap, BasemapError, Geometry, resolution_for_zoom};
use crate::projection::{CAP_CLIP_RADIUS, HORIZON_RADIUS, Projection, ProjectionSpec, UnknownProjection};

type LonLat = [f64; 2];

/// A rectangle in SVG coordinates (projected x, negated projected y).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

impl Rect {
    fn from_points<'a>(pts: impl IntoIterator<Item = &'a [f64; 2]>) -> Option<Rect> {
        let (mut x0, mut y0, mut x1, mut y1) = (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
        for p in pts {
            x0 = x0.min(p[0]);
            y0 = y0.min(p[1]);
            x1 = x1.max(p[0]);
            y1 = y1.max(p[1]);
        }
        (x0 <= x1).then_some(Rect { x: x0, y: y0, w: x1 - x0, h: y1 - y0 })
    }

    fn grow(self, by: f64) -> Rect {
        Rect { x: self.x - by, y: self.y - by, w: self.w + 2.0 * by, h: self.h + 2.0 * by }
    }

    fn intersects(&self, o: &Rect) -> bool {
        self.x <= o.x + o.w && o.x <= self.x + self.w && self.y <= o.y + o.h && o.y <= self.y + self.h
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RenderRequest {
    pub projection: ProjectionSpec,
    /// The visible part of the map; `None` for the whole map.
    pub view: Option<Rect>,
    /// Width of the map on screen, in pixels; sets how much detail to keep.
    pub px_width: f64,
    pub layers: Vec<String>,
    /// Graticule spacing in degrees; 0 for none.
    pub graticule: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct RenderedLayer {
    pub id: String,
    pub geometry: Geometry,
    pub d: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RenderedMap {
    /// The edge of the projected world (the sphere outline), as path data.
    pub outline: String,
    /// The bounding box of the whole projected world.
    pub extent: Rect,
    pub zoom: f64,
    pub resolution: String,
    pub layers: Vec<RenderedLayer>,
    /// Layers that could not be drawn, with the reason.
    pub missing: Vec<String>,
}

#[derive(Debug, thiserror::Error)]
pub enum RenderError {
    #[error(transparent)]
    Projection(#[from] UnknownProjection),
    #[error(transparent)]
    Basemap(#[from] BasemapError),
}

pub fn render(basemap: &Basemap, req: &RenderRequest) -> Result<RenderedMap, RenderError> {
    let proj = Projection::new(&req.projection)?;
    let outline_pts = outline(&proj);
    let extent = Rect::from_points(&outline_pts).expect("outline has points");
    let view = req.view.unwrap_or(extent);
    let zoom = extent.w / view.w.max(1e-9);
    let resolution = resolution_for_zoom(zoom);
    let mut out = PathWriter::new(view, req.px_width);

    let mut outline_d = String::new();
    out.write(&mut outline_d, &outline_pts, true, false);

    let mut layers = Vec::new();
    let mut missing = Vec::new();
    let mut used = resolution;
    for id in &req.layers {
        let mut d = String::new();
        if id == "graticule" {
            if req.graticule > 0.0 {
                for line in graticule(req.graticule) {
                    for piece in clip(&proj, &line, false) {
                        out.write(&mut d, &project(&proj, &piece), false, true);
                    }
                }
            }
            layers.push(RenderedLayer { id: id.clone(), geometry: Geometry::Line, d });
            continue;
        }
        let (layer, res) = match basemap.layer(id, resolution) {
            Ok(found) => found,
            Err(e) => {
                missing.push(e.to_string());
                continue;
            }
        };
        if id == "land" {
            used = res;
        }
        let closed = layer.geometry == Geometry::Polygon;
        for part in &layer.parts {
            if !proj.is_globe() && !proj.is_regional() && part.bbox[1] > proj.max_lat {
                continue;
            }
            for piece in clip(&proj, &part.points, closed) {
                out.write(&mut d, &project(&proj, &piece), closed, true);
            }
        }
        layers.push(RenderedLayer { id: id.clone(), geometry: layer.geometry, d });
    }

    Ok(RenderedMap { outline: outline_d, extent, zoom, resolution: used.to_string(), layers, missing })
}

/// SVG positions of points; `None` for points the projection does not show.
pub fn project_points(spec: &ProjectionSpec, points: &[LonLat]) -> Result<Vec<Option<[f64; 2]>>, UnknownProjection> {
    let proj = Projection::new(spec)?;
    Ok(points
        .iter()
        .map(|&[lon, lat]| {
            if !proj.in_domain(lon, lat) {
                return None;
            }
            proj.forward(lon, lat).map(|(x, y)| [x, -y])
        })
        .collect())
}

/// Longitude/latitude under an SVG position, for the cursor read-out.
pub fn unproject(spec: &ProjectionSpec, x: f64, y: f64) -> Result<Option<LonLat>, UnknownProjection> {
    let proj = Projection::new(spec)?;
    Ok(proj.inverse(x, -y).map(|(lon, lat)| [lon, lat]))
}

fn project(proj: &Projection, pts: &[LonLat]) -> Vec<[f64; 2]> {
    pts.iter().filter_map(|&[lon, lat]| proj.forward(lon, lat)).map(|(x, y)| [x, -y]).collect()
}

/// The boundary of the drawn world, densified, in SVG coordinates.
fn outline(proj: &Projection) -> Vec<[f64; 2]> {
    let mut ring: Vec<LonLat> = Vec::new();
    if proj.is_globe() {
        for i in 0..=360 {
            ring.push(destination(proj, i as f64, HORIZON_RADIUS));
        }
    } else {
        let (hs, lo, hi) = (proj.lon_halfspan, proj.min_lat, proj.max_lat);
        let lon = |rel: f64| rel + proj.lon_0;
        for v in steps(lo, hi) {
            ring.push([lon(-hs), v]);
        }
        for v in steps(-hs, hs) {
            ring.push([lon(v), hi]);
        }
        for v in steps(lo, hi).into_iter().rev() {
            ring.push([lon(hs), v]);
        }
        for v in steps(-hs, hs).into_iter().rev() {
            ring.push([lon(v), lo]);
        }
    }
    project(proj, &ring)
}

/// Values from `a` to `b` inclusive, about a degree apart.
fn steps(a: f64, b: f64) -> Vec<f64> {
    let n = ((b - a).abs().ceil() as usize).max(1);
    (0..=n).map(|i| a + (b - a) * i as f64 / n as f64).collect()
}

fn graticule(step: f64) -> Vec<Vec<LonLat>> {
    let mut lines = Vec::new();
    let mut lon = -180.0;
    while lon <= 180.0 + 1e-9 {
        lines.push(steps(-90.0, 90.0).into_iter().map(|lat| [lon, lat]).collect());
        lon += step;
    }
    let mut lat = -90.0 + step;
    while lat < 90.0 - 1e-9 {
        lines.push(steps(-180.0, 180.0).into_iter().map(|lon| [lon, lat]).collect());
        lat += step;
    }
    lines
}

// ---- clipping -------------------------------------------------------------

/// Clip a ring (`closed`) or line to the drawn part of the world. A line
/// may come back in several pieces; a ring may too, when it reaches the
/// view from both sides of the cut meridian.
fn clip(proj: &Projection, pts: &[LonLat], closed: bool) -> Vec<Vec<LonLat>> {
    if proj.is_globe() {
        return clip_cap(proj, pts, closed);
    }
    let (hs, lo, hi) = (proj.lon_halfspan, proj.min_lat, proj.max_lat);

    // Longitudes relative to the central meridian, unwrapped so that a ring
    // crossing the cut meridian stays continuous (it may run past ±180).
    let mut rel: Vec<LonLat> = Vec::with_capacity(pts.len());
    for &[lon, lat] in pts {
        let mut x = proj.relative_lon(lon);
        if let Some(prev) = rel.last() {
            while x - prev[0] > 180.0 {
                x -= 360.0;
            }
            while prev[0] - x > 180.0 {
                x += 360.0;
            }
        }
        rel.push([x, lat]);
    }
    let Some(bb) = Rect::from_points(&rel) else { return Vec::new() };

    let mut pieces = Vec::new();
    for k in [-1.0, 0.0, 1.0] {
        let shift = 360.0 * k;
        let (x0, x1) = (-hs + shift, hs + shift);
        if bb.x > x1 || bb.x + bb.w < x0 || bb.y > hi || bb.y + bb.h < lo {
            continue;
        }
        let back = |p: &LonLat| [p[0] - shift + proj.lon_0, p[1]];
        let inside = bb.x >= x0 && bb.x + bb.w <= x1 && bb.y >= lo && bb.y + bb.h <= hi;
        if inside {
            pieces.push(rel.iter().map(back).collect());
        } else if closed {
            let ring = clip_ring_rect(&rel, x0, x1, lo, hi);
            if ring.len() >= 3 {
                pieces.push(ring.iter().map(back).collect());
            }
        } else {
            for run in clip_line_rect(&rel, x0, x1, lo, hi) {
                pieces.push(run.iter().map(back).collect());
            }
        }
    }
    pieces
}

/// Sutherland–Hodgman against an axis-aligned box.
fn clip_ring_rect(ring: &[LonLat], x0: f64, x1: f64, y0: f64, y1: f64) -> Vec<LonLat> {
    let mut poly = ring.to_vec();
    let edges: [(usize, f64, bool); 4] = [(0, x0, true), (0, x1, false), (1, y0, true), (1, y1, false)];
    for (axis, bound, keep_above) in edges {
        if poly.is_empty() {
            break;
        }
        let inside = |p: &LonLat| if keep_above { p[axis] >= bound } else { p[axis] <= bound };
        let cross = |a: &LonLat, b: &LonLat| {
            let t = (bound - a[axis]) / (b[axis] - a[axis]);
            let mut p = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
            p[axis] = bound;
            p
        };
        let mut out = Vec::with_capacity(poly.len());
        let mut prev = *poly.last().unwrap();
        for cur in &poly {
            match (inside(&prev), inside(cur)) {
                (true, true) => out.push(*cur),
                (true, false) => out.push(cross(&prev, cur)),
                (false, true) => {
                    out.push(cross(&prev, cur));
                    out.push(*cur);
                }
                (false, false) => {}
            }
            prev = *cur;
        }
        poly = out;
    }
    poly
}

/// Split a line into the runs that fall inside a box.
fn clip_line_rect(line: &[LonLat], x0: f64, x1: f64, y0: f64, y1: f64) -> Vec<Vec<LonLat>> {
    let inside = |p: &LonLat| p[0] >= x0 && p[0] <= x1 && p[1] >= y0 && p[1] <= y1;
    let mut runs = Vec::new();
    let mut run: Vec<LonLat> = Vec::new();
    for (i, p) in line.iter().enumerate() {
        if inside(p) {
            if run.is_empty() && i > 0 {
                run.push(edge_point(&line[i - 1], p, &inside));
            }
            run.push(*p);
        } else if !run.is_empty() {
            run.push(edge_point(p, &line[i - 1], &inside));
            runs.push(std::mem::take(&mut run));
        }
    }
    if run.len() >= 2 {
        runs.push(run);
    }
    runs
}

/// The point where the segment from `out` to `inn` enters the region, by
/// bisection (works for any convex region given its inside test).
fn edge_point(out: &LonLat, inn: &LonLat, inside: &impl Fn(&LonLat) -> bool) -> LonLat {
    let (mut a, mut b) = (*out, *inn);
    for _ in 0..30 {
        let m = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0];
        if inside(&m) { b = m } else { a = m }
    }
    b
}

fn unit(lon: f64, lat: f64) -> [f64; 3] {
    let (l, p) = (lon.to_radians(), lat.to_radians());
    [p.cos() * l.cos(), p.cos() * l.sin(), p.sin()]
}

fn lonlat(v: [f64; 3]) -> LonLat {
    let n = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt();
    [v[1].atan2(v[0]).to_degrees(), (v[2] / n).clamp(-1.0, 1.0).asin().to_degrees()]
}

/// The point `dist` degrees from the globe's centre along `bearing`.
fn destination(proj: &Projection, bearing: f64, dist: f64) -> LonLat {
    let (p0, l0) = (proj.lat_0.to_radians(), proj.lon_0.to_radians());
    let (b, d) = (bearing.to_radians(), dist.to_radians());
    let p = (p0.sin() * d.cos() + p0.cos() * d.sin() * b.cos()).asin();
    let l = l0 + (b.sin() * d.sin() * p0.cos()).atan2(d.cos() - p0.sin() * p.sin());
    [l.to_degrees(), p.to_degrees()]
}

/// Bearing in degrees of a point as seen from the globe's centre.
fn bearing(proj: &Projection, pt: &LonLat) -> f64 {
    let (p0, p) = (proj.lat_0.to_radians(), pt[1].to_radians());
    let dl = (pt[0] - proj.lon_0).to_radians();
    (dl.sin() * p.cos()).atan2(p0.cos() * p.sin() - p0.sin() * p.cos() * dl.cos()).to_degrees()
}

/// Clip to the visible cap of the globe. Where a ring leaves the cap and
/// comes back, the gap is closed along the rim (the shorter way round).
fn clip_cap(proj: &Projection, pts: &[LonLat], closed: bool) -> Vec<Vec<LonLat>> {
    let center = unit(proj.lon_0, proj.lat_0);
    let cos_r = CAP_CLIP_RADIUS.to_radians().cos();
    let vecs: Vec<[f64; 3]> = pts.iter().map(|p| unit(p[0], p[1])).collect();
    let dot = |v: &[f64; 3]| v[0] * center[0] + v[1] * center[1] + v[2] * center[2];
    let inside: Vec<bool> = vecs.iter().map(|v| dot(v) >= cos_r).collect();
    if inside.iter().all(|&i| i) {
        return vec![pts.to_vec()];
    }
    if !inside.iter().any(|&i| i) {
        return Vec::new();
    }
    // Where the arc from a (outside) to b (inside) meets the cap edge.
    let crossing = |a: &[f64; 3], b: &[f64; 3]| {
        let (mut lo, mut hi) = (*a, *b);
        for _ in 0..30 {
            let m = [(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0];
            let n = (m[0] * m[0] + m[1] * m[1] + m[2] * m[2]).sqrt();
            let m = [m[0] / n, m[1] / n, m[2] / n];
            if dot(&m) >= cos_r { hi = m } else { lo = m }
        }
        lonlat(hi)
    };

    let n = pts.len();
    if !closed {
        let mut runs = Vec::new();
        let mut run: Vec<LonLat> = Vec::new();
        for i in 0..n {
            if inside[i] {
                if run.is_empty() && i > 0 {
                    run.push(crossing(&vecs[i - 1], &vecs[i]));
                }
                run.push(pts[i]);
            } else if !run.is_empty() {
                run.push(crossing(&vecs[i], &vecs[i - 1]));
                runs.push(std::mem::take(&mut run));
            }
        }
        if run.len() >= 2 {
            runs.push(run);
        }
        return runs;
    }

    // Walk the ring starting from an inside vertex.
    let start = inside.iter().position(|&i| i).unwrap();
    let mut out: Vec<LonLat> = Vec::with_capacity(n);
    let mut exit: Option<LonLat> = None;
    for k in 1..=n {
        let (i, j) = ((start + k - 1) % n, (start + k) % n);
        match (inside[i], inside[j]) {
            (true, true) => out.push(pts[j]),
            (true, false) => {
                let p = crossing(&vecs[j], &vecs[i]);
                out.push(p);
                exit = Some(p);
            }
            (false, true) => {
                let entry = crossing(&vecs[i], &vecs[j]);
                if let Some(from) = exit.take() {
                    let (b0, b1) = (bearing(proj, &from), bearing(proj, &entry));
                    let mut delta = b1 - b0;
                    if delta > 180.0 {
                        delta -= 360.0;
                    } else if delta < -180.0 {
                        delta += 360.0;
                    }
                    let count = (delta.abs() / 3.0).ceil() as usize;
                    for s in 1..count {
                        out.push(destination(proj, b0 + delta * s as f64 / count as f64, CAP_CLIP_RADIUS));
                    }
                }
                out.push(entry);
                out.push(pts[j]);
            }
            (false, false) => {}
        }
    }
    if out.len() >= 3 { vec![out] } else { Vec::new() }
}

// ---- path output ----------------------------------------------------------

/// Writes projected rings and lines as compact SVG path data, dropping
/// vertices closer together than about half a pixel.
struct PathWriter {
    cull: Rect,
    tolerance: f64,
    decimals: usize,
}

impl PathWriter {
    fn new(view: Rect, px_width: f64) -> Self {
        let per_px = view.w / px_width.max(1.0);
        let tolerance = per_px * 0.5;
        let decimals = (1.0 - tolerance.log10().floor()).clamp(0.0, 6.0) as usize;
        PathWriter { cull: view.grow(view.w.max(view.h) * 0.5), tolerance, decimals }
    }

    fn write(&mut self, d: &mut String, pts: &[[f64; 2]], closed: bool, cull: bool) {
        if pts.len() < 2 {
            return;
        }
        if cull && !Rect::from_points(pts).is_some_and(|r| r.intersects(&self.cull)) {
            return;
        }
        let dec = self.decimals;
        let mut last = pts[0];
        let _ = write!(d, "M{:.dec$} {:.dec$}", last[0], last[1]);
        let mut written = 1;
        for (i, p) in pts.iter().enumerate().skip(1) {
            let far = (p[0] - last[0]).abs() > self.tolerance || (p[1] - last[1]).abs() > self.tolerance;
            if far || i == pts.len() - 1 {
                let _ = write!(d, "L{:.dec$} {:.dec$}", p[0], p[1]);
                last = *p;
                written += 1;
            }
        }
        if closed && written >= 3 {
            d.push('Z');
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec(name: &str) -> ProjectionSpec {
        ProjectionSpec { name: name.into(), lon_0: None, lat_0: None }
    }

    #[test]
    fn rect_clip_cuts_a_square() {
        let sq = [[-10.0, -10.0], [10.0, -10.0], [10.0, 10.0], [-10.0, 10.0]];
        let out = clip_ring_rect(&sq, 0.0, 20.0, 0.0, 20.0);
        let bb = Rect::from_points(&out).unwrap();
        assert_eq!((bb.x, bb.y, bb.w, bb.h), (0.0, 0.0, 10.0, 10.0));
    }

    #[test]
    fn ring_across_the_cut_meridian_is_not_smeared() {
        // Centred on 0° with ±120° drawn: a ring straddling 180° comes back
        // as two pieces, not one smeared across the whole map.
        let proj = Projection::new(&spec("Lambert Azimuthal (custom)")).unwrap();
        let ring = [[100.0, 10.0], [-100.0, 10.0], [-100.0, 20.0], [100.0, 20.0]];
        let pieces = clip(&proj, &ring, true);
        assert_eq!(pieces.len(), 2);
        for piece in pieces {
            let lons: Vec<f64> = piece.iter().map(|p| proj.relative_lon(p[0])).collect();
            let span = lons.iter().cloned().fold(f64::MIN, f64::max) - lons.iter().cloned().fold(f64::MAX, f64::min);
            assert!(span <= 20.0 + 1e-6, "piece spans {span}°");
        }
    }

    #[test]
    fn globe_hides_the_far_side() {
        let pts = project_points(&spec("Globe (Orthographic)"), &[[0.0, 0.0], [180.0, 0.0]]).unwrap();
        assert!(pts[0].is_some());
        assert!(pts[1].is_none());
    }

    #[test]
    fn cap_clip_closes_along_the_rim() {
        let proj = Projection::new(&spec("Globe (Orthographic)")).unwrap();
        let ring = [[60.0, -20.0], [120.0, -20.0], [120.0, 20.0], [60.0, 20.0]];
        let pieces = clip_cap(&proj, &ring, true);
        assert_eq!(pieces.len(), 1);
        for p in &pieces[0] {
            assert!(proj.cap_distance(p[0], p[1]) <= CAP_CLIP_RADIUS + 1e-6);
        }
    }

    #[test]
    fn missing_data_is_reported_not_fatal() {
        let basemap = Basemap::new(std::env::temp_dir().join("no-such-natural-earth"));
        let req = RenderRequest {
            projection: spec("Robinson"),
            view: None,
            px_width: 1000.0,
            layers: vec!["land".into(), "graticule".into()],
            graticule: 30.0,
        };
        let map = render(&basemap, &req).unwrap();
        assert_eq!(map.missing.len(), 1);
        assert!(!map.outline.is_empty());
        assert!(map.layers[0].d.contains('M'));
    }

    #[test]
    fn renders_pymappr_data_when_present() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../PyMappr/data/shapes");
        if !Basemap::looks_valid(&dir) {
            return;
        }
        let basemap = Basemap::new(dir);
        for name in crate::projection::projection_names() {
            let req = RenderRequest {
                projection: spec(name),
                view: None,
                px_width: 1200.0,
                layers: vec!["land".into(), "countries".into()],
                graticule: 0.0,
            };
            let map = render(&basemap, &req).unwrap();
            assert!(map.missing.is_empty(), "{name}: {:?}", map.missing);
            assert!(map.layers.iter().all(|l| l.d.len() > 1000), "{name}");
            assert!(!map.layers[0].d.contains("NaN"), "{name}");
        }
    }
}
