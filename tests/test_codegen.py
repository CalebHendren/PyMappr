import ast
import io
import math
import os
import re
import shutil
import subprocess
import sys
import types
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from pymappr.export import codegen
from pymappr.files.data_loader import (build_manual_dataset,
                                       combine_name_columns)
from pymappr.files.projects import DatasetEntry, entry_from_dict
from pymappr.geo.projections import get_projection
from pymappr.styling.layout import layout_points
from pymappr.styling.legend import LegendOptions, row_key
from pymappr.styling.styles import (BLACK_AND_WHITE, BLACK_AND_WHITE_NAME,
                                    DEFAULT_PALETTE)


def make_state(**overrides):
    state = {
        "datasets": [],
        "active": 0,
        "map": {
            "projection": "Robinson", "proj_lon0": "", "proj_lat0": "",
            "basemap": "simple", "continent": "World",
            "compass": True, "graticule": "5\N{DEGREE SIGN}",
            "hide_grid_labels": False, "line_width": 1.0, "dpi": "300",
            "ocean": "blue", "lake_fill": "grey", "bathymetry": False,
            "capitals_only": False,
            "lines": {"countries": True, "rivers": True, "wadis": True,
                      "eez": False},
            "fills": {"land": True, "disputed": False},
            "points": {"cities": True},
            "labels": {"countries": False},
        },
        "legend": {"show": True, "frame": True, "location": "upper right",
                   "fontsize": "9", "title_fontsize": "12", "columns": "2",
                   "marker_scale": "1.5", "label_spacing": "0.8",
                   "title": ""},
        "point_alpha": 0.85,
        "view": {"xlim": [-180, 180], "ylim": [-90, 90]},
    }
    state["map"].update(overrides.pop("map", {}))
    state.update(overrides)
    return state


def manual_entry(name="spiders", **kwargs):
    dataset = build_manual_dataset(
        name, "38,-100, Site A\n-25,140, Site B\n")
    defaults = dict(dataset=dataset, name=name, group_by="Legend",
                    legend_overrides={row_key("group", name): {
                        "color": "#123456", "marker": "Star", "size": 45.0}})
    defaults.update(kwargs)
    return DatasetEntry(**defaults)


def file_entry():
    """A dataset as if imported from a CSV with a State name column."""
    return entry_from_dict({
        "name": "us_cities.csv",
        "source_path": "C:/data/us_cities.csv",
        "columns": ["name1", "lon", "lat"],
        "name_labels": ["State"],
        "rows": [["Wyoming", -107.5, 43.0], ["Colorado", -105.5, 39.0],
                 ["Wyoming", -104.8, 41.1]],
        "group_by": "State",
        "styles": {"Wyoming": {"color": "#123456", "marker": "Star",
                               "size": 45.0}},
    })


def find_rscript() -> str | None:
    """Rscript on PATH, else the newest one in a standard Windows install
    (R's installer does not put itself on PATH)."""
    found = shutil.which("Rscript")
    if found:
        return found
    candidates = sorted(Path("C:/Program Files/R").glob("R-*/bin/Rscript.exe"))
    return str(candidates[-1]) if candidates else None


def _rscript():
    path = find_rscript()
    if path is None:
        pytest.skip("Rscript is not installed (not on PATH or in "
                    "C:/Program Files/R)")
    return path


def assert_parses_as_r(code):
    """Parse generated R with a real R interpreter; skip, visibly, when
    there is none."""
    rscript = _rscript()
    result = subprocess.run(
        [rscript, "-e", "invisible(parse(file('stdin'), encoding = 'UTF-8'))"],
        input=code.encode("utf-8"), capture_output=True)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")


def all_styles(ns):
    """Every dataset's label -> style, merged (for single-dataset maps)."""
    return {label: style for spec in ns["DATASETS"]
            for label, style in spec["styles"].items()}


def exec_python(code):
    """Run a generated script's definitions with geopandas stubbed out
    (main() stays unexecuted behind the __main__ guard)."""
    fake = types.ModuleType("geopandas")
    fake.read_file = lambda *a, **k: None
    fake.GeoDataFrame = object
    fake.GeoSeries = object
    fake.points_from_xy = lambda *a, **k: None
    saved = sys.modules.get("geopandas")
    sys.modules["geopandas"] = fake
    try:
        namespace = {"__name__": "recreate_map"}
        exec(compile(code, "recreate_map.py", "exec"), namespace)
    finally:
        if saved is None:
            del sys.modules["geopandas"]
        else:
            sys.modules["geopandas"] = saved
    return namespace


# ------------------------------------------------------------ the basics

def test_languages_and_extensions():
    assert codegen.LANGUAGES == ("Python", "R")
    assert codegen.CODE_EXTENSIONS == {"Python": ".py", "R": ".R"}


def test_unknown_language_rejected():
    with pytest.raises(ValueError):
        codegen.generate_code(make_state(), [], "Julia")


def test_python_output_is_valid_and_placeholder_free():
    code = codegen.generate_code(make_state(), [file_entry()], "Python",
                                 "My Project")
    compile(code, "recreate_map.py", "exec")  # real syntax check
    assert not re.search(r"\b(TODO|FIXME)\b", code)
    assert '"My Project"' in code
    assert "from pre-made function templates and" in code
    assert "no AI involved" not in code


def test_r_output_is_valid_and_placeholder_free():
    code = codegen.generate_code(make_state(), [file_entry()], "R",
                                 "My Project")
    assert_parses_as_r(code)
    assert not re.search(r"\b(TODO|FIXME)\b", code)
    assert "library(sf)" in code
    assert "library(ggplot2)" in code


def test_scripts_carry_pymappr_attribution():
    from pymappr import __version__
    for language in codegen.LANGUAGES:
        code = codegen.generate_code(make_state(), [file_entry()], language)
        first = code.splitlines()[0 if language == "R" else 1]
        assert first == (f"# Made with PyMappr {__version__} - "
                         "https://github.com/CalebHendren/PyMappr")
    # The Python shebang still comes first so the script stays executable.
    py = codegen.generate_code(make_state(), [], "Python")
    assert py.splitlines()[0] == "#!/usr/bin/env python3"


def test_premade_functions_are_identical_across_maps():
    """The function templates are pre-made: only the config block above
    them may differ between two different maps."""
    marker = "pre-made functions (identical for every export)"
    for language in codegen.LANGUAGES:
        one = codegen.generate_code(make_state(), [file_entry()], language)
        two = codegen.generate_code(
            make_state(map={"projection": "Mercator", "ocean": "none"}),
            [manual_entry()], language)
        assert one.split(marker)[1] == two.split(marker)[1]
        assert one.split(marker)[0] != two.split(marker)[0]


# ------------------------------------------------------- settings baked in

def test_python_config_reflects_map_settings():
    code = codegen.generate_code(make_state(), [file_entry()], "Python")
    assert "MAP_CRS = '+proj=robin +lon_0=0 +datum=WGS84" in code
    assert "POINT_ALPHA = 0.85" in code
    assert "DPI = 300" in code
    assert "GRATICULE = {'interval': 5.0" in code
    # Enabled layers, including derived ones and the ocean/lake fills.
    assert "'admin_0_countries'" in code
    assert "'rivers_lake_centerlines'" in code
    assert "('featurecla', ['River (Intermittent)'], True)" in code
    assert "'#d4e6f4'" in code  # blue ocean fill
    assert "'#c9c9c9'" in code  # grey lakes fill
    assert "'populated_places_simple'" in code
    # Disabled layers stay out.
    assert "boundary_lines_maritime" not in code
    assert "'disputed'" not in code
    # Dataset + styling: file data is embedded inline (self-contained),
    # with the original path kept only as a provenance comment.
    assert "'path': None" in code
    assert "State,Longitude,Latitude" in code  # normalized inline CSV
    assert "# originally imported from: C:/data/us_cities.csv" in code
    assert "'group_col': 'State'" in code
    assert "'#123456'" in code and "'marker': '*'" in code
    assert "'Colorado'" in code  # default style assigned to the 2nd group
    assert "'location': 'upper right'" in code and "'columns': 2" in code
    assert "'title': 'State'" in code  # defaults to the group-by column
    # Legend customization options reach the matplotlib legend call.
    assert "'title_fontsize': 12.0" in code
    assert "'marker_scale': 1.5" in code
    assert "'label_spacing': 0.8" in code
    assert 'markerscale=LEGEND["marker_scale"]' in code
    assert 'labelspacing=LEGEND["label_spacing"]' in code
    assert 'title_fontsize=LEGEND["title_fontsize"]' in code


def test_r_config_reflects_map_settings():
    code = codegen.generate_code(make_state(), [file_entry()], "R")
    assert 'MAP_CRS <- "+proj=robin +lon_0=0 +datum=WGS84' in code
    assert "POINT_ALPHA <- 0.85" in code
    assert "DPI <- 300" in code
    assert '"Wyoming" = 8' in code  # Star -> pch 8
    assert '"group_col" = "State"' in code
    assert 'naturalearth.s3.amazonaws.com' in code
    assert '"admin_0_countries"' in code
    # Legend customization options reach the ggplot2 legend/theme.
    assert '"title_fontsize" = 12.0' in code
    assert '"marker_scale" = 1.5' in code
    assert '"label_spacing" = 0.8' in code


def test_legend_options_default_when_absent():
    # Projects saved before these options existed omit the new keys; the
    # export must fall back to sensible defaults instead of raising.
    state = make_state(legend={"show": True, "frame": True,
                               "location": "best", "fontsize": "8",
                               "columns": "1", "title": ""})
    py = codegen.generate_code(state, [file_entry()], "Python")
    assert "'title_fontsize': 9.0" in py
    assert "'marker_scale': 1.0" in py
    assert "'label_spacing': 0.5" in py
    r = codegen.generate_code(state, [file_entry()], "R")
    assert '"title_fontsize" = 9.0' in r
    assert '"marker_scale" = 1.0' in r
    assert '"label_spacing" = 0.5' in r


def test_legend_text_formatting_reaches_exports():
    state = make_state(legend={"show": True, "frame": True, "location": "best",
                               "fontsize": "10", "title": "Sites",
                               "label_bold": True, "label_italic": True,
                               "label_underline": True, "title_bold": True,
                               "title_italic": False, "title_underline": True})
    py = codegen.generate_code(state, [file_entry()], "Python")
    assert "'label_bold': True" in py
    assert "'label_underline': True" in py
    assert "'title_underline': True" in py
    # The Python export styles and underlines legend text.
    assert "style_legend(ax.figure, leg" in py
    r = codegen.generate_code(state, [file_entry()], "R")
    assert '"label_bold" = TRUE' in r
    # Underline is unsupported in ggplot2 element_text: it is called out.
    assert "Underlined legend text" in r


def test_lambert_origin_reaches_the_crs():
    state = make_state(map={"projection": "Lambert: Europe",
                            "proj_lon0": "15", "proj_lat0": "50"})
    for language in codegen.LANGUAGES:
        code = codegen.generate_code(state, [], language)
        assert "+proj=lcc" in code
        assert "+lat_0=50.0 +lon_0=15.0" in code


def test_equirectangular_uses_plain_lonlat():
    # The app draws the plain projection without reprojecting at all; the
    # export mirrors that with MAP_CRS = None (identity).
    code = codegen.generate_code(
        make_state(map={"projection": "Equirectangular"}), [], "Python")
    assert "MAP_CRS = None" in code
    r = codegen.generate_code(
        make_state(map={"projection": "Equirectangular"}), [], "R")
    assert 'MAP_CRS <- "EPSG:4326"' in r
    assert "GEOGRAPHIC <- TRUE" in r


def test_globe_export_clips_to_the_visible_hemisphere():
    state = make_state(map={"projection": "Globe (Orthographic)",
                            "proj_lon0": "-100", "proj_lat0": "40"})
    py = codegen.generate_code(state, [file_entry()], "Python")
    compile(py, "globe.py", "exec")
    assert "+proj=ortho +lat_0=40.0 +lon_0=-100.0" in py
    assert "CLIP_CAP = (-100.0, 40.0, 88.0)" in py
    assert "'hemisphere': True" in py
    r = codegen.generate_code(state, [file_entry()], "R")
    assert_parses_as_r(r)
    assert "CLIP_CAP <- c(-100.0, 40.0, 88.0)" in r


def test_non_globe_export_leaves_clipping_off():
    for language, none in (("Python", "CLIP_CAP = None"),
                           ("R", "CLIP_CAP <- NULL")):
        code = codegen.generate_code(
            make_state(map={"projection": "Robinson"}), [], language)
        assert none in code


def test_globe_cap_polygon_runtime_clips_and_stays_finite():
    """The pre-made cap_polygon/to_map_crs actually run: clip whole-world
    geometry to the near hemisphere and reproject without infinities."""
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import Polygon

    state = make_state(map={"projection": "Globe (Orthographic)",
                            "proj_lon0": "-100", "proj_lat0": "40"})
    py = codegen.generate_code(state, [], "Python")
    namespace: dict = {}
    exec(py.replace('if __name__ == "__main__":\n    main()', ""),
         namespace)
    polys = [Polygon([(lon, lat), (lon + 20, lat), (lon + 20, lat + 20),
                      (lon, lat + 20)])
             for lon in range(-180, 180, 20) for lat in range(-80, 80, 20)]
    gdf = gpd.GeoDataFrame(geometry=polys, crs="EPSG:4326")
    projected = namespace["to_map_crs"](gdf)
    assert 0 < len(projected) < len(gdf)  # far hemisphere dropped
    coords = np.concatenate([np.asarray(geom.exterior.coords)
                             for geom in projected.geometry
                             if not geom.is_empty])
    assert np.isfinite(coords).all()


def test_notes_list_only_external_overlays():
    # Bathymetry, the raster basemap, the compass, and map labels are
    # now reproduced by the Python script; only the optional external
    # overlays stay in the not-reproduced notes.
    state = make_state(map={"bathymetry": True, "basemap": "relief",
                            "compass": True,
                            "fills": {"biodiversity": True}})
    code = codegen.generate_code(state, [], "Python")
    assert "NOT reproduced" in code
    assert "Biodiversity hotspots" in code
    # Isolate just the note comment lines, before the map-configuration block.
    notes_block = code.split("NOT reproduced")[1].split("map configuration")[0]
    assert "Bathymetry" not in notes_block
    assert "basemap" not in notes_block.lower()
    assert "compass" not in notes_block.lower()
    # ... and the features themselves are configured for drawing.
    assert "BASEMAP = 'relief'" in code
    assert "bathymetry_all" in code
    assert "'show': True" in code.split("COMPASS = ")[1].splitlines()[0]


def test_capitals_only_swaps_the_cities_layer():
    code = codegen.generate_code(
        make_state(map={"capitals_only": True}), [], "Python")
    assert "('adm0cap', ['1'], True)" in code
    assert "'marker': '*'" in code  # the capitals star


# ------------------------------------------------------- view and geometry

def test_view_is_exported_verbatim():
    # The stored view (projected map coordinates) reaches the script
    # unchanged - the exported map frames exactly what the app showed.
    projection = get_projection("Robinson")
    x0, x1 = projection.forward([-30.0, 60.0], [0.0, 0.0])[0]
    y = projection.forward([0.0, 0.0], [-10.0, 40.0])[1]
    state = make_state(view={"xlim": [float(x0), float(x1)],
                             "ylim": [float(y[0]), float(y[1])]})
    code = codegen.generate_code(state, [], "Python")
    assert f"VIEW = ({round(float(x0), 6)}" in code
    r = codegen.generate_code(state, [], "R")
    assert f"VIEW <- c({round(float(x0), 6)}" in r


def test_missing_view_falls_back_to_padded_continent_extent():
    state = make_state(view={},
                       map={"projection": "Equirectangular",
                            "continent": "Europe"})
    config = codegen.build_config(state, [])
    x0, x1, y0, y1 = config["view"]
    # Europe is (-25, 45, 34, 72); the box is padded to the canvas aspect
    # so it must contain the preset.
    assert x0 <= -25 and x1 >= 45
    assert y0 <= 34 and y1 >= 72


def test_zoom_matches_the_renderer_formula():
    state = make_state(map={"projection": "Equirectangular"},
                       view={"xlim": [-90, 0], "ylim": [-20, 40]})
    config = codegen.build_config(state, [])
    assert config["zoom"] == pytest.approx(math.log2(360.0 / 90.0), abs=1e-3)


def test_figure_size_drives_export_geometry():
    state = make_state(map={"projection": "Equirectangular"},
                       view={"xlim": [-90, 0], "ylim": [-25, 20]})
    config = codegen.build_config(state, [], figure_size=(15.68, 8.32))
    width, height = config["figsize"]
    assert width == pytest.approx(15.68)
    # Square map units: axes width/height ratio equals the view ratio.
    left, bottom, right, top = config["margins"]
    axes_w = width * (right - left)
    axes_h = height * (top - bottom)
    assert axes_w / axes_h == pytest.approx(90.0 / 45.0, rel=1e-3)


def test_graticule_labels_follow_the_app():
    # Labeled ticks only on the plain projection with labels not hidden.
    on = codegen.build_config(make_state(
        map={"projection": "Equirectangular"}), [])
    assert on["graticule"] == {"interval": 5.0, "labels": True}
    assert on["margins"] == codegen.MARGINS_WITH_TICKS
    hidden = codegen.build_config(make_state(
        map={"projection": "Equirectangular",
             "hide_grid_labels": True}), [])
    assert hidden["graticule"]["labels"] is False
    assert hidden["margins"] == codegen.MARGINS_PLAIN
    curved = codegen.build_config(make_state(), [])  # Robinson
    assert curved["graticule"]["labels"] is False


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


# --------------------------------- executing the generated pre-made code

def test_generated_python_functions_actually_run():
    code = codegen.generate_code(make_state(), [manual_entry()], "Python")
    ns = exec_python(code)

    # The inline dataset loads through the real pre-made loader.
    spec = ns["DATASETS"][0]
    df = ns["load_points"](spec)
    assert len(df) == 2
    assert list(df["_lon"]) == [-100.0, 140.0]
    assert list(df["_lat"]) == [38.0, -25.0]

    # Labels follow the group column and the label map.
    labels = ns["point_labels"](df, spec)
    assert list(labels) == ["spiders", "spiders"]
    assert spec["styles"]["spiders"]["color"] == "#123456"

    # Column auto-detection matches PyMappr's import hints.
    frame = pd.DataFrame({"Site": ["a"], "LONGITUDE": [1.0],
                          "Lat": [2.0]})
    assert ns["find_column"](frame, None, ns["LON_HINTS"],
                             "longitude") == "LONGITUDE"
    assert ns["find_column"](frame, None, ns["LAT_HINTS"],
                             "latitude") == "Lat"
    with pytest.raises(SystemExit):
        ns["find_column"](frame, "Missing", (), "longitude")

    # The pre-made layer filter: case-insensitive columns, numbers that
    # compare like numbers ("1" matches 1.0), and keep=False inversion.
    gdf = pd.DataFrame({"FEATURECLA": ["Desert", "Plateau", "desert"],
                        "adm0cap": [1.0, 0.0, 1.0]})
    kept = ns["filter_layer"](gdf, ("featurecla", ["Desert"], True))
    assert list(kept.index) == [0, 2]
    capitals = ns["filter_layer"](gdf, ("ADM0CAP", ["1"], True))
    assert list(capitals.index) == [0, 2]
    dropped = ns["filter_layer"](gdf, ("featurecla", ["Desert"], False))
    assert list(dropped.index) == [1]
    assert ns["filter_layer"](gdf, None) is gdf


def test_generated_python_attribute_labels_run():
    entry = manual_entry(symbol_by="Label", group_by="")
    code = codegen.generate_code(make_state(), [entry], "Python")
    ns = exec_python(code)
    spec = ns["DATASETS"][0]
    df = ns["load_points"](spec)
    labels = ns["point_labels"](df, spec)
    assert list(labels) == ["Site A", "Site B"]
    assert set(labels) <= set(spec["styles"])


def test_generated_projection_forward_matches_the_app():
    import numpy as np

    state = make_state()  # Robinson
    code = codegen.generate_code(state, [], "Python")
    ns = exec_python(code)
    projection = get_projection("Robinson")
    lons = np.array([-120.0, 0.0, 150.0])
    lats = np.array([-45.0, 10.0, 60.0])
    ax, ay = projection.forward(lons, lats)
    sx, sy = ns["proj_forward"](lons, lats)
    assert np.allclose(ax, sx) and np.allclose(ay, sy)


# ------------------------------------------------------------ bootstrap

def test_python_script_only_installs_packages_when_asked():
    code = codegen.generate_code(make_state(), [file_entry()], "Python")
    # The check runs before the third-party imports it guards.
    boot = code.index("ensure_dependencies()\n")
    assert boot < code.index("import geopandas as gpd")
    # Paths are resolved relative to the script, not the shell's cwd.
    assert "SCRIPT_DIR" in code

    ns = exec_python(code)
    installs = []

    def import_module(name):
        if name == "geopandas":
            raise ImportError(name)

    ns["importlib"] = types.SimpleNamespace(import_module=import_module,
                                            invalidate_caches=lambda: None)
    ns["subprocess"] = types.SimpleNamespace(check_call=installs.append)
    ns["sys"] = types.SimpleNamespace(executable="python",
                                      argv=["recreate_map.py"])
    with pytest.raises(SystemExit) as stopped:
        ns["ensure_dependencies"]()
    assert "python -m pip install geopandas" in str(stopped.value)
    assert installs == []
    ns["sys"].argv.append("--install-deps")
    ns["ensure_dependencies"]()
    assert installs == [["python", "-m", "pip", "install", "geopandas"]]


def test_r_script_only_installs_packages_when_asked():
    code = codegen.generate_code(make_state(), [file_entry()], "R")
    assert "ensure_packages <- function(pkgs)" in code
    assert 'ensure_packages(c("sf", "ggplot2"))' in code
    assert '"--install-deps" %in% commandArgs(trailingOnly = TRUE)' in code
    assert "install.packages(missing" in code
    # The bootstrap runs before the libraries it guards.
    assert (code.index('ensure_packages(c("sf", "ggplot2"))')
            < code.index("library(sf)"))


def test_bootstrapped_python_still_valid_and_runs():
    # The bootstrap must not break syntax or the pre-made loaders.
    code = codegen.generate_code(make_state(), [manual_entry()], "Python")
    ns = exec_python(code)  # top-level ensure_dependencies() runs here
    assert "ensure_dependencies" in ns
    df = ns["load_points"](ns["DATASETS"][0])
    assert len(df) == 2


# --------------------------------------------- export as working directory

def test_working_directory_python_layout():
    files = codegen.generate_working_directory(
        make_state(), [file_entry()], "Python", "My Project")
    assert set(files) >= {"recreate_map.py", "requirements.txt",
                          "README.md", ".gitignore"}
    # Point data lives in data/ as CSV, referenced by a relative path.
    data = [name for name in files if name.startswith("data/")]
    assert data == ["data/us_cities.csv"]
    assert "State,Longitude,Latitude" in files["data/us_cities.csv"]
    script = files["recreate_map.py"]
    compile(script, "recreate_map.py", "exec")
    assert "'path': 'data/us_cities.csv'" in script
    assert "'inline_data': None" in script
    assert "geopandas" in files["requirements.txt"]
    assert "pip install -r requirements.txt" in files["README.md"]


def test_working_directory_r_layout():
    files = codegen.generate_working_directory(
        make_state(), [file_entry()], "R", "My Project")
    # The RStudio project is named after the project, spaces and all.
    assert set(files) >= {"recreate_map.R", "install.R", "README.md",
                          ".gitignore", "My Project.Rproj"}
    assert "data/us_cities.csv" in files
    script = files["recreate_map.R"]
    assert_parses_as_r(script)
    assert '"path" = "data/us_cities.csv"' in script
    assert 'install.packages(c("sf", "ggplot2")' in files["install.R"]
    assert "Version: 1.0" in files["My Project.Rproj"]
    assert "Open `My Project.Rproj` in RStudio" in files["README.md"]


def test_working_directory_dedupes_data_filenames():
    # Two datasets exporting to the same slug get distinct CSV files.
    a = manual_entry("Sites")
    b = manual_entry("Sites")
    files = codegen.generate_working_directory(make_state(), [a, b],
                                               "Python", "P")
    data = sorted(name for name in files if name.startswith("data/"))
    assert data == ["data/Sites.csv", "data/Sites_2.csv"]
    script = files["recreate_map.py"]
    assert "'path': 'data/Sites.csv'" in script
    assert "'path': 'data/Sites_2.csv'" in script


def test_working_directory_manual_data_is_written_as_csv():
    files = codegen.generate_working_directory(
        make_state(), [manual_entry()], "Python", "P")
    data = [name for name in files if name.startswith("data/")]
    assert len(data) == 1
    assert "Legend,Label,Longitude,Latitude" in files[data[0]]


def test_working_directory_unknown_language_rejected():
    with pytest.raises(ValueError):
        codegen.generate_working_directory(make_state(), [], "Julia")


# ------------------------------------ with a real R interpreter, if any

def test_generated_r_parses_with_real_r(tmp_path):
    rscript = _rscript()
    for entries in ([file_entry()], [manual_entry(symbol_by="Label")], []):
        script = tmp_path / "recreate_map.R"
        script.write_text(codegen.generate_code(make_state(), entries, "R"),
                          encoding="utf-8")
        subprocess.run([rscript, "-e",
                        f"invisible(parse('{script.as_posix()}'))"],
                       check=True, capture_output=True)


def test_generated_r_functions_actually_run(tmp_path):
    """Run the R pre-made loaders on the embedded data (no sf/ggplot2
    needed: library lines and the main() call are stripped)."""
    rscript = _rscript()
    code = codegen.generate_code(make_state(), [manual_entry()], "R")
    # Drop the library() lines, the ensure_packages() bootstrap call (it
    # would try to install over the network), and the final main() call;
    # what remains are the loader functions this harness exercises.
    body = "\n".join(line for line in code.splitlines()
                     if not line.startswith("library(")
                     and not line.startswith("ensure_packages(")
                     and line != "main()")
    harness = body + """
spec <- DATASETS[[1]]
df <- load_points(spec)
stopifnot(nrow(df) == 2)
stopifnot(identical(df$`_lon`, c(-100, 140)))
stopifnot(identical(df$`_lat`, c(38, -25)))
labels <- point_labels(df, spec)
stopifnot(identical(labels, c("spiders", "spiders")))
stopifnot(STYLE_FILLS[["spiders"]] == "#123456")
gdf <- data.frame(FEATURECLA = c("Desert", "Plateau", "desert"),
                  adm0cap = c(1, 0, 1))
kept <- filter_layer(gdf, "featurecla", c("Desert"), TRUE)
stopifnot(identical(kept$FEATURECLA, c("Desert", "desert")))
caps <- filter_layer(gdf, "ADM0CAP", c("1"), TRUE)
stopifnot(nrow(caps) == 2)
dropped <- filter_layer(gdf, "featurecla", c("Desert"), FALSE)
stopifnot(identical(dropped$FEATURECLA, "Plateau"))
cat("R functions OK\\n")
"""
    script = tmp_path / "harness.R"
    script.write_text(harness, encoding="utf-8")
    result = subprocess.run([rscript, str(script)], capture_output=True,
                            text=True)
    assert result.returncode == 0, result.stderr
    assert "R functions OK" in result.stdout


def run_r_harness(tmp_path, code, harness, name="harness.R"):
    """Run a generated R script's definitions (the package bootstrap and
    the final main() call dropped) followed by *harness*; return stdout."""
    rscript = _rscript()
    body = "\n".join(line for line in code.splitlines()
                     if not line.startswith("ensure_packages(")
                     and line != "main()")
    script = tmp_path / name
    script.write_text(body + "\n" + harness + '\ncat("HARNESS OK\\n")\n',
                      encoding="utf-8")
    result = subprocess.run([rscript, str(script)], cwd=tmp_path,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
    assert result.returncode == 0, result.stderr[-3000:]
    assert "HARNESS OK" in result.stdout, result.stdout[-2000:]
    return result.stdout


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
    assert "Araneae" in all_styles(ns)
    assert ns["LEGEND_ROWS"] == ["Araneae"]


# ------------------------------------------------- export fixes (1.31.3)

TRICKY_LABELS = ["NA", "007", "T", "1.50", ""]


def coded_entry(name="codes", labels=TRICKY_LABELS, column="Code",
                **extra):
    """A grouped dataset whose group values pandas and R would retype."""
    rows = [[label, -100.0 + i * 10.0, 40.0 - i * 5.0]
            for i, label in enumerate(labels)]
    return entry_from_dict({"name": name, "columns": ["name1", "lon", "lat"],
                            "name_labels": [column], "rows": rows,
                            "group_by": column, **extra})


def ungrouped_entry(name, color, source_path=""):
    entry = manual_entry(name, group_by="",
                         legend_overrides={row_key("group", "All points"): {
                             "color": color}})
    entry.dataset.source_path = source_path
    return entry


def app_labels(entries, legend=None):
    """The labels the app draws each dataset's groups under."""
    layout = layout_points(entries, LegendOptions.from_dict(legend or {}),
                           DEFAULT_PALETTE)
    return [[label for label, _style, _rows in dataset.groups]
            for dataset in layout.datasets]


@pytest.mark.parametrize("data_mode", ["inline", "files"])
def test_python_reads_label_values_as_text(tmp_path, data_mode):
    entry = coded_entry()
    if data_mode == "files":
        files = codegen.generate_working_directory(make_state(), [entry],
                                                   "Python", "P")
        for rel, text in files.items():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text(text, encoding="utf-8")
        code = files["recreate_map.py"]
    else:
        code = codegen.generate_code(make_state(), [entry], "Python")
    ns = exec_python(code)
    ns["SCRIPT_DIR"] = tmp_path
    spec = ns["DATASETS"][0]
    labels = list(ns["point_labels"](ns["load_points"](spec), spec))
    # "NA" is not missing, "007" keeps its zeros, "1.50" its trailing zero.
    assert labels == ["NA", "007", "T", "1.50", "(blank)"]
    assert labels == app_labels([entry])[0]
    assert list(spec["styles"]) == labels


@pytest.mark.parametrize("data_mode", ["inline", "files"])
def test_r_reads_label_values_as_text(tmp_path, data_mode):
    entry = coded_entry()
    if data_mode == "files":
        files = codegen.generate_working_directory(make_state(), [entry],
                                                   "R", "P")
        for rel, text in files.items():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text(text, encoding="utf-8")
        code = files["recreate_map.R"]
    else:
        code = codegen.generate_code(make_state(), [entry], "R")
    run_r_harness(tmp_path, code, """
spec <- DATASETS[[1]]
labels <- point_labels(load_points(spec), spec)
stopifnot(identical(labels, c("NA", "007", "T", "1.50", "(blank)")))
stopifnot(identical(names(STYLE_COLORS), labels))
points <- load_all_points()
stopifnot(identical(points$key, labels))
""")


def test_two_datasets_sharing_a_label_keep_their_own_styles(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    # Two ungrouped datasets with the same name both display as "Sites";
    # the app draws each in its own colour with a legend row each.
    entries = [ungrouped_entry("Sites", "#111111"),
               ungrouped_entry("Sites", "#222222")]
    assert app_labels(entries) == [["Sites"], ["Sites"]]
    ns = exec_python(codegen.generate_code(make_state(), entries, "Python"))
    colors = [spec["styles"]["Sites"]["color"] for spec in ns["DATASETS"]]
    assert colors == ["#111111", "#222222"]
    fig = matplotlib.figure.Figure()
    ax = fig.add_subplot(111)
    ns["add_legend"](ax)
    legend = ax.get_legend()
    assert [t.get_text() for t in legend.get_texts()] == ["Sites", "Sites"]
    assert [h.get_markerfacecolor() for h in legend.legend_handles] == colors

    code = codegen.generate_code(make_state(), entries, "R")
    run_r_harness(tmp_path, code, """
stopifnot(identical(names(STYLE_FILLS), c("Sites", "Sites [2]")))
stopifnot(identical(unname(STYLE_FILLS), c("#111111", "#222222")))
points <- load_all_points()
stopifnot(identical(points$key, c("Sites", "Sites", "Sites [2]",
                                  "Sites [2]")))
guide <- get_guide_data(ggplot() + point_layers(), "fill")
stopifnot(identical(guide$.label, c("Sites", "Sites")))
stopifnot(identical(guide$fill, c("#111111", "#222222")))
""")


def test_attribute_datasets_with_overlapping_values_keep_their_styles():
    # Symbol-by labels get no per-dataset dedupe: both datasets draw
    # "Site A", each with its own override.
    a = manual_entry("One", symbol_by="Label", group_by="")
    b = manual_entry("Two", symbol_by="Label", group_by="")
    a.legend_overrides = {row_key("symbol", "Site A"): {"marker": "Square"}}
    b.legend_overrides = {row_key("symbol", "Site A"): {"marker": "Diamond"}}
    ns = exec_python(codegen.generate_code(make_state(), [a, b], "Python"))
    markers = [spec["styles"]["Site A"]["marker"] for spec in ns["DATASETS"]]
    assert markers == ["s", "D"]
    r_code = codegen.generate_code(make_state(), [a, b], "R")
    shapes = r_code.split("STYLE_SHAPES <- c(")[1].split(")")[0]
    assert '"Site A" = 22' in shapes and '"Site A [2]" = 23' in shapes


def test_r_legend_follows_row_order_and_hides_rows(tmp_path):
    entry = coded_entry(labels=["Zeta", "Beta", "Alpha"], column="Name")
    entry.legend_overrides = {row_key("group", "Zeta"): {"hidden": True}}
    state = make_state(legend={"order": "az", "title": ""})
    code = codegen.generate_code(state, [entry], "R")
    run_r_harness(tmp_path, code, """
stopifnot(identical(LEGEND_ROWS, c("Alpha", "Beta")))
p <- ggplot() + point_layers()
guide <- get_guide_data(p, "colour")
stopifnot(identical(guide$.label, c("Alpha", "Beta")))
# Hiding a row keeps its points.
stopifnot(nrow(layer_data(p, 1)) == 3)
""")
    # Every row hidden is not "no ordering": the legend is empty.
    entry.legend_overrides = {row_key("group", label): {"hidden": True}
                              for label in ("Zeta", "Beta", "Alpha")}
    code = codegen.generate_code(state, [entry], "R")
    assert "LEGEND_ROWS <- character(0)" in code
    run_r_harness(tmp_path, code, """
p <- ggplot() + point_layers()
stopifnot(is.null(get_guide_data(p, "colour")))
stopifnot(nrow(layer_data(p, 1)) == 3)
""")


R_LEGEND_SWATCHES = """
legend_swatches <- function(p) {
  # Point glyphs drawn in the legend box.
  g <- ggplotGrob(p)
  flat <- function(x) {
    if (inherits(x, "gtable")) {
      return(unlist(lapply(x$grobs, flat), recursive = FALSE))
    }
    if (inherits(x, "gTree")) {
      return(unlist(lapply(x$children, flat), recursive = FALSE))
    }
    list(x)
  }
  box <- g$grobs[grepl("guide-box", g$layout$name)]
  grobs <- unlist(lapply(box, flat), recursive = FALSE)
  sum(vapply(grobs, inherits, logical(1), "points"))
}
"""


def test_r_keeps_legend_rows_whose_points_are_off_the_map(tmp_path):
    # Cape Town is on the far side of this globe: its row stays, with its
    # swatch, as in the app - and building the legend must not crash.
    state = make_state(map={"projection": "Globe (Orthographic)",
                            "proj_lon0": "-100", "proj_lat0": "40"})
    code = codegen.generate_code(state, [cities_entry()], "R")
    run_r_harness(tmp_path, code, R_LEGEND_SWATCHES + """
points <- project_points(load_all_points())
stopifnot(identical(unique(points$key), "Paris"))
p <- ggplot() + point_layers()
guide <- get_guide_data(p, "colour")
stopifnot(identical(guide$.label, c("Paris", "Cape Town")))
stopifnot(legend_swatches(p) == 2)
""")


def test_r_points_are_clamped_into_the_band_like_the_app(tmp_path):
    # Lambert: Europe stops at 30N; Cape Town sits on that edge in the app
    # (Projection._clip) rather than vanishing.
    state = make_state(map={"projection": "Lambert: Europe"})
    code = codegen.generate_code(state, [cities_entry()], "R")
    projection = get_projection("Lambert: Europe")
    x, y = projection.forward([18.42], [-33.92])
    run_r_harness(tmp_path, code, f"""
points <- project_points(load_all_points())
stopifnot(nrow(points) == 3)
xy <- sf::st_coordinates(points)[points$key == "Cape Town", ]
stopifnot(abs(xy[["X"]] - ({float(x[0])})) < 1)
stopifnot(abs(xy[["Y"]] - ({float(y[0])})) < 1)
""")


def test_r_draws_wrapped_world_copies(tmp_path):
    # Equirectangular from 100E to 260E: the right half is the next world
    # copy, where Hawaii sits at 203E.
    hawaii = DatasetEntry(dataset=build_manual_dataset(
        "islands", "19.9,-155.6, Hawaii\n"), name="islands",
        group_by="Label")
    state = make_state(map={"projection": "Equirectangular"},
                       view={"xlim": [100, 260], "ylim": [-40, 60]})
    code = codegen.generate_code(state, [hawaii], "R")
    run_r_harness(tmp_path, code, """
stopifnot(identical(wrap_offsets(), c(0, 360)))
points <- wrapped(project_points(load_all_points()))
x <- sf::st_coordinates(points)[, "X"]
stopifnot(isTRUE(all.equal(sort(x), c(-155.6, 204.4))))
""")
    # The globe never wraps.
    globe = codegen.generate_code(
        make_state(map={"projection": "Globe (Orthographic)"}), [hawaii], "R")
    run_r_harness(tmp_path, globe, "stopifnot(identical(wrap_offsets(), 0))")


def test_r_grid_is_drawn_above_the_fills_and_under_the_points(tmp_path):
    state = make_state(map={"projection": "Globe (Orthographic)",
                            "points": {"cities": True}})
    code = codegen.generate_code(state, [manual_entry()], "R")
    run_r_harness(tmp_path, code, """
# Stand-ins that record the draw order instead of loading Natural Earth.
base_layer_geom <- function(layer) {
  annotate("text", x = 0, y = 0, label = layer$name)
}
order <- function(p) {
  vapply(p$layers, function(l) {
    if (!is.null(l$aes_params$label)) l$aes_params$label
    else class(l$geom)[1]
  }, character(1))
}
p <- build_map()
drawn <- order(p)
grid_at <- which(drawn == "GeomSf")[1:2]  # graticule, then horizon
fills <- match(c("ocean", "land", "lakes"), drawn)
cities <- match("populated_places_simple", drawn)
stopifnot(all(fills < grid_at[1]), grid_at[2] < cities)
# The globe always gets its horizon circle, grid or not.
GRID_INTERVAL <- NULL
stopifnot(length(graticule_layers()) == 1)
""")


def test_r_legend_placement_frame_and_text_options(tmp_path):
    legend = {"location": "lower left", "frame": True,
              "frame_color": "#000000", "frame_alpha": 1.0,
              "frame_edge_color": "#ff0000", "frame_width": 2.13,
              "label_color": "#00ff00", "title_color": "#0000ff",
              "font_family": "serif", "fontsize": 9, "title": "Sites"}
    code = codegen.generate_code(make_state(legend=legend, view={}),
                                 [manual_entry()], "R")
    assert "Legend border width" not in code  # it is reproduced now
    run_r_harness(tmp_path, code, """
NE_LAYERS <- list()
p <- build_map()
th <- p$theme
stopifnot(identical(th$legend.position, "inside"))
stopifnot(identical(th$legend.justification.inside, c(0, 0)))
stopifnot(all(th$legend.position.inside > 0),
          all(th$legend.position.inside < 0.05))
stopifnot(identical(th$legend.background$colour, "#ff0000"))
stopifnot(identical(toupper(th$legend.background$fill), "#000000FF"))
stopifnot(abs(th$legend.background$linewidth - 1) < 0.01)
stopifnot(identical(th$legend.text$colour, "#00ff00"))
stopifnot(identical(th$legend.title$colour, "#0000ff"))
stopifnot(identical(th$legend.text$family, "serif"))
stopifnot(identical(legend_anchor("upper right"), c(1, 1)))
stopifnot(identical(legend_anchor("best"), c(1, 1)))
stopifnot(identical(legend_anchor("center left"), c(0, 0.5)))
stopifnot(identical(legend_anchor("right"), c(1, 0.5)))
stopifnot(identical(legend_anchor("lower center"), c(0.5, 0)))
invisible(ggplotGrob(p))
""")


def test_r_header_names_the_marker_approximations():
    entry = manual_entry()  # its one group is a Star
    code = codegen.generate_code(make_state(), [entry], "R")
    notes = code.split("NOT reproduced")[1].split("ensure_packages")[0]
    assert "stars are drawn as asterisks (R pch 8)" in notes
    plain = codegen.generate_code(
        make_state(), [manual_entry(legend_overrides={})], "R")
    assert "R has no exact equivalent" not in plain


def test_r_point_outlines_are_converted_from_points(tmp_path):
    entry = coded_entry(labels=["Filled", "Open"], column="Name")
    entry.legend_overrides = {
        row_key("group", "Open"): {"marker": "Circle (open)"}}
    state = make_state(point_edge={"color": "#333333", "width": 0.5})
    code = codegen.generate_code(state, [entry], "R")
    run_r_harness(tmp_path, code, """
stopifnot(identical(unname(STYLE_STROKES), c(0.5, 1.2)))
strokes <- layer_data(ggplot() + point_layers(), 1)$stroke
# ggplot2 strokes are not points: 0.5 pt is about 0.35 stroke units.
stopifnot(isTRUE(all.equal(strokes, c(0.5, 1.2) * 50.8 / 72)))
""")


def test_names_with_escapes_and_quotes_compile(tmp_path):
    names = ["Field\\Notes 2024", "C:\\path\\x41", 'say "hi"',
             "two\nlines", "caf\u00e9 \u00e5\u00df \u6f22", "\\N{oops}"]
    for name in names:
        entries = [manual_entry(name), ungrouped_entry(name, "#123456")]
        code = codegen.generate_code(make_state(), entries, "Python", name)
        compile(code, "recreate_map.py", "exec")
        ns = exec_python(code)
        assert [spec["name"] for spec in ns["DATASETS"]] == [name, name]
        files = codegen.generate_working_directory(make_state(), entries,
                                                   "Python", name)
        compile(files["recreate_map.py"], "recreate_map.py", "exec")
    expected = tmp_path / "expected.txt"
    for name in names:
        code = codegen.generate_code(make_state(), [manual_entry(name)], "R",
                                     name)
        expected.write_text(name, encoding="utf-8")
        run_r_harness(tmp_path, code, """
wanted <- paste(readLines("expected.txt", encoding = "UTF-8", warn = FALSE),
                collapse = "\\n")
stopifnot(identical(enc2utf8(DATASETS[[1]]$name), wanted))
""")


def test_backslash_project_name_compiles():
    # "\N" in a normal docstring starts a named-character escape.
    code = codegen.generate_code(make_state(), [file_entry()], "Python",
                                 "Field\\Notes 2024")
    docstring = ast.get_docstring(ast.parse(code))
    assert docstring.startswith(
        'Recreate the PyMappr map "Field\\Notes 2024" outside')


def test_source_path_cannot_inject_code(tmp_path):
    attack = "C:/data/x.csv\nINJECTED = 1\r\nINJECTED <- 1"
    entry = ungrouped_entry("Sites", "#123456", source_path=attack)
    py = codegen.generate_code(make_state(), [entry], "Python")
    assert "# originally imported from: C:/data/x.csv INJECTED = 1" in py
    assert "INJECTED" not in exec_python(py)
    r = codegen.generate_code(make_state(), [entry], "R")
    run_r_harness(tmp_path, r, 'stopifnot(!exists("INJECTED"))')


def test_non_finite_numbers_are_valid_literals(tmp_path):
    assert codegen._py(float("nan")) == 'float("nan")'
    assert codegen._py(float("inf")) == 'float("inf")'
    assert codegen._py(-float("inf")) == '-float("inf")'
    assert codegen._py({"a": (float("nan"),)}) == "{'a': (float(\"nan\"),)}"
    assert codegen._r(float("nan")) == "NA_real_"
    assert codegen._r(float("inf")) == "Inf"
    assert codegen._r(-float("inf")) == "-Inf"
    # Typing "nan" as the scale bar's fixed length.
    state = make_state(map={"scale_bar": {"show": True,
                                          "length_mode": "fixed",
                                          "fixed_length": float("nan")}})
    ns = exec_python(codegen.generate_code(state, [], "Python"))
    assert math.isnan(ns["SCALE_BAR"]["fixed_length"])
    r = codegen.generate_code(state, [], "R")
    run_r_harness(tmp_path, r, "stopifnot(is.na(SCALE_BAR$fixed_length))")


def test_stale_color_by_is_ignored_like_the_app():
    entry = manual_entry(symbol_by="Label", group_by="",
                         color_by="Gone")  # names no column any more
    ns = exec_python(codegen.generate_code(make_state(), [entry], "Python"))
    spec = ns["DATASETS"][0]
    assert spec["color_col"] is None and spec["symbol_col"] == "Label"
    labels = ns["point_labels"](ns["load_points"](spec), spec)
    assert list(labels) == ["Site A", "Site B"]


def test_dataset_files_survive_case_and_reserved_names():
    entries = [manual_entry(name) for name in
               ("Sites", "sites", "CON", "nul.csv", "My Sites")]
    files = codegen.generate_working_directory(make_state(), entries,
                                               "Python", "P")
    data = [name for name in files if name.startswith("data/")]
    assert data == ["data/Sites.csv", "data/sites_2.csv", "data/CON_.csv",
                    "data/nul_.csv", "data/My Sites.csv"]
    assert len({name.casefold() for name in data}) == len(data)
    rproj = codegen.generate_working_directory(make_state(), [], "R", "AUX")
    assert "AUX_.Rproj" in rproj


def test_projection_helpers_are_built_once():
    ns = exec_python(codegen.generate_code(make_state(), [], "Python"))
    assert ns["_transformer"]() is ns["_transformer"]()
    assert ns["_geod"]() is ns["_geod"]()


def _zip_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ne_110m_land/ne_110m_land.shp", b"shape")
        archive.writestr("ne_110m_land/ne_110m_land.dbf", b"table")
    return buffer.getvalue()


def test_python_recovers_from_an_interrupted_download(tmp_path):
    ns = exec_python(codegen.generate_code(make_state(), [], "Python"))
    ns["SCRIPT_DIR"] = tmp_path
    cache = tmp_path / "naturalearth_cache"
    cache.mkdir()
    good = _zip_bytes()
    zip_path = cache / "ne_110m_land.zip"
    zip_path.write_bytes(good[: len(good) // 2])  # cut off mid-download
    fetched = []

    def fake_urlretrieve(url, target):
        fetched.append(url)
        Path(target).write_bytes(good)

    ns["urlretrieve"] = fake_urlretrieve
    assert ns["download_archive"]("110m", "physical", "land") == zip_path
    assert fetched and zip_path.read_bytes() == good

    # A download that dies part-way leaves no zip that looks finished.
    zip_path.unlink()

    def dying_urlretrieve(url, target):
        Path(target).write_bytes(good[:10])
        raise KeyboardInterrupt

    ns["urlretrieve"] = dying_urlretrieve
    with pytest.raises(KeyboardInterrupt):
        ns["download_archive"]("110m", "physical", "land")
    assert not zip_path.exists()


def test_python_recovers_from_a_failed_extraction(tmp_path):
    ns = exec_python(codegen.generate_code(make_state(), [], "Python"))
    zip_path = tmp_path / "ne_110m_land.zip"
    zip_path.write_bytes(_zip_bytes())
    folder = tmp_path / "ne_110m_land"
    folder.mkdir()  # what an extraction that failed used to leave behind
    ns["extract_archive"](zip_path, folder, "ne_110m_land.shp")
    assert (folder / "ne_110m_land.shp").read_bytes() == b"shape"
    assert not (tmp_path / "ne_110m_land.part").exists()


# ------------------------------- running whole exported R scripts (opt-in)
#
# These run a generated script's main() end to end with real R, sf and
# ggplot2, against the Natural Earth zips the app already downloaded into
# data/downloads (copied into the script's naturalearth_cache/, so nothing
# is fetched). Slow, so opt in with PYMAPPR_RUN_R=1.

NE_DOWNLOADS = Path(__file__).resolve().parent.parent / "data" / "downloads"

run_r = pytest.mark.skipif(os.environ.get("PYMAPPR_RUN_R") != "1",
                           reason="set PYMAPPR_RUN_R=1 to run whole R "
                                  "scripts")


def r_run_state(projection, lon0="", lat0="", **map_overrides):
    """A small map: world-scale layers only, so the 110m zips do."""
    settings = {"projection": projection, "proj_lon0": lon0,
                "proj_lat0": lat0, "graticule": "10\N{DEGREE SIGN}",
                "ocean": "blue", "lake_fill": "grey",
                "lines": {"countries": True}, "fills": {"land": True},
                "points": {}, "labels": {},
                "scale_bar": {"show": True}}
    settings.update(map_overrides)
    return make_state(map=settings, view={})


def cities_entry():
    """Two groups far apart, so a regional map clips one of them."""
    dataset = build_manual_dataset(
        "cities", "48.86,2.35, Paris\n-33.92,18.42, Cape Town\n"
                  "51.5,-0.12, Paris\n")
    return DatasetEntry(dataset=dataset, name="cities", group_by="Label")


def run_exported_r(tmp_path, state, entries, files=None):
    """Write the exported script (plus any extra *files*) to *tmp_path* with
    a pre-filled Natural Earth cache, run it, and return the result."""
    rscript = _rscript()
    config = codegen.build_config(state, entries)
    cache = tmp_path / "naturalearth_cache"
    cache.mkdir()
    zip_names = [f"ne_{layer['scale']}_{layer['name']}.zip"
                 for layer in config["layers"]]
    if config["basemap"] in codegen.BASEMAP_RASTERS:
        (_scale, _category, name), _jpg = codegen.BASEMAP_RASTERS[
            config["basemap"]]
        zip_names.append(f"{name}.zip")
    for zip_name in zip_names:
        source = NE_DOWNLOADS / zip_name
        if not source.exists():
            pytest.skip(f"{zip_name} is not in {NE_DOWNLOADS}")
        shutil.copyfile(source, cache / zip_name)
    script = tmp_path / "recreate_map.R"
    script.write_text(codegen.generate_code(state, entries, "R"),
                      encoding="utf-8")
    for name, text in (files or {}).items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    result = subprocess.run([rscript, str(script)], cwd=tmp_path,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=600)
    return result


def assert_r_map_saved(tmp_path, result):
    assert result.returncode == 0, result.stderr[-3000:]
    assert (tmp_path / "map.png").stat().st_size > 10_000
    assert "Saved map.png" in result.stderr


@run_r
@pytest.mark.parametrize("projection, lon0, lat0", [
    ("Mercator", "", ""),
    ("Lambert: Europe", "", ""),
    ("Globe (Orthographic)", "0", "0"),
    ("Globe (Orthographic)", "-100", "40"),
])
def test_exported_r_script_draws_the_map(tmp_path, projection, lon0, lat0):
    state = r_run_state(projection, lon0, lat0)
    result = run_exported_r(tmp_path, state, [cities_entry()])
    assert_r_map_saved(tmp_path, result)


@run_r
def test_exported_r_script_wraps_the_world_and_its_basemap(tmp_path):
    # Equirectangular from 100E to 260E: the right half is the next world
    # copy, basemap raster included, with Hawaii drawn at 203E.
    hawaii = DatasetEntry(dataset=build_manual_dataset(
        "islands", "19.9,-155.6, Hawaii"), name="islands",
        group_by="Label")
    state = r_run_state("Equirectangular", basemap="relief_grey")
    state["view"] = {"xlim": [100, 260], "ylim": [-40, 60]}
    result = run_exported_r(tmp_path, state, [hawaii])
    assert_r_map_saved(tmp_path, result)
