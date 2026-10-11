//! The inset map: a small second map in a corner of the main one, as
//! PyMappr builds it (`renderer/inset.py`): its region and projection, its
//! own layers, the box linking it to the main map, and the user's points.

use serde::{Deserialize, Serialize};

use crate::basemap::{Basemap, scale_of};
use crate::catalog::LINE_LAYERS;
use crate::projection::{GLOBE, Projection, ProjectionSpec, UnknownProjection};
use crate::overlays::{ScaleBarOptions, clearance, corner_anchor, scale_bar};
use crate::regions::{InsetOptions, inset_box_target, inset_extent};
use crate::render::{Kind, MapContext, PathWriter, Rect, RenderedLayer, RenderedMap, draw, outline, projected};
use crate::view::{project_extent, view_lonlat};

/// The inset's width stays within these fractions of the map box, its
/// height under MAX_HEIGHT.
const SIZE_RANGE: (f64, f64) = (0.1, 0.6);
const MAX_HEIGHT: f64 = 0.6;
/// Room left around a globe's disk inside its inset.
const GLOBE_MARGIN: f64 = 1.04;
/// Points along each edge of a box, so it bends with the projection.
const EDGE_POINTS: usize = 50;
/// Gap between the inset and the map frame, in axes fraction.
const PAD: f64 = 0.02;
/// Gap between the inset and the scale bar it steps around.
const GAP: f64 = 0.015;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct InsetRequest {
    pub projection: ProjectionSpec,
    /// The main map's view (SVG coordinates).
    pub view: Rect,
    pub px_width: f64,
    /// The map box's height in pixels when it is not the view's shape.
    #[serde(default)]
    pub px_height: Option<f64>,
    #[serde(default = "default_px_per_pt")]
    pub px_per_pt: f64,
    pub options: InsetOptions,
    /// The scale bar's options, so an inset in its corner steps around it.
    #[serde(default)]
    pub scale_bar: Option<ScaleBarOptions>,
    /// The user's visible points, lon/lat.
    #[serde(default)]
    pub points: Vec<[f64; 2]>,
}

fn default_px_per_pt() -> f64 {
    96.0 / 72.0
}

#[derive(Debug, Clone, Serialize)]
pub struct InsetBox {
    /// "inset", "map" or none.
    pub on: Option<&'static str>,
    pub d: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RenderedInset {
    pub map: RenderedMap,
    /// Where the inset sits on the map, in axes fractions: x and y of its
    /// lower-left corner from the map's left and bottom, width and height.
    pub rect: Rect,
    /// The inset's view in its own SVG coordinates.
    pub view: Rect,
    pub projection: ProjectionSpec,
    /// Height / width of the inset box.
    pub aspect: f64,
    #[serde(rename = "box")]
    pub box_: InsetBox,
    pub points: Vec<Option<[f64; 2]>>,
}

fn spec(name: &str, origin: Option<(f64, f64)>) -> ProjectionSpec {
    ProjectionSpec { name: name.into(), lon_0: origin.map(|o| o.0), lat_0: origin.map(|o| o.1) }
}

/// The inset's projection: the one asked for, else the main map's when
/// the region fits it, else plain lon/lat.
fn inset_projection(opts: &InsetOptions, main: &Projection, main_spec: &ProjectionSpec, region: [f64; 4], centre: [f64; 2]) -> ProjectionSpec {
    match opts.projection.as_str() {
        // Whole degrees: a new projection for every pixel of a pan would
        // rebuild the inset each time.
        "Globe" => return spec(GLOBE, Some((centre[0].round_ties_even(), centre[1].round_ties_even()))),
        "Equirectangular" | "Robinson" => return spec(&opts.projection, None),
        _ => {}
    }
    if main.is_globe() {
        return spec("Equirectangular", None);
    }
    if main.is_regional() {
        let [lon0, lon1, lat0, lat1] = region;
        let inside = lat0 >= main.min_lat
            && lat1 <= main.max_lat
            && lon0 >= main.lon_0 - main.lon_halfspan
            && lon1 <= main.lon_0 + main.lon_halfspan;
        if !inside {
            return spec("Equirectangular", None);
        }
    }
    main_spec.clone()
}

/// A rectangle's outline, densified so it can be reprojected.
fn box_ring(x0: f64, x1: f64, y0: f64, y1: f64) -> Vec<[f64; 2]> {
    let t = |i: usize| i as f64 / (EDGE_POINTS - 1) as f64;
    let mut ring = Vec::with_capacity(EDGE_POINTS * 4);
    ring.extend((0..EDGE_POINTS).map(|i| [x0 + (x1 - x0) * t(i), y0]));
    ring.extend((0..EDGE_POINTS).map(|i| [x1, y0 + (y1 - y0) * t(i)]));
    ring.extend((0..EDGE_POINTS).map(|i| [x1 - (x1 - x0) * t(i), y1]));
    ring.extend((0..EDGE_POINTS).map(|i| [x0, y1 - (y1 - y0) * t(i)]));
    ring
}

pub fn render_inset(basemap: &Basemap, req: &InsetRequest) -> Result<RenderedInset, UnknownProjection> {
    let opts = &req.options;
    let main = Projection::new(&req.projection)?;
    let (view_ext, centre) = view_lonlat(&main, req.view);
    let region = inset_extent(Some(basemap), opts, view_ext, centre);
    let proj_spec = inset_projection(opts, &main, &req.projection, region, centre);
    let proj = Projection::new(&proj_spec)?;

    // Its limits in its projection, then fitted to its box.
    let [mut x0, mut x1, y0, y1] = if proj.is_globe() {
        let b = proj.bounds;
        let (cx, cy) = ((b[0] + b[1]) / 2.0, (b[2] + b[3]) / 2.0);
        let half = (b[1] - b[0]).max(b[3] - b[2]) / 2.0 * GLOBE_MARGIN;
        [cx - half, cx + half, cy - half, cy + half]
    } else {
        project_extent(&proj, region)
    };
    let width = opts.size.clamp(SIZE_RANGE.0, SIZE_RANGE.1);
    let (span_x, span_y) = ((x1 - x0).max(1e-9), (y1 - y0).max(1e-9));
    let px_h = req.px_height.filter(|h| *h > 0.0).unwrap_or(req.px_width * req.view.h / req.view.w);
    let box_aspect = req.px_width / px_h;
    let mut height = width * box_aspect * span_y / span_x;
    if height > MAX_HEIGHT {
        height = MAX_HEIGHT;
        let new_x = span_y * width * box_aspect / MAX_HEIGHT;
        let cx = (x0 + x1) / 2.0;
        (x0, x1) = (cx - new_x / 2.0, cx + new_x / 2.0);
    }
    let view = Rect::from_bounds([x0, x1, y0, y1]);
    let aspect = height * px_h / (width * req.px_width);
    let rect = place(opts, width, height, req, px_h);

    // The resolution that suits its own span at its size on the map.
    let zoom = ((proj.world_width() / (x1 - x0).abs().max(1e-9)).log2() + width.max(0.05).log2()).max(0.0);
    let ctx = MapContext::new(proj.clone(), Some(view), req.px_width * width, req.px_per_pt);
    let mut plan: Vec<(&str, Kind, &str)> = Vec::new();
    if matches!(opts.ocean.as_str(), "grey" | "blue") {
        plan.push(("ocean", Kind::Fill, "ocean"));
    }
    if opts.land {
        plan.push(("land", Kind::Fill, "land"));
    }
    // Without country borders the coast is still drawn, as on the map.
    let borders = if opts.countries { "countries" } else { "continents" };
    for (key, on) in [("counties", opts.counties), ("states", opts.states), (borders, true)] {
        if on {
            let source = LINE_LAYERS.iter().find(|l| l.0 == key).map(|l| l.1).unwrap_or(key);
            plan.push((key, Kind::Line, source));
        }
    }
    let mut layers = Vec::new();
    let mut missing = Vec::new();
    for (id, kind, source) in plan {
        match basemap.layer(source, Some(zoom)) {
            Ok(layer) => {
                let mut d = String::new();
                draw(&mut d, &projected(basemap, &layer, &proj), kind, &ctx);
                layers.push(RenderedLayer { id: id.into(), kind, d });
            }
            Err(e) => missing.push(format!("inset {id}: {e}")),
        }
    }
    let mut outline_d = String::new();
    PathWriter::new(&ctx).write(&mut outline_d, &outline(&proj), true);
    let resolution = basemap.directory("land", Some(zoom)).and_then(scale_of).unwrap_or("50m").to_string();
    let map = RenderedMap {
        outline: outline_d,
        extent: Rect::from_bounds(proj.bounds),
        zoom,
        resolution,
        layers,
        markers: Vec::new(),
        labels: Vec::new(),
        raster: None,
        graticule: None,
        missing,
    };

    // The box linking the two maps.
    let target = if !opts.box_ {
        None
    } else if proj.is_globe() {
        Some("inset")
    } else {
        inset_box_target(region, view_ext)
    };
    let svg = |p: Option<(f64, f64)>| p.map(|(x, y)| [x, -y]);
    let box_ = match target {
        Some("inset") => {
            let [mx0, mx1, my0, my1] = req.view.bounds();
            let pts: Vec<_> = box_ring(mx0, mx1, my0, my1)
                .into_iter()
                .map(|[x, y]| svg(main.inverse_raw(x, y).and_then(|(lon, lat)| proj.forward_unclamped(lon, lat))))
                .collect();
            let mut d = String::new();
            PathWriter::new(&ctx).write_gappy(&mut d, &pts);
            InsetBox { on: Some("inset"), d }
        }
        Some(_) => {
            let [lon0, lon1, lat0, lat1] = region;
            let pts: Vec<_> =
                box_ring(lon0, lon1, lat0, lat1).into_iter().map(|[lon, lat]| svg(main.forward_unclamped(lon, lat))).collect();
            let mut d = String::new();
            PathWriter::for_view(req.view, req.px_width).write_gappy(&mut d, &pts);
            InsetBox { on: Some("map"), d }
        }
        None => InsetBox { on: None, d: String::new() },
    };
    let points = if opts.points {
        req.points.iter().map(|&[lon, lat]| svg(proj.forward_unclamped(lon, lat))).collect()
    } else {
        Vec::new()
    };
    Ok(RenderedInset { map, rect, view, projection: proj_spec, aspect, box_, points })
}

/// Put the inset in its corner, or where it was dragged, stepping above
/// (or below) a scale bar in the same corner (PyMappr's `_place_inset`).
fn place(opts: &InsetOptions, width: f64, height: f64, req: &InsetRequest, px_h: f64) -> Rect {
    if let (Some(ax), Some(ay)) = (opts.anchor_x, opts.anchor_y) {
        return Rect { x: ax.clamp(0.0, 1.0 - width), y: ay.clamp(0.0, 1.0 - height), w: width, h: height };
    }
    let (cx, cy) = corner_anchor(&opts.position, PAD);
    let (right, top) = (cx > 0.5, cy > 0.5);
    let x = if right { cx - width } else { cx };
    let mut y = if top { cy - height } else { cy };
    if let Some(bar_opts) = req.scale_bar.as_ref().filter(|b| b.show && b.position == opts.position) {
        if let Ok(proj) = Projection::new(&req.projection) {
            let bar = scale_bar(&proj, req.view, bar_opts);
            if let Some((frac, points)) = clearance(bar_opts, &bar) {
                let lift = points / 72.0 * (req.px_per_pt * 72.0) / px_h.max(1.0);
                y = if top { y.min(frac + lift - GAP - height) } else { y.max(frac + lift + GAP) };
            }
        }
    }
    Rect { x, y, w: width, h: height }
}

#[cfg(test)]
mod tests {
    use super::*;

    const LANCASTER: [f64; 4] = [-97.3, -96.2, 40.5, 41.4];
    const ASPECT: f64 = (6.5 * (0.988 - 0.012)) / (9.0 * (0.99 - 0.01));

    fn data() -> Option<Basemap> {
        let dir = crate::pymappr_dir().join("data");
        Basemap::looks_valid(&dir.join("shapes")).then(|| Basemap::new(dir))
    }

    fn request(projection: &str, extent: [f64; 4], options: InsetOptions) -> InsetRequest {
        let spec = spec(projection, None);
        let proj = Projection::new(&spec).unwrap();
        let view = crate::view::extent_view(&proj, extent, ASPECT);
        InsetRequest {
            projection: spec,
            view,
            px_width: 900.0,
            px_height: None,
            px_per_pt: 100.0 / 72.0,
            options,
            scale_bar: None,
            points: Vec::new(),
        }
    }

    fn opts(region: &str) -> InsetOptions {
        InsetOptions { show: true, region: region.into(), ..Default::default() }
    }

    #[test]
    fn a_state_locator_marks_the_view_on_the_inset() {
        let Some(b) = data() else { return };
        let mut o = opts("state");
        o.states = true;
        o.counties = true;
        let mut req = request("Equirectangular", LANCASTER, o);
        req.points = vec![[-96.7, 40.8], [-96.5, 41.0]];
        let inset = render_inset(&b, &req).unwrap();
        assert_eq!(inset.box_.on, Some("inset"));
        let ids: Vec<&str> = inset.map.layers.iter().map(|l| l.id.as_str()).collect();
        assert_eq!(ids, ["land", "counties", "states", "countries"]);
        // No national border runs through Nebraska; the rest is drawn.
        for l in inset.map.layers.iter().filter(|l| l.id != "countries") {
            assert!(!l.d.is_empty(), "{} is empty", l.id);
        }
        // The box is the view, inside Nebraska's frame.
        let v = inset.view;
        assert!(v.w > req.view.w * 3.0, "{v:?}");
        assert!(v.contains([req.view.x, req.view.y]) && v.contains([req.view.x + req.view.w, req.view.y + req.view.h]));
        assert!(inset.box_.d.starts_with('M'));
        assert_eq!(inset.points.len(), 2);
        assert!(inset.points.iter().all(|p| p.is_some_and(|p| v.contains(p))));
        assert!((inset.aspect - v.h / v.w).abs() < 1e-9);
    }

    #[test]
    fn a_zoomed_inset_is_boxed_on_the_world_map() {
        let Some(b) = data() else { return };
        let o = InsetOptions { lon_min: Some(-160.5), lon_max: Some(-154.5), lat_min: Some(18.7), lat_max: Some(22.4), ..opts("custom") };
        let inset = render_inset(&b, &request("Equirectangular", [-180.0, 180.0, -90.0, 90.0], o)).unwrap();
        assert_eq!(inset.box_.on, Some("map"));
        assert!(inset.box_.d.contains("-160"));
    }

    #[test]
    fn the_inset_follows_projection_rules() {
        let Some(b) = data() else { return };
        let inset = render_inset(&b, &request("Lambert: N. America", LANCASTER, opts("country"))).unwrap();
        assert_eq!(inset.projection.name, "Lambert: N. America", "the region fits the projection");
        let o = InsetOptions { projection: "Robinson".into(), ..opts("country") };
        assert_eq!(render_inset(&b, &request("Equirectangular", LANCASTER, o)).unwrap().projection.name, "Robinson");
        let inset = render_inset(&b, &request("Lambert: Europe", [-25.0, 45.0, 34.0, 72.0], opts("World"))).unwrap();
        assert_eq!(inset.projection.name, "Equirectangular", "the world does not fit Lambert: Europe");
    }

    #[test]
    fn a_globe_inset_is_a_disk_centred_on_the_map() {
        let Some(b) = data() else { return };
        let o = InsetOptions { projection: "Globe".into(), ..opts("state") };
        let inset = render_inset(&b, &request("Equirectangular", [41.0, 53.0, -27.0, -11.0], o)).unwrap();
        assert_eq!(inset.projection.name, GLOBE);
        assert!((inset.projection.lon_0.unwrap() - 47.0).abs() <= 1.0);
        assert!((inset.aspect - 1.0).abs() < 1e-9, "square");
        assert_eq!(inset.box_.on, Some("inset"));
    }

    #[test]
    fn a_tall_region_is_widened_to_fit() {
        let Some(b) = data() else { return };
        let o = InsetOptions { size: 0.6, ..opts("South America") };
        let req = request("Equirectangular", LANCASTER, o);
        let inset = render_inset(&b, &req).unwrap();
        let box_aspect = req.view.w / req.view.h;
        assert!(inset.aspect * 0.6 * box_aspect <= MAX_HEIGHT + 1e-9);
    }
}
