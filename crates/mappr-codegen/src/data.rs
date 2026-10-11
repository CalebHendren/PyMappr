//! The datasets as PyMappr's `entry_from_dict` reads them from a project
//! state, and the normalized CSV the scripts embed or write to `data/`.

use indexmap::IndexMap;
use serde_json::{Map, Value};

use crate::lit::float_repr;
use crate::options::{py_float, py_str, truthy};

/// One cell of a dataset's frame.
#[derive(Debug, Clone, PartialEq)]
pub enum Cell {
    Text(String),
    Number(f64),
    Missing,
}

impl Cell {
    /// The cell after `fillna("")` and `astype(str)`, which is how every
    /// grouping and matching rule in PyMappr reads a name column.
    pub fn text(&self) -> String {
        match self {
            Cell::Text(s) => s.clone(),
            Cell::Number(f) => float_repr(*f),
            Cell::Missing => String::new(),
        }
    }

    /// `str(value)` without `fillna` first: a missing value reads "nan".
    pub fn raw_text(&self) -> String {
        match self {
            Cell::Missing => "nan".into(),
            other => other.text(),
        }
    }
}

/// A row override as stored: label, hidden, order, color, marker, size.
pub type Override = Map<String, Value>;

#[derive(Debug, Clone)]
pub struct Entry {
    pub name: String,
    pub visible: bool,
    pub source_path: String,
    pub columns: Vec<String>,
    pub rows: Vec<Vec<Cell>>,
    pub name_labels: Vec<String>,
    pub group_by: String,
    pub color_by: String,
    pub symbol_by: String,
    pub vary_symbols: bool,
    pub open_by: String,
    pub open_values: Vec<String>,
    pub overrides: IndexMap<String, Override>,
}

const OVERRIDE_FIELDS: [&str; 6] = ["label", "hidden", "order", "color", "marker", "size"];

fn get_str(data: &Map<String, Value>, key: &str, default: &str) -> String {
    data.get(key).map_or_else(|| default.to_string(), py_str)
}

impl Entry {
    /// `entry_from_dict`.
    pub fn from_value(data: &Value) -> Entry {
        let empty = Map::new();
        let data = data.as_object().unwrap_or(&empty);
        let columns: Vec<String> =
            data.get("columns").and_then(Value::as_array).map(|c| c.iter().map(py_str).collect()).unwrap_or_default();
        let numeric: Vec<bool> = columns.iter().map(|c| c == "lon" || c == "lat").collect();
        let rows = data
            .get("rows")
            .and_then(Value::as_array)
            .map(|rows| {
                rows.iter()
                    .map(|row| {
                        let cells = row.as_array().map(Vec::as_slice).unwrap_or(&[]);
                        (0..columns.len())
                            .map(|i| match cells.get(i) {
                                None | Some(Value::Null) => Cell::Missing,
                                Some(v) if numeric[i] => py_float(v).map_or(Cell::Missing, |f| {
                                    if f.is_nan() { Cell::Missing } else { Cell::Number(f) }
                                }),
                                // Name cells are text in every frame PyMappr
                                // builds (build_dataset reads them as str).
                                Some(Value::Number(n)) => Cell::Text(py_str(&Value::Number(n.clone()))),
                                Some(v) => Cell::Text(py_str(v)),
                            })
                            .collect()
                    })
                    .collect()
            })
            .unwrap_or_default();
        let open_by = match data.get("open_by") {
            Some(v) if truthy(v) => py_str(v),
            _ => String::new(),
        };
        let open_values = match data.get("open_values") {
            Some(Value::Array(values)) => values.iter().map(py_str).collect(),
            _ => Vec::new(),
        };
        Entry {
            name: get_str(data, "name", "Dataset"),
            visible: data.get("visible").is_none_or(truthy),
            source_path: get_str(data, "source_path", ""),
            columns,
            rows,
            name_labels: data
                .get("name_labels")
                .and_then(Value::as_array)
                .map(|l| l.iter().map(py_str).collect())
                .unwrap_or_default(),
            group_by: get_str(data, "group_by", ""),
            color_by: get_str(data, "color_by", ""),
            symbol_by: get_str(data, "symbol_by", ""),
            vary_symbols: data.get("vary_symbols").is_some_and(truthy),
            open_by,
            open_values,
            overrides: overrides_from(data),
        }
    }

    pub fn len(&self) -> usize {
        self.rows.len()
    }

    pub fn is_empty(&self) -> bool {
        self.rows.is_empty()
    }

    pub fn name_keys(&self) -> Vec<String> {
        (1..=self.name_labels.len()).map(|i| format!("name{i}")).collect()
    }

    /// `column_key`: the frame column for a name-column label.
    pub fn column_key(&self, label: &str) -> Option<String> {
        if label.is_empty() || label == "None" {
            return None;
        }
        // dict(zip(labels, keys)): a repeated label maps to its last key.
        self.name_labels.iter().zip(self.name_keys()).filter(|(l, _)| *l == label).map(|(_, k)| k).next_back()
    }

    pub fn column_index(&self, key: &str) -> Option<usize> {
        self.columns.iter().position(|c| c == key)
    }

    /// A column's values (after `fillna("")`) for the given rows.
    pub fn texts(&self, column: usize, rows: &[usize]) -> Vec<String> {
        rows.iter().map(|r| self.rows[*r][column].text()).collect()
    }

    pub fn all_rows(&self) -> Vec<usize> {
        (0..self.rows.len()).collect()
    }

    pub fn override_for(&self, key: &str) -> Option<&Override> {
        self.overrides.get(key)
    }

    /// The dataset's points as normalized CSV (label columns plus
    /// Longitude/Latitude), as pandas writes it; *limit* keeps only the
    /// first rows.
    pub fn csv(&self, newline: &str, limit: Option<usize>) -> String {
        let keys = self.name_keys();
        let mut picked: Vec<(usize, String)> = Vec::new();
        for (i, column) in self.columns.iter().enumerate() {
            let header = if column == "lon" {
                Some("Longitude".to_string())
            } else if column == "lat" {
                Some("Latitude".to_string())
            } else {
                // dict(zip(keys, labels)): a key maps to its own label.
                keys.iter().position(|k| k == column).map(|p| self.name_labels[p].clone())
            };
            if let Some(header) = header {
                picked.push((i, header));
            }
        }
        let mut out = String::new();
        if picked.is_empty() {
            // pandas writes an empty header line and one per row.
            out.push_str("\"\"");
            out.push_str(newline);
            for _ in self.rows.iter().take(limit.unwrap_or(usize::MAX)) {
                out.push_str("\"\"");
                out.push_str(newline);
            }
            return out.replace('\0', "");
        }
        let line = |fields: Vec<String>| -> String {
            let single = fields.len() == 1;
            fields
                .into_iter()
                .map(|f| csv_field(&f, single))
                .collect::<Vec<_>>()
                .join(",")
        };
        out.push_str(&line(picked.iter().map(|(_, h)| h.clone()).collect()));
        out.push_str(newline);
        for row in self.rows.iter().take(limit.unwrap_or(usize::MAX)) {
            out.push_str(&line(picked.iter().map(|(i, _)| row[*i].text()).collect()));
            out.push_str(newline);
        }
        // Without NULs, like every other string in the scripts.
        out.replace('\0', "")
    }
}

/// One field as Python's csv module writes it (QUOTE_MINIMAL).
fn csv_field(field: &str, only_field: bool) -> String {
    let needs = field.contains([',', '"', '\n', '\r']) || (only_field && field.is_empty());
    if needs { format!("\"{}\"", field.replace('"', "\"\"")) } else { field.to_string() }
}

/// `_overrides_from_dict`, migrating a project saved before overrides.
fn overrides_from(data: &Map<String, Value>) -> IndexMap<String, Override> {
    let mut overrides: IndexMap<String, Override> = IndexMap::new();
    if !data.contains_key("legend_overrides")
        && let Some(Value::Object(styles)) = data.get("styles") {
            for (label, raw) in styles {
                let Some(raw) = raw.as_object() else { continue };
                let size = match raw.get("size") {
                    None => Some(30.0),
                    Some(v) => py_float(v),
                };
                let Some(size) = size else { continue };
                let mut o = Map::new();
                o.insert("color".into(), Value::String(raw.get("color").map_or("#d62728".into(), py_str)));
                o.insert("marker".into(), Value::String(raw.get("marker").map_or("Circle".into(), py_str)));
                o.insert("size".into(), serde_json::Number::from_f64(size).map_or(Value::Null, Value::Number));
                overrides.insert(format!("group\0{label}"), o);
            }
        }
    if let Some(Value::Object(stored)) = data.get("legend_overrides") {
        for (key, raw) in stored {
            let Some(raw) = raw.as_object() else { continue };
            let kept: Map<String, Value> = OVERRIDE_FIELDS
                .iter()
                .filter_map(|f| raw.get(*f).filter(|v| !v.is_null()).map(|v| (f.to_string(), v.clone())))
                .collect();
            if !kept.is_empty() {
                overrides.entry(key.clone()).or_default().extend(kept);
            }
        }
    }
    overrides
}

/// The entries of a project state.
pub fn entries(state: &Value) -> Vec<Entry> {
    state.get("datasets").and_then(Value::as_array).map(|d| d.iter().map(Entry::from_value).collect()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn csv_like_pandas() {
        let e = Entry::from_value(&json!({
            "columns": ["name1", "name2", "lon", "lat"], "name_labels": ["A,b", "C"],
            "rows": [["x\"y", null, -68, 1.5], ["", "a\nb", "2.5", "bad"]],
        }));
        assert_eq!(
            e.csv("\n", None),
            "\"A,b\",C,Longitude,Latitude\n\"x\"\"y\",,-68.0,1.5\n,\"a\nb\",2.5,\n"
        );
        assert_eq!(e.csv("\r\n", Some(1)), "\"A,b\",C,Longitude,Latitude\r\n\"x\"\"y\",,-68.0,1.5\r\n");
    }

    #[test]
    fn legacy_styles_become_group_overrides() {
        let e = Entry::from_value(&json!({"styles": {"Wyoming": {"color": "#123456", "marker": "Star", "size": 45.0}}}));
        let o = e.override_for("group\0Wyoming").unwrap();
        assert_eq!(o["marker"], "Star");
        let e = Entry::from_value(&json!({"styles": {"W": {"color": "#1"}}, "legend_overrides": {}}));
        assert!(e.overrides.is_empty());
    }
}
