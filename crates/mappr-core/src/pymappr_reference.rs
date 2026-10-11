//! Geometry checked against PyMappr's own renderer: view framing, graticule
//! ticks, place labels, point markers, scale bars and insets, to within
//! 0.01 pt on PyMappr's 9 x 6.5 in, 100 dpi test figure. The reference
//! values come from `scripts/pymappr_rendering_reference.py`.

use serde_json::Value;

use crate::basemap::Basemap;
use crate::projection::{Projection, ProjectionSpec};
use crate::render::{LayerSettings, MapContext, Rect};

const REFERENCE: &str = include_str!("../tests/data/pymappr_rendering_reference.json");
/// The match asked for: 0.01 typographic point.
const TOL_PT: f64 = 0.01;

fn reference() -> Value {
    serde_json::from_str(REFERENCE).unwrap()
}

fn data() -> Option<Basemap> {
    let dir = crate::pymappr_dir().join("data");
    Basemap::looks_valid(&dir.join("shapes")).then(|| Basemap::new(dir))
}

fn f(v: &Value) -> f64 {
    v.as_f64().unwrap_or(f64::NAN)
}

fn pair(v: &Value) -> [f64; 2] {
    [f(&v[0]), f(&v[1])]
}

/// One reference case's map: its projection, view and size on screen.
struct Case {
    name: String,
    spec: ProjectionSpec,
    proj: Projection,
    view: Rect,
    px: [f64; 2],
    px_per_pt: f64,
    aspect: f64,
    extent: [f64; 4],
}

impl Case {
    fn new(c: &Value) -> Case {
        let origin = c["origin"].as_array().map(|o| (f(&o[0]), f(&o[1])));
        let name = c["projection"].as_str().unwrap().to_string();
        let spec = ProjectionSpec { name: name.clone(), lon_0: origin.map(|o| o.0), lat_0: origin.map(|o| o.1) };
        let proj = Projection::new(&spec).unwrap();
        let ([x0, x1], [y0, y1]) = (pair(&c["xlim"]), pair(&c["ylim"]));
        let e = &c["extent"];
        Case {
            name,
            spec,
            proj,
            view: Rect::from_bounds([x0.min(x1), x0.max(x1), y0.min(y1), y0.max(y1)]),
            px: pair(&c["px"]),
            px_per_pt: f(&c["px_per_pt"]),
            aspect: f(&c["aspect"]),
            extent: [f(&e[0]), f(&e[1]), f(&e[2]), f(&e[3])],
        }
    }

    fn ctx(&self) -> MapContext {
        MapContext::new(self.proj.clone(), Some(self.view), self.px[0], self.px_per_pt).with_px_height(Some(self.px[1]))
    }

    /// 0.01 pt in map units, horizontally and vertically.
    fn tol(&self) -> (f64, f64) {
        let px = TOL_PT * self.px_per_pt;
        (px * self.view.w / self.px[0], px * self.view.h / self.px[1])
    }

    fn label(&self) -> String {
        format!("{} {:?}", self.name, self.extent)
    }
}

#[test]
fn extent_framing_matches_pymappr() {
    let r = reference();
    let mut failures = Vec::new();
    for c in r["extent"].as_array().unwrap() {
        let case = Case::new(c);
        let got = crate::view::extent_view(&case.proj, case.extent, case.aspect);
        let (tx, ty) = case.tol();
        let want = case.view;
        if (got.x - want.x).abs() > tx
            || (got.w - want.w).abs() > tx
            || (got.y - want.y).abs() > ty
            || (got.h - want.h).abs() > ty
        {
            failures.push(format!("{} aspect {:.4}: got {got:?}, want {want:?}", case.label(), case.aspect));
        }
    }
    assert!(failures.is_empty(), "{} mismatches:\n{}", failures.len(), failures.join("\n"));
}

#[test]
fn graticule_ticks_match_pymappr() {
    let r = reference();
    let mut failures = Vec::new();
    for c in r["ticks"].as_array().unwrap() {
        let case = Case::new(c);
        let step = f(&c["step"]);
        let g = crate::graticule::graticule(&case.ctx(), step, true);
        let (tx, ty) = case.tol();
        let want_x: Vec<(f64, String)> =
            c["x_ticks"].as_array().unwrap().iter().map(|t| (f(&t[0]), t[1].as_str().unwrap().to_string())).collect();
        let want_y: Vec<(f64, String)> =
            c["y_ticks"].as_array().unwrap().iter().map(|t| (-f(&t[0]), t[1].as_str().unwrap().to_string())).collect();
        let mut got_x: Vec<(f64, String)> = g.x_ticks.iter().map(|t| (t.pos, t.text.clone())).collect();
        let mut got_y: Vec<(f64, String)> = g.y_ticks.iter().map(|t| (t.pos, t.text.clone())).collect();
        got_x.sort_by(|a, b| a.0.total_cmp(&b.0));
        got_y.sort_by(|a, b| a.0.total_cmp(&b.0));
        let mut want_y = want_y;
        want_y.sort_by(|a, b| a.0.total_cmp(&b.0));
        let same = |a: &[(f64, String)], b: &[(f64, String)], tol: f64| {
            a.len() == b.len() && a.iter().zip(b).all(|(p, q)| (p.0 - q.0).abs() <= tol && p.1 == q.1)
        };
        if !same(&got_x, &want_x, tx) {
            failures.push(format!("{} x: got {got_x:?}\n   want {want_x:?}", case.label()));
        }
        if !same(&got_y, &want_y, ty) {
            failures.push(format!("{} y: got {got_y:?}\n   want {want_y:?}", case.label()));
        }
    }
    assert!(failures.is_empty(), "{} mismatches:\n{}", failures.len(), failures.join("\n"));
}

fn settings_with(kind: &str, keys: &[Value], capitals: bool) -> LayerSettings {
    let map = keys.iter().map(|k| (k.as_str().unwrap().to_string(), true)).collect();
    let mut s = LayerSettings { capitals_only: capitals, ..Default::default() };
    match kind {
        "labels" => s.labels = map,
        _ => s.points = map,
    }
    s
}

#[test]
fn place_labels_match_pymappr() {
    let Some(b) = data() else { return };
    let r = reference();
    let mut failures = Vec::new();
    for c in r["labels"].as_array().unwrap() {
        let case = Case::new(c);
        let s = settings_with("labels", c["keys"].as_array().unwrap(), c["capitals_only"].as_bool().unwrap());
        let mut missing = Vec::new();
        let got = crate::labels::labels(&b, &case.ctx(), &s, &[], &mut missing);
        let want: Vec<(String, String, f64, f64)> = c["labels"]
            .as_array()
            .unwrap()
            .iter()
            .map(|l| (l[0].as_str().unwrap().into(), l[1].as_str().unwrap().into(), f(&l[2]), -f(&l[3])))
            .collect();
        let (tx, ty) = case.tol();
        let key = |l: &(String, String, f64, f64)| format!("{}|{}", l.0, l.1);
        let got_t: Vec<(String, String, f64, f64)> =
            got.iter().map(|l| (l.layer.clone(), l.text.clone(), l.x, l.y)).collect();
        let missing_labels: Vec<String> = want
            .iter()
            .filter(|w| !got_t.iter().any(|g| key(g) == key(w) && (g.2 - w.2).abs() <= tx && (g.3 - w.3).abs() <= ty))
            .map(|w| format!("{}:{} ({:.4}, {:.4})", w.0, w.1, w.2, w.3))
            .collect();
        let extra: Vec<String> = got_t
            .iter()
            .filter(|g| !want.iter().any(|w| key(g) == key(w) && (g.2 - w.2).abs() <= tx && (g.3 - w.3).abs() <= ty))
            .map(|g| format!("{}:{} ({:.4}, {:.4})", g.0, g.1, g.2, g.3))
            .collect();
        if !missing_labels.is_empty() || !extra.is_empty() {
            failures.push(format!(
                "{}: {} of {} wanted are missing or moved: {:?}\n   {} extra: {:?}",
                case.label(),
                missing_labels.len(),
                want.len(),
                &missing_labels[..missing_labels.len().min(12)],
                extra.len(),
                &extra[..extra.len().min(12)]
            ));
        }
        for (l, w) in got.iter().zip(c["labels"].as_array().unwrap()) {
            let size = crate::catalog::LABEL_STYLES.iter().find(|s| s.key == l.layer).unwrap().fontsize * l.font_scale;
            if l.text == w[1].as_str().unwrap() && (size - f(&w[4])).abs() > 1e-9 {
                failures.push(format!("{}: {} font {size} vs {}", case.label(), l.text, f(&w[4])));
                break;
            }
        }
    }
    assert!(failures.is_empty(), "{} mismatches:\n{}", failures.len(), failures.join("\n"));
}

#[test]
fn point_markers_match_pymappr() {
    let Some(b) = data() else { return };
    let r = reference();
    let mut failures = Vec::new();
    for c in r["markers"].as_array().unwrap() {
        let case = Case::new(c);
        let capitals = c["capitals_only"].as_bool().unwrap();
        let s = settings_with("points", c["keys"].as_array().unwrap(), capitals);
        let mut missing = Vec::new();
        let got = crate::labels::markers(&b, &case.ctx(), &s, &mut missing);
        let (tx, ty) = case.tol();
        for (key, pts) in c["markers"].as_object().unwrap() {
            let layer = if key == "cities" && capitals { "capitals" } else { key.as_str() };
            let want: Vec<[f64; 2]> = pts.as_array().unwrap().iter().map(|p| [f(&p[0]), -f(&p[1])]).collect();
            let mine: Vec<[f64; 2]> = got.iter().filter(|m| m.layer == layer).map(|m| [m.x, m.y]).collect();
            let unmatched = want.iter().filter(|w| !mine.iter().any(|g| (g[0] - w[0]).abs() <= tx && (g[1] - w[1]).abs() <= ty)).count();
            if unmatched > 0 || mine.len() != want.len() {
                failures.push(format!("{} {key}: {} of {} unmatched, got {}", case.label(), unmatched, want.len(), mine.len()));
            }
        }
    }
    assert!(failures.is_empty(), "{} mismatches:\n{}", failures.len(), failures.join("\n"));
}

#[test]
fn scale_bars_match_pymappr() {
    let r = reference();
    let mut failures = Vec::new();
    for c in r["scale_bar"].as_array().unwrap() {
        let case = Case::new(c);
        let opts: crate::overlays::ScaleBarOptions = serde_json::from_value(c["options"].clone()).unwrap();
        let got = crate::overlays::scale_bar(&case.proj, case.view, &opts);
        let want_bars = c["bars"].as_array().unwrap();
        let want_labels: Vec<&str> = c["labels"].as_array().unwrap().iter().map(|l| l.as_str().unwrap()).collect();
        let note = c["note"].as_str();
        // Axes fractions: 0.01 pt of the map box.
        let (fx, fy) = (TOL_PT * case.px_per_pt / case.px[0], TOL_PT * case.px_per_pt / case.px[1]);
        let mut ok = got.error.as_deref() == note && got.bars.len() == want_bars.len();
        for (g, w) in got.bars.iter().zip(want_bars) {
            ok &= (g.x - f(&w[0])).abs() <= fx
                && (g.y - f(&w[1])).abs() <= fy
                && (g.width - f(&w[2])).abs() <= fx
                && g.segments as f64 == f(&w[3]);
        }
        let labels: Vec<&str> = got.bars.iter().map(|b| b.label.as_str()).collect();
        ok &= labels == want_labels;
        if !ok {
            failures.push(format!(
                "{} {}: got {:?} {:?}\n   want {:?} {want_labels:?} {note:?}",
                case.label(),
                c["options"],
                got.bars.iter().map(|b| [b.x, b.y, b.width]).collect::<Vec<_>>(),
                got.error,
                want_bars
            ));
        }
    }
    assert!(failures.is_empty(), "{} mismatches:\n{}", failures.len(), failures.join("\n"));
}

#[test]
fn insets_match_pymappr() {
    let Some(b) = data() else { return };
    let r = reference();
    let mut failures = Vec::new();
    for c in r["inset"].as_array().unwrap() {
        let case = Case::new(c);
        let options: crate::regions::InsetOptions = serde_json::from_value(c["options"].clone()).unwrap();
        let scale_bar = (!c["scale_bar"].is_null()).then(|| serde_json::from_value(c["scale_bar"].clone()).unwrap());
        let req = crate::inset::InsetRequest {
            projection: case.spec.clone(),
            view: case.view,
            px_width: case.px[0],
            px_height: Some(case.px[1]),
            px_per_pt: case.px_per_pt,
            options,
            scale_bar,
            points: Vec::new(),
        };
        let got = crate::inset::render_inset(&b, &req).unwrap();
        let mut errors = Vec::new();
        let (fx, fy) = (TOL_PT * case.px_per_pt / case.px[0], TOL_PT * case.px_per_pt / case.px[1]);
        let rect: Vec<f64> = c["rect"].as_array().unwrap().iter().map(f).collect();
        let g = got.rect;
        if (g.x - rect[0]).abs() > fx || (g.w - rect[2]).abs() > fx || (g.y - rect[1]).abs() > fy || (g.h - rect[3]).abs() > fy {
            errors.push(format!("rect {g:?} vs {rect:?}"));
        }
        let limits: Vec<f64> = c["limits"].as_array().unwrap().iter().map(f).collect();
        let want_view = Rect::from_bounds([limits[0], limits[1], limits[2], limits[3]]);
        // 0.01 pt of the inset box.
        let (lx, ly) = (
            TOL_PT * case.px_per_pt * want_view.w / (rect[2] * case.px[0]),
            TOL_PT * case.px_per_pt * want_view.h / (rect[3] * case.px[1]),
        );
        let v = got.view;
        if (v.x - want_view.x).abs() > lx || (v.w - want_view.w).abs() > lx || (v.y - want_view.y).abs() > ly || (v.h - want_view.h).abs() > ly {
            errors.push(format!("limits {v:?} vs {want_view:?}"));
        }
        let p = &c["inset_projection"];
        if got.projection.name != p[0].as_str().unwrap() {
            errors.push(format!("projection {} vs {}", got.projection.name, p[0]));
        }
        let target = c["box"]["target"].as_str().map(|t| if t == "main" { "map" } else { t });
        if got.box_.on != target {
            errors.push(format!("box {:?} vs {target:?}", got.box_.on));
        }
        if !errors.is_empty() {
            failures.push(format!("{} {}: {}", case.label(), c["options"]["region"], errors.join("; ")));
        }
    }
    assert!(failures.is_empty(), "{} mismatches:\n{}", failures.len(), failures.join("\n"));
}
