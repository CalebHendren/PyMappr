"""Code export: the script basics, the map settings baked in, and the view
and geometry."""

import math
import re

import pytest

from pymappr.export import codegen
from pymappr.geo.projections import get_projection

from codegen_helpers import (make_state, manual_entry, file_entry,
                             assert_parses_as_r, exec_python)


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
    # Labeled ticks on every projection but the globe, labels not hidden.
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
    assert curved["graticule"]["labels"] is True
    assert curved["margins"] == codegen.MARGINS_WITH_TICKS
    globe = codegen.build_config(make_state(
        map={"projection": "Globe (Orthographic)", "proj_lon0": "0",
             "proj_lat0": "0"}), [])
    assert globe["graticule"]["labels"] is False


@pytest.mark.parametrize("projection, extent", [
    ("Lambert: Europe", "Europe"),
    ("Robinson", "World"),
    ("Mercator", (-100.0, -77.0, 6.0, 21.0)),
])
def test_exported_python_labels_the_grid_like_the_app(projection, extent):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from pymappr.geo.layers import LayerStore
    from pymappr.renderer import MapRenderer

    def labels(ax):
        return ([t.get_text() for t in ax.get_xticklabels() if t.get_text()],
                [t.get_text() for t in ax.get_yticklabels() if t.get_text()])

    app_fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(app_fig)
    r = MapRenderer(app_fig, LayerStore())
    r.set_projection(projection)
    r.set_extent(extent)
    r.set_graticule(5.0)
    app_fig.canvas.draw()

    state = make_state(map={"projection": projection,
                            "graticule": "5\N{DEGREE SIGN}"})
    ns = exec_python(codegen.generate_code(state, [], "Python"))
    fig = ns["plt"].figure(figsize=(9, 6.5), dpi=100)
    ax = fig.add_axes(list(r.ax.get_position().bounds))
    ax.tick_params(labelsize=7, length=2.5, direction="out")
    ax.set_xlim(*r.ax.get_xlim())
    ax.set_ylim(*r.ax.get_ylim())
    ns["draw_graticule"](ax)
    fig.canvas.draw()
    exported = labels(ax)
    ns["plt"].close(fig)
    assert exported == labels(r.ax)
    assert exported[0] and exported[1]
