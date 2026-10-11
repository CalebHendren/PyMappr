//! Turns the base layers into SVG path data for one view of the map, in
//! PyMappr's draw order, with its markers, labels, raster and graticule.
//!
//! Geometry is clipped to the part of the world the projection draws (a
//! longitude/latitude box, or a cap of the sphere for the globe), projected
//! once per projection and cached, then cut to the view, thinned to the
//! screen resolution and written out. SVG has y down, so every y is
//! negated.

use std::collections::HashMap;
use std::fmt::Write as _;
use std::sync::Arc;

use rayon::prelude::*;
use serde::{Deserialize, Serialize};

use crate::basemap::{Basemap, BasemapError, Geometry, Layer, scale_of};
use crate::catalog::{self, BATHYMETRY_STEPS, FILL_LAYERS, LINE_LAYERS, Z_BATHYMETRY, Z_DISTRICTS, Z_LAKE_FILL, layer_spec};
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
    pub fn from_points<'a>(pts: impl IntoIterator<Item = &'a [f64; 2]>) -> Option<Rect> {
        let (mut x0, mut y0, mut x1, mut y1) = (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
        for p in pts {
            x0 = x0.min(p[0]);
            y0 = y0.min(p[1]);
            x1 = x1.max(p[0]);
            y1 = y1.max(p[1]);
        }
        (x0 <= x1).then_some(Rect { x: x0, y: y0, w: x1 - x0, h: y1 - y0 })
    }

    /// From projected bounds (x0, x1, y0, y1 with y up).
    pub fn from_bounds(b: [f64; 4]) -> Rect {
        Rect { x: b[0], y: -b[3], w: b[1] - b[0], h: b[3] - b[2] }
    }

    /// As projected bounds (x0, x1, y0, y1 with y up).
    pub fn bounds(&self) -> [f64; 4] {
        [self.x, self.x + self.w, -(self.y + self.h), -self.y]
    }

    pub fn grow(self, by: f64) -> Rect {
        Rect { x: self.x - by, y: self.y - by, w: self.w + 2.0 * by, h: self.h + 2.0 * by }
    }

    pub fn shift(self, dx: f64) -> Rect {
        Rect { x: self.x + dx, ..self }
    }

    pub fn intersects(&self, o: &Rect) -> bool {
        self.x <= o.x + o.w && o.x <= self.x + self.w && self.y <= o.y + o.h && o.y <= self.y + self.h
    }

    pub fn contains_rect(&self, o: &Rect) -> bool {
        o.x >= self.x && o.x + o.w <= self.x + self.w && o.y >= self.y && o.y + o.h <= self.y + self.h
    }

    pub fn contains(&self, p: [f64; 2]) -> bool {
        p[0] >= self.x && p[0] <= self.x + self.w && p[1] >= self.y && p[1] <= self.y + self.h
    }
}

/// The layer switches, as in the PyMappr project's `map` section.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct LayerSettings {
    pub lines: HashMap<String, bool>,
    pub fills: HashMap<String, bool>,
    pub points: HashMap<String, bool>,
    pub labels: HashMap<String, bool>,
    pub ocean: String,
    pub lake_fill: String,
    pub bathymetry: bool,
    pub capitals_only: bool,
    pub basemap: String,
    pub graticule: String,
    pub hide_grid_labels: bool,
}

impl LayerSettings {
    pub fn line(&self, key: &str) -> bool {
        self.lines.get(key).copied().unwrap_or(false)
    }
    pub fn fill(&self, key: &str) -> bool {
        self.fills.get(key).copied().unwrap_or(false)
    }
    pub fn point(&self, key: &str) -> bool {
        self.points.get(key).copied().unwrap_or(false)
    }
    pub fn label(&self, key: &str) -> bool {
        self.labels.get(key).copied().unwrap_or(false)
    }
    /// Graticule spacing in degrees from "Off", "1°", "5°", "10°".
    pub fn graticule_step(&self) -> Option<f64> {
        self.graticule.trim_end_matches('°').trim().parse::<f64>().ok().filter(|v| *v > 0.0)
    }
}

fn default_px_per_pt() -> f64 {
    96.0 / 72.0
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RenderRequest {
    pub projection: ProjectionSpec,
    /// The visible part of the map; `None` for the whole map.
    pub view: Option<Rect>,
    /// Width of the map on screen, in pixels; sets how much detail to keep.
    pub px_width: f64,
    /// Height of the map on screen, in pixels, when the view is stretched
    /// to a box of another shape (PyMappr's world maps fill the canvas);
    /// `None` for square map units.
    #[serde(default)]
    pub px_height: Option<f64>,
    #[serde(default = "default_px_per_pt")]
    pub px_per_pt: f64,
    #[serde(default)]
    pub detail_boost: f64,
    #[serde(default)]
    pub layers: LayerSettings,
    #[serde(default)]
    pub districts: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    Fill,
    Line,
}

#[derive(Debug, Clone, Serialize)]
pub struct RenderedLayer {
    pub id: String,
    pub kind: Kind,
    pub d: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct NeMarker {
    pub layer: String,
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MapLabel {
    pub layer: String,
    pub text: String,
    pub x: f64,
    pub y: f64,
    /// "bottom" puts the text above the point; "center" centres it.
    pub va: &'static str,
    pub font_scale: f64,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Tick {
    pub pos: f64,
    pub text: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Graticule {
    pub d: String,
    pub horizon: Option<String>,
    pub x_ticks: Vec<Tick>,
    pub y_ticks: Vec<Tick>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Raster {
    pub href: String,
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RenderedMap {
    /// The edge of the projected world (the sphere outline), as path data.
    pub outline: String,
    /// The projected world (PyMappr's `bounds`).
    pub extent: Rect,
    /// log2(world width / view width).
    pub zoom: f64,
    /// Natural Earth scale used for the multi-resolution layers.
    pub resolution: String,
    pub layers: Vec<RenderedLayer>,
    pub markers: Vec<NeMarker>,
    pub labels: Vec<MapLabel>,
    pub raster: Option<Raster>,
    pub graticule: Option<Graticule>,
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

/// One view of the map: the projection, what is on screen and at what size.
#[derive(Debug, Clone)]
pub struct MapContext {
    pub proj: Projection,
    /// The view in SVG coordinates.
    pub view: Rect,
    pub px_width: f64,
    /// Height of the view on screen, in pixels.
    pub px_height: f64,
    pub px_per_pt: f64,
    /// PyMappr's zoom: log2(world width / view width).
    pub zoom: f64,
    /// World copies the view reaches (0 first): ±1 world width once the
    /// view crosses an edge of the world, as PyMappr's wrap copies.
    pub offsets: Vec<f64>,
}

impl MapContext {
    pub fn new(proj: Projection, view: Option<Rect>, px_width: f64, px_per_pt: f64) -> MapContext {
        let extent = Rect::from_bounds(proj.bounds);
        let view = view.filter(|v| v.w > 0.0 && v.h > 0.0 && v.x.is_finite() && v.y.is_finite()).unwrap_or(extent);
        let world_w = proj.world_width();
        let zoom = (world_w / view.w.max(1e-9)).log2();
        let mut offsets = vec![0.0];
        if !proj.is_globe() {
            let [wx0, wx1, ..] = proj.bounds;
            if view.x < wx0 {
                offsets.push(-world_w);
            }
            if view.x + view.w > wx1 {
                offsets.push(world_w);
            }
        }
        let px_width = px_width.max(1.0);
        let px_height = px_width * view.h / view.w;
        MapContext { proj, view, px_width, px_height, px_per_pt, zoom, offsets }
    }

    /// The same view drawn `px_height` pixels tall (map units not square).
    pub fn with_px_height(mut self, px_height: Option<f64>) -> MapContext {
        if let Some(h) = px_height.filter(|h| *h > 0.0 && h.is_finite()) {
            self.px_height = h;
        }
        self
    }

    /// Screen pixels per map unit vertically.
    pub fn px_per_unit_y(&self) -> f64 {
        self.px_height / self.view.h
    }

    /// The view as projected bounds (x0, x1, y0, y1, y up).
    pub fn data_view(&self) -> [f64; 4] {
        self.view.bounds()
    }

    /// Screen pixels per map unit horizontally.
    pub fn px_per_unit(&self) -> f64 {
        self.px_width / self.view.w
    }

    /// Every wrap copy PyMappr keeps (its `_offsets`), in view or not.
    pub fn all_offsets(&self) -> Vec<f64> {
        if self.proj.is_globe() {
            vec![0.0]
        } else {
            let w = self.proj.world_width();
            vec![-w, 0.0, w]
        }
    }
}

pub fn render(basemap: &Basemap, req: &RenderRequest) -> Result<RenderedMap, RenderError> {
    let proj = Projection::new(&req.projection)?;
    let ctx = MapContext::new(proj, req.view, req.px_width, req.px_per_pt).with_px_height(req.px_height);
    let settings = &req.layers;
    let data_zoom = ctx.zoom + req.detail_boost;
    let mut missing = Vec::new();

    let mut outline_d = String::new();
    let ring = outline(&ctx.proj);
    let mut writer = PathWriter::new(&ctx);
    for off in &ctx.offsets {
        let shifted: Vec<[f64; 2]> = ring.iter().map(|p| [p[0] + off, p[1]]).collect();
        writer.write(&mut outline_d, &shifted, true);
    }

    let plan = layer_plan(basemap, settings, &req.districts, &mut missing);
    let drawn: Vec<Result<String, String>> = plan
        .par_iter()
        .map(|entry| {
            let mut d = String::new();
            for source in &entry.sources {
                let layer = basemap.layer(source, Some(data_zoom)).map_err(|e| format!("{}: {e}", entry.id))?;
                let pieces = projected(basemap, &layer, &ctx.proj);
                draw(&mut d, &pieces, entry.kind, &ctx);
            }
            Ok(d)
        })
        .collect();
    let mut layers = Vec::new();
    for (entry, result) in plan.iter().zip(drawn) {
        match result {
            Ok(d) => layers.push(RenderedLayer { id: entry.id.clone(), kind: entry.kind, d }),
            Err(e) => missing.push(e),
        }
    }

    let resolution = basemap
        .directory("land", Some(data_zoom))
        .or_else(|| basemap.directory("countries", Some(data_zoom)))
        .and_then(scale_of)
        .or_else(|| layer_spec("land").and_then(|s| scale_of(s.directory_for_zoom(Some(data_zoom)))))
        .unwrap_or("50m")
        .to_string();

    let markers = crate::labels::markers(basemap, &ctx, settings, &mut missing);
    let labels = crate::labels::labels(basemap, &ctx, settings, &req.districts, &mut missing);
    let graticule =
        settings.graticule_step().map(|step| crate::graticule::graticule(&ctx, step, !settings.hide_grid_labels));
    let raster = match crate::raster::raster(basemap, &ctx, &settings.basemap) {
        Ok(r) => r,
        Err(e) => {
            missing.push(e);
            None
        }
    };

    Ok(RenderedMap {
        outline: outline_d,
        extent: Rect::from_bounds(ctx.proj.bounds),
        zoom: ctx.zoom,
        resolution,
        layers,
        markers,
        labels,
        raster,
        graticule,
        missing,
    })
}

/// One drawn layer: its id, kind, z-order and the layers it is made of.
#[derive(Debug, Clone)]
pub struct PlanEntry {
    pub id: String,
    pub kind: Kind,
    pub z: f64,
    pub sources: Vec<String>,
}

/// The layers a request draws, in PyMappr's z-order. Optional layers that
/// are not downloaded go to `missing` instead.
pub fn layer_plan(
    basemap: &Basemap,
    settings: &LayerSettings,
    districts: &[String],
    missing: &mut Vec<String>,
) -> Vec<PlanEntry> {
    let entry = |id: &str, kind, z, source: &str| PlanEntry { id: id.into(), kind, z, sources: vec![source.into()] };
    let mut plan = Vec::new();
    if settings.bathymetry {
        for (_, depth) in BATHYMETRY_STEPS {
            let key = format!("bathymetry:{depth}");
            plan.push(entry(&key, Kind::Fill, Z_BATHYMETRY + depth as f64 * 1e-6, &key));
        }
    }
    for &(key, source, z) in FILL_LAYERS {
        if !settings.fill(key) {
            continue;
        }
        if catalog::OPTIONAL_LAYERS.contains(&key) && !basemap.has_layer_data(key) {
            missing.push(format!("{key}: not downloaded"));
            continue;
        }
        plan.push(entry(key, Kind::Fill, z, source));
    }
    if matches!(settings.lake_fill.as_str(), "grey" | "blue") {
        plan.push(entry("lakes", Kind::Fill, Z_LAKE_FILL, "lakes"));
    }
    for &(key, source, z) in LINE_LAYERS {
        // Without country borders the continents' outlines stand in.
        let on = if key == "continents" { !settings.line("countries") } else { settings.line(key) };
        if on {
            plan.push(entry(key, Kind::Line, z, source));
        }
    }
    if !districts.is_empty() {
        let sources = districts.iter().map(|c| format!("districts:{}", c.to_ascii_uppercase())).collect();
        plan.push(PlanEntry { id: "districts".into(), kind: Kind::Line, z: Z_DISTRICTS, sources });
    }
    plan.sort_by(|a, b| a.z.total_cmp(&b.z));
    plan
}

/// SVG positions of the user's points; `None` for points the projection
/// does not show. On a regional map points outside the region are pulled
/// onto its edge, as PyMappr does, so none go missing.
pub fn project_points(spec: &ProjectionSpec, points: &[LonLat]) -> Result<Vec<Option<[f64; 2]>>, UnknownProjection> {
    let proj = Projection::new(spec)?;
    Ok(points.iter().map(|&[lon, lat]| proj.forward_clamped(lon, lat).map(|(x, y)| [x, -y])).collect())
}

/// Longitude/latitude under an SVG position, for the cursor read-out.
pub fn unproject(spec: &ProjectionSpec, x: f64, y: f64) -> Result<Option<LonLat>, UnknownProjection> {
    let proj = Projection::new(spec)?;
    Ok(proj.inverse(x, -y).map(|(lon, lat)| [lon, lat]))
}

/// A projected piece of a layer, in SVG coordinates.
#[derive(Debug, Clone)]
pub struct Piece {
    pub pts: Vec<[f64; 2]>,
    pub bbox: Rect,
    pub closed: bool,
    /// Index of the feature it came from.
    pub feature: u32,
}

/// A layer clipped to the drawn world and projected, cached per
/// projection. Point layers have no pieces.
pub fn projected(basemap: &Basemap, layer: &Layer, proj: &Projection) -> Arc<Vec<Piece>> {
    let key = format!("projected:{}:{}", layer.source, proj.key());
    basemap.cached_lru(&key, || {
        if layer.geometry == Geometry::Point {
            return Vec::new();
        }
        let closed = layer.geometry == Geometry::Polygon;
        layer
            .features
            .par_iter()
            .enumerate()
            .flat_map_iter(|(i, f)| {
                let mut out = Vec::new();
                for part in &f.parts {
                    if !proj.is_globe() && !proj.is_regional() && (part.bbox[1] > proj.max_lat || part.bbox[3] < proj.min_lat) {
                        continue;
                    }
                    for piece in clip(proj, &part.points, closed) {
                        let pts = project(proj, &piece);
                        if let Some(bbox) = Rect::from_points(&pts) {
                            out.push(Piece { pts, bbox, closed, feature: i as u32 });
                        }
                    }
                }
                out
            })
            .collect()
    })
}

/// Write the pieces in view (and in any wrap copy in view) as path data:
/// fills cut to the view's surroundings, lines split where they leave it.
pub fn draw(d: &mut String, pieces: &[Piece], kind: Kind, ctx: &MapContext) {
    let mut writer = PathWriter::new(ctx);
    for &off in &ctx.offsets {
        let clip_box = writer.clip.shift(-off);
        let [x0, x1, y0, y1] = [clip_box.x, clip_box.x + clip_box.w, clip_box.y, clip_box.y + clip_box.h];
        let shift = |pts: &[[f64; 2]]| -> Vec<[f64; 2]> { pts.iter().map(|p| [p[0] + off, p[1]]).collect() };
        for piece in pieces {
            if !piece.bbox.intersects(&clip_box) {
                continue;
            }
            let inside = clip_box.contains_rect(&piece.bbox);
            match (kind, piece.closed) {
                (Kind::Fill, _) => {
                    if inside {
                        writer.write(d, &shift(&piece.pts), true);
                    } else {
                        let ring = clip_ring_rect(&piece.pts, x0, x1, y0, y1);
                        if ring.len() >= 3 {
                            writer.write(d, &shift(&ring), true);
                        }
                    }
                }
                (Kind::Line, closed) => {
                    if inside {
                        writer.write(d, &shift(&piece.pts), closed);
                    } else {
                        let mut line = piece.pts.clone();
                        if closed {
                            line.push(piece.pts[0]);
                        }
                        for run in clip_line_rect(&line, x0, x1, y0, y1) {
                            writer.write(d, &shift(&run), false);
                        }
                    }
                }
            }
        }
    }
}

fn project(proj: &Projection, pts: &[LonLat]) -> Vec<[f64; 2]> {
    pts.iter().filter_map(|&[lon, lat]| proj.forward(lon, lat)).map(|(x, y)| [x, -y]).collect()
}

/// The boundary of the drawn world, densified, in SVG coordinates.
pub fn outline(proj: &Projection) -> Vec<[f64; 2]> {
    let mut ring: Vec<LonLat> = Vec::new();
    if proj.is_globe() {
        ring = crate::projection::cap_ring(proj.lon_0, proj.lat_0, HORIZON_RADIUS, 361);
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

// ---- clipping -------------------------------------------------------------

/// Clip a ring (`closed`) or line to the drawn part of the world. A line
/// may come back in several pieces; a ring may too, when it reaches the
/// view from both sides of the cut meridian.
pub fn clip(proj: &Projection, pts: &[LonLat], closed: bool) -> Vec<Vec<LonLat>> {
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
pub fn clip_ring_rect(ring: &[LonLat], x0: f64, x1: f64, y0: f64, y1: f64) -> Vec<LonLat> {
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

/// Split a line into the runs that fall inside a box (Liang-Barsky per
/// segment, so a segment crossing the box without a vertex in it counts).
pub fn clip_line_rect(line: &[LonLat], x0: f64, x1: f64, y0: f64, y1: f64) -> Vec<Vec<LonLat>> {
    let mut runs = Vec::new();
    let mut run: Vec<LonLat> = Vec::new();
    for w in line.windows(2) {
        let (a, b) = (w[0], w[1]);
        let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
        let (mut t0, mut t1) = (0.0f64, 1.0f64);
        let mut visible = true;
        for (p, q) in [(-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])] {
            if p == 0.0 {
                if q < 0.0 {
                    visible = false;
                    break;
                }
            } else {
                let r = q / p;
                if p < 0.0 {
                    t0 = t0.max(r);
                } else {
                    t1 = t1.min(r);
                }
            }
        }
        if !visible || t0 > t1 {
            if run.len() >= 2 {
                runs.push(std::mem::take(&mut run));
            }
            run.clear();
            continue;
        }
        let at = |t: f64| [a[0] + t * dx, a[1] + t * dy];
        if run.is_empty() {
            run.push(if t0 > 0.0 { at(t0) } else { a });
        }
        if t1 < 1.0 {
            run.push(at(t1));
            if run.len() >= 2 {
                runs.push(std::mem::take(&mut run));
            }
            run.clear();
        } else {
            run.push(b);
        }
    }
    if run.len() >= 2 {
        runs.push(run);
    }
    runs
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
pub struct PathWriter {
    /// What is kept: the view and a margin, so cut edges stay off screen.
    pub clip: Rect,
    tolerance: f64,
    decimals: usize,
}

impl PathWriter {
    pub fn new(ctx: &MapContext) -> Self {
        Self::for_view(ctx.view, ctx.px_width)
    }

    pub fn for_view(view: Rect, px_width: f64) -> Self {
        let per_px = view.w / px_width.max(1.0);
        let tolerance = per_px * 0.5;
        let decimals = (1.0 - tolerance.log10().floor()).clamp(0.0, 9.0) as usize;
        PathWriter { clip: view.grow(view.w.max(view.h) * 0.05 + per_px * 4.0), tolerance, decimals }
    }

    pub fn write(&mut self, d: &mut String, pts: &[[f64; 2]], closed: bool) {
        if pts.len() < 2 {
            return;
        }
        let dec = self.decimals;
        let start = d.len();
        let mut last = pts[0];
        let _ = write!(d, "M{:.dec$} {:.dec$}", last[0], last[1]);
        let mut written = 1;
        for (i, p) in pts.iter().enumerate().skip(1) {
            let far = (p[0] - last[0]).abs() > self.tolerance || (p[1] - last[1]).abs() > self.tolerance;
            if far || (i == pts.len() - 1 && !closed) {
                let _ = write!(d, "L{:.dec$} {:.dec$}", p[0], p[1]);
                last = *p;
                written += 1;
            }
        }
        if closed {
            if written >= 3 {
                d.push('Z');
            } else {
                // A ring thinner than a pixel: nothing to see.
                d.truncate(start);
            }
        }
    }

    /// A polyline that may have gaps (`None`), as separate subpaths.
    pub fn write_gappy(&mut self, d: &mut String, pts: &[Option<[f64; 2]>]) {
        for run in pts.split(|p| p.is_none()) {
            let run: Vec<[f64; 2]> = run.iter().flatten().copied().collect();
            self.write(d, &run, false);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    pub(crate) fn spec(name: &str) -> ProjectionSpec {
        ProjectionSpec { name: name.into(), lon_0: None, lat_0: None }
    }

    pub(crate) fn settings(lines: &[&str], fills: &[&str]) -> LayerSettings {
        LayerSettings {
            lines: lines.iter().map(|k| (k.to_string(), true)).collect(),
            fills: fills.iter().map(|k| (k.to_string(), true)).collect(),
            ocean: "none".into(),
            lake_fill: "none".into(),
            basemap: "simple".into(),
            graticule: "Off".into(),
            ..Default::default()
        }
    }

    pub(crate) fn request(name: &str, view: Option<Rect>, layers: LayerSettings) -> RenderRequest {
        RenderRequest {
            projection: spec(name),
            view,
            px_width: 1200.0,
            px_height: None,
            px_per_pt: 96.0 / 72.0,
            detail_boost: 0.0,
            layers,
            districts: Vec::new(),
        }
    }

    fn data() -> Option<Basemap> {
        let dir = crate::pymappr_dir().join("data");
        Basemap::looks_valid(&dir.join("shapes")).then(|| Basemap::new(dir))
    }

    #[test]
    fn rect_clip_cuts_a_square() {
        let sq = [[-10.0, -10.0], [10.0, -10.0], [10.0, 10.0], [-10.0, 10.0]];
        let out = clip_ring_rect(&sq, 0.0, 20.0, 0.0, 20.0);
        let bb = Rect::from_points(&out).unwrap();
        assert_eq!((bb.x, bb.y, bb.w, bb.h), (0.0, 0.0, 10.0, 10.0));
    }

    #[test]
    fn a_segment_crossing_the_box_without_a_vertex_in_it_is_kept() {
        let runs = clip_line_rect(&[[-10.0, 5.0], [20.0, 5.0], [20.0, 30.0]], 0.0, 10.0, 0.0, 10.0);
        assert_eq!(runs, vec![vec![[0.0, 5.0], [10.0, 5.0]]]);
        let runs = clip_line_rect(&[[1.0, 1.0], [2.0, 2.0], [20.0, 2.0], [20.0, 3.0], [3.0, 3.0]], 0.0, 10.0, 0.0, 10.0);
        assert_eq!(runs.len(), 2);
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
    fn points_outside_a_lambert_region_are_pulled_onto_its_edge() {
        let pts = project_points(&spec("Lambert: Europe"), &[[10.0, 52.0], [10.0, 10.0]]).unwrap();
        let proj = Projection::new(&spec("Lambert: Europe")).unwrap();
        let (_, edge_y) = proj.forward(10.0, 30.0).unwrap();
        assert!(pts[0].is_some());
        assert!((pts[1].unwrap()[1] + edge_y).abs() < 1e-6);
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
    fn view_across_the_antimeridian_gets_wrap_copies() {
        let proj = Projection::new(&spec("Robinson")).unwrap();
        let w = proj.world_width();
        let ctx = MapContext::new(proj.clone(), Some(Rect { x: w * 0.4, y: -1e6, w: w * 0.2, h: 2e6 }), 800.0, 1.0);
        assert_eq!(ctx.offsets.len(), 2);
        assert!(ctx.offsets[1] > 0.0);
        let ctx = MapContext::new(proj, Some(Rect { x: -1e6, y: -1e6, w: 2e6, h: 2e6 }), 800.0, 1.0);
        assert_eq!(ctx.offsets, vec![0.0]);
        assert!((ctx.zoom - (w / 2e6).log2()).abs() < 1e-12);
    }

    #[test]
    fn plan_follows_pymappr_z_order() {
        let b = Basemap::new(std::env::temp_dir().join("no-such-natural-earth"));
        let mut s = settings(&["rivers", "states", "lakes_outline"], &["land", "glaciers", "biodiversity"]);
        s.lake_fill = "blue".into();
        s.bathymetry = true;
        let mut missing = Vec::new();
        let plan = layer_plan(&b, &s, &["KEN".into()], &mut missing);
        let ids: Vec<&str> = plan.iter().map(|e| e.id.as_str()).collect();
        assert_eq!(&ids[..2], &["bathymetry:0", "bathymetry:200"]);
        let tail: Vec<&str> = ids[12..].to_vec();
        assert_eq!(tail, vec!["land", "lakes", "glaciers", "rivers", "lakes_outline", "districts", "states", "continents"]);
        assert_eq!(missing.len(), 1, "{missing:?}");
    }

    #[test]
    fn missing_data_is_reported_not_fatal() {
        let basemap = Basemap::new(std::env::temp_dir().join("no-such-natural-earth"));
        let mut s = settings(&["countries"], &["land"]);
        s.graticule = "10°".into();
        let map = render(&basemap, &request("Robinson", None, s)).unwrap();
        assert_eq!(map.missing.len(), 2, "{:?}", map.missing);
        assert!(!map.outline.is_empty());
        assert!(map.graticule.unwrap().d.contains('M'));
    }

    #[test]
    fn renders_pymappr_data_when_present() {
        let Some(basemap) = data() else { return };
        for name in crate::projection::projection_names() {
            let map = render(&basemap, &request(name, None, settings(&["countries"], &["land"]))).unwrap();
            assert!(map.missing.is_empty(), "{name}: {:?}", map.missing);
            assert_eq!(map.layers.len(), 2);
            assert!(map.layers.iter().all(|l| l.d.len() > 1000), "{name}");
            assert!(!map.layers[0].d.contains("NaN"), "{name}");
            assert_eq!(map.resolution, "110m", "{name}");
        }
    }

    #[test]
    fn zooming_in_switches_to_finer_data() {
        let Some(basemap) = data() else { return };
        let proj = Projection::new(&spec("Equirectangular")).unwrap();
        let view = Rect { x: 5.0, y: -50.0, w: 6.0, h: 4.0 }; // the Alps
        let map = render(&basemap, &request("Equirectangular", Some(view), settings(&["countries"], &[]))).unwrap();
        assert_eq!(map.resolution, "10m");
        assert!(map.zoom > 5.0 && (map.zoom - (proj.world_width() / 6.0).log2()).abs() < 1e-9);
        // Countries off: the continents' outline is drawn instead.
        let map = render(&basemap, &request("Equirectangular", Some(view), settings(&[], &[]))).unwrap();
        assert_eq!(map.layers[0].id, "continents");
    }

    #[test]
    fn downloaded_districts_are_drawn_and_labelled() {
        let dir = std::env::temp_dir().join(format!("rustymappr-districts-{}", std::process::id()));
        std::fs::create_dir_all(dir.join("districts")).unwrap();
        let fixture = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/districts_fixture.geojson");
        std::fs::copy(fixture, dir.join("districts").join("TST.geojson")).unwrap();
        let basemap = Basemap::new(&dir);
        let mut s = settings(&[], &[]);
        s.labels.insert("counties".into(), true);
        let mut req = request("Equirectangular", Some(Rect { x: -1.0, y: -11.0, w: 12.0, h: 12.0 }), s);
        req.districts = vec!["tst".into()];
        let map = render(&basemap, &req).unwrap();
        let districts = map.layers.iter().find(|l| l.id == "districts").expect("districts layer");
        assert_eq!(districts.kind, Kind::Line);
        assert_eq!(districts.d.matches('M').count(), 2, "Alpha's shell and hole: {}", districts.d);
        assert!(map.labels.iter().any(|l| l.layer == "districts" && l.text == "Alpha"), "{:?}", map.labels);
        // A country with no download is reported, not fatal.
        req.districts = vec!["KEN".into()];
        let map = render(&basemap, &req).unwrap();
        assert!(map.missing.iter().any(|m| m.contains("KEN")), "{:?}", map.missing);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
