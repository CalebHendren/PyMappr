//! Place names and Natural Earth point markers (cities, capitals, airports,
//! ports), as PyMappr places them (`renderer/labels.py`, the markers in
//! `renderer/layers.py` and the anchors in `geo/layers.py`): which fit the
//! view, most important first, without overlapping each other.

use std::sync::Arc;

use geo::{MultiPolygon, Polygon, Rect as GeoRect};

use crate::basemap::{Basemap, Feature, Geometry, Layer};
use crate::catalog::{DISTRICT_LABEL_CAP, LABEL_STYLES, LabelStyle, derived_source, layer_spec, point_layer};
use crate::geom;
use crate::projection::Projection;
use crate::render::{LayerSettings, MapContext, MapLabel, NeMarker, clip_line_rect};

/// A label anchor in longitude/latitude.
#[derive(Debug, Clone)]
pub struct Anchor {
    pub lon: f64,
    pub lat: f64,
    pub text: String,
    /// Natural Earth's curated rank: smaller shows earlier.
    pub min_label: f64,
}

/// The spec a label key reads its label column from.
fn label_source_spec(key: &str) -> Option<&'static crate::catalog::LayerSpec> {
    match derived_source(key) {
        Some(source) if key != "continents" => layer_spec(source),
        _ => layer_spec(key),
    }
}

/// A regional (Lambert) map's lon/lat area for anchoring labels, as boxes
/// (lon0, lat0, lon1, lat1) within ±180° (PyMappr's `label_region`);
/// `None` on other projections.
pub fn label_region(proj: &Projection) -> Option<Vec<[f64; 4]>> {
    if proj.is_globe() || !proj.is_regional() {
        return None;
    }
    let lon0 = (proj.lon_0 + 180.0).rem_euclid(360.0) - 180.0;
    let hs = proj.lon_halfspan;
    let boxes: Vec<[f64; 4]> = [-360.0, 0.0, 360.0]
        .iter()
        .filter_map(|off| {
            let (a, b) = ((lon0 - hs + off).max(-180.0), (lon0 + hs + off).min(180.0));
            (b > a).then_some([a, proj.min_lat, b, proj.max_lat])
        })
        .collect();
    Some(boxes)
}

/// Label anchors for a layer (PyMappr's `label_points`), cached. On a
/// regional map polygon and line labels are anchored on the part of each
/// feature inside `region`.
pub fn anchors(basemap: &Basemap, key: &str, region: Option<&[[f64; 4]]>) -> Result<Arc<Vec<Anchor>>, String> {
    let layer = basemap.layer(key, None).map_err(|e| format!("{key} labels: {e}"))?;
    let region = region.filter(|_| layer.geometry != Geometry::Point);
    let cache_key = format!("anchors:{}:{:?}", layer.source, region);
    Ok(basemap.cached(&cache_key, || label_frame(key, &layer, region)))
}

fn label_frame(key: &str, layer: &Layer, region: Option<&[[f64; 4]]>) -> Vec<Anchor> {
    let column = label_source_spec(key).map(|s| s.label_column).unwrap_or("name");
    let has = |f: fn(&Feature) -> bool| layer.features.iter().any(f);
    let rank_of: fn(&Feature) -> Option<f64> = if matches!(key, "cities" | "capitals") {
        |f| f.attrs.min_zoom
    } else if has(|f| f.attrs.min_label.is_some()) {
        |f| f.attrs.min_label
    } else if has(|f| f.attrs.min_zoom.is_some()) {
        |f| f.attrs.min_zoom
    } else if has(|f| f.attrs.scalerank.is_some()) {
        |f| f.attrs.scalerank
    } else {
        |_| None
    };
    let region_mp = region.map(|boxes| {
        MultiPolygon::new(
            boxes.iter().map(|b| GeoRect::new((b[0], b[1]), (b[2], b[3])).to_polygon()).collect::<Vec<Polygon>>(),
        )
    });
    let mut rows: Vec<(Anchor, f64)> = Vec::new();
    for f in &layer.features {
        let Some(text) = f.attrs.text(column).filter(|t| !t.is_empty()) else { continue };
        let rank = rank_of(f).filter(|v| v.is_finite()).unwrap_or(5.0);
        let point = match layer.geometry {
            Geometry::Point => Some((f.parts[0].points[0], 0.0)),
            Geometry::Line => {
                let lines: Vec<Vec<[f64; 2]>> = match region {
                    Some(boxes) => f
                        .parts
                        .iter()
                        .flat_map(|p| boxes.iter().flat_map(|b| clip_line_rect(&p.points, b[0], b[2], b[1], b[3])))
                        .collect(),
                    None => f.parts.iter().map(|p| p.points.clone()).collect(),
                };
                let refs: Vec<&[[f64; 2]]> = lines.iter().map(|l| l.as_slice()).collect();
                if refs.is_empty() { None } else { geom::midpoint_along(&refs).map(|p| (p, geom::length(&refs))) }
            }
            Geometry::Polygon => {
                let anchor = match (region, &region_mp) {
                    (Some(boxes), Some(mp)) => {
                        let b = f.bbox;
                        let inside = boxes.iter().any(|r| b[0] >= r[0] && b[2] <= r[2] && b[1] >= r[1] && b[3] <= r[3]);
                        let outside = boxes.iter().all(|r| b[0] > r[2] || b[2] < r[0] || b[1] > r[3] || b[3] < r[1]);
                        if outside {
                            None
                        } else if inside {
                            polygon_anchor(f)
                        } else {
                            let cut = geom::intersect(&geom::feature_to_geo(f), mp);
                            polygon_anchor(&Feature::new(geom::geo_to_parts(&cut), Default::default()))
                        }
                    }
                    _ => polygon_anchor(f),
                };
                anchor.map(|p| (p, 0.0))
            }
        };
        if let Some((p, len)) = point {
            rows.push((Anchor { lon: p[0], lat: p[1], text: text.to_string(), min_label: rank }, len));
        }
    }
    if matches!(key, "rivers" | "wadis") {
        // A river is split into many segments; label the longest.
        rows.sort_by(|a, b| b.1.total_cmp(&a.1));
        let mut seen = std::collections::HashSet::new();
        rows.retain(|r| seen.insert(r.0.text.clone()));
    }
    rows.into_iter().map(|r| r.0).collect()
}

fn polygon_anchor(f: &Feature) -> Option<[f64; 2]> {
    let polys: Vec<Vec<&[[f64; 2]]>> =
        f.polygons().iter().map(|poly| poly.iter().map(|p| p.points.as_slice()).collect()).collect();
    geom::representative_point(&polys)
}

/// Slightly smaller fonts when zoomed far out (PyMappr's font scale).
pub fn font_scale(zoom: f64) -> f64 {
    (0.78 + 0.06 * zoom).clamp(0.78, 1.15)
}

/// A label's rough pixel box, cheap enough for every candidate.
pub fn estimate_rect(sx: f64, sy: f64, text: &str, fontsize_px: f64) -> [f64; 4] {
    let half_w = (text.chars().count() as f64 * 0.31 + 0.3) * fontsize_px;
    let half_h = 0.72 * fontsize_px;
    [sx - half_w, sy - half_h, sx + half_w, sy + half_h]
}

fn overlaps_any(r: &[f64; 4], placed: &[[f64; 4]]) -> bool {
    placed.iter().any(|b| r[0] < b[2] && r[2] > b[0] && r[1] < b[3] && r[3] > b[1])
}

struct Candidate {
    text: String,
    x: f64,
    y: f64,
    rank: f64,
}

/// The labels for a view, in PyMappr's layer order: each layer's
/// candidates in view, most important first up to its cap, each kept only
/// if it does not overlap a label placed before it.
pub fn labels(
    basemap: &Basemap,
    ctx: &MapContext,
    settings: &LayerSettings,
    districts: &[String],
    missing: &mut Vec<String>,
) -> Vec<MapLabel> {
    let zoom = ctx.zoom;
    let scale = font_scale(zoom);
    let region = label_region(&ctx.proj);
    let mut placed: Vec<[f64; 4]> = Vec::new();
    let mut out = Vec::new();
    let ppu = ctx.px_per_unit();
    for style in LABEL_STYLES {
        let on = match style.key {
            "districts" => !districts.is_empty() && (settings.label("districts") || settings.label("counties")),
            key => settings.label(key),
        };
        if !on || zoom < style.min_zoom {
            continue;
        }
        let sources: Vec<String> = match style.key {
            "districts" => districts.iter().map(|c| format!("districts:{}", c.to_ascii_uppercase())).collect(),
            "cities" if settings.capitals_only => vec!["capitals".into()],
            _ => vec![style.source.into()],
        };
        let cap = match style.key {
            "districts" => DISTRICT_LABEL_CAP,
            _ => layer_spec(style.source).map(|s| s.label_cap).unwrap_or(0),
        };
        let mut candidates = Vec::new();
        for source in &sources {
            match anchors(basemap, source, region.as_deref()) {
                Ok(anchors) => candidates.extend(candidates_in_view(basemap, ctx, source, &anchors, style)),
                Err(e) => missing.push(e),
            }
        }
        candidates.sort_by(|a, b| a.rank.total_cmp(&b.rank));
        candidates.truncate(cap);
        let va = if point_layer(style.key).is_some() { "bottom" } else { "center" };
        let fontsize_px = style.fontsize * scale * ctx.px_per_pt;
        for c in candidates {
            let rect = estimate_rect((c.x - ctx.view.x) * ppu, (c.y - ctx.view.y) * ppu, &c.text, fontsize_px);
            if overlaps_any(&rect, &placed) {
                continue;
            }
            placed.push(rect);
            out.push(MapLabel { layer: style.key.into(), text: c.text, x: c.x, y: c.y, va, font_scale: scale });
        }
    }
    out
}

/// Projected anchors (PyMappr's `_label_xy`), cached per projection.
fn projected_anchors(
    basemap: &Basemap,
    ctx: &MapContext,
    source: &str,
    anchors: &[Anchor],
) -> Arc<Vec<Option<[f64; 2]>>> {
    let region = label_region(&ctx.proj).is_some();
    let key = format!("anchor-xy:{source}:{region}:{}:{}", anchors.len(), ctx.proj.key());
    basemap.cached_lru(&key, || {
        anchors.iter().map(|a| ctx.proj.forward_unclamped(a.lon, a.lat).map(|(x, y)| [x, -y])).collect()
    })
}

fn candidates_in_view(
    basemap: &Basemap,
    ctx: &MapContext,
    source: &str,
    anchors: &[Anchor],
    style: &LabelStyle,
) -> Vec<Candidate> {
    let xy = projected_anchors(basemap, ctx, source, anchors);
    let mut out = Vec::new();
    for off in ctx.all_offsets() {
        for (a, p) in anchors.iter().zip(xy.iter()) {
            let Some(p) = p else { continue };
            let (x, y) = (p[0] + off, p[1]);
            if !ctx.view.contains([x, y]) {
                continue;
            }
            if style.feature_bias.is_some_and(|bias| a.min_label > ctx.zoom + bias) {
                continue;
            }
            out.push(Candidate { text: a.text.clone(), x, y, rank: a.min_label });
        }
    }
    out
}

/// Natural Earth point markers in view whose `min_zoom` the zoom allows.
pub fn markers(basemap: &Basemap, ctx: &MapContext, settings: &LayerSettings, missing: &mut Vec<String>) -> Vec<NeMarker> {
    let mut out = Vec::new();
    let near = ctx.view.grow(ctx.view.w.max(ctx.view.h) * 0.02);
    for key in ["cities", "airports", "ports"] {
        if !settings.point(key) {
            continue;
        }
        let layer_key = if key == "cities" && settings.capitals_only { "capitals" } else { key };
        let Some((_, source, bias)) = point_layer(layer_key) else { continue };
        let layer = match basemap.layer(source, None) {
            Ok(l) => l,
            Err(e) => {
                missing.push(format!("{key}: {e}"));
                continue;
            }
        };
        let cache_key = format!("points:{}:{}", layer.source, ctx.proj.key());
        let points = basemap.cached_lru(&cache_key, || {
            let has_min_zoom = layer.features.iter().any(|f| f.attrs.min_zoom.is_some());
            let has_scalerank = layer.features.iter().any(|f| f.attrs.scalerank.is_some());
            layer
                .features
                .iter()
                .filter_map(|f| {
                    let p = f.parts.first()?.points.first()?;
                    let (x, y) = ctx.proj.forward_unclamped(p[0], p[1])?;
                    let rank = if has_min_zoom {
                        f.attrs.min_zoom
                    } else if has_scalerank {
                        f.attrs.scalerank
                    } else {
                        Some(0.0)
                    };
                    Some(([x, -y], rank.filter(|v| v.is_finite()).unwrap_or(5.0)))
                })
                .collect::<Vec<_>>()
        });
        for off in ctx.all_offsets() {
            for (p, min_zoom) in points.iter() {
                let (x, y) = (p[0] + off, p[1]);
                if *min_zoom <= ctx.zoom + bias && near.contains([x, y]) {
                    out.push(NeMarker { layer: layer_key.into(), x, y });
                }
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::projection::ProjectionSpec;
    use crate::render::Rect;

    fn data() -> Option<Basemap> {
        let dir = crate::pymappr_dir().join("data");
        Basemap::looks_valid(&dir.join("shapes")).then(|| Basemap::new(dir))
    }

    fn ctx(name: &str, view: Option<Rect>) -> MapContext {
        let proj = Projection::new(&ProjectionSpec { name: name.into(), lon_0: None, lat_0: None }).unwrap();
        MapContext::new(proj, view, 1000.0, 100.0 / 72.0)
    }

    fn with_labels(keys: &[&str]) -> LayerSettings {
        LayerSettings { labels: keys.iter().map(|k| (k.to_string(), true)).collect(), ..Default::default() }
    }

    #[test]
    fn font_scale_is_clipped() {
        assert_eq!(font_scale(-1.0), 0.78);
        assert!((font_scale(2.0) - 0.90).abs() < 1e-12);
        assert_eq!(font_scale(10.0), 1.15);
    }

    #[test]
    fn country_anchors_sit_inside_their_country() {
        let Some(b) = data() else { return };
        let anchors = anchors(&b, "countries", None).unwrap();
        let france = anchors.iter().find(|a| a.text == "France").unwrap();
        assert!((france.lon - 2.5).abs() < 3.0 && (france.lat - 46.5).abs() < 2.0, "{france:?}");
        let chile = anchors.iter().find(|a| a.text == "Chile").unwrap();
        assert!(chile.lon < -65.0 && chile.lat < -15.0, "{chile:?}");
    }

    #[test]
    fn world_labels_do_not_overlap_and_follow_the_cap() {
        let Some(b) = data() else { return };
        let c = ctx("Equirectangular", None);
        let mut missing = Vec::new();
        let placed = labels(&b, &c, &with_labels(&["countries", "cities"]), &[], &mut missing);
        assert!(missing.is_empty(), "{missing:?}");
        let countries = placed.iter().filter(|l| l.layer == "countries").count();
        assert!(countries > 30 && countries <= 400, "{countries}");
        assert!(placed.iter().any(|l| l.layer == "cities" && l.va == "bottom"));
        let ppu = c.px_per_unit();
        let rects: Vec<[f64; 4]> = placed
            .iter()
            .map(|l| {
                let size = if l.layer == "countries" { 9.0 } else { 7.5 };
                estimate_rect((l.x - c.view.x) * ppu, (l.y - c.view.y) * ppu, &l.text, size * l.font_scale * c.px_per_pt)
            })
            .collect();
        for (i, r) in rects.iter().enumerate() {
            assert!(!overlaps_any(r, &rects[..i]), "{} overlaps", placed[i].text);
        }
    }

    #[test]
    fn states_wait_for_their_zoom_and_lambert_labels_stay_in_region() {
        let Some(b) = data() else { return };
        let mut missing = Vec::new();
        let world = labels(&b, &ctx("Robinson", None), &with_labels(&["states"]), &[], &mut missing);
        assert!(world.is_empty());
        let c = ctx("Lambert: Europe", None);
        let placed = labels(&b, &c, &with_labels(&["countries"]), &[], &mut missing);
        assert!(placed.iter().any(|l| l.text == "Russia"), "Russia is labelled where it is drawn");
        assert!(placed.iter().all(|l| c.view.contains([l.x, l.y])));
    }

    #[test]
    fn capitals_only_swaps_the_city_markers() {
        let Some(b) = data() else { return };
        let c = ctx("Equirectangular", Some(Rect { x: -10.0, y: -60.0, w: 40.0, h: 25.0 }));
        let mut s = LayerSettings { points: [("cities".to_string(), true)].into(), ..Default::default() };
        let mut missing = Vec::new();
        let cities = markers(&b, &c, &s, &mut missing);
        s.capitals_only = true;
        let capitals = markers(&b, &c, &s, &mut missing);
        assert!(capitals.iter().all(|m| m.layer == "capitals"));
        assert!(!capitals.is_empty() && capitals.len() < cities.len());
        assert!(missing.is_empty());
    }
}
