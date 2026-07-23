import math
import shutil
import subprocess
import sys
import types

import pandas as pd
import pytest

from pymappr import codecheck, codegen
from pymappr.data_loader import build_manual_dataset
from pymappr.projections import get_projection
from pymappr.projects import DatasetEntry, entry_from_dict
from pymappr.styles import PointStyle


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
                    styles={name: PointStyle(color="#123456",
                                             marker="Star", size=45.0)})
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
    assert codecheck.validate_code("Python", code) == []
    assert '"My Project"' in code
    assert "from pre-made function templates and" in code
    assert "no AI involved" not in code


def test_r_output_is_valid_and_placeholder_free():
    code = codegen.generate_code(make_state(), [file_entry()], "R",
                                 "My Project")
    assert codecheck.validate_code("R", code) == []
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
    assert "override.aes = list(size = key_sizes)" in code
    assert "unname(STYLE_SIZES) * LEGEND$marker_scale" in code
    assert "element_text(size = LEGEND$title_fontsize)" in code
    assert "grid::unit(1 + LEGEND$label_spacing" in code


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
    assert codecheck.validate_code("Python", py) == []
    assert "+proj=ortho +lat_0=40.0 +lon_0=-100.0" in py
    assert "CLIP_CAP = (-100.0, 40.0, 88.0)" in py
    assert "'hemisphere': True" in py
    r = codegen.generate_code(state, [file_entry()], "R")
    assert codecheck.validate_code("R", r) == []
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
    assert "COMPASS = True" in code


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
    # Filled markers carry a white edge; open markers outline-only.
    code = codegen.generate_code(make_state(), [manual_entry()], "Python")
    assert 'face, edge, lw = style["color"], "white", 0.5' in code
    assert 'face, edge, lw = "none", style["color"], 1.2' in code
    assert "framealpha=0.85" in code


def test_attribute_mode_emits_sectioned_legend():
    entry = manual_entry(symbol_by="Label", group_by="")
    code = codegen.generate_code(make_state(), [entry], "Python")
    ns = exec_python(code)
    sections = ns["LEGEND_SECTIONS"]
    assert sections is not None
    titles = [title for title, _entries in sections]
    assert titles == ["Label"]
    labels = [label for label, _style in sections[0][1]]
    assert labels == ["Site A", "Site B"]
    # Symbol-key entries use the neutral marker color, like the app.
    assert sections[0][1][0][1]["color"] == "#555555"
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
    assert "COMPASS = True" in code
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
    assert ns["STYLES"]["spiders"]["color"] == "#123456"

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
    assert set(labels) <= set(ns["STYLES"])


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

def test_python_script_bootstraps_missing_packages():
    code = codegen.generate_code(make_state(), [file_entry()], "Python")
    # A pip-based bootstrap runs before the third-party imports, so a
    # fresh interpreter installs what it needs on first run.
    assert "def ensure_dependencies():" in code
    assert "ensure_dependencies()" in code
    assert '"-m", "pip", "install"' in code
    boot = code.index("ensure_dependencies()\n")
    assert boot < code.index("import geopandas as gpd")
    # Paths are resolved relative to the script, not the shell's cwd.
    assert "SCRIPT_DIR" in code


def test_r_script_bootstraps_missing_packages():
    code = codegen.generate_code(make_state(), [file_entry()], "R")
    assert "ensure_packages <- function(pkgs)" in code
    assert 'ensure_packages(c("sf", "ggplot2"))' in code
    assert "install.packages(missing" in code
    # The bootstrap runs before the libraries it guards.
    assert (code.index('ensure_packages(c("sf", "ggplot2"))')
            < code.index("library(sf)"))


def test_bootstrapped_python_still_valid_and_runs():
    # The bootstrap must not break syntax or the pre-made loaders.
    code = codegen.generate_code(make_state(), [manual_entry()], "Python")
    assert codecheck.validate_code("Python", code) == []
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
    assert codecheck.validate_code("Python", script) == []
    assert "'path': 'data/us_cities.csv'" in script
    assert "'inline_data': None" in script
    assert "geopandas" in files["requirements.txt"]
    assert "pip install -r requirements.txt" in files["README.md"]


def test_working_directory_r_layout():
    files = codegen.generate_working_directory(
        make_state(), [file_entry()], "R", "My Project")
    assert set(files) >= {"recreate_map.R", "install.R", "README.md",
                          ".gitignore", "My_Project.Rproj"}
    assert "data/us_cities.csv" in files
    script = files["recreate_map.R"]
    assert codecheck.validate_code("R", script) == []
    assert '"path" = "data/us_cities.csv"' in script
    assert 'install.packages(c("sf", "ggplot2")' in files["install.R"]
    assert "Version: 1.0" in files["My_Project.Rproj"]


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

def _rscript():
    path = shutil.which("Rscript")
    if path is None:
        pytest.skip("Rscript is not installed")
    return path


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
