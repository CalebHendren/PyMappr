"""Code export: renderer fidelity, datasets, groups and styles, the nested
legend, and per-row legend customization."""

import re
from pathlib import Path

import pandas as pd
import pytest

from pymappr.export import codegen
from pymappr.files.data_loader import combine_name_columns
from pymappr.files.projects import entry_from_dict
from pymappr.styling.legend import row_key
from pymappr.styling.styles import BLACK_AND_WHITE, BLACK_AND_WHITE_NAME

from codegen_helpers import (make_state, manual_entry, file_entry, all_styles,
                             exec_python)


# ------------------------------------------------- renderer fidelity bits

def test_layers_carry_true_renderer_zorder():
    code = codegen.generate_code(make_state(), [file_entry()], "Python")
    ns = exec_python(code)
    by_key = {}
    for layer in ns["LAYERS"]:
        by_key[layer["name"], layer.get("member")] = layer
    zs = [layer["z"] for layer in ns["LAYERS"]]
    assert zs == sorted(zs)
    # Ocean fill below land fill below country lines, like the renderer.
    kinds = {layer["kind"] for layer in ns["LAYERS"]}
    assert {"fill", "line", "point"} <= kinds
    fills = [layer for layer in ns["LAYERS"] if layer["kind"] == "fill"]
    lines = [layer for layer in ns["LAYERS"] if layer["kind"] == "line"]
    assert max(f["z"] for f in fills) < max(line["z"] for line in lines)


def test_zoom_picks_the_layer_resolution():
    # Zoomed to the world -> 110m countries; zoomed to a country -> 10m.
    world = codegen.generate_code(
        make_state(map={"projection": "Equirectangular"},
                   view={"xlim": [-180, 180], "ylim": [-90, 90]}),
        [], "Python")
    assert "'scale': '110m', 'kind': 'line'" in world
    zoomed = codegen.generate_code(
        make_state(map={"projection": "Equirectangular"},
                   view={"xlim": [-10, 10], "ylim": [40, 52]}),
        [], "Python")
    assert "'name': 'admin_0_countries', 'category': 'cultural', " \
           "'scale': '10m'" in zoomed


def test_countries_off_swaps_in_continent_outlines():
    state = make_state(map={"lines": {"countries": False}})
    code = codegen.generate_code(state, [], "Python")
    assert "'kind': 'continents'" in code
    on = codegen.generate_code(make_state(), [], "Python")
    assert "'kind': 'continents'" not in on


def test_city_markers_are_zoom_culled():
    state = make_state(map={"projection": "Equirectangular"},
                       view={"xlim": [-180, 180], "ylim": [-90, 90]})
    code = codegen.generate_code(state, [], "Python")
    ns = exec_python(code)
    cities = [layer for layer in ns["LAYERS"]
              if layer["kind"] == "point"][0]
    # zoom 0 + bias 2.0, like the app's fade-in rule.
    assert cities["min_zoom_max"] == pytest.approx(2.0, abs=1e-3)
    # Capitals-only shows every capital (bias 99 disables culling).
    caps = codegen.generate_code(
        make_state(map={"capitals_only": True}), [], "Python")
    ns2 = exec_python(caps)
    capitals = [layer for layer in ns2["LAYERS"]
                if layer["kind"] == "point"][0]
    assert "min_zoom_max" not in capitals


def test_bathymetry_becomes_stacked_fill_layers():
    code = codegen.generate_code(
        make_state(map={"bathymetry": True}), [], "Python")
    ns = exec_python(code)
    depths = [layer for layer in ns["LAYERS"]
              if layer["name"] == "bathymetry_all"]
    assert len(depths) == 12
    assert depths[0]["member"] == "ne_10m_bathymetry_L_0"
    assert depths[0]["color"] == "#e3f2fa"      # shallow
    assert depths[-1]["color"] == "#103862"     # deep
    assert depths[0]["z"] < depths[-1]["z"]


def test_label_layers_reach_the_script():
    state = make_state(map={"projection": "Equirectangular",
                            "labels": {"countries": True, "cities": True},
                            "points": {"cities": True}})
    code = codegen.generate_code(state, [], "Python")
    ns = exec_python(code)
    keys = [spec["key"] for spec in ns["LABEL_LAYERS"]]
    assert keys == ["countries", "cities"]
    countries = ns["LABEL_LAYERS"][0]
    assert countries["cap"] == 400
    assert countries["font"]["fontweight"] == "bold"
    cities = ns["LABEL_LAYERS"][1]
    assert cities["point_layer"] is True
    assert cities["feature_bias"] == 2.0


def test_marker_styling_matches_the_app():
    # Filled markers carry the point outline (white for a project saved
    # before it was settable); open markers outline-only.
    code = codegen.generate_code(make_state(), [manual_entry()], "Python")
    ns = exec_python(code)
    assert ns["POINT_EDGE"] == {"color": "#ffffff", "width": 0.5}
    paint = ns["marker_paint"]
    assert paint({"color": "#123456", "open": False}) == ("#123456",
                                                          "#ffffff", 0.5)
    assert paint({"color": "#123456", "open": True}) == ("none", "#123456",
                                                         1.2)
    # Frame opacity is a setting now, so the call reads it from LEGEND
    # rather than hard-coding it - but it still defaults to 0.85.
    assert 'framealpha=LEGEND["frame_alpha"]' in code
    assert "'frame_alpha': 0.85" in code


def test_attribute_mode_emits_sectioned_legend():
    entry = manual_entry(symbol_by="Label", group_by="")
    code = codegen.generate_code(make_state(), [entry], "Python")
    ns = exec_python(code)
    sections = ns["LEGEND_SECTIONS"]
    assert sections is not None
    titles = [title for title, _entries in sections]
    assert titles == ["Label"]
    labels = [label for label, _style, _depth in sections[0][1]]
    assert labels == ["Site A", "Site B"]
    # No color column to nest under, so this is a plain symbol key: neutral
    # swatches at depth 0, like the app.
    assert sections[0][1][0][1]["color"] == "#555555"
    assert all(depth == 0 for _label, _style, depth in sections[0][1])
    # Plain mode has no sections.
    plain = codegen.generate_code(make_state(), [manual_entry()], "Python")
    assert "LEGEND_SECTIONS = None" in plain


def test_raster_basemap_is_reproduced():
    code = codegen.generate_code(
        make_state(map={"basemap": "relief"}), [], "Python")
    assert "BASEMAP = 'relief'" in code
    assert "NE1_50M_SR_W" in code
    assert "BASEMAP_IMG_SIZE = (5400, 2700)" in code  # PyMappr's resample
    off = codegen.generate_code(make_state(), [], "Python")
    assert "BASEMAP = 'simple'" in off


def test_compass_is_reproduced():
    code = codegen.generate_code(make_state(), [], "Python")
    compass = code.split("COMPASS = ")[1].splitlines()[0]
    assert "'show': True" in compass
    assert "'position': 'upper right'" in compass
    assert 'arrowstyle="-|>,head_width=0.28,head_length=0.55"' in code


# -------------------------------------------- datasets, groups, and styles

def test_manual_dataset_is_embedded_inline():
    code = codegen.generate_code(make_state(), [manual_entry()], "Python")
    assert "Legend,Label,Longitude,Latitude" in code
    assert "-100.0,38.0" in code and "140.0,-25.0" in code
    code_r = codegen.generate_code(make_state(), [manual_entry()], "R")
    assert "Legend,Label,Longitude,Latitude" in code_r


def test_file_dataset_is_embedded_inline_for_single_file_export():
    # The single-file export is self-contained: file-based data is
    # embedded inline (normalized to labels + Longitude/Latitude) instead
    # of pointing at a path that may not exist when the script is moved.
    for language in codegen.LANGUAGES:
        code = codegen.generate_code(make_state(), [file_entry()], language)
        assert "State,Longitude,Latitude" in code
        assert "Wyoming,-107.5,43.0" in code
        # The original path survives only as a provenance comment.
        assert "originally imported from: C:/data/us_cities.csv" in code
    py = codegen.generate_code(make_state(), [file_entry()], "Python")
    assert "'path': None" in py
    assert "'lon_col': 'Longitude'" in py and "'lat_col': 'Latitude'" in py


def test_hidden_and_empty_datasets_are_skipped():
    hidden = file_entry()
    hidden.visible = False
    code = codegen.generate_code(make_state(), [hidden], "Python")
    assert "us_cities" not in code
    assert "DATASETS = [\n]" in code


def test_multi_dataset_labels_are_disambiguated():
    # Two datasets without grouping both render as "All points"; the
    # legend must use the dataset names instead.
    a = manual_entry("Alpha", group_by="")
    b = manual_entry("Beta", group_by="")
    code = codegen.generate_code(make_state(), [a, b], "Python")
    assert "'All points': 'Alpha'" in code
    assert "'All points': 'Beta'" in code


def test_attribute_mode_styles_by_two_columns():
    entry = manual_entry(symbol_by="Label", group_by="")
    code = codegen.generate_code(make_state(), [entry], "Python")
    assert "'symbol_col': 'Label'" in code
    # One style per per-point value, like the app's two-attribute mode.
    assert "'Site A'" in code and "'Site B'" in code


def test_palette_and_point_outline_reach_the_script():
    entry = manual_entry(color_by="Legend", symbol_by="Label", group_by="")
    state = make_state(map={"palette": BLACK_AND_WHITE_NAME},
                       point_edge={"color": "#333333", "width": 0.6})
    ns = exec_python(codegen.generate_code(state, [entry], "Python"))
    assert ns["POINT_EDGE"] == {"color": "#333333", "width": 0.6}
    # Colours come from the map's palette, not always the default one.
    colors = {style["color"] for style in all_styles(ns).values()}
    assert colors == {BLACK_AND_WHITE[0]}
    r_code = codegen.generate_code(state, [entry], "R")
    assert "POINT_STROKE <- 0.6" in r_code
    style_colors = r_code.split("STYLE_COLORS <- c(")[1].split(")")[0]
    assert '"#333333"' in style_colors


def test_an_ungrouped_dataset_draws_in_its_own_style():
    # The script used to key these points by the dataset name while STYLES
    # held "All points", so they fell back to a grey default.
    entry = manual_entry(group_by="")
    ns = exec_python(codegen.generate_code(make_state(), [entry], "Python"))
    spec = ns["DATASETS"][0]
    labels = ns["point_labels"](ns["load_points"](spec), spec)
    assert set(labels) <= set(spec["styles"])


def test_combined_name_column_is_exported():
    entry = manual_entry()
    entry.dataset, label = combine_name_columns(entry.dataset,
                                                ["Legend", "Label"])
    entry.group_by = label
    ns = exec_python(codegen.generate_code(make_state(), [entry], "Python"))
    spec = ns["DATASETS"][0]
    assert spec["group_col"] == "Legend Label"
    labels = ns["point_labels"](ns["load_points"](spec), spec)
    assert list(labels) == ["spiders Site A", "spiders Site B"]


# ----------------------------------------------------------- nested legend

def beetle_entry():
    """The shipped taxonomy sample: genus/species, perfectly nested."""
    frame = pd.read_csv(Path(__file__).resolve().parent.parent
                        / "sample_data" / "south_america_beetles.csv")
    return entry_from_dict({
        "name": "beetles",
        "columns": ["name1", "name2", "lon", "lat"],
        "name_labels": ["Genus", "Species"],
        "rows": [[r.Genus, r.Species, r.Longitude, r.Latitude]
                 for r in frame.itertuples()],
        "color_by": "Genus",
        "symbol_by": "Species",
    })


def test_nested_taxonomy_exports_a_nested_legend():
    code = codegen.generate_code(make_state(), [beetle_entry()], "Python")
    ns = exec_python(code)
    sections = ns["LEGEND_SECTIONS"]
    # One nested key, not a colour key plus a symbol key.
    assert [title for title, _rows in sections] == ["Genus / Species"]
    rows = sections[0][1]
    genera = [label for label, _style, depth in rows if depth == 0]
    species = [label for label, _style, depth in rows if depth == 1]
    assert genera == ["Eleusis", "Xanthopygus", "Plociopterus"]
    assert len(species) == 9
    # Species swatches carry their genus's colour, never the neutral grey.
    assert all(style["color"] != "#555555" for _label, style, _d in rows)
    # And the map spends three shapes, not nine.
    assert len({style["marker"] for _label, style, depth in rows
                if depth == 1}) == 3


def test_exported_nested_legend_draws():
    # The generated add_legend must handle the depth field end to end.
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    code = codegen.generate_code(make_state(), [beetle_entry()], "Python")
    ns = exec_python(code)
    fig = matplotlib.figure.Figure()
    ax = fig.add_subplot(111)
    ns["add_legend"](ax)  # builds its own handles from LEGEND_SECTIONS
    legend = ax.get_legend()
    assert legend is not None
    texts = [t.get_text() for t in legend.get_texts()]
    # Genus rows sit one indent in, species rows two.
    assert "   Eleusis" in texts
    assert "      chapadensis" in texts


def test_counts_option_reaches_the_exported_legend():
    state = make_state()
    state["legend"] = {**state["legend"], "counts": True}
    ns = exec_python(codegen.generate_code(state, [beetle_entry()], "Python"))
    labels = [label for label, _s, _d in ns["LEGEND_SECTIONS"][0][1]]
    assert "Eleusis (18)" in labels and "chapadensis (6)" in labels


# ------------------------------------------------- per-row customization


def test_row_overrides_reach_the_exported_legend():
    entry = beetle_entry()
    entry.legend_overrides = {
        row_key("pair", "Eleusis", "chapadensis"): {"label": "E. chapadensis",
                                                    "color": "#123456"},
        row_key("pair", "Eleusis", "andina"): {"hidden": True},
    }
    code = codegen.generate_code(make_state(), [entry], "Python")
    assert "E. chapadensis" in code
    assert "#123456" in code
    # A hidden row leaves the legend but keeps its points, so the section
    # loses the row while the dataset still carries every point.
    sections = re.search(r"LEGEND_SECTIONS = \[(.*?)\n\]", code, re.S).group(1)
    assert "andina" not in sections


def test_hidden_group_rows_keep_their_points_in_the_export():
    entry = manual_entry()
    entry.legend_overrides = {row_key("group", "spiders"): {"hidden": True}}
    code = codegen.generate_code(make_state(), [entry], "Python")
    # Out of the legend...
    assert "LEGEND_ROWS = []" in code
    # ...but still styled and drawn.
    assert "'spiders'" in code


def test_renamed_group_rows_carry_their_new_name_through_styles():
    entry = manual_entry()
    entry.legend_overrides = {row_key("group", "spiders"): {"label": "Araneae"}}
    code = codegen.generate_code(make_state(), [entry], "Python")
    ns = exec_python(code)
    spec = ns["DATASETS"][0]
    # Styles are keyed by the group value; label_map gives the row's text.
    assert spec["label_map"] == {"spiders": "Araneae"}
    assert "spiders" in spec["styles"]
    assert ns["LEGEND_ROWS"] == ["Araneae"]
