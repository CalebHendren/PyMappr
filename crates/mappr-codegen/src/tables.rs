//! PyMappr's layer, style and projection tables (`pymappr/renderer/tables.py`,
//! `pymappr/geo/layers.py`, `pymappr/export/layers_config.py`), read from
//! `tables.json`. That file is generated from PyMappr itself
//! (`scripts/reference_codegen.py tables`), so the numbers - and whether
//! each is an int or a float, which the scripts print differently - are
//! exactly PyMappr's.

use std::sync::OnceLock;

use indexmap::IndexMap;
use serde_json::Value;

use crate::lit::Lit;

/// A JSON value as the Python value it was written from (ints stay ints).
pub fn json_lit(value: &Value) -> Lit {
    match value {
        Value::Null => Lit::None,
        Value::Bool(b) => Lit::Bool(*b),
        Value::Number(n) => match n.as_i64() {
            Some(i) if !n.is_f64() => Lit::Int(i),
            _ => Lit::Float(n.as_f64().unwrap_or(f64::NAN)),
        },
        Value::String(s) => Lit::Str(s.clone()),
        Value::Array(items) => Lit::List(items.iter().map(json_lit).collect()),
        Value::Object(map) => Lit::Dict(map.iter().map(|(k, v)| (Lit::Str(k.clone()), json_lit(v))).collect()),
    }
}

/// A renderer line style: "solid", or a dash tuple `(0, (4, 2))`, which
/// JSON stores as `[0, [4, 2]]`.
pub fn linestyle_lit(value: &Value) -> Lit {
    match value {
        Value::Array(parts) if parts.len() == 2 => {
            let dashes = match &parts[1] {
                Value::Array(d) => Lit::Tuple(d.iter().map(json_lit).collect()),
                other => json_lit(other),
            };
            Lit::Tuple(vec![json_lit(&parts[0]), dashes])
        }
        other => json_lit(other),
    }
}

/// A layer filter: `(column, [values], keep)`.
pub fn filter_lit(value: &Value) -> Lit {
    match value {
        Value::Array(parts) => Lit::Tuple(parts.iter().map(json_lit).collect()),
        _ => Lit::None,
    }
}

pub struct LineLayer {
    pub source: String,
    pub color: String,
    pub width: f64,
    pub z: f64,
    pub linestyle: Lit,
}

pub struct FillLayer {
    pub source: String,
    pub face: String,
    pub edge: String,
    pub edge_width: f64,
    pub alpha: f64,
    pub z: f64,
}

pub struct PointLayer {
    pub source: String,
    pub marker: String,
    pub size: f64,
    pub face: String,
    pub edge: String,
    pub bias: f64,
}

pub struct LabelStyle {
    pub key: String,
    pub source: String,
    pub font: Lit,
    pub min_zoom: f64,
    pub feature_bias: Option<f64>,
}

pub struct LayerSpec {
    pub directory: String,
    pub geometry: String,
    pub label_cap: i64,
    pub shapefile: Option<String>,
    pub resolutions: Vec<(f64, String)>,
    pub label_column: String,
}

impl LayerSpec {
    pub fn directory_for_zoom(&self, zoom: f64) -> &str {
        let Some(first) = self.resolutions.first() else { return &self.directory };
        let mut chosen = &first.1;
        for (min_zoom, directory) in &self.resolutions {
            if zoom >= *min_zoom {
                chosen = directory;
            }
        }
        chosen
    }

    /// The most detailed resolution's directory.
    pub fn last_directory(&self) -> &str {
        self.resolutions.last().map_or(&self.directory, |r| &r.1)
    }
}

pub struct ProjectionDef {
    pub crs: Option<String>,
    pub bounds: [f64; 4],
    pub max_lat: f64,
    pub min_lat: f64,
    pub lon_0: f64,
    pub lat_0: f64,
    pub lon_halfspan: f64,
    pub hemisphere: bool,
}

pub struct Tables {
    pub pymappr_version: String,
    pub repo: String,
    pub cap_clip_radius: f64,
    pub line_layers: IndexMap<String, LineLayer>,
    pub fill_colors: Vec<(String, String, String)>,
    pub fill_layers: IndexMap<String, FillLayer>,
    pub bathymetry_colors: IndexMap<i64, String>,
    pub bathymetry_steps: Vec<(String, i64)>,
    pub point_layers: IndexMap<String, PointLayer>,
    pub label_styles: Vec<LabelStyle>,
    pub z_bathymetry: f64,
    pub z_ocean: f64,
    pub z_lake_fill: f64,
    pub z_point_layers: f64,
    pub margins_with_ticks: [f64; 4],
    pub margins_plain: [f64; 4],
    pub layer_specs: IndexMap<String, LayerSpec>,
    pub category: IndexMap<String, String>,
    /// Derived source -> (spec key of the real data, filter literal).
    pub derived_sources: IndexMap<String, (String, Lit)>,
    pub external_fills: IndexMap<String, String>,
    pub continent_extents: IndexMap<String, [f64; 4]>,
    pub projections: IndexMap<String, ProjectionDef>,
}

impl Tables {
    pub fn fill_color(&self, layer: &str, mode: &str) -> Option<&str> {
        self.fill_colors.iter().find(|(l, m, _)| l == layer && m == mode).map(|(_, _, c)| c.as_str())
    }
}

fn f(v: &Value) -> f64 {
    v.as_f64().expect("number in tables.json")
}

fn s(v: &Value) -> String {
    v.as_str().expect("string in tables.json").to_string()
}

fn four(v: &Value) -> [f64; 4] {
    let a = v.as_array().expect("array in tables.json");
    [f(&a[0]), f(&a[1]), f(&a[2]), f(&a[3])]
}

fn obj(v: &Value) -> &serde_json::Map<String, Value> {
    v.as_object().expect("object in tables.json")
}

fn arr(v: &Value) -> &Vec<Value> {
    v.as_array().expect("array in tables.json")
}

fn load() -> Tables {
    let data: Value = serde_json::from_str(include_str!("tables.json")).expect("tables.json parses");
    Tables {
        pymappr_version: s(&data["pymappr_version"]),
        repo: s(&data["repo"]),
        cap_clip_radius: f(&data["cap_clip_radius"]),
        line_layers: obj(&data["line_layers"])
            .iter()
            .map(|(k, v)| {
                let a = arr(v);
                (
                    k.clone(),
                    LineLayer { source: s(&a[0]), color: s(&a[1]), width: f(&a[2]), z: f(&a[3]), linestyle: linestyle_lit(&a[4]) },
                )
            })
            .collect(),
        fill_colors: arr(&data["fill_colors"])
            .iter()
            .map(|v| {
                let a = arr(v);
                (s(&a[0]), s(&a[1]), s(&a[2]))
            })
            .collect(),
        fill_layers: obj(&data["fill_layers"])
            .iter()
            .map(|(k, v)| {
                let a = arr(v);
                (
                    k.clone(),
                    FillLayer {
                        source: s(&a[0]),
                        face: s(&a[1]),
                        edge: s(&a[2]),
                        edge_width: f(&a[3]),
                        alpha: f(&a[4]),
                        z: f(&a[5]),
                    },
                )
            })
            .collect(),
        bathymetry_colors: arr(&data["bathymetry_colors"])
            .iter()
            .map(|v| (arr(v)[0].as_i64().unwrap(), s(&arr(v)[1])))
            .collect(),
        bathymetry_steps: arr(&data["bathymetry_steps"])
            .iter()
            .map(|v| (s(&arr(v)[0]), arr(v)[1].as_i64().unwrap()))
            .collect(),
        point_layers: obj(&data["point_layers"])
            .iter()
            .map(|(k, v)| {
                let a = arr(v);
                (
                    k.clone(),
                    PointLayer {
                        source: s(&a[0]),
                        marker: s(&a[1]),
                        size: f(&a[2]),
                        face: s(&a[3]),
                        edge: s(&a[4]),
                        bias: f(&a[5]),
                    },
                )
            })
            .collect(),
        label_styles: arr(&data["label_styles"])
            .iter()
            .map(|v| {
                let a = arr(v);
                LabelStyle {
                    key: s(&a[0]),
                    source: s(&a[1]),
                    font: Lit::Dict(
                        arr(&a[2]).iter().map(|p| (Lit::Str(s(&arr(p)[0])), json_lit(&arr(p)[1]))).collect(),
                    ),
                    min_zoom: f(&a[3]),
                    feature_bias: a[4].as_f64(),
                }
            })
            .collect(),
        z_bathymetry: f(&data["z"]["bathymetry"]),
        z_ocean: f(&data["z"]["ocean"]),
        z_lake_fill: f(&data["z"]["lake_fill"]),
        z_point_layers: f(&data["z"]["point_layers"]),
        margins_with_ticks: four(&data["margins_with_ticks"]),
        margins_plain: four(&data["margins_plain"]),
        layer_specs: obj(&data["layer_specs"])
            .iter()
            .map(|(k, v)| {
                (
                    k.clone(),
                    LayerSpec {
                        directory: s(&v["directory"]),
                        geometry: s(&v["geometry"]),
                        label_cap: v["label_cap"].as_i64().unwrap(),
                        shapefile: v["shapefile"].as_str().map(str::to_string),
                        resolutions: arr(&v["resolutions"]).iter().map(|r| (f(&arr(r)[0]), s(&arr(r)[1]))).collect(),
                        label_column: s(&v["label_column"]),
                    },
                )
            })
            .collect(),
        category: obj(&data["category"]).iter().map(|(k, v)| (k.clone(), s(v))).collect(),
        derived_sources: obj(&data["derived_sources"])
            .iter()
            .map(|(k, v)| (k.clone(), (s(&arr(v)[0]), filter_lit(&arr(v)[1]))))
            .collect(),
        external_fills: obj(&data["external_fills"]).iter().map(|(k, v)| (k.clone(), s(v))).collect(),
        continent_extents: obj(&data["continent_extents"]).iter().map(|(k, v)| (k.clone(), four(v))).collect(),
        projections: obj(&data["projections"])
            .iter()
            .map(|(k, v)| {
                (
                    k.clone(),
                    ProjectionDef {
                        crs: v["crs"].as_str().map(str::to_string),
                        bounds: four(&v["bounds"]),
                        max_lat: f(&v["max_lat"]),
                        min_lat: f(&v["min_lat"]),
                        lon_0: f(&v["lon_0"]),
                        lat_0: f(&v["lat_0"]),
                        lon_halfspan: f(&v["lon_halfspan"]),
                        hemisphere: v["hemisphere"].as_bool().unwrap(),
                    },
                )
            })
            .collect(),
    }
}

pub fn tables() -> &'static Tables {
    static TABLES: OnceLock<Tables> = OnceLock::new();
    TABLES.get_or_init(load)
}
