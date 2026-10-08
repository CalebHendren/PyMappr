"""Code export: running the generated Python's pre-made code, the package
bootstrap, and the compass."""

import re
import types

import pandas as pd
import pytest

from pymappr.export import codegen
from pymappr.geo.projections import get_projection

from codegen_helpers import (make_state, manual_entry, file_entry, exec_python,
                             run_r_harness)


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


def test_generated_projection_forward_matches_the_app_on_a_region():
    import numpy as np

    name = "Lambert: N. America"
    code = codegen.generate_code(make_state(map={"projection": name}), [],
                                 "Python")
    ns = exec_python(code)
    projection = get_projection(name)
    # 175E wraps to 185W; 10E and 2N are outside the region.
    lons = np.array([175.0, -100.0, 10.0, -120.0])
    lats = np.array([52.0, 45.0, 50.0, 2.0])
    for clamp in (True, False):
        ax, ay = projection.forward(lons, lats, clamp=clamp)
        sx, sy = ns["proj_forward"](lons, lats, clamp=clamp)
        np.testing.assert_allclose(sx, ax)
        np.testing.assert_allclose(sy, ay)


def test_generated_python_graticule_draws_no_chords_across_the_region():
    # As in the app, parallels run west to east across a regional
    # projection instead of wrapping part of the line to its far edge.
    import numpy as np
    from matplotlib.figure import Figure

    for name in ("Lambert: Europe", "Lambert: N. America"):
        code = codegen.generate_code(make_state(map={"projection": name}),
                                     [], "Python")
        ns = exec_python(code)
        ax = Figure().add_subplot()
        ns["draw_graticule"](ax)
        lines = ax.collections[0].get_segments()
        meridians = len(np.arange(-180, 180 + 2.5, 5))
        for seg in lines[meridians:]:
            assert (np.diff(seg[:, 0]) >= -1e-6).all(), name


def test_generated_python_anchors_lambert_labels_like_the_app():
    # A country reaching off Lambert: Europe is labelled on its part on
    # the map (as the app does); one wholly off it is not labelled.
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import box

    name = "Lambert: Europe"
    state = make_state(map={"projection": name,
                            "labels": {"countries": True}})
    py = codegen.generate_code(state, [], "Python")
    ns: dict = {}
    exec(py.replace('if __name__ == "__main__":\n    main()', ""), ns)
    shapes = {"Northland": box(5.0, 58.0, 30.0, 81.0),   # past 72N
              "Eastland": box(50.0, 40.0, 90.0, 55.0),   # past 65E
              "Southland": box(0.0, 4.0, 14.0, 14.0)}    # below 30N
    gdf = gpd.GeoDataFrame({"name": list(shapes), "min_label": 1.0},
                           geometry=list(shapes.values()), crs="EPSG:4326")
    ns["load_natural_earth"] = lambda *args, **kwargs: gdf.copy()
    spec = next(s for s in ns["LABEL_LAYERS"] if s["column"] == "name")
    anchors = ns["label_anchors"](spec)
    assert list(anchors["text"]) == ["Northland", "Eastland"]
    region = get_projection(name).label_region()
    for row in anchors.itertuples():
        expected = shapes[row.text].intersection(region).representative_point()
        assert (row.x, row.y) == (expected.x, expected.y)
    xs, ys = ns["proj_forward"](anchors["x"].to_numpy(),
                                anchors["y"].to_numpy(), clamp=False)
    assert np.isfinite(xs).all() and np.isfinite(ys).all()
    # Off a Lambert map the anchors are the whole features', as before.
    ns["PROJ"] = dict(ns["PROJ"], lon_halfspan=180.0, min_lat=-90.0,
                      max_lat=90.0)
    assert ns["label_region"]() is None


def test_generated_python_drops_natural_earth_features_outside_the_region():
    # Like the app: Natural Earth markers and labels outside a regional
    # projection are dropped, the user's own points clamped onto its edge.
    code = codegen.generate_code(make_state(), [], "Python")
    calls = {re.sub(r"\s+", "", call) for call in
             re.findall(r"proj_forward\(([^()]*(?:\([^()]*\)[^()]*)*)\)",
                        code)}
    assert ("gdf.geometry.x.to_numpy(),gdf.geometry.y.to_numpy(),clamp=False"
            in calls)
    assert 'points["x"].to_numpy(),points["y"].to_numpy(),clamp=False' in calls
    # The user's points, group by group (see dataset_groups), clamped.
    assert "lons,lats" in calls


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


# ------------------------------------------------------------ the compass

CORNER_NAMES = ["upper left", "upper right", "lower left", "lower right"]


def drawn_python_compass(position, style, size=1.0, figsize=(9, 6.5)):
    """The exported script's compass on an Agg figure: the axes, the
    annotation or triangle patch, and the "N"."""
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    state = make_state(map={"compass_options": {
        "position": position, "style": style, "size": size}})
    ns = exec_python(codegen.generate_code(state, [], "Python"))
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = matplotlib.figure.Figure(figsize=figsize)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0.05, 0.05, 0.9, 0.9])
    ns["draw_compass"](ax)
    fig.canvas.draw()
    return fig, ax


def _display(ax, coords, xy):
    transform = ax.transAxes if coords == "axes fraction" else coords
    return transform.transform(xy)


@pytest.mark.parametrize("position", CORNER_NAMES)
def test_python_compass_arrow_points_north_in_every_corner(position):
    _fig, ax = drawn_python_compass(position, "arrow")
    annotation, = ax.texts
    head = _display(ax, annotation.xycoords, annotation.xy)
    label = _display(ax, annotation.anncoords, annotation.xyann)
    assert head[1] > label[1]
    assert head[0] == pytest.approx(label[0])
    if position.startswith("upper"):  # top corners are unchanged
        assert annotation.xy == pytest.approx(
            (0.025 if "left" in position else 0.975, 0.975))


@pytest.mark.parametrize("position", CORNER_NAMES)
def test_python_compass_triangle_points_north_in_every_corner(position):
    _fig, ax = drawn_python_compass(position, "triangle")
    triangle, = ax.patches
    label, = ax.texts
    tip, *base = triangle.get_transform().transform(triangle.get_xy()[:3])
    assert all(tip[1] > corner[1] for corner in base)
    assert label.get_window_extent().y1 <= min(c[1] for c in base) + 1.0


@pytest.mark.parametrize("style", ["arrow", "triangle"])
@pytest.mark.parametrize("position", CORNER_NAMES)
def test_python_compass_stays_inside_the_map(position, style):
    fig, ax = drawn_python_compass(position, style, size=3.0,
                                   figsize=(5, 4))
    renderer = fig.canvas.get_renderer()
    frame = ax.bbox
    for artist in [*ax.texts, *ax.patches]:
        box = artist.get_window_extent(renderer)
        assert box.x0 >= frame.x0 - 1 and box.x1 <= frame.x1 + 1
        assert box.y0 >= frame.y0 - 1 and box.y1 <= frame.y1 + 1


@pytest.mark.parametrize("style", ["arrow", "triangle"])
@pytest.mark.parametrize("position", CORNER_NAMES)
def test_r_compass_points_north_in_every_corner(tmp_path, position, style):
    state = make_state(map={"compass_options": {
        "position": position, "style": style, "size": 3.0}})
    code = codegen.generate_code(state, [], "R")
    run_r_harness(tmp_path, code, """
layers <- compass_layers()
geoms <- vapply(layers, function(l) class(l$geom)[1], character(1))
label <- layers[[which(geoms == "GeomText")]]$data
frac <- function(x, y) {
  c((x - VIEW[1]) / (VIEW[2] - VIEW[1]), (y - VIEW[3]) / (VIEW[4] - VIEW[3]))
}
n <- frac(label$x, label$y)
if (COMPASS$style == "triangle") {
  poly <- layers[[which(geoms == "GeomPolygon")]]$data
  tip <- frac(poly$x[1], poly$y[1])
  base <- frac(poly$x[2:3], poly$y[2:3])
  stopifnot(tip[2] > max(base[3:4]), max(base[3:4]) > n[2])
  xs <- c(poly$x, label$x)
} else {
  seg <- layers[[which(geoms == "GeomSegment")]]$data
  start <- frac(seg$x, seg$y)
  head <- frac(seg$xend, seg$yend)
  stopifnot(head[2] > start[2], start[2] > n[2], head[1] == n[1])
  xs <- c(seg$x, label$x)
}
# Grown to size 3, it still sits inside the frame.
fx <- (xs - VIEW[1]) / (VIEW[2] - VIEW[1])
stopifnot(all(fx > 0), all(fx < 1), n[2] > 0)
if (startsWith(COMPASS$position, "upper")) {
  top <- if (COMPASS$style == "triangle") tip[2] else head[2]
  stopifnot(abs(top - 0.975) < 1e-9)
}
""")
