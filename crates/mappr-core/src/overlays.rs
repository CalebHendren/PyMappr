//! The scale bar, laid out as PyMappr does (`renderer/overlays.py`,
//! `styling/decorations.py`): each unit gets its own round length,
//! measured on the WGS84 ellipsoid on the row the bar is drawn on and
//! refined against the bar's own ends, or a reason why no honest bar fits.

use serde::{Deserialize, Serialize};

use crate::projection::Projection;
use crate::render::Rect;
use crate::view::ground_distance;

pub const METRES_PER_MILE: f64 = 1609.344;
/// Round numbers a bar may show.
const NICE: [f64; 4] = [1.0, 2.0, 3.0, 5.0];
const BAR_HEIGHT: f64 = 0.011;
const BAR_GAP: f64 = 0.005;
/// Room one label row needs, so a stack can be lifted clear of the frame.
const LABEL_ROOM: f64 = 0.030;

/// The scale bar's options, as in the project's `map.scale_bar`.
#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
pub struct ScaleBarOptions {
    pub show: bool,
    pub units: String,
    pub position: String,
    pub style: String,
    pub length_mode: String,
    pub fixed_length: Option<f64>,
    pub segments: i64,
    pub width: f64,
    pub fontsize: f64,
    pub color: String,
    pub draggable: bool,
    pub anchor_x: Option<f64>,
    pub anchor_y: Option<f64>,
}

impl Default for ScaleBarOptions {
    fn default() -> Self {
        ScaleBarOptions {
            show: false,
            units: "km".into(),
            position: "lower left".into(),
            style: "segmented".into(),
            length_mode: "auto".into(),
            fixed_length: None,
            segments: 4,
            width: 0.22,
            fontsize: 8.0,
            color: "#1a1a1a".into(),
            draggable: false,
            anchor_x: None,
            anchor_y: None,
        }
    }
}

impl ScaleBarOptions {
    fn anchor(&self) -> Option<(f64, f64)> {
        Some((self.anchor_x?, self.anchor_y?))
    }

    fn units_shown(&self) -> Vec<&'static str> {
        match self.units.as_str() {
            "both" => vec!["km", "mi"],
            "mi" => vec!["mi"],
            _ => vec!["km"],
        }
    }
}

/// One bar in axes fractions (0..1 from the left and bottom).
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Bar {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub label: String,
    pub units: String,
    pub segments: u32,
}

#[derive(Debug, Clone, Serialize, Default)]
pub struct ScaleBar {
    pub bars: Vec<Bar>,
    /// Why no bar could be drawn, for the status line.
    pub error: Option<String>,
}

/// Metres in one unit ("both" measures in km).
pub fn unit_metres(units: &str) -> f64 {
    if units == "mi" { METRES_PER_MILE } else { 1000.0 }
}

/// The axes-fraction point a decoration in `corner` is anchored to.
pub fn corner_anchor(corner: &str, pad: f64) -> (f64, f64) {
    let corner = match corner {
        "lower left" | "lower right" | "upper left" | "upper right" => corner,
        _ => "lower left",
    };
    let x = if corner.ends_with("left") { pad } else { 1.0 - pad };
    let y = if corner.starts_with("lower") { pad } else { 1.0 - pad };
    (x, y)
}

/// A round bar length in metres, at or just below `metres`.
pub fn nice_length(metres: f64, units: &str) -> f64 {
    let per_unit = unit_metres(units);
    let value = metres / per_unit;
    if !value.is_finite() || value <= 0.0 {
        return 0.0;
    }
    let decade = 10f64.powf(value.log10().floor());
    for candidate in NICE.iter().rev() {
        if candidate * decade <= value {
            return candidate * decade * per_unit;
        }
    }
    NICE[3] * decade / 10.0 * per_unit
}

/// Python's `%g` (`digits` significant digits), enough for bar labels.
fn fmt_g(v: f64, digits: usize) -> String {
    if v == 0.0 {
        return "0".into();
    }
    let exp = v.abs().log10().floor() as i32;
    if exp < -4 || exp >= digits as i32 {
        let s = format!("{:.*e}", digits - 1, v);
        let (m, e) = s.split_once('e').unwrap();
        let m = if m.contains('.') { m.trim_end_matches('0').trim_end_matches('.') } else { m };
        let e: i32 = e.parse().unwrap();
        return format!("{m}e{}{:02}", if e < 0 { '-' } else { '+' }, e.abs());
    }
    let decimals = (digits as i32 - 1 - exp).max(0) as usize;
    let s = format!("{v:.decimals$}");
    if s.contains('.') { s.trim_end_matches('0').trim_end_matches('.').to_string() } else { s }
}

/// A bar's label, e.g. "500 km"; metric bars under a kilometre in metres.
pub fn format_length(metres: f64, units: &str) -> String {
    if units != "mi" && metres < 1000.0 {
        return format!("{} m", fmt_g(metres, 6));
    }
    let value = metres / unit_metres(units);
    let text = if value >= 1.0 { fmt_g(value, 6) } else { fmt_g(value, 3) };
    format!("{text} {}", if units == "mi" { "mi" } else { "km" })
}

/// The map's scale in a view, measured in axes fractions.
struct Measure<'a> {
    proj: &'a Projection,
    view: [f64; 4],
}

impl Measure<'_> {
    fn to_data(&self, fx: f64, fy: f64) -> [f64; 2] {
        let [x0, x1, y0, y1] = self.view;
        [x0 + (x1 - x0) * fx, y0 + (y1 - y0) * fy]
    }

    /// Ground metres between two axes-fraction x positions on row `fy`.
    fn span(&self, fx0: f64, fx1: f64, fy: f64) -> f64 {
        ground_distance(self.proj, self.to_data(fx0, fy), self.to_data(fx1, fy))
    }

    /// A row where the scale can be measured: the bar's own, else stepping
    /// towards the middle of the view.
    fn reference_row(&self, fy: f64) -> f64 {
        let mut rows = vec![fy];
        rows.extend([0.25, 0.5, 0.75, 1.0].iter().map(|s| fy + (0.5 - fy) * s));
        rows.into_iter().find(|&row| self.span(0.45, 0.55, row).is_finite()).unwrap_or(0.5)
    }

    /// Ground metres per unit of axes x-fraction near `fx` (a first guess).
    fn estimate(&self, fx: f64, fy: f64) -> f64 {
        let left = (fx - 0.05).clamp(0.0, 0.9);
        let mut metres = self.span(left, left + 0.1, fy);
        if !metres.is_finite() || metres <= 0.0 {
            metres = self.span(0.45, 0.55, fy);
        }
        if !metres.is_finite() || metres <= 0.0 {
            return f64::NAN;
        }
        metres / 0.1
    }

    /// The width a bar of `metres` needs, refined against its own ends up
    /// to six times, or `None` when no honest bar of that length fits.
    fn fit_width(&self, metres: f64, x: f64, row: f64, right_anchored: bool) -> Option<f64> {
        let per = self.estimate(x, row);
        if !per.is_finite() || per <= 0.0 {
            return None;
        }
        let mut width = metres / per;
        for _ in 0..6 {
            if !width.is_finite() || width <= 0.0 || width > 0.95 {
                return None;
            }
            let x0 = if right_anchored { x - width } else { x };
            let mut actual = self.span(x0, x0 + width, row);
            if !actual.is_finite() || actual <= 0.0 {
                actual = self.span(0.5 - width / 2.0, 0.5 + width / 2.0, row);
            }
            if !actual.is_finite() || actual <= 0.0 {
                break;
            }
            let adjust = metres / actual;
            if (adjust - 1.0).abs() < 0.001 {
                break;
            }
            width *= adjust;
        }
        (width.is_finite() && width > 0.0 && width <= 0.95).then_some(width)
    }
}

const CANNOT_MEASURE: &str = "Scale bar: the map scale cannot be measured at this view.";
const VARIES: &str = "Scale bar: scale varies too much across this view to draw an accurate bar - zoom in, or move the bar away from the poles.";

/// The scale bar for a view (SVG coordinates).
pub fn scale_bar(proj: &Projection, view: Rect, opts: &ScaleBarOptions) -> ScaleBar {
    if !opts.show {
        return ScaleBar::default();
    }
    let m = Measure { proj, view: view.bounds() };
    let units = opts.units_shown();
    let dragged = opts.anchor().is_some();
    let (x, y) = opts.anchor().unwrap_or_else(|| corner_anchor(&opts.position, 0.03));
    let right_anchored = x > 0.5 && !dragged;
    let top_anchored = y > 0.5 && !dragged;
    let n = units.len() as f64;
    let stack = n * BAR_HEIGHT + (n - 1.0) * BAR_GAP;
    let mut base_y = if top_anchored { y - stack } else { y };
    if units.len() > 1 && !top_anchored && !dragged {
        base_y += LABEL_ROOM;
    }
    let last = units.len() - 1;
    let segments = if opts.style == "segmented" { opts.segments.max(1) as u32 } else { 1 };
    let mut bars = Vec::new();
    for (i, unit) in units.iter().enumerate() {
        let y0 = base_y + (last - i) as f64 * (BAR_HEIGHT + BAR_GAP);
        let row = m.reference_row(y0 + BAR_HEIGHT / 2.0);
        let metres = match opts.fixed_length {
            Some(len) if i == 0 && opts.length_mode == "fixed" && len != 0.0 => len * unit_metres(&opts.units),
            _ => {
                let estimate = m.estimate(x, row);
                if !estimate.is_finite() || estimate <= 0.0 {
                    return ScaleBar { bars: Vec::new(), error: Some(CANNOT_MEASURE.into()) };
                }
                nice_length(estimate * opts.width, unit)
            }
        };
        if metres <= 0.0 {
            return ScaleBar::default();
        }
        let Some(width) = m.fit_width(metres, x, row, right_anchored) else {
            return ScaleBar { bars: Vec::new(), error: Some(VARIES.into()) };
        };
        let x0 = if right_anchored { x - width } else { x };
        bars.push(Bar { x: x0, y: y0, width, label: format_length(metres, unit), units: unit.to_string(), segments });
    }
    ScaleBar { bars, error: None }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::projection::{GLOBE, ProjectionSpec};
    use crate::view::extent_view;

    const AFRICA: [f64; 4] = [-20.0, 55.0, -38.0, 40.0];
    const ASPECT: f64 = (6.5 * (0.988 - 0.012)) / (9.0 * (0.99 - 0.01));

    fn setup(name: &str, extent: [f64; 4]) -> (Projection, Rect) {
        let proj = Projection::new(&ProjectionSpec { name: name.into(), lon_0: None, lat_0: None }).unwrap();
        let view = extent_view(&proj, extent, ASPECT);
        (proj, view)
    }

    fn on() -> ScaleBarOptions {
        ScaleBarOptions { show: true, ..Default::default() }
    }

    fn claimed(label: &str) -> f64 {
        let (n, unit) = label.split_once(' ').unwrap();
        let n: f64 = n.parse().unwrap();
        match unit {
            "km" => n * 1000.0,
            "mi" => n * METRES_PER_MILE,
            _ => n,
        }
    }

    fn measured(proj: &Projection, view: Rect, bar: &Bar) -> f64 {
        let m = Measure { proj, view: view.bounds() };
        m.span(bar.x, bar.x + bar.width, bar.y + BAR_HEIGHT / 2.0)
    }

    #[test]
    fn nice_length_is_round_and_never_longer_than_asked() {
        for metres in [55.0, 300.0, 1234.0, 137_000.0, 999_999.0, 4.2e6, 3.0e7] {
            for units in ["km", "mi"] {
                let chosen = nice_length(metres, units);
                assert!(chosen > 0.0 && chosen <= metres);
                let mut mantissa = chosen / unit_metres(units);
                mantissa /= 10f64.powf(mantissa.log10().floor());
                let r = (mantissa * 1e6).round() / 1e6;
                assert!([1.0, 2.0, 3.0, 5.0].contains(&r), "{metres} {units}: {r}");
            }
        }
    }

    #[test]
    fn a_metric_bar_under_a_kilometre_is_labelled_in_metres() {
        assert_eq!(format_length(500.0, "km"), "500 m");
        assert_eq!(format_length(2_000_000.0, "km"), "2000 km");
        assert_eq!(format_length(1609.344, "mi"), "1 mi");
        assert_eq!(format_length(0.5 * METRES_PER_MILE, "mi"), "0.5 mi");
    }

    #[test]
    fn corner_anchor_maps_each_corner_to_its_own_quadrant() {
        assert_eq!(corner_anchor("lower left", 0.03), (0.03, 0.03));
        assert_eq!(corner_anchor("upper right", 0.03), (0.97, 0.97));
        assert_eq!(corner_anchor("nowhere", 0.03), corner_anchor("lower left", 0.03));
    }

    #[test]
    fn the_drawn_bar_is_the_length_its_label_claims() {
        for name in ["Equirectangular", "Mercator", "Lambert: N. America"] {
            for position in ["lower left", "upper right"] {
                let (proj, view) = setup(name, AFRICA);
                let bar = scale_bar(&proj, view, &ScaleBarOptions { position: position.into(), ..on() });
                assert!(bar.error.is_none(), "{name} {position}: {:?}", bar.error);
                let b = &bar.bars[0];
                let got = measured(&proj, view, b);
                assert!((got / claimed(&b.label) - 1.0).abs() < 0.01, "{name} {position}: {got} vs {}", b.label);
            }
        }
    }

    #[test]
    fn zooming_in_shortens_the_bar_monotonically() {
        let (proj, mut view) = setup("Equirectangular", AFRICA);
        let mut lengths = Vec::new();
        for _ in 0..4 {
            let bar = scale_bar(&proj, view, &on());
            lengths.push(measured(&proj, view, &bar.bars[0]));
            let (cx, cy) = (view.x + view.w / 2.0, view.y + view.h / 2.0);
            view = Rect { x: cx - view.w / 8.0, y: cy - view.h / 8.0, w: view.w / 4.0, h: view.h / 4.0 };
        }
        assert!(lengths.windows(2).all(|w| w[0] > w[1]), "{lengths:?}");
        assert!(lengths[0] > lengths[3] * 10.0);
    }

    #[test]
    fn each_unit_of_a_both_bar_gets_its_own_round_length() {
        let (proj, view) = setup("Equirectangular", AFRICA);
        let bar = scale_bar(&proj, view, &ScaleBarOptions { units: "both".into(), ..on() });
        let labels: Vec<&str> = bar.bars.iter().map(|b| b.label.as_str()).collect();
        assert_eq!(labels, ["2000 km", "1000 mi"]);
        assert!((measured(&proj, view, &bar.bars[0]) / 2e6 - 1.0).abs() < 0.01);
        assert!((measured(&proj, view, &bar.bars[1]) / (1000.0 * METRES_PER_MILE) - 1.0).abs() < 0.01);
        // The lower label sits under its bar: the stack is lifted clear.
        assert!(bar.bars[1].y - 0.012 > 0.0);
        assert!(bar.bars[0].y > bar.bars[1].y);
    }

    #[test]
    fn fixed_lengths_are_honoured_or_refused_with_a_reason() {
        let (proj, view) = setup("Equirectangular", AFRICA);
        let fixed = |len| ScaleBarOptions { length_mode: "fixed".into(), fixed_length: Some(len), ..on() };
        let bar = scale_bar(&proj, view, &fixed(750.0));
        assert_eq!(bar.bars[0].label, "750 km");
        assert!((measured(&proj, view, &bar.bars[0]) / 750_000.0 - 1.0).abs() < 0.01);
        let bar = scale_bar(&proj, view, &fixed(500_000.0));
        assert!(bar.bars.is_empty());
        assert!(bar.error.unwrap().contains("scale varies"));
    }

    #[test]
    fn plain_and_segmented_bars() {
        let (proj, view) = setup("Equirectangular", AFRICA);
        assert_eq!(scale_bar(&proj, view, &ScaleBarOptions { style: "plain".into(), ..on() }).bars[0].segments, 1);
        assert_eq!(scale_bar(&proj, view, &on()).bars[0].segments, 4);
        assert!(scale_bar(&proj, view, &ScaleBarOptions::default()).bars.is_empty());
    }

    #[test]
    fn a_bar_is_drawn_or_explained_on_every_projection() {
        for name in ["Equirectangular", "Mercator", "Lambert: N. America", "Robinson", "Mollweide", "Winkel Tripel", GLOBE] {
            let (proj, view) = setup(name, AFRICA);
            let bar = scale_bar(&proj, view, &on());
            assert!(!bar.bars.is_empty() || bar.error.is_some(), "{name}");
        }
    }

    /// PyMappr refuses a bar on a whole Winkel Tripel world because pyproj
    /// wraps the off-map corner's longitude and the bar's measurement goes
    /// wrong. Here the corner has no lon/lat, so the bar is measured on the
    /// nearest row that is on the map, as PyMappr does on Robinson.
    #[test]
    fn a_world_view_is_measured_where_the_map_is() {
        let (proj, view) = setup("Winkel Tripel", [-180.0, 180.0, -90.0, 90.0]);
        let bar = scale_bar(&proj, view, &on());
        assert!(bar.error.is_some() || bar.bars[0].width <= 0.95);
        let (proj, view) = setup("Mercator", [-180.0, 180.0, -85.0, 85.0]);
        let bar = scale_bar(&proj, view, &ScaleBarOptions { length_mode: "fixed".into(), fixed_length: Some(20_000.0), ..on() });
        assert!(bar.error.unwrap().contains("zoom in"));
    }
}
