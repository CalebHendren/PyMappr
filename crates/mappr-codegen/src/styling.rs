//! Point styles and the rules that assign them (PyMappr's
//! `pymappr/styling/styles.py`), as far as the code export needs them.

use indexmap::{IndexMap, IndexSet};
use serde_json::Value;

use crate::data::{Entry, Override};
use crate::lit::Lit;
use crate::options::{py_float, py_str, truthy};

pub const OPEN_SUFFIX: &str = " (open)";
pub const OPEN_FILL: &str = "#ffffff";
const OPEN_LIGHT_OUTLINE: &str = "#000000";
const OPEN_LIGHT_LUMINANCE: f64 = 0.85;

const BASE_MARKERS: [(&str, &str); 15] = [
    ("Circle", "o"),
    ("Square", "s"),
    ("Triangle", "^"),
    ("Triangle down", "v"),
    ("Triangle left", "<"),
    ("Triangle right", ">"),
    ("Diamond", "D"),
    ("Thin diamond", "d"),
    ("Star", "*"),
    ("Plus", "P"),
    ("X", "X"),
    ("Pentagon", "p"),
    ("Hexagon", "h"),
    ("Octagon", "8"),
    ("Dot", "."),
];

pub const MARKER_CYCLE: [&str; 14] = [
    "Circle",
    "Square",
    "Triangle",
    "Diamond",
    "Star",
    "Plus",
    "X",
    "Pentagon",
    "Triangle down",
    "Hexagon",
    "Thin diamond",
    "Triangle left",
    "Octagon",
    "Triangle right",
];

pub const DEFAULT_PALETTE: [&str; 10] =
    ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f"];
const OKABE_ITO: [&str; 8] = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9", "#f0e442", "#000000"];
const BLACK_AND_WHITE: [&str; 3] = ["#000000", "#ffffff", "#808080"];

pub const POINT_EDGE_COLOR: &str = "#ffffff";
pub const POINT_EDGE_WIDTH: f64 = 0.5;

/// `palette_for`: the palette a name refers to, else the default.
pub fn palette_for(name: Option<&str>) -> Vec<String> {
    let colors: &[&str] = match name.unwrap_or("") {
        "Colourblind safe (Okabe-Ito)" => &OKABE_ITO,
        "Black & white" => &BLACK_AND_WHITE,
        _ => &DEFAULT_PALETTE,
    };
    colors.iter().map(|c| c.to_string()).collect()
}

/// matplotlib marker code for a PyMappr marker name.
pub fn mpl_marker(name: &str) -> &'static str {
    let base = name.strip_suffix(OPEN_SUFFIX).unwrap_or(name);
    BASE_MARKERS.iter().find(|(n, _)| *n == base).map_or("o", |(_, m)| m)
}

#[derive(Debug, Clone, PartialEq)]
pub struct PointStyle {
    pub color: String,
    pub marker: String,
    pub size: f64,
    pub fill: Option<String>,
}

impl Default for PointStyle {
    fn default() -> Self {
        PointStyle { color: "#d62728".into(), marker: "Circle".into(), size: 30.0, fill: None }
    }
}

impl PointStyle {
    pub fn new(color: &str, marker: &str) -> Self {
        PointStyle { color: color.into(), marker: marker.into(), ..Default::default() }
    }

    pub fn is_open(&self) -> bool {
        self.marker.ends_with(OPEN_SUFFIX)
    }

    /// Whether `MARKERS` knows the name (`mpl_marker` falls back to "o").
    pub fn mpl_marker(&self) -> &'static str {
        let known = BASE_MARKERS
            .iter()
            .any(|(n, _)| *n == self.marker || format!("{n}{OPEN_SUFFIX}") == self.marker);
        if known { mpl_marker(&self.marker) } else { "o" }
    }

    /// `_style_dict`.
    pub fn to_lit(&self) -> Lit {
        Lit::dict(vec![
            ("color", Lit::str(&self.color)),
            ("marker", Lit::str(self.mpl_marker())),
            ("size", Lit::Float(self.size)),
            ("open", Lit::Bool(self.is_open())),
            ("fill", Lit::opt_str(self.fill.as_deref())),
        ])
    }
}

fn hex_rgb(color: &str) -> Option<(f64, f64, f64)> {
    let named = match color.trim().to_lowercase().as_str() {
        "w" | "white" => Some("#ffffff"),
        "k" | "black" => Some("#000000"),
        "r" => Some("#ff0000"),
        "g" => Some("#008000"),
        "b" => Some("#0000ff"),
        "c" => Some("#00bfbf"),
        "m" => Some("#bf00bf"),
        "y" => Some("#bfbf00"),
        "red" => Some("#ff0000"),
        "green" => Some("#008000"),
        "blue" => Some("#0000ff"),
        "yellow" => Some("#ffff00"),
        "grey" | "gray" => Some("#808080"),
        "silver" => Some("#c0c0c0"),
        "ivory" => Some("#fffff0"),
        "snow" => Some("#fffafa"),
        "whitesmoke" => Some("#f5f5f5"),
        "lightgrey" | "lightgray" => Some("#d3d3d3"),
        _ => None,
    };
    let hex = named.unwrap_or(color).strip_prefix('#')?;
    let expand: String = match hex.len() {
        3 | 4 => hex.chars().take(3).flat_map(|c| [c, c]).collect(),
        6 | 8 => hex[..6].to_string(),
        _ => return None,
    };
    let v = u32::from_str_radix(&expand, 16).ok()?;
    Some((f64::from((v >> 16) & 0xff) / 255.0, f64::from((v >> 8) & 0xff) / 255.0, f64::from(v & 0xff) / 255.0))
}

/// `open_form`: the outline of a style's symbol, filled white; a colour too
/// light to see on white is outlined in black.
pub fn open_form(style: &PointStyle) -> PointStyle {
    let marker = if style.is_open() { style.marker.clone() } else { format!("{}{OPEN_SUFFIX}", style.marker) };
    let mut color = style.color.clone();
    if let Some((r, g, b)) = hex_rgb(&color)
        && 0.2126 * r + 0.7152 * g + 0.0722 * b > OPEN_LIGHT_LUMINANCE
    {
        color = OPEN_LIGHT_OUTLINE.into();
    }
    PointStyle { color, marker, size: style.size, fill: Some(OPEN_FILL.into()) }
}

/// `row_key`.
pub fn row_key(kind: &str, parts: &[&str]) -> String {
    let mut key = kind.to_string();
    for p in parts {
        key.push('\0');
        key.push_str(p);
    }
    key
}

fn override_text(o: &Override, field: &str) -> Option<String> {
    o.get(field).filter(|v| truthy(v)).map(py_str)
}

/// `apply_override`: a style with the color/marker/size a row pinned.
pub fn apply_override(style: Option<PointStyle>, o: Option<&Override>) -> Option<PointStyle> {
    let (Some(style), Some(o)) = (style.clone(), o) else { return style };
    if o.is_empty() {
        return Some(style);
    }
    let size = match o.get("size").filter(|v| truthy(v)) {
        Some(v) => py_float(v).unwrap_or(style.size),
        None => style.size,
    };
    Some(PointStyle {
        color: override_text(o, "color").unwrap_or(style.color),
        marker: override_text(o, "marker").unwrap_or(style.marker),
        size,
        fill: None,
    })
}

pub fn override_label(o: Option<&Override>) -> Option<String> {
    o.and_then(|o| override_text(o, "label"))
}

pub fn is_hidden(o: Option<&Override>) -> bool {
    o.and_then(|o| o.get("hidden")).is_some_and(truthy)
}

/// `manual_order`: unplaced rows sort last.
pub fn manual_order(o: Option<&Override>) -> i64 {
    const LAST: i64 = 1 << 30;
    match o.and_then(|o| o.get("order")) {
        None | Some(Value::Null) => LAST,
        Some(Value::Bool(b)) => i64::from(*b),
        Some(Value::Number(n)) => n.as_i64().or_else(|| n.as_f64().filter(|f| f.is_finite()).map(|f| f.trunc() as i64)).unwrap_or(LAST),
        Some(Value::String(s)) => crate::lit::py_strip(s).replace('_', "").parse::<i64>().unwrap_or(LAST),
        Some(_) => LAST,
    }
}

/// `group_points`: (label, row indices) by first appearance.
pub fn group_points(entry: &Entry, rows: &[usize], group_key: Option<&str>) -> Vec<(String, Vec<usize>)> {
    if rows.is_empty() {
        return Vec::new();
    }
    let Some(col) = group_key.and_then(|k| entry.column_index(k)) else {
        return vec![("All points".into(), rows.to_vec())];
    };
    let mut groups: IndexMap<String, Vec<usize>> = IndexMap::new();
    for r in rows {
        groups.entry(entry.rows[*r][col].text()).or_default().push(*r);
    }
    groups.into_iter().map(|(value, sub)| (if value.is_empty() { "(blank)".into() } else { value }, sub)).collect()
}

/// `default_styles`.
pub fn default_styles(
    labels: &[String],
    color_keys: Option<&[String]>,
    vary_symbols: bool,
    palette_offset: usize,
    palette: &[String],
) -> IndexMap<String, PointStyle> {
    let mut styles = IndexMap::new();
    match color_keys {
        None => {
            for (i, label) in labels.iter().enumerate() {
                let marker = if vary_symbols { MARKER_CYCLE[i % MARKER_CYCLE.len()] } else { "Circle" };
                styles.insert(label.clone(), PointStyle::new(&palette[(i + palette_offset) % palette.len()], marker));
            }
        }
        Some(keys) => {
            let order: IndexSet<&String> = keys.iter().collect();
            let mut seen: IndexMap<&String, usize> = IndexMap::new();
            for (label, key) in labels.iter().zip(keys) {
                let shape = *seen.get(key).unwrap_or(&0);
                seen.insert(key, shape + 1);
                let color = order.get_index_of(key).unwrap() + palette_offset;
                styles.insert(
                    label.clone(),
                    PointStyle::new(&palette[color % palette.len()], MARKER_CYCLE[shape % MARKER_CYCLE.len()]),
                );
            }
        }
    }
    styles
}

fn column_texts(entry: &Entry, key: Option<&str>) -> Option<Vec<String>> {
    let col = key.and_then(|k| entry.column_index(k))?;
    Some(entry.rows.iter().map(|r| r[col].text()).collect())
}

/// `nests_within(frame, outer, inner)`.
fn nests_within(entry: &Entry, outer: Option<&str>, inner: Option<&str>) -> bool {
    if entry.is_empty() {
        return false;
    }
    let (Some(outer), Some(inner)) = (column_texts(entry, outer), column_texts(entry, inner)) else { return false };
    let mut owner: IndexMap<&String, &String> = IndexMap::new();
    for (o, i) in outer.iter().zip(&inner) {
        match owner.get(i) {
            Some(prev) if *prev != o => return false,
            _ => {
                owner.insert(i, o);
            }
        }
    }
    true
}

/// `resolve_nesting`.
pub fn resolve_nesting(entry: &Entry, color_key: Option<&str>, symbol_key: Option<&str>, mode: &str) -> bool {
    if color_key.is_none() || symbol_key.is_none() || entry.is_empty() {
        return false;
    }
    if column_texts(entry, color_key).is_none() || column_texts(entry, symbol_key).is_none() {
        return false;
    }
    match mode {
        "never" => false,
        "always" => true,
        _ => nests_within(entry, color_key, symbol_key),
    }
}

/// `owner_map`: symbol value -> its first color value.
pub fn owner_map(entry: &Entry, symbol_key: Option<&str>, color_key: Option<&str>) -> IndexMap<String, String> {
    let mut owner = IndexMap::new();
    if let (Some(symbols), Some(colors)) = (column_texts(entry, symbol_key), column_texts(entry, color_key)) {
        for (s, c) in symbols.into_iter().zip(colors) {
            owner.entry(s).or_insert(c);
        }
    }
    owner
}

/// `attribute_style_maps`: value -> color and value -> marker.
pub fn attribute_style_maps(
    entry: &Entry,
    color_key: Option<&str>,
    symbol_key: Option<&str>,
    hierarchy: &str,
    palette: &[String],
) -> (IndexMap<String, String>, IndexMap<String, String>) {
    let mut color_map = IndexMap::new();
    if let Some(values) = column_texts(entry, color_key) {
        for value in values {
            if !color_map.contains_key(&value) {
                let color = palette[color_map.len() % palette.len()].clone();
                color_map.insert(value, color);
            }
        }
    }
    let mut symbol_map = IndexMap::new();
    if let Some(values) = column_texts(entry, symbol_key) {
        let nested = resolve_nesting(entry, color_key, symbol_key, hierarchy);
        let owner = if nested { owner_map(entry, symbol_key, color_key) } else { IndexMap::new() };
        let mut seen: IndexMap<String, usize> = IndexMap::new();
        for value in values {
            if symbol_map.contains_key(&value) {
                continue;
            }
            let group = owner.get(&value).cloned().unwrap_or_default();
            let index = *seen.get(&group).unwrap_or(&0);
            seen.insert(group, index + 1);
            symbol_map.insert(value, MARKER_CYCLE[index % MARKER_CYCLE.len()].to_string());
        }
    }
    (color_map, symbol_map)
}

/// `style_by_attributes`: render groups by (color value, symbol value).
pub fn style_by_attributes(
    entry: &Entry,
    color_key: Option<&str>,
    symbol_key: Option<&str>,
    color_map: &IndexMap<String, String>,
    symbol_map: &IndexMap<String, String>,
    nested: bool,
    palette: &[String],
) -> Vec<(String, PointStyle, Vec<usize>)> {
    if entry.is_empty() {
        return Vec::new();
    }
    let blank = vec![String::new(); entry.len()];
    let cvals = column_texts(entry, color_key);
    let has_color_key = cvals.is_some();
    let cvals = cvals.unwrap_or_else(|| blank.clone());
    let svals = column_texts(entry, symbol_key).unwrap_or(blank);
    let default_color = color_map.values().next().cloned().unwrap_or_else(|| palette[0].clone());
    let mut combos: IndexMap<(String, String), Vec<usize>> = IndexMap::new();
    for (i, (c, s)) in cvals.iter().zip(&svals).enumerate() {
        combos.entry((c.clone(), s.clone())).or_default().push(i);
    }
    combos
        .into_iter()
        .map(|((cval, sval), rows)| {
            let parts: Vec<&str> = [cval.as_str(), sval.as_str()].into_iter().filter(|p| !p.is_empty()).collect();
            let label = if parts.is_empty() { "All points".to_string() } else { parts.join(" / ") };
            let mut style = PointStyle::new(
                color_map.get(&cval).unwrap_or(&default_color),
                symbol_map.get(&sval).map_or("Circle", String::as_str),
            );
            if !entry.overrides.is_empty() {
                style = override_for(&style, entry, &cval, &sval, nested, has_color_key);
            }
            (label, style, rows)
        })
        .collect()
}

fn override_for(style: &PointStyle, entry: &Entry, cval: &str, sval: &str, nested: bool, has_color_key: bool) -> PointStyle {
    if nested {
        return apply_override(Some(style.clone()), entry.override_for(&row_key("pair", &[cval, sval]))).unwrap();
    }
    let base = style.clone();
    let mut style = apply_override(Some(style.clone()), entry.override_for(&row_key("symbol", &[sval]))).unwrap();
    if has_color_key {
        style = PointStyle { color: base.color, marker: style.marker, size: style.size, fill: None };
    }
    let color = entry.override_for(&row_key("color", &[cval])).and_then(|o| override_text(o, "color"));
    PointStyle { color: color.unwrap_or(style.color), marker: style.marker, size: style.size, fill: None }
}
