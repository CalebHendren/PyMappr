//! PyMappr's code export tests (tests/test_codegen_*.py) that need no
//! renderer and no Python or R interpreter, ported; plus the data modes
//! RustyMappr adds.

use mappr_codegen::config::{DataMode, build_config, export_filename};
use mappr_codegen::{
    Branding, ExportOptions, InlineData, Language, generate_code, generate_working_directory, restore_data,
};
use serde_json::{Value, json};

fn opts(name: &str) -> ExportOptions {
    ExportOptions {
        project_name: name.into(),
        branding: Branding::pymappr(),
        csv_newline: "\n".into(),
        ..Default::default()
    }
}

/// codegen_helpers.make_state.
fn make_state(map: Value, extra: Value) -> Value {
    let mut state = json!({
        "datasets": [],
        "active": 0,
        "map": {
            "projection": "Robinson", "proj_lon0": "", "proj_lat0": "",
            "basemap": "simple", "continent": "World",
            "compass": true, "graticule": "5\u{b0}",
            "hide_grid_labels": false, "line_width": 1.0, "dpi": "300",
            "ocean": "blue", "lake_fill": "grey", "bathymetry": false,
            "capitals_only": false,
            "lines": {"countries": true, "rivers": true, "wadis": true, "eez": false},
            "fills": {"land": true, "disputed": false},
            "points": {"cities": true},
            "labels": {"countries": false},
        },
        "legend": {"show": true, "frame": true, "location": "upper right",
                   "fontsize": "9", "title_fontsize": "12", "columns": "2",
                   "marker_scale": "1.5", "label_spacing": "0.8", "title": ""},
        "point_alpha": 0.85,
        "view": {"xlim": [-180, 180], "ylim": [-90, 90]},
    });
    for (k, v) in map.as_object().unwrap() {
        state["map"][k] = v.clone();
    }
    for (k, v) in extra.as_object().unwrap() {
        state[k] = v.clone();
    }
    state
}

fn state() -> Value {
    make_state(json!({}), json!({}))
}

fn with(mut state: Value, datasets: Vec<Value>) -> Value {
    state["datasets"] = Value::Array(datasets);
    state
}

/// codegen_helpers.file_entry: a CSV with a State column.
fn file_entry() -> Value {
    json!({
        "name": "us_cities.csv",
        "source_path": "C:/data/us_cities.csv",
        "columns": ["name1", "lon", "lat"],
        "name_labels": ["State"],
        "rows": [["Wyoming", -107.5, 43.0], ["Colorado", -105.5, 39.0], ["Wyoming", -104.8, 41.1]],
        "group_by": "State",
        "styles": {"Wyoming": {"color": "#123456", "marker": "Star", "size": 45.0}},
    })
}

/// codegen_helpers.manual_entry: two typed-in points.
fn manual_entry(name: &str, settings: Value) -> Value {
    let mut entry = json!({
        "name": name,
        "source_path": "",
        "columns": ["name1", "name2", "lon", "lat"],
        "name_labels": ["Legend", "Label"],
        "rows": [[name, "Site A", -100.0, 38.0], [name, "Site B", 140.0, -25.0]],
        "group_by": "Legend",
        "legend_overrides": {format!("group\u{0}{name}"): {"color": "#123456", "marker": "Star", "size": 45.0}},
    });
    for (k, v) in settings.as_object().unwrap() {
        entry[k] = v.clone();
    }
    entry
}

fn beetle_entry() -> Value {
    let fixture: Value =
        serde_json::from_str(include_str!("../../../src/lib/fixtures/beetles-standard.pymappr")).unwrap();
    let mut entry = fixture["state"]["datasets"][0].clone();
    entry["name"] = json!("beetles");
    entry["color_by"] = json!("Genus");
    entry["symbol_by"] = json!("Species");
    entry["vary_symbols"] = json!(false);
    entry
}

fn code(state: &Value, language: Language) -> String {
    generate_code(state, language, InlineData::Embedded, &opts("Untitled")).unwrap().code
}

fn py(state: &Value) -> String {
    code(state, Language::Python)
}

fn r(state: &Value) -> String {
    code(state, Language::R)
}

fn files(state: &Value, language: Language, name: &str) -> Vec<(String, String)> {
    generate_working_directory(state, language, &opts(name)).unwrap()
}

fn file<'a>(files: &'a [(String, String)], name: &str) -> &'a str {
    &files.iter().find(|(n, _)| n == name).unwrap_or_else(|| panic!("no {name}")).1
}

// ------------------------------------------------------------ the basics

#[test]
fn languages_and_extensions() {
    assert_eq!(Language::parse("Python").unwrap().extension(), ".py");
    assert_eq!(Language::parse("R").unwrap().extension(), ".R");
    assert!(Language::parse("Julia").is_err());
}

#[test]
fn scripts_carry_the_attribution() {
    let s = with(state(), vec![file_entry()]);
    let want = format!("# Made with PyMappr {} - https://github.com/CalebHendren/PyMappr", mappr_codegen::tables::tables().pymappr_version);
    assert_eq!(py(&s).lines().nth(1).unwrap(), want);
    assert_eq!(r(&s).lines().next().unwrap(), want);
    assert_eq!(py(&state()).lines().next().unwrap(), "#!/usr/bin/env python3");
    let own = generate_code(&s, Language::R, InlineData::Embedded, &ExportOptions::default()).unwrap().code;
    assert!(own.starts_with("# Made with RustyMappr "));
}

#[test]
fn premade_functions_are_identical_across_maps() {
    let marker = "pre-made functions (identical for every export)";
    for language in [Language::Python, Language::R] {
        let one = code(&with(state(), vec![file_entry()]), language);
        let two = code(
            &with(make_state(json!({"projection": "Mercator", "ocean": "none"}), json!({})), vec![manual_entry("spiders", json!({}))]),
            language,
        );
        assert_eq!(one.split(marker).nth(1), two.split(marker).nth(1));
        assert_ne!(one.split(marker).next(), two.split(marker).next());
    }
}

#[test]
fn python_config_reflects_map_settings() {
    let c = py(&with(state(), vec![file_entry()]));
    for needle in [
        "MAP_CRS = '+proj=robin +lon_0=0 +datum=WGS84",
        "POINT_ALPHA = 0.85",
        "DPI = 300",
        "GRATICULE = {'interval': 5.0",
        "'admin_0_countries'",
        "'rivers_lake_centerlines'",
        "('featurecla', ['River (Intermittent)'], True)",
        "'#d4e6f4'",
        "'#c9c9c9'",
        "'populated_places_simple'",
        "'path': None",
        "State,Longitude,Latitude",
        "# originally imported from: C:/data/us_cities.csv",
        "'group_col': 'State'",
        "'#123456'",
        "'marker': '*'",
        "'Colorado'",
        "'location': 'upper right'",
        "'columns': 2",
        "'title': 'State'",
        "'title_fontsize': 12.0",
        "'marker_scale': 1.5",
        "'label_spacing': 0.8",
    ] {
        assert!(c.contains(needle), "missing {needle}");
    }
    assert!(!c.contains("boundary_lines_maritime"));
    assert!(!c.contains("'disputed'"));
}

#[test]
fn r_config_reflects_map_settings() {
    let c = r(&with(state(), vec![file_entry()]));
    for needle in [
        "MAP_CRS <- \"+proj=robin +lon_0=0 +datum=WGS84",
        "POINT_ALPHA <- 0.85",
        "DPI <- 300",
        "\"Wyoming\" = 8",
        "\"group_col\" = \"State\"",
        "\"admin_0_countries\"",
        "\"title_fontsize\" = 12.0",
        "\"marker_scale\" = 1.5",
        "\"label_spacing\" = 0.8",
    ] {
        assert!(c.contains(needle), "missing {needle}");
    }
}

#[test]
fn legend_options_default_when_absent() {
    let s = with(
        make_state(json!({}), json!({"legend": {"show": true, "frame": true, "location": "best", "fontsize": "8", "columns": "1", "title": ""}})),
        vec![file_entry()],
    );
    let p = py(&s);
    assert!(p.contains("'title_fontsize': 9.0") && p.contains("'marker_scale': 1.0") && p.contains("'label_spacing': 0.5"));
    let rc = r(&s);
    assert!(rc.contains("\"title_fontsize\" = 9.0") && rc.contains("\"label_spacing\" = 0.5"));
}

#[test]
fn legend_text_formatting_reaches_exports() {
    let s = with(
        make_state(
            json!({}),
            json!({"legend": {"show": true, "frame": true, "location": "best", "fontsize": "10", "title": "Sites",
                   "label_bold": true, "label_italic": true, "label_underline": true, "title_bold": true,
                   "title_italic": false, "title_underline": true}}),
        ),
        vec![file_entry()],
    );
    let p = py(&s);
    assert!(p.contains("'label_bold': True") && p.contains("'label_underline': True") && p.contains("'title_underline': True"));
    let rc = r(&s);
    assert!(rc.contains("\"label_bold\" = TRUE") && rc.contains("Underlined legend text"));
}

#[test]
fn lambert_origin_reaches_the_crs() {
    let s = make_state(json!({"projection": "Lambert: Europe", "proj_lon0": "15", "proj_lat0": "50"}), json!({}));
    for language in [Language::Python, Language::R] {
        let c = code(&s, language);
        assert!(c.contains("+proj=lcc") && c.contains("+lat_0=50.0 +lon_0=15.0"));
    }
}

#[test]
fn equirectangular_uses_plain_lonlat() {
    let s = make_state(json!({"projection": "Equirectangular"}), json!({}));
    assert!(py(&s).contains("MAP_CRS = None"));
    let rc = r(&s);
    assert!(rc.contains("MAP_CRS <- \"EPSG:4326\"") && rc.contains("GEOGRAPHIC <- TRUE"));
}

#[test]
fn globe_export_clips_to_the_visible_hemisphere() {
    let s = with(make_state(json!({"projection": "Globe (Orthographic)", "proj_lon0": "-100", "proj_lat0": "40"}), json!({})), vec![file_entry()]);
    let p = py(&s);
    assert!(p.contains("+proj=ortho +lat_0=40.0 +lon_0=-100.0"));
    assert!(p.contains("CLIP_CAP = (-100.0, 40.0, 88.0)"));
    assert!(p.contains("'hemisphere': True"));
    assert!(r(&s).contains("CLIP_CAP <- c(-100.0, 40.0, 88.0)"));
    assert!(py(&state()).contains("CLIP_CAP = None"));
    assert!(r(&state()).contains("CLIP_CAP <- NULL"));
}

#[test]
fn non_finite_origin_exports_the_default_centre() {
    let s = make_state(json!({"projection": "Globe (Orthographic)", "proj_lon0": "inf", "proj_lat0": "1e400"}), json!({}));
    assert!(py(&s).contains("CLIP_CAP = (0.0, 0.0, 88.0)"));
}

#[test]
fn notes_list_only_external_overlays() {
    let s = make_state(json!({"bathymetry": true, "basemap": "relief", "compass": true, "fills": {"biodiversity": true}}), json!({}));
    let c = py(&s);
    let notes = c.split("NOT reproduced").nth(1).unwrap().split("map configuration").next().unwrap();
    assert!(notes.contains("Biodiversity hotspots"));
    assert!(!notes.contains("Bathymetry") && !notes.to_lowercase().contains("basemap"));
    assert!(c.contains("BASEMAP = 'relief'") && c.contains("bathymetry_all"));
    assert!(c.split("COMPASS = ").nth(1).unwrap().lines().next().unwrap().contains("'show': True"));
}

#[test]
fn capitals_only_swaps_the_cities_layer() {
    let c = py(&make_state(json!({"capitals_only": true}), json!({})));
    assert!(c.contains("('adm0cap', ['1'], True)") && c.contains("'marker': '*'"));
    let layers = c.split("\nLAYERS = [").nth(1).unwrap().split("\n]").next().unwrap();
    assert!(!layers.contains("min_zoom_max"));
}

// ------------------------------------------------------- view and geometry

#[test]
fn missing_view_falls_back_to_padded_continent_extent() {
    let mut s = make_state(json!({"projection": "Equirectangular", "continent": "Europe"}), json!({}));
    s["view"] = json!({});
    let c = build_config(&s, DataMode::Inline(InlineData::Embedded), &opts("x")).unwrap();
    let [x0, x1, y0, y1] = c.view;
    assert!(x0 <= -25.0 && x1 >= 45.0 && y0 <= 34.0 && y1 >= 72.0);
}

#[test]
fn zoom_matches_the_renderer_formula() {
    let s = make_state(json!({"projection": "Equirectangular"}), json!({"view": {"xlim": [-90, 0], "ylim": [-20, 40]}}));
    let c = build_config(&s, DataMode::Inline(InlineData::Embedded), &opts("x")).unwrap();
    assert!((c.zoom - 2.0).abs() < 1e-3);
}

#[test]
fn figure_size_drives_export_geometry() {
    let s = make_state(json!({"projection": "Equirectangular"}), json!({"view": {"xlim": [-90, 0], "ylim": [-25, 20]}}));
    let o = ExportOptions { figure_size: Some((15.68, 8.32)), ..opts("x") };
    let c = build_config(&s, DataMode::Inline(InlineData::Embedded), &o).unwrap();
    let (w, h) = c.figsize;
    assert!((w - 15.68).abs() < 1e-9);
    let [l, b, rr, t] = c.margins;
    assert!(((w * (rr - l)) / (h * (t - b)) - 2.0).abs() < 2e-3);
}

#[test]
fn zoom_picks_the_layer_resolution() {
    let world = py(&make_state(json!({"projection": "Equirectangular"}), json!({})));
    assert!(world.contains("'scale': '110m', 'kind': 'line'"));
    let zoomed = py(&make_state(json!({"projection": "Equirectangular"}), json!({"view": {"xlim": [-10, 10], "ylim": [40, 52]}})));
    assert!(zoomed.contains("'name': 'admin_0_countries', 'category': 'cultural', 'scale': '10m'"));
}

#[test]
fn countries_off_swaps_in_continent_outlines() {
    assert!(py(&make_state(json!({"lines": {"countries": false}}), json!({}))).contains("'kind': 'continents'"));
    assert!(!py(&state()).contains("'kind': 'continents'"));
}

#[test]
fn bathymetry_becomes_stacked_fill_layers() {
    let c = py(&make_state(json!({"bathymetry": true}), json!({})));
    assert_eq!(c.matches("'name': 'bathymetry_all'").count(), 12);
    assert!(c.contains("'member': 'ne_10m_bathymetry_L_0'") && c.contains("'#103862'"));
}

#[test]
fn label_layers_reach_the_script() {
    let s = make_state(
        json!({"projection": "Equirectangular", "labels": {"countries": true, "cities": true}, "points": {"cities": true}}),
        json!({}),
    );
    let c = py(&s);
    let block = c.split("LABEL_LAYERS = [").nth(1).unwrap().split("\n]").next().unwrap();
    let keys: Vec<&str> = block.lines().filter_map(|l| l.split("'key': '").nth(1)?.split('\'').next()).collect();
    assert_eq!(keys, ["countries", "cities"]);
    assert!(block.contains("'cap': 400") && block.contains("'fontweight': 'bold'"));
    assert!(block.contains("'feature_bias': 2.0, 'point_layer': True"));
}

// ------------------------------------------------------------- datasets

#[test]
fn hidden_and_empty_datasets_are_skipped() {
    let mut hidden = file_entry();
    hidden["visible"] = json!(false);
    let c = py(&with(state(), vec![hidden]));
    assert!(!c.contains("us_cities") && c.contains("DATASETS = [\n]"));
}

#[test]
fn multi_dataset_labels_are_disambiguated() {
    let c = py(&with(state(), vec![manual_entry("Alpha", json!({"group_by": ""})), manual_entry("Beta", json!({"group_by": ""}))]));
    assert!(c.contains("'All points': 'Alpha'") && c.contains("'All points': 'Beta'"));
}

#[test]
fn attribute_mode_styles_by_two_columns() {
    let c = py(&with(state(), vec![manual_entry("spiders", json!({"symbol_by": "Label", "group_by": ""}))]));
    assert!(c.contains("'symbol_col': 'Label'") && c.contains("'Site A'") && c.contains("'Site B'"));
    assert!(c.contains("LEGEND_SECTIONS = [\n"));
}

#[test]
fn stale_color_by_is_ignored_like_the_app() {
    let c = py(&with(state(), vec![manual_entry("spiders", json!({"symbol_by": "Label", "group_by": "", "color_by": "Gone"}))]));
    assert!(c.contains("'color_col': None") && c.contains("'symbol_col': 'Label'"));
}

#[test]
fn palette_and_point_outline_reach_the_script() {
    let entry = manual_entry("spiders", json!({"color_by": "Legend", "symbol_by": "Label", "group_by": ""}));
    let s = with(make_state(json!({"palette": "Black & white"}), json!({"point_edge": {"color": "#333333", "width": 0.6}})), vec![entry]);
    let p = py(&s);
    assert!(p.contains("POINT_EDGE = {'color': '#333333', 'width': 0.6}"));
    let styles = p.split("'styles': {").nth(1).unwrap().split("        },").next().unwrap();
    assert!(styles.contains("'#000000'") && !styles.contains("'#d62728'"));
    let rc = r(&s);
    assert!(rc.contains("POINT_STROKE <- 0.6"));
    assert!(rc.split("STYLE_COLORS <- c(").nth(1).unwrap().split(')').next().unwrap().contains("\"#333333\""));
}

#[test]
fn nested_taxonomy_exports_a_nested_legend() {
    let c = py(&with(state(), vec![beetle_entry()]));
    let sections = c.split("LEGEND_SECTIONS = [").nth(1).unwrap().split("\n]").next().unwrap();
    assert!(sections.contains("('Genus / Species', ["));
    let genera: Vec<&str> = sections.lines().filter(|l| l.ends_with(", 0),")).collect();
    let species: Vec<&str> = sections.lines().filter(|l| l.ends_with(", 1),")).collect();
    assert_eq!(genera.len(), 3);
    assert!(genera[0].contains("'Eleusis'") && genera[1].contains("'Xanthopygus'") && genera[2].contains("'Plociopterus'"));
    assert_eq!(species.len(), 9);
    assert!(!sections.contains("#555555"));
}

#[test]
fn counts_option_reaches_the_exported_legend() {
    let mut s = with(state(), vec![beetle_entry()]);
    s["legend"]["counts"] = json!(true);
    let c = py(&s);
    assert!(c.contains("'Eleusis (18)'") && c.contains("'chapadensis (6)'"));
}

#[test]
fn row_overrides_reach_the_exported_legend() {
    let mut entry = beetle_entry();
    entry["legend_overrides"] = json!({
        "pair\u{0}Eleusis\u{0}chapadensis": {"label": "E. chapadensis", "color": "#123456"},
        "pair\u{0}Eleusis\u{0}andina": {"hidden": true},
    });
    let c = py(&with(state(), vec![entry]));
    assert!(c.contains("E. chapadensis") && c.contains("#123456"));
    let sections = c.split("LEGEND_SECTIONS = [").nth(1).unwrap().split("\n]").next().unwrap();
    assert!(!sections.contains("andina"));
}

#[test]
fn hidden_group_rows_keep_their_points_in_the_export() {
    let entry = manual_entry("spiders", json!({"legend_overrides": {"group\u{0}spiders": {"hidden": true}}}));
    let c = py(&with(state(), vec![entry]));
    assert!(c.contains("LEGEND_ROWS = []") && c.contains("'spiders'"));
}

#[test]
fn renamed_group_rows_carry_their_new_name_through_styles() {
    let entry = manual_entry("spiders", json!({"legend_overrides": {"group\u{0}spiders": {"label": "Araneae"}}}));
    let c = py(&with(state(), vec![entry]));
    assert!(c.contains("'label_map': {'spiders': 'Araneae'},"));
    assert!(c.contains("            'spiders': {"));
    assert!(c.contains("LEGEND_ROWS = ['Araneae']"));
}

#[test]
fn nul_characters_never_reach_the_scripts() {
    let entry = json!({
        "name": "nul\u{0}name", "source_path": "C:/data/x\u{0}.csv",
        "columns": ["name1", "lon", "lat"], "name_labels": ["Code"],
        "rows": [["a\u{0}b", 1.0, 2.0], ["c", 3.0, 4.0]], "group_by": "Code",
    });
    let s = with(state(), vec![entry]);
    for language in [Language::Python, Language::R] {
        let c = generate_code(&s, language, InlineData::Embedded, &opts("P\u{0}Q")).unwrap().code;
        assert!(!c.contains('\0'));
    }
    assert!(py(&s).contains("'name': 'nulname',"));
}

#[test]
fn names_with_escapes_and_quotes_are_valid_literals() {
    let entry = json!({
        "name": "it's \"x\"\\", "columns": ["name1", "lon", "lat"], "name_labels": ["N"],
        "rows": [["a'b\"c\\d\ne", 1.0, 2.0]], "group_by": "N",
    });
    let s = with(state(), vec![entry]);
    let p = generate_code(&s, Language::Python, InlineData::Embedded, &opts("Field\\Notes \"q\"\n")).unwrap().code;
    assert!(p.contains("\"\"\"Recreate the PyMappr map \"Field\\\\Notes 'q'\" outside PyMappr."));
    assert!(p.contains("'name': 'it\\'s \"x\"\\\\',"));
    let rc = r(&s);
    assert!(rc.contains("\"name\" = \"it's \\\"x\\\"\\\\\""));
}

// ------------------------------------------------------- working directory

#[test]
fn working_directory_python_layout() {
    let f = files(&with(state(), vec![file_entry()]), Language::Python, "My Project");
    let names: Vec<&str> = f.iter().map(|(n, _)| n.as_str()).collect();
    assert_eq!(names, ["recreate_map.py", "requirements.txt", "README.md", ".gitignore", "data/us_cities.csv"]);
    assert!(file(&f, "data/us_cities.csv").contains("State,Longitude,Latitude"));
    let script = file(&f, "recreate_map.py");
    assert!(script.contains("'path': 'data/us_cities.csv'") && script.contains("'inline_data': None"));
    assert!(file(&f, "requirements.txt").contains("geopandas"));
    assert!(file(&f, "README.md").contains("pip install -r requirements.txt"));
}

#[test]
fn working_directory_r_layout() {
    let f = files(&with(state(), vec![file_entry()]), Language::R, "My Project");
    assert!(file(&f, "recreate_map.R").contains("\"path\" = \"data/us_cities.csv\""));
    assert!(file(&f, "install.R").contains("install.packages(c(\"sf\", \"ggplot2\")"));
    assert!(file(&f, "My Project.Rproj").contains("Version: 1.0"));
    assert!(file(&f, "README.md").contains("Open `My Project.Rproj` in RStudio"));
}

#[test]
fn dataset_files_survive_case_and_reserved_names() {
    let entries = ["Sites", "sites", "CON", "nul.csv", "My Sites"].iter().map(|n| manual_entry(n, json!({}))).collect();
    let f = files(&with(state(), entries), Language::Python, "P");
    let data: Vec<&str> = f.iter().map(|(n, _)| n.as_str()).filter(|n| n.starts_with("data/")).collect();
    assert_eq!(data, ["data/Sites.csv", "data/sites_2.csv", "data/CON_.csv", "data/nul_.csv", "data/My Sites.csv"]);
    assert!(files(&state(), Language::R, "AUX").iter().any(|(n, _)| n == "AUX_.Rproj"));
}

#[test]
fn export_filename_rules() {
    let mut used = Vec::new();
    assert_eq!(export_filename("CON.csv", ".csv", &mut used, "data"), "CON_.csv");
    assert_eq!(export_filename("sites.csv.", ".csv", &mut used, "data"), "sites.csv");
    assert_eq!(export_filename(".csv", ".csv", &mut used, "data"), "data.csv");
    let mut used = Vec::new();
    assert_eq!(export_filename("NUL.tar", ".csv", &mut used, "dataset"), "NUL_.tar.csv");
    assert_eq!(export_filename("con", ".csv", &mut used, "dataset"), "con_.csv");
    assert_eq!(export_filename("Console", ".csv", &mut used, "dataset"), "Console.csv");
}

#[test]
fn templates_are_plain_ascii() {
    assert!(mappr_codegen::python::TEMPLATE.is_ascii());
    assert!(mappr_codegen::r_script::TEMPLATE.is_ascii());
}

// ------------------------------------------------------------- data modes

fn fixture_state() -> Value {
    let fixture: Value =
        serde_json::from_str(include_str!("../../../src/lib/fixtures/hornbills-orchids.pymappr")).unwrap();
    fixture["state"].clone()
}

#[test]
fn placeholder_mode_sends_no_data() {
    let s = fixture_state();
    for language in [Language::Python, Language::R] {
        let c = generate_code(&s, language, InlineData::Placeholder, &opts("x")).unwrap().code;
        assert!(c.contains("__RUSTYMAPPR_DATA_0__") && c.contains("__RUSTYMAPPR_DATA_1__"));
        for value in ["94.50885", "26.17346", "1.49385", "apifera,", "Holotype,"] {
            assert!(!c.contains(value), "{value} leaked");
        }
    }
}

#[test]
fn head_mode_keeps_the_first_rows() {
    let s = fixture_state();
    let c = generate_code(&s, Language::Python, InlineData::Head(2), &opts("x")).unwrap().code;
    assert!(c.contains("'Genus,Species,Type status,Longitude,Latitude\\nBuceros,bicornis,,94.50885,26.17346\\nBuceros,bicornis,,75.14686,14.53722\\n'"));
    assert!(!c.contains("94.89993"));
}

#[test]
fn restore_data_round_trips() {
    let s = fixture_state();
    for language in [Language::Python, Language::R] {
        let full = generate_code(&s, language, InlineData::Embedded, &opts("x")).unwrap().code;
        for mode in [InlineData::Placeholder, InlineData::Head(3)] {
            let partial = generate_code(&s, language, mode, &opts("x")).unwrap().code;
            assert_ne!(partial, full);
            let back = restore_data(&partial, &s, language, mode, "\n");
            assert_eq!(back.restored, [0, 1]);
            assert!(back.missing.is_empty());
            assert_eq!(back.code, full, "{language:?} {mode:?}");
        }
    }
    // Stripping a full script gives the generated partial one.
    for mode in [InlineData::Placeholder, InlineData::Head(2)] {
        let full = generate_code(&s, Language::R, InlineData::Embedded, &opts("x")).unwrap().code;
        let partial = generate_code(&s, Language::R, mode, &opts("x")).unwrap().code;
        assert_eq!(mappr_codegen::strip_data(&full, &s, Language::R, mode, "\n").code, partial);
    }
    // Edited elsewhere, quotes changed: still found.
    let partial = generate_code(&s, Language::Python, InlineData::Placeholder, &opts("x")).unwrap().code;
    let edited = partial.replace("'__RUSTYMAPPR_DATA_1__'", "\"\"\"__RUSTYMAPPR_DATA_1__\"\"\"").replace("'__RUSTYMAPPR_DATA_0__'", "");
    let back = restore_data(&edited, &s, Language::Python, InlineData::Placeholder, "\n");
    assert_eq!((back.restored, back.missing), (vec![1], vec![0]));
    assert!(back.code.contains("Ophrys,apifera"));
}
