//! What gets drawn: every visible dataset turned into styled point groups
//! and the legend rows describing them (PyMappr's
//! `pymappr/styling/layout.py` and the row builders of `legend.py`), for
//! the whole dataset as the code export draws it (no filter).

use std::collections::{HashMap, HashSet};

use indexmap::IndexMap;

use crate::data::{Entry, Override};
use crate::lit::casefold;
use crate::options::Legend;
use crate::styling::{
    PointStyle, apply_override, attribute_style_maps, default_styles, group_points, is_hidden, manual_order,
    open_form, override_label, owner_map, resolve_nesting, row_key, style_by_attributes,
};

/// A legend row: (label, swatch style or none, depth).
pub type Row = (String, Option<PointStyle>, usize);
/// A legend section: (title, rows). Plain datasets joining a sectioned
/// legend bring two-field rows, which print without a depth.
pub type Section = (String, Vec<Row>);

pub struct DatasetLayout<'a> {
    pub entry: &'a Entry,
    /// (label, style, rows) per drawn group.
    pub groups: Vec<(String, PointStyle, Vec<usize>)>,
    pub label_map: IndexMap<String, String>,
    pub rows: Vec<(String, PointStyle)>,
    pub sections: Vec<Section>,
    pub attribute: bool,
    pub open_groups: Vec<(String, PointStyle, Vec<usize>)>,
}

pub struct MapLayout<'a> {
    pub datasets: Vec<DatasetLayout<'a>>,
    pub sections: Option<Vec<Section>>,
    pub row_order: Option<Vec<String>>,
    pub open_note: Option<(String, PointStyle)>,
}

pub const OPEN_GROUP_PREFIX: &str = "_open: ";

fn visible(entries: &[Entry]) -> Vec<&Entry> {
    entries.iter().filter(|e| e.visible && !e.is_empty()).collect()
}

/// `with_default_title`: a single group-by dataset is titled by its column.
pub fn with_default_title(entries: &[Entry], options: &mut Legend) {
    use crate::lit::Lit;
    if !options.bool("show_title") {
        options.set("title", Lit::None);
        return;
    }
    if options.opt_str("title").is_some() {
        return;
    }
    let shown = visible(entries);
    if shown.len() == 1 && shown[0].column_key(&shown[0].symbol_by).is_none() {
        let group_by = &shown[0].group_by;
        options.set("title", if group_by.is_empty() { Lit::None } else { Lit::str(group_by) });
    }
}

// ------------------------------------------------------------------ counts

#[derive(Hash, PartialEq, Eq, Clone)]
enum CountKey {
    Total,
    Color(String),
    Symbol(String),
    Pair(String, String),
}

fn legend_counts(entry: &Entry, color_key: Option<&str>, symbol_key: Option<&str>) -> HashMap<CountKey, usize> {
    let mut counts = HashMap::new();
    if entry.is_empty() {
        return counts;
    }
    counts.insert(CountKey::Total, entry.len());
    let all = entry.all_rows();
    let ccol = color_key.and_then(|k| entry.column_index(k));
    let scol = symbol_key.and_then(|k| entry.column_index(k));
    if let Some(c) = ccol {
        for v in entry.texts(c, &all) {
            *counts.entry(CountKey::Color(v)).or_insert(0) += 1;
        }
    }
    if let Some(s) = scol {
        for v in entry.texts(s, &all) {
            *counts.entry(CountKey::Symbol(v)).or_insert(0) += 1;
        }
    }
    if let (Some(c), Some(s)) = (ccol, scol) {
        for (cv, sv) in entry.texts(c, &all).into_iter().zip(entry.texts(s, &all)) {
            *counts.entry(CountKey::Pair(cv, sv)).or_insert(0) += 1;
        }
    }
    counts
}

/// `format_count`.
pub fn format_count(label: &str, n: usize, total: usize, fmt: &str) -> String {
    let pct = if total > 0 { 100.0 * n as f64 / total as f64 } else { 0.0 };
    match fmt {
        "n" => format!("{label} {n}"),
        "(n, %)" => format!("{label} ({n}, {pct:.0}%)"),
        "%" => format!("{label} {pct:.0}%"),
        _ => format!("{label} ({n})"),
    }
}

fn legend_label(
    value: &str,
    counts: &HashMap<CountKey, usize>,
    key: CountKey,
    options: &Legend,
    o: Option<&Override>,
) -> String {
    let label = override_label(o).unwrap_or_else(|| {
        if value.is_empty() { options.str("blank_label").to_string() } else { value.to_string() }
    });
    let n = counts.get(&key);
    match n {
        Some(n) if options.bool("counts") => format_count(
            &label,
            *n,
            *counts.get(&CountKey::Total).unwrap_or(&0),
            options.str("count_format"),
        ),
        _ => label,
    }
}

// ---------------------------------------------------------------- ordering

/// `order_labels`.
pub fn order_labels(values: Vec<String>, order: &str, count_of: &dyn Fn(&str) -> i64) -> Vec<String> {
    let mut values = values;
    match order {
        "az" => values.sort_by_cached_key(|v| casefold(v)),
        "za" => {
            let keys: HashMap<String, String> = values.iter().map(|v| (v.clone(), casefold(v))).collect();
            values.sort_by(|a, b| keys[b].cmp(&keys[a]));
        }
        "count_desc" | "count_asc" => {
            let sign = if order == "count_desc" { -1 } else { 1 };
            values.sort_by_cached_key(|v| (sign * count_of(v), casefold(v)));
        }
        _ => {}
    }
    values
}

fn ordered_rows(
    values: Vec<String>,
    options: &Legend,
    count_of: &dyn Fn(&str) -> i64,
    override_of: &dyn Fn(&str) -> Option<Override>,
) -> Vec<String> {
    if options.str("order") == "manual" {
        let first: HashMap<&String, usize> =
            values.iter().enumerate().rev().map(|(i, v)| (v, i)).collect::<HashMap<_, _>>();
        let mut keyed: Vec<(i64, usize, String)> =
            values.iter().map(|v| (manual_order(override_of(v).as_ref()), first[v], v.clone())).collect();
        keyed.sort_by(|a, b| (a.0, a.1).cmp(&(b.0, b.1)));
        return keyed.into_iter().map(|(_, _, v)| v).collect();
    }
    order_labels(values, options.str("order"), count_of)
}

// ---------------------------------------------------------------- sections

fn section_title(options: &Legend, prefix: &str, parts: &[&str]) -> String {
    if !options.bool("section_titles") {
        return String::new();
    }
    let joined = parts.iter().filter(|p| !p.is_empty()).copied().collect::<Vec<_>>().join(options.str("title_separator"));
    format!("{prefix}{}", if joined.is_empty() { "Key" } else { &joined })
}

fn group_swatch(color: &str, kids: &[String], symbol_map: &IndexMap<String, String>, options: &Legend) -> Option<PointStyle> {
    match options.str("group_swatch") {
        "none" => None,
        "child" if !kids.is_empty() => {
            Some(PointStyle::new(color, symbol_map.get(&kids[0]).map_or("Circle", String::as_str)))
        }
        _ => Some(PointStyle::new(color, "Circle")),
    }
}

#[allow(clippy::too_many_arguments)]
fn legend_sections(
    entry: &Entry,
    color_key: Option<&str>,
    symbol_key: Option<&str>,
    color_map: &IndexMap<String, String>,
    symbol_map: &IndexMap<String, String>,
    counts: &HashMap<CountKey, usize>,
    prefix: &str,
    options: &Legend,
) -> Vec<Section> {
    let ov = |key: String| entry.override_for(&key).cloned();
    if resolve_nesting(entry, color_key, symbol_key, options.str("hierarchy")) {
        let owner = owner_map(entry, symbol_key, color_key);
        let mut children: IndexMap<String, Vec<String>> = color_map.keys().map(|v| (v.clone(), Vec::new())).collect();
        for value in symbol_map.keys() {
            children.entry(owner.get(value).cloned().unwrap_or_default()).or_default().push(value.clone());
        }
        let parents = ordered_rows(
            color_map.keys().cloned().collect(),
            options,
            &|v| *counts.get(&CountKey::Color(v.into())).unwrap_or(&0) as i64,
            &|v| ov(row_key("color", &[v])),
        );
        let mut entries: Vec<Row> = Vec::new();
        for value in parents {
            let color = &color_map[&value];
            let parent = ov(row_key("color", &[&value]));
            let kids = children.get(&value).cloned().unwrap_or_default();
            let kids = ordered_rows(
                kids,
                options,
                &|k| *counts.get(&CountKey::Pair(value.clone(), k.into())).unwrap_or(&0) as i64,
                &|k| ov(row_key("pair", &[&value, k])),
            );
            if is_hidden(parent.as_ref()) {
                continue;
            }
            let shown: Vec<String> =
                kids.into_iter().filter(|k| !is_hidden(ov(row_key("pair", &[&value, k])).as_ref())).collect();
            entries.push((
                legend_label(&value, counts, CountKey::Color(value.clone()), options, parent.as_ref()),
                apply_override(group_swatch(color, &shown, symbol_map, options), parent.as_ref()),
                0,
            ));
            for kid in &shown {
                let leaf = ov(row_key("pair", &[&value, kid]));
                entries.push((
                    legend_label(kid, counts, CountKey::Pair(value.clone(), kid.clone()), options, leaf.as_ref()),
                    apply_override(Some(PointStyle::new(color, &symbol_map[kid])), leaf.as_ref()),
                    1,
                ));
            }
        }
        if entries.is_empty() {
            return Vec::new();
        }
        return vec![(section_title(options, prefix, &[&entry.color_by, &entry.symbol_by]), entries)];
    }

    let mut sections = Vec::new();
    let mut build = |source: &IndexMap<String, String>, kind: &str, base: &dyn Fn(&str) -> PointStyle, label: &str| {
        let count_key = |v: &str| if kind == "color" { CountKey::Color(v.into()) } else { CountKey::Symbol(v.into()) };
        let picked = ordered_rows(
            source.keys().cloned().collect(),
            options,
            &|v| *counts.get(&count_key(v)).unwrap_or(&0) as i64,
            &|v| ov(row_key(kind, &[v])),
        );
        let rows: Vec<Row> = picked
            .iter()
            .filter_map(|v| {
                let o = ov(row_key(kind, &[v]));
                (!is_hidden(o.as_ref())).then(|| {
                    (legend_label(v, counts, count_key(v), options, o.as_ref()), apply_override(Some(base(v)), o.as_ref()), 0)
                })
            })
            .collect();
        if !rows.is_empty() {
            sections.push((section_title(options, prefix, &[label]), rows));
        }
    };
    if !color_map.is_empty() {
        let label = if entry.color_by.is_empty() { "Color" } else { &entry.color_by };
        build(color_map, "color", &|v| PointStyle::new(&color_map[v], "Circle"), label);
    }
    if !symbol_map.is_empty() {
        let label = if entry.symbol_by.is_empty() { "Symbol" } else { &entry.symbol_by };
        let swatch = options.str("symbol_swatch_color").to_string();
        build(symbol_map, "symbol", &|v| PointStyle::new(&swatch, &symbol_map[v]), label);
    }
    sections
}

// ------------------------------------------------------------------ layout

/// `group_styles`: group label -> style in group-by mode.
fn group_styles(entry: &Entry, palette: &[String], palette_offset: usize) -> IndexMap<String, PointStyle> {
    let all = entry.all_rows();
    let groups = group_points(entry, &all, entry.column_key(&entry.group_by).as_deref());
    let labels: Vec<String> = groups.iter().map(|(l, _)| l.clone()).collect();
    let color_keys: Option<Vec<String>> =
        entry.column_key(&entry.color_by).and_then(|k| entry.column_index(&k)).map(|col| {
            groups
                .iter()
                .map(|(_, sub)| sub.first().map_or_else(String::new, |r| entry.rows[*r][col].raw_text()))
                .collect()
        });
    let fresh = default_styles(&labels, color_keys.as_deref(), entry.vary_symbols, palette_offset, palette);
    labels
        .iter()
        .map(|label| {
            let style = apply_override(fresh.get(label).cloned(), entry.override_for(&row_key("group", &[label])));
            (label.clone(), style.unwrap())
        })
        .collect()
}

fn plain_layout<'a>(
    entry: &'a Entry,
    palette: &[String],
    palette_offset: usize,
    multi: bool,
    used: &mut HashSet<String>,
    options: &Legend,
) -> (DatasetLayout<'a>, usize) {
    let styles = group_styles(entry, palette, palette_offset);
    let mut layout = DatasetLayout {
        entry,
        groups: Vec::new(),
        label_map: IndexMap::new(),
        rows: Vec::new(),
        sections: Vec::new(),
        attribute: false,
        open_groups: Vec::new(),
    };
    let all = entry.all_rows();
    let groups = group_points(entry, &all, entry.column_key(&entry.group_by).as_deref());
    let total: usize = groups.iter().map(|(_, s)| s.len()).sum();
    let mut counts: IndexMap<String, usize> = IndexMap::new();
    let mut placed: HashMap<String, i64> = HashMap::new();
    for (label, sub) in groups {
        let o = entry.override_for(&row_key("group", &[&label]));
        let mut display = match override_label(o) {
            Some(text) => text,
            None => {
                if multi && label == "All points" {
                    entry.name.clone()
                } else if multi && used.contains(&label) {
                    format!("{label} ({})", entry.name)
                } else {
                    label.clone()
                }
            }
        };
        used.insert(display.clone());
        if options.bool("counts") {
            display = format_count(&display, sub.len(), total, options.str("count_format"));
        }
        let style = styles.get(&label).cloned().unwrap_or_default();
        layout.label_map.insert(label.clone(), display.clone());
        let n = sub.len();
        layout.groups.push((display.clone(), style.clone(), sub));
        if is_hidden(o) {
            continue;
        }
        layout.rows.push((display.clone(), style));
        counts.insert(display.clone(), n);
        placed.insert(display, manual_order(o));
    }
    let order: Vec<String> = if options.str("order") == "manual" {
        let mut keys: Vec<String> = counts.keys().cloned().collect();
        keys.sort_by_key(|k| placed[k]);
        keys
    } else {
        order_labels(counts.keys().cloned().collect(), options.str("order"), &|t| {
            *counts.get(t).unwrap_or(&0) as i64
        })
    };
    let rank: HashMap<&String, usize> = order.iter().enumerate().map(|(i, t)| (t, i)).collect();
    layout.rows.sort_by_key(|(text, _)| rank[text]);
    (layout, palette_offset + styles.len())
}

fn attribute_layout<'a>(entry: &'a Entry, palette: &[String], multi: bool, options: &Legend) -> DatasetLayout<'a> {
    let color_key = entry.column_key(&entry.color_by);
    let symbol_key = entry.column_key(&entry.symbol_by);
    let (ck, sk) = (color_key.as_deref(), symbol_key.as_deref());
    let hierarchy = options.str("hierarchy");
    let (color_map, symbol_map) = attribute_style_maps(entry, ck, sk, hierarchy, palette);
    let nested = resolve_nesting(entry, ck, sk, hierarchy);
    let groups = style_by_attributes(entry, ck, sk, &color_map, &symbol_map, nested, palette);
    let counts = if options.bool("counts") || options.orders_by_count() {
        legend_counts(entry, ck, sk)
    } else {
        HashMap::new()
    };
    let prefix = if multi && options.bool("dataset_prefix") { format!("{}: ", entry.name) } else { String::new() };
    let sections = legend_sections(entry, ck, sk, &color_map, &symbol_map, &counts, &prefix, options);
    DatasetLayout {
        entry,
        groups,
        label_map: IndexMap::new(),
        rows: Vec::new(),
        sections,
        attribute: true,
        open_groups: Vec::new(),
    }
}

fn split_open(layout: &mut DatasetLayout) {
    let entry = layout.entry;
    let key = entry.column_key(&entry.open_by).and_then(|k| entry.column_index(&k));
    let (Some(col), false) = (key, entry.open_values.is_empty()) else { return };
    let values: HashSet<&String> = entry.open_values.iter().collect();
    let mut kept = Vec::new();
    for (label, style, rows) in std::mem::take(&mut layout.groups) {
        let (open, closed): (Vec<usize>, Vec<usize>) =
            rows.iter().partition(|r| values.contains(&entry.rows[**r][col].text()));
        if open.is_empty() {
            kept.push((label, style, rows));
            continue;
        }
        layout.open_groups.push((format!("{OPEN_GROUP_PREFIX}{label}"), open_form(&style), open));
        kept.push((label, style, closed));
    }
    layout.groups = kept;
}

fn open_note(datasets: &[DatasetLayout], options: &Legend) -> Option<(String, PointStyle)> {
    let mut values: Vec<String> = Vec::new();
    for d in datasets.iter().filter(|d| !d.open_groups.is_empty()) {
        for v in &d.entry.open_values {
            if !values.contains(v) {
                values.push(v.clone());
            }
        }
    }
    if values.is_empty() {
        return None;
    }
    let style = PointStyle::new(options.str("symbol_swatch_color"), "Circle");
    Some((values.join(", "), open_form(&style)))
}

/// `layout_points` over every row of every visible dataset.
pub fn layout_points<'a>(entries: &'a [Entry], options: &Legend, palette: &[String]) -> MapLayout<'a> {
    let shown = visible(entries);
    let multi = shown.len() > 1;
    let sectioned = shown.iter().any(|e| e.column_key(&e.symbol_by).is_some());
    let mut datasets = Vec::new();
    let mut sections: Vec<Section> = Vec::new();
    let mut row_order: Vec<String> = Vec::new();
    let mut palette_offset = 0;
    let mut used = HashSet::new();
    for entry in shown {
        let mut layout = if entry.column_key(&entry.symbol_by).is_some() {
            let layout = attribute_layout(entry, palette, multi, options);
            sections.extend(layout.sections.iter().cloned());
            layout
        } else {
            let (layout, offset) = plain_layout(entry, palette, palette_offset, multi, &mut used, options);
            palette_offset = offset;
            row_order.extend(layout.rows.iter().map(|(t, _)| t.clone()));
            if sectioned && !layout.rows.is_empty() {
                let title = if options.bool("section_titles") { entry.name.clone() } else { String::new() };
                // Two-field rows in PyMappr; they print with depth 0.
                sections.push((title, layout.rows.iter().map(|(t, s)| (t.clone(), Some(s.clone()), 0)).collect()));
            }
            layout
        };
        split_open(&mut layout);
        datasets.push(layout);
    }
    let note = open_note(&datasets, options);
    MapLayout {
        datasets,
        sections: sectioned.then_some(sections),
        row_order: (!sectioned).then_some(row_order),
        open_note: note,
    }
}
