//! The settings dataclasses (`LegendOptions`, `ScaleBarOptions`,
//! `CompassOptions`, `InsetOptions`) as PyMappr reads them back from a
//! stored dict: unknown keys dropped, missing or unreadable values
//! defaulted, the rest coerced to the field's type (`values_from_dict`).
//!
//! The coercion matters for the scripts as well as for correctness: the
//! webview's JSON cannot tell `30` from `30.0`, but PyMappr prints a float
//! field as `30.0` whatever was stored.

use serde_json::Value;

use crate::lit::{Lit, float_repr, py, py_strip};
use crate::tables::json_lit;

#[derive(Clone, Copy, PartialEq)]
pub enum Kind {
    Bool,
    Int,
    Float,
    Str,
    OptFloat,
    OptStr,
}

/// Python's `float(text)`.
pub fn parse_py_float(text: &str) -> Option<f64> {
    let t = py_strip(text);
    if t.is_empty() {
        return None;
    }
    let cleaned: String = if t.contains('_') {
        let bytes: Vec<char> = t.chars().collect();
        for (i, c) in bytes.iter().enumerate() {
            if *c == '_' {
                let ok = i > 0
                    && i + 1 < bytes.len()
                    && bytes[i - 1].is_ascii_digit()
                    && bytes[i + 1].is_ascii_digit();
                if !ok {
                    return None;
                }
            }
        }
        t.replace('_', "")
    } else {
        t.to_string()
    };
    cleaned.parse::<f64>().ok()
}

/// Python's `float(value)` on a JSON value.
pub fn py_float(value: &Value) -> Option<f64> {
    match value {
        Value::Number(n) => n.as_f64(),
        Value::Bool(b) => Some(f64::from(u8::from(*b))),
        Value::String(s) => parse_py_float(s),
        _ => None,
    }
}

/// PyMappr's `_num(value, fallback)`.
pub fn num(value: Option<&Value>, fallback: f64) -> f64 {
    value.and_then(py_float).unwrap_or(fallback)
}

/// Python's `str(value)` on a JSON value.
pub fn py_str(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::String(s) => s.clone(),
        Value::Number(n) => match json_lit(value) {
            Lit::Int(i) => i.to_string(),
            _ => float_repr(n.as_f64().unwrap_or(f64::NAN)),
        },
        other => py(&json_lit(other)),
    }
}

/// Python's `bool(value)` on a JSON value.
pub fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// `coerce_value`: the value as its field's type, or None to keep the default.
pub fn coerce(value: &Value, kind: Kind) -> Option<Lit> {
    if value.is_null() {
        return matches!(kind, Kind::OptFloat | Kind::OptStr).then_some(Lit::None);
    }
    match kind {
        Kind::Bool => Some(Lit::Bool(match value {
            Value::String(s) => matches!(py_strip(s).to_lowercase().as_str(), "1" | "true" | "yes" | "on"),
            other => truthy(other),
        })),
        Kind::Int => py_float(value).filter(|f| f.is_finite()).map(|f| Lit::Int(f.trunc() as i64)),
        Kind::Float | Kind::OptFloat => py_float(value).map(Lit::Float),
        Kind::Str | Kind::OptStr => Some(Lit::Str(py_str(value))),
    }
}

/// An options dataclass's values, in field order.
#[derive(Debug, Clone)]
pub struct Options(pub Vec<(&'static str, Lit)>);

impl Options {
    pub fn from_value(fields: &[(&'static str, Kind, Lit)], data: Option<&Value>) -> Self {
        let map = data.and_then(Value::as_object);
        Options(
            fields
                .iter()
                .map(|(name, kind, default)| {
                    let value = map.and_then(|m| m.get(*name)).and_then(|v| coerce(v, *kind));
                    (*name, value.unwrap_or_else(|| default.clone()))
                })
                .collect(),
        )
    }

    pub fn get(&self, name: &str) -> &Lit {
        self.0.iter().find(|(n, _)| *n == name).map(|(_, v)| v).unwrap_or(&Lit::None)
    }

    pub fn set(&mut self, name: &str, value: Lit) {
        if let Some(slot) = self.0.iter_mut().find(|(n, _)| *n == name) {
            slot.1 = value;
        }
    }

    pub fn str(&self, name: &str) -> &str {
        self.get(name).as_str().unwrap_or("")
    }

    pub fn opt_str(&self, name: &str) -> Option<&str> {
        self.get(name).as_str()
    }

    pub fn f64(&self, name: &str) -> f64 {
        self.get(name).as_f64().unwrap_or(0.0)
    }

    pub fn opt_f64(&self, name: &str) -> Option<f64> {
        self.get(name).as_f64()
    }

    pub fn bool(&self, name: &str) -> bool {
        self.get(name).truthy()
    }

    pub fn to_lit(&self) -> Lit {
        Lit::Dict(self.0.iter().map(|(k, v)| (Lit::str(*k), v.clone())).collect())
    }
}

fn b(v: bool) -> Lit {
    Lit::Bool(v)
}
fn fl(v: f64) -> Lit {
    Lit::Float(v)
}
fn st(v: &str) -> Lit {
    Lit::str(v)
}

pub const NEUTRAL_MARKER_COLOR: &str = "#555555";

pub fn legend_fields() -> Vec<(&'static str, Kind, Lit)> {
    use Kind::*;
    vec![
        ("show", Bool, b(true)),
        ("title", OptStr, Lit::None),
        ("show_title", Bool, b(true)),
        ("location", Str, st("best")),
        ("hierarchy", Str, st("auto")),
        ("order", Str, st("data")),
        ("counts", Bool, b(false)),
        ("count_format", Str, st("(n)")),
        ("blank_label", Str, st("(blank)")),
        ("section_titles", Bool, b(true)),
        ("title_separator", Str, st(" / ")),
        ("dataset_prefix", Bool, b(true)),
        ("empty_groups", Bool, b(false)),
        ("indent", Int, Lit::Int(3)),
        ("bold_groups", Bool, b(true)),
        ("group_spacer", Bool, b(true)),
        ("group_swatch", Str, st("circle")),
        ("symbol_swatch_color", Str, st(NEUTRAL_MARKER_COLOR)),
        ("columns", Int, Lit::Int(1)),
        ("label_spacing", Float, fl(0.5)),
        ("column_spacing", Float, fl(2.0)),
        ("handle_text_pad", OptFloat, Lit::None),
        ("handle_length", Float, fl(2.0)),
        ("border_pad", Float, fl(0.4)),
        ("marker_scale", Float, fl(1.0)),
        ("frame", Bool, b(true)),
        ("frame_color", Str, st("#ffffff")),
        ("frame_alpha", Float, fl(0.85)),
        ("frame_edge_color", Str, st("#cccccc")),
        ("frame_width", Float, fl(0.8)),
        ("rounded", Bool, b(true)),
        ("shadow", Bool, b(false)),
        ("fontsize", Float, fl(8.0)),
        ("title_fontsize", Float, fl(9.0)),
        ("font_family", Str, st("")),
        ("label_color", Str, st("#000000")),
        ("title_color", Str, st("#000000")),
        ("label_bold", Bool, b(false)),
        ("label_italic", Bool, b(false)),
        ("label_underline", Bool, b(false)),
        ("title_bold", Bool, b(true)),
        ("title_italic", Bool, b(false)),
        ("title_underline", Bool, b(false)),
        ("title_align", Str, st("center")),
    ]
}

pub fn scale_bar_fields() -> Vec<(&'static str, Kind, Lit)> {
    use Kind::*;
    vec![
        ("show", Bool, b(false)),
        ("units", Str, st("km")),
        ("position", Str, st("lower left")),
        ("style", Str, st("segmented")),
        ("length_mode", Str, st("auto")),
        ("fixed_length", OptFloat, Lit::None),
        ("segments", Int, Lit::Int(4)),
        ("width", Float, fl(0.22)),
        ("fontsize", Float, fl(8.0)),
        ("color", Str, st("#1a1a1a")),
        ("draggable", Bool, b(false)),
        ("anchor_x", OptFloat, Lit::None),
        ("anchor_y", OptFloat, Lit::None),
    ]
}

pub fn compass_fields() -> Vec<(&'static str, Kind, Lit)> {
    use Kind::*;
    vec![
        ("show", Bool, b(false)),
        ("position", Str, st("upper right")),
        ("style", Str, st("arrow")),
        ("size", Float, fl(1.0)),
        ("color", Str, st("#1a1a1a")),
    ]
}

pub fn inset_fields() -> Vec<(&'static str, Kind, Lit)> {
    use Kind::*;
    vec![
        ("show", Bool, b(false)),
        ("position", Str, st("lower right")),
        ("size", Float, fl(0.3)),
        ("region", Str, st("state")),
        ("zoom_out", Float, fl(6.0)),
        ("lon_min", OptFloat, Lit::None),
        ("lon_max", OptFloat, Lit::None),
        ("lat_min", OptFloat, Lit::None),
        ("lat_max", OptFloat, Lit::None),
        ("projection", Str, st("same")),
        ("countries", Bool, b(true)),
        ("states", Bool, b(false)),
        ("counties", Bool, b(false)),
        ("land", Bool, b(true)),
        ("ocean", Str, st("none")),
        ("points", Bool, b(true)),
        ("box", Bool, b(true)),
        ("box_color", Str, st("#d62728")),
        ("draggable", Bool, b(false)),
        ("anchor_x", OptFloat, Lit::None),
        ("anchor_y", OptFloat, Lit::None),
    ]
}

/// LegendOptions with the helpers layout needs.
pub type Legend = Options;

impl Options {
    pub fn legend(data: Option<&Value>) -> Legend {
        Options::from_value(&legend_fields(), data)
    }

    pub fn legend_default() -> Legend {
        Options::from_value(&legend_fields(), None)
    }

    pub fn orders_by_count(&self) -> bool {
        matches!(self.str("order"), "count_desc" | "count_asc")
    }

    pub fn pad_for(&self, sectioned: bool) -> f64 {
        match self.opt_f64("handle_text_pad") {
            Some(p) => p,
            None if sectioned => 0.4,
            None => 0.8,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn coerces_like_values_from_dict() {
        let legend = Options::legend(Some(&json!({
            "fontsize": "9", "columns": "2", "counts": "false", "frame": "yes",
            "title": 5, "marker_scale": 1, "unknown": 1, "indent": 2.9, "label_spacing": "x",
            "handle_text_pad": null, "show": null,
        })));
        assert_eq!(legend.get("fontsize"), &Lit::Float(9.0));
        assert_eq!(legend.get("columns"), &Lit::Int(2));
        assert_eq!(legend.get("counts"), &Lit::Bool(false));
        assert_eq!(legend.get("frame"), &Lit::Bool(true));
        assert_eq!(legend.get("title"), &Lit::str("5"));
        assert_eq!(legend.get("marker_scale"), &Lit::Float(1.0));
        assert_eq!(legend.get("indent"), &Lit::Int(2));
        assert_eq!(legend.get("label_spacing"), &Lit::Float(0.5));
        assert_eq!(legend.get("show"), &Lit::Bool(true));
        assert_eq!(legend.0.len(), legend_fields().len());
    }

    #[test]
    fn python_float_parsing() {
        assert_eq!(parse_py_float(" 1_000.5 "), Some(1000.5));
        assert_eq!(parse_py_float("1__0"), None);
        assert_eq!(parse_py_float("-Infinity"), Some(f64::NEG_INFINITY));
        assert!(parse_py_float("nan").unwrap().is_nan());
        assert_eq!(parse_py_float(""), None);
    }
}
