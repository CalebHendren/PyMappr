//! The lon/lat area an inset map shows, worked out from where the main map
//! is (PyMappr's `geo/regions.py` and the inset rules in
//! `styling/decorations.py`).

use serde::Deserialize;

use crate::basemap::{Basemap, Feature, Part};
use crate::catalog::continent_extent;
use crate::geom;

/// Room left around a state or country, as a fraction of its span.
const PAD: f64 = 0.08;
/// Parts of a country kept with the one holding the point: within this
/// fraction of that part's span (but at least NEARBY_MIN degrees).
const NEARBY: f64 = 0.1;
const NEARBY_MIN: f64 = 2.0;
/// A state wider than this (degrees of longitude) is cut to the part
/// holding the point too.
const WIDE_STATE: f64 = 40.0;

/// The inset's options, as in the project's `map.inset`.
#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
pub struct InsetOptions {
    pub show: bool,
    pub position: String,
    pub size: f64,
    pub region: String,
    pub zoom_out: f64,
    pub lon_min: Option<f64>,
    pub lon_max: Option<f64>,
    pub lat_min: Option<f64>,
    pub lat_max: Option<f64>,
    pub projection: String,
    pub countries: bool,
    pub states: bool,
    pub counties: bool,
    pub land: bool,
    pub ocean: String,
    pub points: bool,
    #[serde(rename = "box")]
    pub box_: bool,
    pub box_color: String,
    pub draggable: bool,
    pub anchor_x: Option<f64>,
    pub anchor_y: Option<f64>,
}

impl Default for InsetOptions {
    fn default() -> Self {
        InsetOptions {
            show: false,
            position: "lower right".into(),
            size: 0.3,
            region: "state".into(),
            zoom_out: 6.0,
            lon_min: None,
            lon_max: None,
            lat_min: None,
            lat_max: None,
            projection: "same".into(),
            countries: true,
            states: false,
            counties: false,
            land: true,
            ocean: "none".into(),
            points: true,
            box_: true,
            box_color: "#d62728".into(),
            draggable: false,
            anchor_x: None,
            anchor_y: None,
        }
    }
}

impl InsetOptions {
    /// The typed-in extent, once all four sides are set and make a box.
    pub fn custom_extent(&self) -> Option<[f64; 4]> {
        let sides = [self.lon_min?, self.lon_max?, self.lat_min?, self.lat_max?];
        if sides.iter().any(|v| !v.is_finite()) || sides[1] <= sides[0] || sides[3] <= sides[2] {
            return None;
        }
        Some([sides[0], sides[1], sides[2].max(-90.0), sides[3].min(90.0)])
    }

    /// Whether the inset's region changes as the main map moves.
    pub fn follows_view(&self) -> bool {
        matches!(self.region.as_str(), "state" | "country" | "around") || self.projection == "Globe"
    }
}

fn area(e: [f64; 4]) -> f64 {
    (e[1] - e[0]).max(0.0) * (e[3] - e[2]).max(0.0)
}

/// Where the box linking the two maps goes: "inset" when the inset shows
/// a wider area around the map, "main" when it shows a smaller area inside
/// it, `None` when the two hardly overlap.
pub fn inset_box_target(inset: [f64; 4], view: [f64; 4]) -> Option<&'static str> {
    let (ia, va) = (area(inset), area(view));
    if ia <= 0.0 || va <= 0.0 {
        return None;
    }
    let shared = area([inset[0].max(view[0]), inset[1].min(view[1]), inset[2].max(view[2]), inset[3].min(view[3])]);
    if ia >= 1.5 * va && shared >= 0.5 * va {
        return Some("inset");
    }
    if ia * 1.5 <= va && shared >= 0.5 * ia {
        return Some("main");
    }
    None
}

fn pad(e: [f64; 4]) -> [f64; 4] {
    let dx = ((e[1] - e[0]) * PAD).max(0.05);
    let dy = ((e[3] - e[2]) * PAD).max(0.05);
    [(e[0] - dx).max(-180.0), (e[1] + dx).min(180.0), (e[2] - dy).max(-90.0), (e[3] + dy).min(90.0)]
}

/// A view's lon/lat extent grown `factor` times about its centre, kept on
/// the globe.
pub fn around_extent(view: [f64; 4], factor: f64) -> [f64; 4] {
    let factor = factor.max(1.0);
    let (cx, cy) = ((view[0] + view[1]) / 2.0, (view[2] + view[3]) / 2.0);
    let half_w = ((view[1] - view[0]) * factor / 2.0).min(180.0);
    let half_h = ((view[3] - view[2]) * factor / 2.0).min(90.0);
    let (mut lon0, mut lon1) = (cx - half_w, cx + half_w);
    if lon0 < -180.0 {
        (lon0, lon1) = (-180.0, (-180.0 + 2.0 * half_w).min(180.0));
    } else if lon1 > 180.0 {
        (lon0, lon1) = ((180.0 - 2.0 * half_w).max(-180.0), 180.0);
    }
    let (mut lat0, mut lat1) = (cy - half_h, cy + half_h);
    if lat0 < -90.0 {
        (lat0, lat1) = (-90.0, (-90.0 + 2.0 * half_h).min(90.0));
    } else if lat1 > 90.0 {
        (lat0, lat1) = ((90.0 - 2.0 * half_h).max(-90.0), 90.0);
    }
    [lon0, lon1, lat0, lat1]
}

fn rings<'a>(poly: &[&'a Part]) -> Vec<&'a [[f64; 2]]> {
    poly.iter().map(|p| p.points.as_slice()).collect()
}

fn feature_contains(f: &Feature, lon: f64, lat: f64) -> bool {
    if lon < f.bbox[0] || lon > f.bbox[2] || lat < f.bbox[1] || lat > f.bbox[3] {
        return false;
    }
    f.polygons().iter().any(|poly| geom::contains(&rings(poly), [lon, lat]))
}

/// The padded lon/lat extent of the "states" or "countries" feature
/// holding a point, or `None` when none does (the point is at sea).
pub fn containing_extent(basemap: &Basemap, key: &str, lon: f64, lat: f64) -> Option<[f64; 4]> {
    // 10m countries, so small ones are found too.
    let zoom = if key == "countries" { Some(3.5) } else { None };
    let layer = basemap.layer(key, zoom).ok()?;
    let index = layer.features.iter().position(|f| feature_contains(f, lon, lat))?;
    let feature = &layer.features[index];
    let polys = feature.polygons();
    let home = polys.iter().position(|poly| geom::contains(&rings(poly), [lon, lat])).unwrap_or(0);
    let cache_key = format!("containing:{}:{index}:{home}", layer.source);
    let found = basemap.cached(&cache_key, || {
        let whole = feature.bbox[2] - feature.bbox[0];
        let near_only = key == "countries" || whole > WIDE_STATE;
        let hb = polys[home][0].bbox;
        let reach = ((hb[2] - hb[0]).max(hb[3] - hb[1]) * NEARBY).max(NEARBY_MIN);
        let home_rings = rings(&polys[home]);
        let mut e = [f64::MAX, f64::MIN, f64::MAX, f64::MIN];
        for (i, poly) in polys.iter().enumerate() {
            let b = poly[0].bbox;
            if near_only && i != home {
                // Bounding boxes farther apart than the reach rule a part out
                // without measuring it.
                let gap_x = (b[0] - hb[2]).max(hb[0] - b[2]).max(0.0);
                let gap_y = (b[1] - hb[3]).max(hb[1] - b[3]).max(0.0);
                if gap_x.hypot(gap_y) > reach || geom::polygon_distance(&rings(poly), &home_rings) > reach {
                    continue;
                }
            }
            e = [e[0].min(b[0]), e[1].max(b[2]), e[2].min(b[1]), e[3].max(b[3])];
        }
        pad(e)
    });
    Some(*found)
}

/// The lon/lat extent the inset shows, given the main map's lon/lat
/// extent and centre. A state or country that cannot be found falls back
/// to the area around the view; an incomplete custom box to the world.
pub fn inset_extent(basemap: Option<&Basemap>, opts: &InsetOptions, view: [f64; 4], centre: [f64; 2]) -> [f64; 4] {
    if let Some(extent) = continent_extent(&opts.region) {
        return extent;
    }
    if opts.region == "custom" {
        return opts.custom_extent().unwrap_or([-180.0, 180.0, -90.0, 90.0]);
    }
    if matches!(opts.region.as_str(), "state" | "country") && centre[0].is_finite() && centre[1].is_finite() {
        let key = if opts.region == "state" { "states" } else { "countries" };
        if let Some(found) = basemap.and_then(|b| containing_extent(b, key, centre[0], centre[1])) {
            return found;
        }
    }
    around_extent(view, opts.zoom_out)
}

/// ISO3 codes of the countries drawn inside a view (SVG coordinates),
/// for offering their districts. The United States is left out: Natural
/// Earth's counties cover it.
pub fn countries_in_view(basemap: &Basemap, proj: &crate::projection::Projection, view: crate::render::Rect) -> Vec<String> {
    use crate::render::{MapContext, clip_ring_rect, projected};
    let ctx = MapContext::new(proj.clone(), Some(view), 1000.0, 1.0);
    let Ok(layer) = basemap.layer("countries", Some(ctx.zoom)) else { return Vec::new() };
    let pieces = projected(basemap, &layer, proj);
    let mut found = std::collections::BTreeSet::new();
    for &off in &ctx.offsets {
        let v = view.shift(-off);
        for piece in pieces.iter() {
            if !piece.bbox.intersects(&v) {
                continue;
            }
            let Some(iso3) = layer.features[piece.feature as usize].attrs.iso3() else { continue };
            if iso3 == "USA" || found.contains(iso3) {
                continue;
            }
            let cut = clip_ring_rect(&piece.pts, v.x, v.x + v.w, v.y, v.y + v.h);
            let area: f64 = cut.iter().zip(cut.iter().cycle().skip(1)).map(|(a, b)| a[0] * b[1] - b[0] * a[1]).sum();
            if cut.len() >= 3 && area.abs() > 0.0 {
                found.insert(iso3.to_string());
            }
        }
    }
    found.into_iter().collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    const LANCASTER: [f64; 4] = [-97.3, -96.2, 40.5, 41.4];
    const HAWAII: [f64; 4] = [-160.5, -154.5, 18.7, 22.4];

    fn data() -> Option<Basemap> {
        let dir = crate::pymappr_dir().join("data");
        Basemap::looks_valid(&dir.join("shapes")).then(|| Basemap::new(dir))
    }

    #[test]
    fn a_custom_extent_needs_all_four_sides_in_order() {
        assert!(InsetOptions { region: "custom".into(), ..Default::default() }.custom_extent().is_none());
        let o = |a, b, c, d| InsetOptions { lon_min: Some(a), lon_max: Some(b), lat_min: Some(c), lat_max: Some(d), ..Default::default() };
        assert!(o(5.0, -5.0, 0.0, 1.0).custom_extent().is_none());
        assert_eq!(o(-5.0, 5.0, 0.0, 1.0).custom_extent(), Some([-5.0, 5.0, 0.0, 1.0]));
    }

    #[test]
    fn only_view_dependent_regions_follow_the_map() {
        let o = |region: &str, projection: &str| InsetOptions { region: region.into(), projection: projection.into(), ..Default::default() };
        assert!(o("state", "same").follows_view());
        assert!(o("around", "same").follows_view());
        assert!(!o("World", "same").follows_view());
        assert!(o("World", "Globe").follows_view());
    }

    #[test]
    fn box_targets() {
        assert_eq!(inset_box_target([-105.0, -95.0, 40.0, 43.0], LANCASTER), Some("inset"));
        assert_eq!(inset_box_target(HAWAII, [-180.0, 180.0, -90.0, 90.0]), Some("main"));
        assert_eq!(inset_box_target(HAWAII, LANCASTER), None);
        assert_eq!(inset_box_target(LANCASTER, LANCASTER), None);
    }

    #[test]
    fn around_grows_the_view_and_stays_on_the_globe() {
        let e = around_extent([-10.0, 10.0, 0.0, 10.0], 4.0);
        assert_eq!((e[1] - e[0], e[3] - e[2]), (80.0, 40.0));
        assert_eq!(around_extent([170.0, 179.0, 80.0, 89.0], 10.0)[1], 180.0);
        assert_eq!(around_extent([170.0, 179.0, 80.0, 89.0], 10.0)[3], 90.0);
    }

    #[test]
    fn fixed_regions_need_no_layer_data() {
        let centre = [-96.7, 41.0];
        let europe = InsetOptions { region: "Europe".into(), ..Default::default() };
        assert_eq!(inset_extent(None, &europe, LANCASTER, centre), [-25.0, 45.0, 34.0, 72.0]);
        let custom = InsetOptions { region: "custom".into(), lon_min: Some(1.0), lon_max: Some(2.0), lat_min: Some(3.0), lat_max: Some(4.0), ..Default::default() };
        assert_eq!(inset_extent(None, &custom, LANCASTER, centre), [1.0, 2.0, 3.0, 4.0]);
        let half = InsetOptions { region: "custom".into(), ..Default::default() };
        assert_eq!(inset_extent(None, &half, LANCASTER, centre), [-180.0, 180.0, -90.0, 90.0]);
    }

    #[test]
    fn the_state_holding_the_map_is_found() {
        let Some(b) = data() else { return };
        let [lon0, lon1, lat0, lat1] = containing_extent(&b, "states", -96.7, 40.9).unwrap();
        assert!(-106.0 < lon0 && lon0 < -104.0 && -95.0 < lon1 && lon1 < -94.0, "{lon0} {lon1}");
        assert!(39.0 < lat0 && lat0 < 40.0 && 43.0 < lat1 && lat1 < 44.0, "{lat0} {lat1}");
    }

    #[test]
    fn a_country_inset_keeps_to_the_part_holding_the_map() {
        let Some(b) = data() else { return };
        let [lon0, lon1, _, lat1] = containing_extent(&b, "countries", -83.5, 35.6).unwrap();
        assert!(-132.0 < lon0 && lon0 < -124.0 && -68.0 < lon1 && lon1 < -60.0, "{lon0} {lon1}");
        assert!(lat1 < 53.0);
    }

    #[test]
    fn countries_in_view_of_east_africa() {
        let Some(b) = data() else { return };
        let proj = crate::projection::Projection::new(&crate::projection::ProjectionSpec {
            name: "Equirectangular".into(),
            lon_0: None,
            lat_0: None,
        })
        .unwrap();
        let view = crate::render::Rect { x: 33.0, y: -5.0, w: 10.0, h: 8.0 }; // lat 5S..3N
        let found = countries_in_view(&b, &proj, view);
        for want in ["KEN", "UGA", "TZA"] {
            assert!(found.iter().any(|c| c == want), "{found:?}");
        }
        assert!(!found.iter().any(|c| c == "EGY"));
        let usa = crate::render::Rect { x: -100.0, y: -45.0, w: 10.0, h: 8.0 };
        assert!(countries_in_view(&b, &proj, usa).is_empty());
    }

    #[test]
    fn open_sea_falls_back_to_the_area_around_the_view() {
        let Some(b) = data() else { return };
        let view = [-40.0, -30.0, -10.0, 0.0];
        let opts = InsetOptions { region: "state".into(), zoom_out: 3.0, ..Default::default() };
        assert_eq!(inset_extent(Some(&b), &opts, view, [-35.0, -5.0]), around_extent(view, 3.0));
    }
}
