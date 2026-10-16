//! The code export's configuration: the project state turned into the plain
//! data both scripts are written from (PyMappr's `export/config.py` and
//! `export/layers_config.py`).

use indexmap::IndexMap;
use serde_json::Value;

use crate::data::{Entry, entries};
use crate::layout::{MapLayout, Section, layout_points, with_default_title};
use crate::lit::{Lit, py_strip, round6, round_to};
use crate::options::{Options, compass_fields, inset_fields, num, py_float, py_str, scale_bar_fields, truthy};
use crate::proj::{GLOBE, ProjInfo};
use crate::styling::{POINT_EDGE_COLOR, POINT_EDGE_WIDTH, PointStyle, palette_for};
use crate::tables::{json_lit, linestyle_lit, tables};

const DEFAULT_FIGSIZE: (f64, f64) = (9.0, 6.5);
const INSET_GAP: f64 = 0.015;

/// How a single-file script carries the point data.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InlineData {
    /// Every row, as PyMappr does.
    Embedded,
    /// A marker standing in for the data (`__RUSTYMAPPR_DATA_<i>__`), for
    /// sending a script somewhere without the data.
    Placeholder,
    /// The header and the first N rows.
    Head(usize),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DataMode {
    Inline(InlineData),
    /// `data/<name>.csv` files beside the script (working directory).
    Files,
}

/// The placeholder standing in for dataset *index*'s CSV.
pub fn placeholder(index: usize) -> String {
    format!("__RUSTYMAPPR_DATA_{index}__")
}

/// The name and home page the scripts credit.
#[derive(Debug, Clone)]
pub struct Branding {
    /// "PyMappr 1.34.0" in PyMappr; RustyMappr's own name and version here.
    pub generator: String,
    pub repo_url: String,
}

impl Branding {
    pub fn rustymappr() -> Self {
        Branding {
            generator: format!("RustyMappr {}", env!("CARGO_PKG_VERSION")),
            repo_url: format!("https://github.com/{}", tables().repo),
        }
    }

    /// Exactly what PyMappr writes (for the byte-compatibility tests).
    pub fn pymappr() -> Self {
        Branding {
            generator: format!("PyMappr {}", tables().pymappr_version),
            repo_url: format!("https://github.com/{}", tables().repo),
        }
    }
}

/// Everything about one export besides the project state.
#[derive(Debug, Clone)]
pub struct ExportOptions {
    pub project_name: String,
    /// The exported map size in inches, as PyMappr's
    /// `renderer.export_size_inches(width_cm)`: at the chosen print width
    /// (`map.export_width`, e.g. 17 cm = 6.693 in) or the on-screen size,
    /// and for a portrait map the cropped map rather than the letterboxed
    /// canvas. Only the width is used as given; the height follows from
    /// the view's aspect. None means PyMappr's default 9 x 6.5 in canvas.
    pub figure_size: Option<(f64, f64)>,
    /// What `MapRenderer.inset_export()` returns, or None without an inset
    /// (a `state["inset_export"]` is used when this is None). JSON fields:
    ///
    /// - `rect`: [x, y, width, height], the inset's place in the main map's
    ///   axes fraction (0..1 from the lower left), rounded to 6 places;
    /// - `projection` (name), `crs` (proj4 string or null for plain
    ///   lon/lat), `hemisphere` (bool, the globe), `lon_0`, `lat_0`,
    ///   `min_lat`, `max_lat`, `lon_halfspan`: the inset's own projection
    ///   after any "same" fallback, as `ProjInfo` has them;
    /// - `region`: [lon0, lon1, lat0, lat1] it shows; `limits`: its axis
    ///   limits [x0, x1, y0, y1] in its own projected coordinates;
    /// - `zoom`: log2(world width / limits width) without any export detail
    ///   boost, which picks its Natural Earth resolution;
    /// - `layers`: [[source, kwargs], ...] in draw order, source a layer key
    ///   ("land", "countries", "continents", "states", "counties", "ocean")
    ///   and kwargs the matplotlib style: a fill has `facecolor` (not
    ///   "none"), `edgecolor`, `zorder`; a line has `facecolor: "none"`,
    ///   `edgecolor`, `linewidth`, `linestyle` ("solid" or [0, [on, off]]),
    ///   `zorder`;
    /// - `points` (bool), `point_scale` (0.3), `frame_width` (0.8);
    /// - `horizon`: for the globe, [[x...], [y...]] of the disk outline
    ///   (null where a point does not project), else null;
    /// - `box`: null, or {`target`: "inset" | "main", `x`: [...], `y`: [...]
    ///   (null breaks the line), `color`, `width` (1.2)}: the outline linking
    ///   the maps, in the target map's coordinates.
    pub inset_export: Option<Value>,
    pub branding: Branding,
    /// The CSV line ending; pandas writes the platform's (`\r\n` on Windows).
    pub csv_newline: String,
}

impl Default for ExportOptions {
    fn default() -> Self {
        ExportOptions {
            project_name: "Untitled".into(),
            figure_size: None,
            inset_export: None,
            branding: Branding::rustymappr(),
            csv_newline: if cfg!(windows) { "\r\n".into() } else { "\n".into() },
        }
    }
}

#[derive(Debug, Clone)]
pub struct Layer {
    pub key: String,
    pub name: String,
    pub category: String,
    pub scale: String,
    pub member: Option<String>,
    pub filter: Lit,
    pub kind: String,
    pub z: f64,
    pub color: Lit,
    pub edgecolor: Lit,
    pub width: f64,
    pub alpha: f64,
    pub linestyle: Lit,
    pub marker: String,
    pub size: f64,
    pub min_zoom_max: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct DatasetConfig {
    pub name: String,
    pub path: Option<String>,
    pub inline_data: Option<String>,
    pub group_col: Option<String>,
    pub color_col: Option<String>,
    pub symbol_col: Option<String>,
    pub label_map: IndexMap<String, String>,
    pub styles: IndexMap<String, PointStyle>,
    pub source: Option<String>,
    pub open_col: Option<String>,
    pub open_values: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct InsetBox {
    pub target: String,
    pub x: Vec<Option<f64>>,
    pub y: Vec<Option<f64>>,
    pub color: String,
    pub width: f64,
}

#[derive(Debug, Clone)]
pub struct InsetConfig {
    pub projection: String,
    pub crs: Option<String>,
    pub rect: Vec<f64>,
    pub lon_0: f64,
    pub lat_0: f64,
    pub min_lat: f64,
    pub max_lat: f64,
    pub lon_halfspan: f64,
    pub hemisphere: bool,
    pub clip_cap: Option<[f64; 3]>,
    pub band: Option<[f64; 2]>,
    pub limits: Vec<f64>,
    pub zoom: f64,
    pub layers: Vec<Layer>,
    pub points: bool,
    pub point_scale: f64,
    pub frame_width: f64,
    pub horizon: Option<[Vec<Option<f64>>; 2]>,
    pub boxed: Option<InsetBox>,
    pub clear: Option<(String, f64)>,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub project: String,
    pub generator: String,
    pub repo_url: String,
    pub projection: String,
    pub crs: Option<String>,
    pub proj: ProjInfo,
    pub clip_cap: Option<[f64; 3]>,
    pub view: [f64; 4],
    pub zoom: f64,
    pub figsize: (f64, f64),
    pub margins: [f64; 4],
    pub basemap: String,
    pub layers: Vec<Layer>,
    pub label_layers: Vec<Lit>,
    pub graticule: Option<f64>,
    pub grid_labels: bool,
    pub compass: bool,
    pub compass_options: Options,
    pub scale_bar: Options,
    pub datasets: Vec<DatasetConfig>,
    pub data_files: bool,
    pub file_contents: Vec<(String, String)>,
    pub legend_sections: Option<Vec<Section>>,
    pub legend_rows: Option<Vec<String>>,
    pub open_note: Option<(String, PointStyle)>,
    /// LegendOptions as a dict, title resolved and the swatch gap filled in.
    pub legend: Options,
    pub point_alpha: f64,
    pub point_edge: (String, f64),
    pub dpi: i64,
    pub inset: Option<InsetConfig>,
    pub notes: Vec<String>,
}

impl Config {
    pub fn crs_r(&self) -> String {
        self.crs.clone().unwrap_or_else(|| "EPSG:4326".into())
    }
}

fn map_section(state: &Value) -> serde_json::Map<String, Value> {
    state.get("map").and_then(Value::as_object).cloned().unwrap_or_default()
}

/// The Lambert/Globe origin ("" or a non-finite value = default).
fn origin(m: &serde_json::Map<String, Value>) -> (Option<f64>, Option<f64>) {
    let parse = |key: &str| {
        let f = crate::options::parse_py_float(&py_str(m.get(key)?))?;
        f.is_finite().then_some(f)
    };
    (parse("proj_lon0"), parse("proj_lat0"))
}

fn str_or(m: &serde_json::Map<String, Value>, key: &str, default: &str) -> String {
    m.get(key).map_or_else(|| default.to_string(), py_str)
}

fn view_and_zoom(state: &Value, projection: &ProjInfo, figsize: (f64, f64), margins: [f64; 4], continent: &str) -> ([f64; 4], f64) {
    let mut view_box = None;
    if let Some(view) = state.get("view").and_then(Value::as_object)
        && let (Some(Value::Array(x)), Some(Value::Array(y))) = (view.get("xlim"), view.get("ylim"))
            && x.len() == 2
            && y.len() == 2
            && let (Some(x0), Some(x1), Some(y0), Some(y1)) = (py_float(&x[0]), py_float(&x[1]), py_float(&y[0]), py_float(&y[1])) {
                view_box = Some([x0, x1, y0, y1]);
            }
    let view_box = view_box.unwrap_or_else(|| {
        let t = tables();
        let extent = t.continent_extents.get(continent).copied().unwrap_or([-180.0, 180.0, -90.0, 90.0]);
        let [mut x0, mut x1, mut y0, mut y1] = projection.project_extent(extent);
        let [wx0, wx1, wy0, wy1] = projection.bounds;
        let [left, bottom, right, top] = margins;
        let box_ratio = ((figsize.0 * (right - left)) / (figsize.1 * (top - bottom))).max(1e-6);
        let (width, height) = (x1 - x0, y1 - y0);
        if width / height < box_ratio {
            let new_w = height * box_ratio;
            if new_w <= wx1 - wx0 {
                let cx = ((x0 + x1) / 2.0).max(wx0 + new_w / 2.0).min(wx1 - new_w / 2.0);
                (x0, x1) = (cx - new_w / 2.0, cx + new_w / 2.0);
            }
        } else {
            let new_h = width / box_ratio;
            if new_h <= wy1 - wy0 {
                let cy = ((y0 + y1) / 2.0).max(wy0 + new_h / 2.0).min(wy1 - new_h / 2.0);
                (y0, y1) = (cy - new_h / 2.0, cy + new_h / 2.0);
            }
        }
        [x0, x1, y0, y1]
    });
    let width = (view_box[1] - view_box[0]).abs().max(1e-9);
    (view_box, (projection.world_width() / width).log2())
}

/// `_export_filename`: a filesystem-safe, case-insensitively unique name.
pub fn export_filename(name: &str, extension: &str, used: &mut Vec<String>, fallback: &str) -> String {
    let mut raw = py_strip(name).trim_end_matches(['.', ' ']).to_string();
    if !extension.is_empty() && raw.to_lowercase().ends_with(&extension.to_lowercase()) && raw.len() >= extension.len() {
        raw = raw[..raw.len() - extension.len()].trim_end_matches(['.', ' ']).to_string();
    }
    let stem = if raw.is_empty() { fallback.to_string() } else { safe_filename(&raw) };
    let taken: Vec<String> = used.iter().map(|u| crate::lit::casefold(u)).collect();
    let mut candidate = format!("{stem}{extension}");
    let mut counter = 2;
    while taken.contains(&crate::lit::casefold(&candidate)) {
        candidate = format!("{stem}_{counter}{extension}");
        counter += 1;
    }
    used.push(candidate.clone());
    candidate
}

/// `safe_filename`: PyMappr's rule for a project's file name.
pub fn safe_filename(name: &str) -> String {
    const RESERVED: [&str; 22] = [
        "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9", "lpt1",
        "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    ];
    let cleaned: String =
        py_strip(name).chars().map(|c| if "<>:\"/\\|?*".contains(c) || (c as u32) < 32 { '_' } else { c }).collect();
    let cleaned = cleaned.trim_matches(['.', ' ']);
    let cleaned = if cleaned.is_empty() { "Untitled".to_string() } else { cleaned.to_string() };
    let (first, rest) = match cleaned.split_once('.') {
        Some((f, r)) => (f.to_string(), Some(r.to_string())),
        None => (cleaned.clone(), None),
    };
    if RESERVED.contains(&py_strip(&first).to_lowercase().as_str()) {
        let first = first.trim_end_matches(crate::lit::is_py_space);
        return match rest {
            Some(rest) => format!("{first}_.{rest}"),
            None => format!("{first}_"),
        };
    }
    cleaned
}

// ------------------------------------------------------------------ layers

fn split_directory(directory: &str) -> (String, String) {
    let mut parts = directory.splitn(3, '_');
    let _ne = parts.next();
    let scale = parts.next().unwrap_or("").to_string();
    let name = parts.next().unwrap_or("").to_string();
    (scale, name)
}

/// (scale, category, dataset name, member) for a renderer source key.
fn source_archive(source: &str, zoom: f64) -> Option<(String, String, String, Option<String>)> {
    let t = tables();
    let category = t.category.get(source)?.clone();
    if source == "continents" {
        let (scale, name) = split_directory(&t.layer_specs["countries"].directory);
        return Some((scale, category, name, None));
    }
    if let Some((spec_key, _)) = t.derived_sources.get(source) {
        let spec = t.layer_specs.get(spec_key)?;
        let (scale, name) = split_directory(spec.last_directory());
        return Some((scale, category, name, spec.shapefile.clone()));
    }
    let spec = t.layer_specs.get(source)?;
    let (scale, name) = split_directory(spec.directory_for_zoom(zoom));
    Some((scale, category, name, spec.shapefile.clone()))
}

fn base_layer(key: &str, kind: &str, z: f64) -> Layer {
    Layer {
        key: key.into(),
        name: String::new(),
        category: String::new(),
        scale: String::new(),
        member: None,
        filter: Lit::None,
        kind: kind.into(),
        z,
        color: Lit::None,
        edgecolor: Lit::None,
        width: 0.0,
        alpha: 1.0,
        linestyle: Lit::str("solid"),
        marker: String::new(),
        size: 0.0,
        min_zoom_max: None,
    }
}

/// `_ne_layer`: a Natural Earth layer at the resolution drawn for *zoom*.
fn ne_layer(source: &str, key: &str, kind: &str, z: f64, zoom: f64) -> Option<Layer> {
    let (scale, category, name, member) = source_archive(source, zoom)?;
    let filter = tables().derived_sources.get(source).map_or(Lit::None, |(_, f)| f.clone());
    Some(Layer { name, category, scale, member, filter, ..base_layer(key, kind, z) })
}

fn enabled(m: &serde_json::Map<String, Value>, section: &str) -> Vec<String> {
    m.get(section)
        .and_then(Value::as_object)
        .map(|o| o.iter().filter(|(_, v)| truthy(v)).map(|(k, _)| k.clone()).collect())
        .unwrap_or_default()
}

fn base_layers(m: &serde_json::Map<String, Value>, zoom: f64) -> (Vec<Layer>, Vec<String>) {
    let t = tables();
    let scale = num(m.get("line_width"), 1.0);
    let mut layers = Vec::new();
    let mut notes = Vec::new();
    for (mode_key, z, mode) in [("ocean", t.z_ocean, str_or(m, "ocean", "none")), ("lakes", t.z_lake_fill, str_or(m, "lake_fill", "none"))] {
        if mode == "none" {
            continue;
        }
        let (Some(color), Some(layer)) = (t.fill_color(mode_key, &mode), ne_layer(mode_key, &format!("{mode_key}_fill"), "fill", z, zoom))
        else {
            continue;
        };
        layers.push(Layer { color: Lit::str(color), edgecolor: Lit::str("none"), width: 0.0, alpha: 1.0, ..layer });
    }
    if m.get("bathymetry").is_some_and(truthy) {
        for (letter, depth) in &t.bathymetry_steps {
            layers.push(Layer {
                name: "bathymetry_all".into(),
                category: "physical".into(),
                scale: "10m".into(),
                member: Some(format!("ne_10m_bathymetry_{letter}_{depth}")),
                color: Lit::str(&t.bathymetry_colors[depth]),
                edgecolor: Lit::str("none"),
                width: 0.0,
                alpha: 1.0,
                ..base_layer(&format!("bathymetry_{depth}"), "fill", t.z_bathymetry + *depth as f64 * 1e-6)
            });
        }
    }
    for key in enabled(m, "fills") {
        if let Some(note) = t.external_fills.get(&key) {
            notes.push(note.clone());
            continue;
        }
        let Some(f) = t.fill_layers.get(&key) else { continue };
        let Some(layer) = ne_layer(&f.source, &key, "fill", f.z, zoom) else { continue };
        layers.push(Layer {
            color: Lit::str(&f.face),
            edgecolor: Lit::str(&f.edge),
            width: f.edge_width,
            alpha: f.alpha,
            ..layer
        });
    }
    let lines = enabled(m, "lines");
    for key in &lines {
        let Some(l) = t.line_layers.get(key) else { continue };
        let Some(layer) = ne_layer(&l.source, key, "line", l.z, zoom) else { continue };
        layers.push(Layer { color: Lit::str(&l.color), width: l.width * scale, linestyle: l.linestyle.clone(), ..layer });
    }
    if !lines.iter().any(|k| k == "countries") {
        let l = &t.line_layers["continents"];
        if let Some(layer) = ne_layer("continents", "continents", "continents", l.z, zoom) {
            layers.push(Layer { color: Lit::str(&l.color), width: l.width * scale, linestyle: l.linestyle.clone(), ..layer });
        }
    }
    let capitals_only = m.get("capitals_only").is_some_and(truthy);
    for key in enabled(m, "points") {
        let key = if key == "cities" && capitals_only { "capitals".to_string() } else { key };
        let Some(p) = t.point_layers.get(&key) else { continue };
        let threshold = if p.bias >= 99.0 { None } else { Some(round_to(zoom + p.bias, 4)) };
        let Some(layer) = ne_layer(&p.source, &key, "point", t.z_point_layers, zoom) else { continue };
        layers.push(Layer {
            color: Lit::str(&p.face),
            edgecolor: Lit::str(&p.edge),
            marker: p.marker.clone(),
            size: p.size,
            min_zoom_max: threshold,
            ..layer
        });
    }
    layers.sort_by(|a, b| a.z.total_cmp(&b.z));
    (layers, notes)
}

fn label_layers(m: &serde_json::Map<String, Value>, zoom: f64) -> Vec<Lit> {
    let t = tables();
    let on = enabled(m, "labels");
    let capitals_only = m.get("capitals_only").is_some_and(truthy);
    let mut labels = Vec::new();
    for style in &t.label_styles {
        let key = style.key.as_str();
        if !on.iter().any(|k| k == key) || zoom < style.min_zoom {
            continue;
        }
        let source = if key == "cities" && capitals_only { "capitals" } else { style.source.as_str() };
        let derived = t.derived_sources.get(source);
        let spec_key = derived.map_or(source, |(k, _)| k.as_str());
        let Some(spec) = t.layer_specs.get(spec_key) else { continue };
        let (scale, name) = split_directory(&spec.directory);
        let filter = derived.map_or(Lit::None, |(_, f)| f.clone());
        let cap_key = if source == "capitals" { "cities" } else { source };
        let cap = t.layer_specs.get(cap_key).map_or(0, |s| s.label_cap);
        labels.push(Lit::dict(vec![
            ("key", Lit::str(key)),
            ("name", Lit::str(name)),
            ("category", Lit::str(t.category.get(spec_key).cloned().unwrap_or_default())),
            ("scale", Lit::str(scale)),
            ("member", Lit::opt_str(spec.shapefile.as_deref())),
            ("filter", filter),
            ("column", Lit::str(&spec.label_column)),
            ("geometry", Lit::str(&spec.geometry)),
            ("cap", Lit::Int(cap)),
            ("min_label_from_min_zoom", Lit::Bool(key == "cities")),
            ("dedupe_longest", Lit::Bool(key == "rivers" || key == "wadis")),
            ("feature_bias", Lit::opt_float(style.feature_bias)),
            ("point_layer", Lit::Bool(t.point_layers.contains_key(key))),
            ("font", style.font.clone()),
        ]));
    }
    labels
}

// ------------------------------------------------------------------- inset

fn floats_or_none(value: Option<&Value>) -> Vec<Option<f64>> {
    value
        .and_then(Value::as_array)
        .map(|a| a.iter().map(|v| if v.is_null() { None } else { Some(py_float(v).unwrap_or(f64::NAN)) }).collect())
        .unwrap_or_default()
}

fn inset_config(data: Option<&Value>, state: &Value) -> Option<InsetConfig> {
    let data = data?.as_object()?;
    let t = tables();
    let zoom = num(data.get("zoom"), 0.0);
    let mut layers = Vec::new();
    for item in data.get("layers").and_then(Value::as_array).into_iter().flatten() {
        let Some([source, kwargs]) = item.as_array().map(Vec::as_slice).and_then(|a| <&[Value; 2]>::try_from(a).ok()) else {
            continue;
        };
        let source = py_str(source);
        if !t.category.contains_key(&source) {
            continue;
        }
        let empty = serde_json::Map::new();
        let kw = kwargs.as_object().unwrap_or(&empty);
        let z = num(kw.get("zorder"), 1.0);
        let face = kw.get("facecolor").map_or(Lit::str("none"), json_lit);
        if face != Lit::str("none") {
            let Some(layer) = ne_layer(&source, &source, "fill", z, zoom) else { continue };
            layers.push(Layer {
                color: face,
                edgecolor: kw.get("edgecolor").map_or(Lit::str("none"), json_lit),
                width: num(kw.get("linewidth"), 0.0),
                alpha: 1.0,
                ..layer
            });
            continue;
        }
        let linestyle = kw.get("linestyle").map_or(Lit::str("solid"), linestyle_lit);
        let kind = if source == "continents" { "continents" } else { "line" };
        let Some(layer) = ne_layer(&source, &source, kind, z, zoom) else { continue };
        layers.push(Layer {
            color: kw.get("edgecolor").map_or(Lit::str("#000000"), json_lit),
            width: num(kw.get("linewidth"), 0.5),
            linestyle,
            ..layer
        });
    }
    layers.sort_by(|a, b| a.z.total_cmp(&b.z));

    let crs = data.get("crs").filter(|v| !v.is_null()).map(py_str);
    let hemisphere = data.get("hemisphere").is_some_and(truthy);
    let min_lat = num(data.get("min_lat"), -90.0);
    let max_lat = num(data.get("max_lat"), 90.0);
    let lon_0 = num(data.get("lon_0"), 0.0);
    let lat_0 = num(data.get("lat_0"), 0.0);
    let lon_halfspan = num(data.get("lon_halfspan"), 180.0);
    let (mut clip_cap, mut band) = (None, None);
    if crs.is_some() {
        if hemisphere {
            clip_cap = Some([round6(lon_0), round6(lat_0), round6(t.cap_clip_radius)]);
        } else if lon_halfspan < 180.0 || min_lat != -max_lat {
            band = Some([min_lat, max_lat]);
        } else if max_lat < 90.0 {
            band = Some([-max_lat, max_lat]);
        }
    }
    let rect: Vec<f64> = match data.get("rect").and_then(Value::as_array) {
        Some(values) => values.iter().map(|v| py_float(v).unwrap_or(0.0)).collect(),
        None => vec![0.0, 0.0, 0.3, 0.3],
    };
    let horizon = if hemisphere {
        data.get("horizon").and_then(Value::as_array).filter(|h| h.len() == 2).map(|h| [floats_or_none(Some(&h[0])), floats_or_none(Some(&h[1]))])
    } else {
        None
    };
    let boxed = data.get("box").and_then(Value::as_object).and_then(|b| {
        let target = b.get("target").and_then(Value::as_str)?;
        (target == "inset" || target == "main").then(|| InsetBox {
            target: target.into(),
            x: floats_or_none(b.get("x")),
            y: floats_or_none(b.get("y")),
            color: b.get("color").filter(|v| truthy(v)).map_or("#d62728".into(), py_str),
            width: num(b.get("width"), 1.2),
        })
    });
    let options = Options::from_value(&inset_fields(), map_section(state).get("inset"));
    let anchored = options.opt_f64("anchor_x").is_some() && options.opt_f64("anchor_y").is_some();
    let clear = if anchored || rect.len() < 4 {
        None
    } else {
        let position = options.str("position").to_string();
        let y = if position.starts_with("upper") { round6(rect[1] - INSET_GAP) } else { round6(rect[1] + rect[3] + INSET_GAP) };
        Some((position, y))
    };
    Some(InsetConfig {
        projection: data.get("projection").map_or("Equirectangular".into(), py_str),
        crs,
        rect,
        lon_0,
        lat_0,
        min_lat,
        max_lat,
        lon_halfspan,
        hemisphere,
        clip_cap,
        band,
        limits: match data.get("limits").and_then(Value::as_array) {
            Some(values) => values.iter().map(|v| py_float(v).unwrap_or(0.0)).collect(),
            None => vec![0.0, 1.0, 0.0, 1.0],
        },
        zoom: round_to(zoom, 4),
        layers,
        points: data.get("points").is_none_or(truthy),
        point_scale: num(data.get("point_scale"), 0.3),
        frame_width: num(data.get("frame_width"), 0.8),
        horizon,
        boxed,
        clear,
    })
}

// ---------------------------------------------------------------- datasets

fn dataset_configs(
    layout: &MapLayout,
    mode: DataMode,
    newline: &str,
) -> (Vec<DatasetConfig>, Vec<(String, String)>) {
    let mut used_files = Vec::new();
    let mut configs = Vec::new();
    let mut files = Vec::new();
    for (index, dataset) in layout.datasets.iter().enumerate() {
        let entry: &Entry = dataset.entry;
        let values: Vec<String> = if dataset.label_map.is_empty() {
            dataset.groups.iter().map(|(label, _, _)| label.clone()).collect()
        } else {
            dataset.label_map.keys().cloned().collect()
        };
        let styles: IndexMap<String, PointStyle> =
            values.into_iter().zip(dataset.groups.iter().map(|(_, s, _)| s.clone())).collect();
        let mut config = DatasetConfig {
            name: entry.name.clone(),
            path: None,
            inline_data: None,
            group_col: None,
            color_col: None,
            symbol_col: None,
            label_map: dataset.label_map.clone(),
            styles,
            source: (!entry.source_path.is_empty()).then(|| entry.source_path.clone()),
            open_col: None,
            open_values: Vec::new(),
        };
        if !dataset.open_groups.is_empty() {
            config.open_col = Some(entry.open_by.clone());
            config.open_values = entry.open_values.clone();
        }
        match mode {
            DataMode::Files => {
                let rel = format!("data/{}", export_filename(&entry.name, ".csv", &mut used_files, "dataset"));
                files.push((rel.clone(), entry.csv(newline, None)));
                config.path = Some(rel);
            }
            DataMode::Inline(InlineData::Embedded) => config.inline_data = Some(entry.csv(newline, None)),
            DataMode::Inline(InlineData::Head(n)) => config.inline_data = Some(entry.csv(newline, Some(n))),
            DataMode::Inline(InlineData::Placeholder) => config.inline_data = Some(placeholder(index)),
        }
        if dataset.attribute {
            if entry.column_key(&entry.color_by).is_some() {
                config.color_col = Some(entry.color_by.clone());
            }
            if entry.column_key(&entry.symbol_by).is_some() {
                config.symbol_col = Some(entry.symbol_by.clone());
            }
        } else if entry.column_key(&entry.group_by).is_some() {
            config.group_col = Some(entry.group_by.clone());
        }
        configs.push(config);
    }
    (configs, files)
}

/// `build_config`: everything the script templates need.
pub fn build_config(state: &Value, mode: DataMode, opts: &ExportOptions) -> Result<Config, String> {
    let t = tables();
    let m = map_section(state);
    let (lon0, lat0) = origin(&m);
    let projection_name = str_or(&m, "projection", "Equirectangular");
    let projection = ProjInfo::get(&projection_name, lon0, lat0)?;

    let graticule = match str_or(&m, "graticule", "Off").as_str() {
        "1\u{b0}" => Some(1.0),
        "5\u{b0}" => Some(5.0),
        "10\u{b0}" => Some(10.0),
        _ => None,
    };
    let labels_on = graticule.is_some() && !m.get("hide_grid_labels").is_some_and(truthy) && !projection.hemisphere;
    let margins = if labels_on { t.margins_with_ticks } else { t.margins_plain };

    let base_size = opts.figure_size.unwrap_or(DEFAULT_FIGSIZE);
    let continent = str_or(&m, "continent", "World");
    let (view, zoom) = view_and_zoom(state, &projection, base_size, margins, &continent);
    let [left, bottom, right, top] = margins;
    let axes_w = base_size.0 * (right - left);
    let view_w = (view[1] - view[0]).abs().max(1e-9);
    let view_h = (view[3] - view[2]).abs().max(1e-9);
    let fig_h = axes_w * (view_h / view_w) / (top - bottom);
    let figsize = (round_to(base_size.0, 3), round_to(fig_h, 3));

    let (layers, notes) = base_layers(&m, zoom);
    let label_layers = label_layers(&m, zoom);

    let entries = entries(state);
    let mut options = Options::legend(state.get("legend"));
    if py_strip(options.opt_str("title").unwrap_or("")).is_empty() {
        options.set("title", Lit::None);
    }
    with_default_title(&entries, &mut options);
    let palette = palette_for(m.get("palette").filter(|v| truthy(v)).map(py_str).as_deref());
    let layout = layout_points(&entries, &options, &palette);
    let (datasets, file_contents) = dataset_configs(&layout, mode, &opts.csv_newline);

    let title = py_strip(options.opt_str("title").unwrap_or("")).to_string();
    let mut legend = options.clone();
    legend.set("title", Lit::Str(title));
    legend.set("handle_text_pad", Lit::Float(options.pad_for(layout.sections.is_some())));

    let edge = state.get("point_edge").and_then(Value::as_object).cloned().unwrap_or_default();
    let clip_cap = (projection_name == GLOBE)
        .then(|| [round6(projection.lon_0), round6(projection.lat_0), round6(t.cap_clip_radius)]);
    let mut compass_options = Options::from_value(&compass_fields(), m.get("compass_options"));
    let compass = m.get("compass").is_some_and(truthy);
    compass_options.set("show", Lit::Bool(compass));
    let inset_data = opts.inset_export.as_ref().or_else(|| state.get("inset_export"));
    Ok(Config {
        project: opts.project_name.clone(),
        generator: opts.branding.generator.clone(),
        repo_url: opts.branding.repo_url.clone(),
        projection: projection_name,
        crs: projection.crs.clone(),
        clip_cap,
        view: view.map(round6),
        zoom: round_to(zoom, 4),
        figsize,
        margins,
        basemap: str_or(&m, "basemap", "simple"),
        layers,
        label_layers,
        graticule,
        grid_labels: labels_on,
        compass,
        compass_options,
        scale_bar: Options::from_value(&scale_bar_fields(), m.get("scale_bar")),
        datasets,
        data_files: mode == DataMode::Files,
        file_contents,
        legend_sections: layout.sections.clone(),
        legend_rows: layout.row_order.clone(),
        open_note: layout.open_note.clone(),
        legend,
        point_alpha: num(state.get("point_alpha"), 1.0),
        point_edge: (
            edge.get("color").filter(|v| truthy(v)).map_or(POINT_EDGE_COLOR.into(), py_str),
            num(Some(edge.get("width").unwrap_or(&Value::from(POINT_EDGE_WIDTH))), POINT_EDGE_WIDTH),
        ),
        dpi: {
            let dpi = num(m.get("dpi").or(Some(&Value::from(200))), 200.0);
            if dpi.is_finite() { dpi.trunc() as i64 } else { 200 }
        },
        inset: inset_config(inset_data.filter(|v| !v.is_null()), state),
        notes,
        proj: projection,
    })
}
