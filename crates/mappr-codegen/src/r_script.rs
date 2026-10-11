//! The R script: its header and configuration block (PyMappr's
//! `export/r_script.py`), above the template pasted verbatim.

use indexmap::IndexMap;

use crate::config::{Config, InsetConfig, Layer};
use crate::lit::{Lit, comment_text, linewidth_mm, r, r_linetype, r_named, r_str, rf, round6, size_mm, wrapped_items};
use crate::options::Options;
use crate::styling::{OPEN_SUFFIX, PointStyle, open_form};

pub const TEMPLATE: &str = include_str!("../templates/recreate_map.R");

pub const INSTALL: &str = "install.packages(c(\"sf\", \"ggplot2\"),\n                 repos = \"https://cloud.r-project.org\")\n";
pub const GITIGNORE: &str = "naturalearth_cache/\nmap.png\n.Rproj.user/\n.Rhistory\n.RData\n";
pub const RPROJ: &str = "Version: 1.0\n\nRestoreWorkspace: Default\nSaveWorkspace: Default\nAlwaysSaveHistory: Default\n\nEnableCodeIndexing: Yes\nUseSpacesForTab: Yes\nNumSpacesForTab: 2\nEncoding: UTF-8\n";

const OPEN_KEY_SUFFIX: &str = " [open]";
const OPEN_NOTE_KEY: &str = "[open symbols]";
const OPEN_MARKER_EDGE: f64 = 1.2;

fn pch(marker: &str) -> Option<i64> {
    let base = marker.strip_suffix(OPEN_SUFFIX);
    let open = base.is_some();
    let code = match base.unwrap_or(marker) {
        "Circle" | "Pentagon" | "Hexagon" | "Octagon" => (21, 1),
        "Square" => (22, 0),
        "Triangle" | "Triangle left" | "Triangle right" => (24, 2),
        "Triangle down" => (25, 6),
        "Diamond" | "Thin diamond" => (23, 5),
        "Star" => (8, 8),
        "Plus" => (3, 3),
        "X" => (4, 4),
        "Dot" => (20, 20),
        _ => return None,
    };
    Some(if open { code.1 } else { code.0 })
}

fn marker_note(marker: &str) -> Option<&'static str> {
    Some(match marker {
        "Star" | "Star (open)" => "stars are drawn as asterisks (R pch 8)",
        "Plus" | "Plus (open)" => "plus markers are thin crosses (R pch 3)",
        "X" | "X (open)" => "X markers are thin crosses (R pch 4)",
        "Triangle left" | "Triangle left (open)" | "Triangle right" | "Triangle right (open)" => {
            "left/right triangles point up"
        }
        "Thin diamond" | "Thin diamond (open)" => "thin diamonds are regular diamonds",
        "Pentagon" | "Pentagon (open)" | "Hexagon" | "Hexagon (open)" | "Octagon" | "Octagon (open)" => {
            "pentagons, hexagons and octagons are circles"
        }
        "Dot (open)" => "open dots are filled dots",
        _ => return None,
    })
}

fn legend_notes(legend: &Options) -> Vec<String> {
    let defaults = Options::legend_default();
    let unsupported = [
        ("group_swatch", "The nested key's group swatch style"),
        ("symbol_swatch_color", "The crossed-key symbol swatch colour"),
        ("indent", "The nested key's indent width"),
        ("bold_groups", "Bolding of the nested key's group rows"),
        ("group_spacer", "Blank rows between nested groups"),
        ("handle_length", "Legend swatch width"),
        ("border_pad", "Legend inner padding"),
        ("column_spacing", "Legend column spacing"),
        ("rounded", "Rounded legend corners"),
        ("shadow", "The legend's drop shadow"),
        ("title_align", "Legend title alignment"),
    ];
    let mut notes: Vec<String> = unsupported
        .iter()
        .filter(|(key, _)| !legend.get(key).py_eq(defaults.get(key)))
        .map(|(_, d)| format!("{d} (no ggplot2 equivalent)"))
        .collect();
    let pad = legend.get("handle_text_pad");
    if !(pad.py_eq(&Lit::Float(0.4)) || pad.py_eq(&Lit::Float(0.8))) {
        notes.push("The swatch-to-label gap (no ggplot2 equivalent)".into());
    }
    if legend.bool("show") && legend.str("location") == "best" {
        notes.push("Automatic (\"best\") legend placement: the legend sits in the upper right".into());
    }
    notes
}

fn header(c: &Config) -> String {
    let mut notes = c.notes.clone();
    notes.push("Map labels (country/city/... name placement)".into());
    if c.legend.bool("label_underline") || c.legend.bool("title_underline") {
        notes.push("Underlined legend text (ggplot2 element_text has no underline; bold/italic are applied)".into());
    }
    if c.legend_sections.is_some() {
        notes.push("The sectioned two-attribute legend (rendered as one row per combination)".into());
    }
    notes.extend(legend_notes(&c.legend));
    let mut found: Vec<&str> = Vec::new();
    for spec in &c.datasets {
        for style in spec.styles.values() {
            if let Some(note) = marker_note(&style.marker)
                && !found.contains(&note)
            {
                found.push(note);
            }
        }
    }
    if !found.is_empty() {
        notes.push(format!("Some marker shapes (R has no exact equivalent): {}", found.join("; ")));
    }
    let listed: String = notes.iter().map(|n| format!("\n#   - {n}")).collect();
    let listed = format!("\n# Shown in PyMappr but NOT reproduced by this script:{listed}");
    let data_note = if c.data_files {
        "# Your point data is in the data/ folder as CSV - edit or replace those\n# files to update the map."
    } else {
        "# Your point data is embedded below in DATASETS, so this single file is\n# self-contained."
    };
    let generator = &c.generator;
    format!(
        "# Made with {generator} - {repo}
# Recreate the PyMappr map {project} outside PyMappr.
#
# Generated by {generator} from pre-made function templates and
# the map's saved settings - deterministically. The layers, colors, view,
# and styling mirror PyMappr's renderer as closely as sf + ggplot2 allow.
#
# Just run it: open this file in RStudio and click Source, or run
# `Rscript recreate_map.R` in a terminal. If sf or ggplot2 is missing it
# stops with the install.packages() line to run - or run
# `Rscript recreate_map.R --install-deps` to have them installed for you.
# The map data is downloaded from Natural Earth and cached in
# naturalearth_cache/ next to this script.
#
# Output: map.png
#
{data_note}
# The satellite basemap needs the terra and tidyterra packages; without
# them the script draws the vector map only.
#
# Projection: {projection}{listed}

ensure_packages <- function(pkgs) {{
  missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1),
                          quietly = TRUE)]
  if (length(missing) == 0) return(invisible())
  command <- sprintf(
    'install.packages(c(%s), repos = \"https://cloud.r-project.org\")',
    paste0('\"', missing, '\"', collapse = \", \"))
  if (!(\"--install-deps\" %in% commandArgs(trailingOnly = TRUE))) {{
    stop(\"This script needs \", paste(missing, collapse = \", \"),
         \". Install with:\\n    \", command,
         \"\\nor run it with Rscript ... --install-deps to install them \",
         \"automatically.\", call. = FALSE)
  }}
  message(\"Installing missing packages: \", paste(missing, collapse = \", \"))
  install.packages(missing, repos = \"https://cloud.r-project.org\")
}}
ensure_packages(c(\"sf\", \"ggplot2\"))

library(sf)
library(ggplot2)
",
        repo = c.repo_url,
        project = r_str(&c.project),
        projection = c.projection,
    )
}

fn pairs(items: Vec<(&str, String)>) -> Vec<(String, String)> {
    items.into_iter().map(|(k, v)| (k.to_string(), v)).collect()
}

fn layer(layer: &Layer) -> String {
    let mut p = pairs(vec![
        ("name", r_str(&layer.name)),
        ("category", r_str(&layer.category)),
        ("scale", r_str(&layer.scale)),
        ("member", r(&Lit::opt_str(layer.member.as_deref()))),
        ("kind", r_str(&layer.kind)),
        ("color", r(&layer.color)),
    ]);
    match &layer.filter {
        Lit::Tuple(parts) if layer.filter.truthy() => {
            let values = match parts.get(1) {
                Some(Lit::List(v) | Lit::Tuple(v)) => v.iter().map(r).collect::<Vec<_>>().join(", "),
                _ => String::new(),
            };
            p.extend(pairs(vec![
                ("filter_column", r(parts.first().unwrap_or(&Lit::None))),
                ("filter_values", format!("c({values})")),
                ("filter_keep", r(&Lit::Bool(parts.get(2).is_some_and(Lit::truthy)))),
            ]));
        }
        _ => p.extend(pairs(vec![
            ("filter_column", "NULL".into()),
            ("filter_values", "NULL".into()),
            ("filter_keep", "TRUE".into()),
        ])),
    }
    p.push(("min_zoom_max".into(), r(&Lit::opt_float(layer.min_zoom_max))));
    p.push(("z".into(), rf(round6(layer.z))));
    match layer.kind.as_str() {
        "fill" => {
            let edge = if layer.edgecolor == Lit::str("none") { Lit::None } else { layer.edgecolor.clone() };
            p.extend(pairs(vec![
                ("fill", r(&layer.color)),
                ("edgecolor", r(&edge)),
                ("linewidth", rf(linewidth_mm(layer.width))),
                ("alpha", rf(layer.alpha)),
                ("linetype", r_str("solid")),
                ("size", "NULL".into()),
                ("shape", "NULL".into()),
            ]));
        }
        "line" | "continents" => p.extend(pairs(vec![
            ("fill", "NULL".into()),
            ("edgecolor", "NULL".into()),
            ("linewidth", rf(linewidth_mm(layer.width))),
            ("alpha", rf(1.0)),
            ("linetype", r_str(r_linetype(&layer.linestyle))),
            ("size", "NULL".into()),
            ("shape", "NULL".into()),
        ])),
        _ => {
            let shape = match layer.marker.as_str() {
                "*" => 8,
                "^" => 24,
                "v" => 25,
                _ => 21,
            };
            p.extend(pairs(vec![
                ("fill", "NULL".into()),
                ("edgecolor", r(&layer.edgecolor)),
                ("linewidth", "NULL".into()),
                ("alpha", rf(1.0)),
                ("linetype", r_str("solid")),
                ("size", rf(size_mm(layer.size))),
                ("shape", r(&Lit::Int(shape))),
            ]));
        }
    }
    format!("  list({})", r_named(&p, "    "))
}

fn vector(name: &str, p: &[(String, String)]) -> String {
    if p.is_empty() { format!("{name} <- c()") } else { format!("{name} <- c({})", r_named(p, "  ")) }
}

type StyleKeys = (Vec<IndexMap<String, String>>, Vec<(String, String, PointStyle)>, Option<Vec<String>>);

fn style_keys(c: &Config) -> StyleKeys {
    let mut taken: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut per_dataset = Vec::new();
    let mut groups = Vec::new();
    for (number, spec) in c.datasets.iter().enumerate() {
        let number = number + 1;
        let mut renamed = IndexMap::new();
        for (value, style) in &spec.styles {
            let label = spec.label_map.get(value).cloned().unwrap_or_else(|| value.clone());
            let mut key = label.clone();
            let mut suffix = 0;
            while taken.contains(&key) {
                suffix += 1;
                key = if suffix == 1 { format!("{label} [{number}]") } else { format!("{label} [{number}.{suffix}]") };
            }
            taken.insert(key.clone());
            if &key != value {
                renamed.insert(value.clone(), key.clone());
            }
            groups.push((key, label, style.clone()));
        }
        per_dataset.push(renamed);
    }
    let Some(rows) = &c.legend_rows else { return (per_dataset, groups, None) };
    let rank: std::collections::HashMap<&String, usize> = rows.iter().enumerate().map(|(i, l)| (l, i)).collect();
    let mut shown: Vec<&(String, String, PointStyle)> = groups.iter().filter(|g| rank.contains_key(&g.1)).collect();
    shown.sort_by_key(|g| rank[&g.1]);
    let keys = shown.iter().map(|g| g.0.clone()).collect();
    (per_dataset, groups, Some(keys))
}

fn config_block(c: &Config) -> String {
    let mut l: Vec<String> = vec![
        String::new(),
        "# ------------------------- map configuration (from PyMappr) -------------------------".into(),
        String::new(),
    ];
    l.push(format!("MAP_CRS <- {}", r_str(&c.crs_r())));
    l.push(format!(
        "VIEW <- c({})  # axis limits in map coordinates (x0, x1, y0, y1)",
        c.view.iter().map(|v| rf(*v)).collect::<Vec<_>>().join(", ")
    ));
    match c.clip_cap {
        None => l.push("CLIP_CAP <- NULL  # (lon0, lat0, radius) visible cap for the globe, else NULL".into()),
        Some(cap) => l.push(format!(
            "CLIP_CAP <- c({})  # (lon0, lat0, radius) visible cap for the globe",
            cap.iter().map(|v| rf(*v)).collect::<Vec<_>>().join(", ")
        )),
    }
    let p = &c.proj;
    l.push(format!("MAX_LAT <- {}  # the projection's usable latitude band", rf(p.max_lat)));
    l.push(format!("MIN_LAT <- {}", rf(p.min_lat)));
    l.push(format!("LON_0 <- {}  # central meridian, and how far either side is usable", rf(p.lon_0)));
    l.push(format!("LON_HALFSPAN <- {}", rf(p.lon_halfspan)));
    l.push(format!(
        "PROJ_X <- c({}, {})  # the world's x range, for wrapped copies",
        rf(round6(p.bounds[0])),
        rf(round6(p.bounds[1]))
    ));
    l.push(format!("HEMISPHERE <- {}  # a globe: only the near side is drawn", r(&Lit::Bool(p.hemisphere))));
    l.push(format!("FIGSIZE <- c({}, {})  # inches; the app canvas geometry", rf(c.figsize.0), rf(c.figsize.1)));
    l.push(format!("GEOGRAPHIC <- {}  # plain lon/lat degrees?", r(&Lit::Bool(c.crs.is_none()))));
    l.push(format!("BASEMAP <- {}  # raster basemap mode (\"simple\" = none)", r_str(&c.basemap)));
    l.push(format!("GRID_INTERVAL <- {}  # graticule spacing in degrees (NULL = off)", r(&Lit::opt_float(c.graticule))));
    l.push(format!("GRID_LABELS <- {}", r(&Lit::Bool(c.grid_labels))));
    l.push(format!("POINT_ALPHA <- {}", rf(c.point_alpha)));
    l.push(format!("POINT_STROKE <- {}  # outline width of filled markers, in points", rf(c.point_edge.1)));
    l.push(format!("POINT_EDGE_COLOR <- {}", r_str(&c.point_edge.0)));
    let named = |o: &Options| o.0.iter().map(|(k, v)| (k.to_string(), r(v))).collect::<Vec<_>>();
    l.push(format!("COMPASS <- list({})", r_named(&named(&c.compass_options), "  ")));
    l.push(format!("SCALE_BAR <- list({})", r_named(&named(&c.scale_bar), "  ")));
    l.push(format!("DPI <- {}", r(&Lit::Int(c.dpi))));
    l.push("OUTPUT_FILE <- \"map.png\"".into());
    l.push(String::new());
    l.push("# Natural Earth layers enabled in PyMappr, in draw order.".into());
    l.push("NE_LAYERS <- list(".into());
    l.push(c.layers.iter().map(layer).collect::<Vec<_>>().join(",\n"));
    l.push(")".into());
    l.push(String::new());
    l.push("# One entry per dataset. lon_col/lat_col name the coordinate columns".into());
    l.push("# (NULL = auto-detect by column name).".into());
    l.push("# style_keys maps a group value to its STYLE_* key where the two differ.".into());
    l.push(format!("OPEN_KEY_SUFFIX <- {}", r_str(OPEN_KEY_SUFFIX)));
    l.push("DATASETS <- list(".into());
    let (keys, mut groups, mut legend_keys) = style_keys(c);
    if let Some((note_label, note_style)) = &c.open_note {
        let base: Vec<String> = groups.iter().map(|g| g.0.clone()).collect();
        let open: Vec<(String, String, PointStyle)> =
            groups.iter().map(|(k, label, s)| (format!("{k}{OPEN_KEY_SUFFIX}"), label.clone(), open_form(s))).collect();
        groups.extend(open);
        groups.push((OPEN_NOTE_KEY.into(), note_label.clone(), note_style.clone()));
        let mut lk = legend_keys.unwrap_or(base);
        lk.push(OPEN_NOTE_KEY.into());
        legend_keys = Some(lk);
    }
    let mut blocks = Vec::new();
    for (spec, renamed) in c.datasets.iter().zip(&keys) {
        let opt = |v: &Option<String>| r(&Lit::opt_str(v.as_deref()));
        let mut p = pairs(vec![
            ("name", r_str(&spec.name)),
            ("path", opt(&spec.path)),
            ("inline_data", opt(&spec.inline_data)),
            ("lon_col", r_str("Longitude")),
            ("lat_col", r_str("Latitude")),
            ("group_col", opt(&spec.group_col)),
            ("color_col", opt(&spec.color_col)),
            ("symbol_col", opt(&spec.symbol_col)),
            ("default_label", r_str("All points")),
            ("open_col", opt(&spec.open_col)),
        ]);
        p.push((
            "open_values".into(),
            if spec.open_values.is_empty() {
                "character(0)".into()
            } else {
                format!("c({})", spec.open_values.iter().map(|v| r_str(v)).collect::<Vec<_>>().join(", "))
            },
        ));
        for (name, mapping) in [("label_map", &spec.label_map), ("style_keys", renamed)] {
            if mapping.is_empty() {
                p.push((name.into(), "c()".into()));
            } else {
                let body: Vec<(String, String)> = mapping.iter().map(|(k, v)| (k.clone(), r_str(v))).collect();
                p.push((name.into(), format!("c({})", r_named(&body, "      "))));
            }
        }
        let mut block = format!("  list({})", r_named(&p, "    "));
        if let Some(source) = &spec.source {
            block = format!("  # originally imported from: {}\n{block}", comment_text(source));
        }
        blocks.push(block);
    }
    l.push(blocks.join(",\n"));
    l.push(")".into());
    l.push(String::new());
    l.push("# Legend key -> style, in render order. A key is the legend label, with".into());
    l.push("# \" [n]\" added where dataset n repeats a label another dataset already uses".into());
    l.push("# (STYLE_LABELS holds those keys' labels). Fillable shapes (21-25) carry".into());
    l.push("# the app's marker outline; sizes approximate PyMappr's marker areas and".into());
    l.push("# strokes are outline widths in points.".into());
    let (edge_color, edge_width) = &c.point_edge;
    let (mut shapes, mut colors, mut fills, mut sizes, mut strokes, mut renamed) =
        (Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for (key, label, style) in &groups {
        let filled_open = style.is_open() && style.fill.is_some();
        let mut code = pch(&style.marker).unwrap_or(21);
        if filled_open {
            code = pch(style.marker.strip_suffix(OPEN_SUFFIX).unwrap_or(&style.marker)).unwrap_or(code);
        }
        shapes.push((key.clone(), r(&Lit::Int(code))));
        if filled_open {
            colors.push((key.clone(), r_str(&style.color)));
            fills.push((key.clone(), r_str(style.fill.as_deref().unwrap_or(""))));
        } else if (21..=25).contains(&code) {
            colors.push((key.clone(), r_str(edge_color)));
            fills.push((key.clone(), r_str(&style.color)));
        } else {
            colors.push((key.clone(), r_str(&style.color)));
            fills.push((key.clone(), r_str(&style.color)));
        }
        sizes.push((key.clone(), rf(size_mm(style.size))));
        strokes.push((key.clone(), rf(if style.is_open() { OPEN_MARKER_EDGE } else { *edge_width })));
        if key != label {
            renamed.push((key.clone(), r_str(label)));
        }
    }
    for (name, p) in [
        ("STYLE_COLORS", &colors),
        ("STYLE_FILLS", &fills),
        ("STYLE_SHAPES", &shapes),
        ("STYLE_SIZES", &sizes),
        ("STYLE_STROKES", &strokes),
        ("STYLE_LABELS", &renamed),
    ] {
        l.push(vector(name, p));
    }
    l.push(String::new());
    l.push("# Legend rows, in order: hidden rows are left out but their points still draw".into());
    l.push("# (NULL = every STYLE_* key).".into());
    match &legend_keys {
        None => l.push("LEGEND_ROWS <- NULL".into()),
        Some(keys) if !keys.is_empty() => {
            l.push(format!("LEGEND_ROWS <- c({})", keys.iter().map(|k| r_str(k)).collect::<Vec<_>>().join(", ")))
        }
        Some(_) => l.push("LEGEND_ROWS <- character(0)  # every row is hidden".into()),
    }
    l.push(String::new());
    l.push(format!("LEGEND <- list({})", r_named(&named(&c.legend), "  ")));
    l.push(String::new());
    l.extend(inset_lines(c.inset.as_ref()));
    l.join("\n") + "\n"
}

fn numbers(values: &[Option<f64>], indent: &str) -> String {
    let items: Vec<String> = values.iter().map(|v| v.map_or("NA_real_".into(), rf)).collect();
    if items.is_empty() {
        return "numeric(0)".into();
    }
    format!("c(\n{})", wrapped_items(&items, indent, 78).join("\n"))
}

fn inset_lines(inset: Option<&InsetConfig>) -> Vec<String> {
    let mut l: Vec<String> = [
        "# The inset map, as PyMappr drew it (NULL = no inset): rect is its place in the",
        "# map's panel fraction (x, y, width, height), limits its axis limits in its own",
        "# CRS, clip_cap / band what layers are clipped to before reprojecting, and box",
        "# the outline linking the two maps, drawn on the inset or on the main map (NA",
        "# in x/y breaks the line).",
    ]
    .map(String::from)
    .to_vec();
    let Some(i) = inset else {
        l.push("INSET <- NULL".into());
        return l;
    };
    let vector = |values: Option<&[f64]>| match values {
        None => "NULL".to_string(),
        Some(v) => format!("c({})", v.iter().map(|x| rf(*x)).collect::<Vec<_>>().join(", ")),
    };
    let mut p = pairs(vec![
        ("projection", r_str(&i.projection)),
        ("crs", r_str(i.crs.as_deref().unwrap_or("EPSG:4326"))),
        ("geographic", r(&Lit::Bool(i.crs.is_none()))),
        ("rect", vector(Some(&i.rect))),
        ("lon_0", rf(i.lon_0)),
        ("lat_0", rf(i.lat_0)),
        ("min_lat", rf(i.min_lat)),
        ("max_lat", rf(i.max_lat)),
        ("lon_halfspan", rf(i.lon_halfspan)),
        ("hemisphere", r(&Lit::Bool(i.hemisphere))),
        ("clip_cap", vector(i.clip_cap.as_ref().map(|c| c.as_slice()))),
        ("band", vector(i.band.as_ref().map(|b| b.as_slice()))),
        ("limits", vector(Some(&i.limits))),
        ("points", r(&Lit::Bool(i.points))),
        ("point_scale", rf(i.point_scale)),
        ("frame_width", rf(i.frame_width)),
        (
            "clear",
            i.clear.as_ref().map_or("NULL".into(), |(corner, y)| format!("list(corner = {}, y = {})", r_str(corner), rf(*y))),
        ),
    ]);
    let layers = i
        .layers
        .iter()
        .map(|ly| layer(ly).lines().map(|line| format!("  {line}")).collect::<Vec<_>>().join("\n"))
        .collect::<Vec<_>>()
        .join(",\n");
    p.push(("layers".into(), if layers.is_empty() { "list()".into() } else { format!("list(\n{layers}\n  )") }));
    match &i.horizon {
        None => p.push(("horizon".into(), "NULL".into())),
        Some([x, y]) => p.push((
            "horizon".into(),
            format!("list(\n    x = {},\n    y = {})", numbers(x, "      "), numbers(y, "      ")),
        )),
    }
    match &i.boxed {
        None => p.push(("box".into(), "NULL".into())),
        Some(b) => p.push((
            "box".into(),
            format!(
                "list(\n    target = {}, color = {}, width = {},\n    x = {},\n    y = {})",
                r_str(&b.target),
                r_str(&b.color),
                rf(b.width),
                numbers(&b.x, "      "),
                numbers(&b.y, "      ")
            ),
        )),
    }
    l.push(format!("INSET <- list({})", r_named(&p, "  ")));
    l
}

pub fn script(c: &Config) -> String {
    header(c) + &config_block(c) + TEMPLATE
}

pub fn readme(project: &str, rproj: &str) -> String {
    format!(
        "# {project} - PyMappr map export

A ready-to-run R recreation of the PyMappr map \"{project}\"
(sf + ggplot2).

## Run it

Open `{rproj}` in RStudio, open `recreate_map.R`, and click Source.
Or, from a terminal in this folder:

    Rscript recreate_map.R

If sf or ggplot2 is missing the script tells you; install them with:

    Rscript install.R

It downloads its map data from Natural Earth into
`naturalearth_cache/` and reads your point data from the CSV files in
`data/`. The finished map is written to `map.png`.
"
    )
}
