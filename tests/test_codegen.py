import shutil
import subprocess
import sys
import types

import pandas as pd
import pytest

from pymappr import codecheck, codegen
from pymappr.data_loader import build_manual_dataset
from pymappr.layers import CONTINENT_EXTENTS
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
    assert "deterministically" in code
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
    assert "GRID_INTERVAL = 5.0" in code
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
    # Dataset + styling.
    assert "'C:/data/us_cities.csv'" in code
    assert "'group_col': 'State'" in code
    assert "'#123456'" in code and "'marker': '*'" in code
    assert "'Colorado'" in code  # default style assigned to the 2nd group
    assert "'location': 'upper right'" in code and "'columns': 2" in code
    assert "'title': 'State'" in code  # defaults to the group-by column
    # Legend customization options reach the matplotlib legend call.
    assert "'title_fontsize': 12.0" in code
    assert "'marker_scale': 1.5" in code
    assert "'label_spacing': 0.8" in code
    assert "markerscale=LEGEND[\"marker_scale\"]" in code
    assert "labelspacing=LEGEND[\"label_spacing\"]" in code
    assert "title_fontsize=LEGEND[\"title_fontsize\"]" in code


def test_r_config_reflects_map_settings():
    code = codegen.generate_code(make_state(), [file_entry()], "R")
    assert 'MAP_CRS <- "+proj=robin +lon_0=0 +datum=WGS84' in code
    assert "POINT_ALPHA <- 0.85" in code
    assert "DPI <- 300" in code
    assert '"Wyoming" = "#123456"' in code
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


def test_equirectangular_uses_plain_crs():
    code = codegen.generate_code(
        make_state(map={"projection": "Equirectangular"}), [], "Python")
    assert "MAP_CRS = 'EPSG:4326'" in code


def test_globe_export_clips_to_the_visible_hemisphere():
    state = make_state(map={"projection": "Globe (Orthographic)",
                            "proj_lon0": "-100", "proj_lat0": "40"})
    py = codegen.generate_code(state, [file_entry()], "Python")
    compile(py, "globe.py", "exec")
    assert codecheck.validate_code("Python", py) == []
    assert "+proj=ortho +lat_0=40.0 +lon_0=-100.0" in py
    assert "CLIP_CAP = (-100.0, 40.0, 88.0)" in py
    assert "WORLD_BOUNDS = (" in py  # the projected disk to frame
    r = codegen.generate_code(state, [file_entry()], "R")
    assert codecheck.validate_code("R", r) == []
    assert "CLIP_CAP <- c(-100.0, 40.0, 88.0)" in r
    assert "WORLD_BOUNDS <- c(" in r


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


def test_notes_list_unreproduced_features():
    state = make_state(map={"bathymetry": True, "basemap": "satellite",
                            "fills": {"biodiversity": True}})
    code = codegen.generate_code(state, [], "Python")
    assert "NOT reproduced" in code
    assert "Bathymetry" in code
    assert "satellite" in code
    assert "Biodiversity hotspots" in code
    assert "compass" in code
    # ... and nothing pretends to draw them.
    assert "biodiversity" not in code.split("NE_LAYERS")[1].split("]")[0]


def test_capitals_only_swaps_the_cities_layer():
    code = codegen.generate_code(
        make_state(map={"capitals_only": True}), [], "Python")
    assert "('adm0cap', ['1'], True)" in code
    assert "'marker': '*'" in code  # the capitals star


# ---------------------------------------------------------------- extent

def test_view_extent_geographic_partial_view():
    state = make_state(map={"projection": "Equirectangular"},
                       view={"xlim": [-30, 60], "ylim": [-10, 40]})
    assert codegen.view_extent_lonlat(state) == (-30, 60, -10, 40)


def test_view_extent_full_world_falls_back_to_continent():
    state = make_state(map={"projection": "Equirectangular",
                            "continent": "Europe"},
                       view={"xlim": [-180, 180], "ylim": [-90, 90]})
    assert codegen.view_extent_lonlat(state) == CONTINENT_EXTENTS["Europe"]


def test_view_extent_projected_view_inverts_to_lonlat():
    projection = get_projection("Robinson")
    x0, x1 = projection.forward([-30.0, 60.0], [0.0, 0.0])[0]
    y = projection.forward([0.0, 0.0], [-10.0, 40.0])[1]
    state = make_state(view={"xlim": [float(x0), float(x1)],
                             "ylim": [float(y[0]), float(y[1])]})
    lon0, lon1, lat0, lat1 = codegen.view_extent_lonlat(state)
    # The view is a rectangle in projected space, so its lon/lat bounds
    # are somewhat wider than the equator span it was built from - but
    # they must contain it and stay close.
    assert lon0 == pytest.approx(-30, abs=8) and lon0 <= -30
    assert lon1 == pytest.approx(60, abs=8) and lon1 >= 60
    assert lat0 == pytest.approx(-10, abs=1)
    assert lat1 == pytest.approx(40, abs=1)


def test_view_extent_missing_view_falls_back():
    state = make_state(view={})
    assert codegen.view_extent_lonlat(state) == (-180.0, 180.0,
                                                 -90.0, 90.0)


# -------------------------------------------- datasets, groups, and styles

def test_manual_dataset_is_embedded_inline():
    code = codegen.generate_code(make_state(), [manual_entry()], "Python")
    assert "Legend,Label,Longitude,Latitude" in code
    assert "-100.0,38.0" in code and "140.0,-25.0" in code
    code_r = codegen.generate_code(make_state(), [manual_entry()], "R")
    assert "Legend,Label,Longitude,Latitude" in code_r


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
    body = "\n".join(line for line in code.splitlines()
                     if not line.startswith("library(")
                     and line != "main()")
    harness = body + """
spec <- DATASETS[[1]]
df <- load_points(spec)
stopifnot(nrow(df) == 2)
stopifnot(identical(df$`_lon`, c(-100, 140)))
stopifnot(identical(df$`_lat`, c(38, -25)))
labels <- point_labels(df, spec)
stopifnot(identical(labels, c("spiders", "spiders")))
stopifnot(STYLE_COLORS[["spiders"]] == "#123456")
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
