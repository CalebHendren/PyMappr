"""Code export: the inset map."""

import math
import types

import pytest

from pymappr.export import codegen, layers_config

from codegen_helpers import (make_state, manual_entry, exec_python,
                             run_r_harness, run_r, r_run_state, cities_entry,
                             run_exported_r, assert_r_map_saved)


# --------------------------------------------------------------- inset map
#
# The app hands the exporter its inset fully resolved, from
# MapRenderer.inset_export(); these stand in for it, so the tests need no
# map data. Each box is the outline the app would draw: the main map's view
# on a locator inset, or a zoomed inset's area on the main map.

LOCATOR_VIEW = (-97.3, -96.2, 40.5, 41.4)
ZOOM_VIEW = (-130.0, -60.0, 20.0, 55.0)
GLOBE_CRS = ("+proj=ortho +lat_0=41.0 +lon_0=-97.0 +x_0=0 +y_0=0 "
             "+datum=WGS84 +units=m +no_defs")


def _ring(x0, x1, y0, y1, n=5):
    steps = [i / (n - 1) for i in range(n)]
    xs = ([x0 + (x1 - x0) * t for t in steps] + [x1] * n
          + [x1 - (x1 - x0) * t for t in steps] + [x0] * n)
    ys = ([y0] * n + [y0 + (y1 - y0) * t for t in steps] + [y1] * n
          + [y1 - (y1 - y0) * t for t in steps])
    return xs, ys


def inset_export(kind="locator"):
    """What MapRenderer.inset_export() returns for a Nebraska locator, a
    zoom on the northeastern US, or a globe."""
    lines = {"facecolor": "none", "edgecolor": "#8a8a8a",
             "linestyle": "solid", "linewidth": 0.21, "zorder": 1.4}
    export = {
        "rect": [0.68, 0.02, 0.3, 0.15], "projection": "Equirectangular",
        "crs": None, "hemisphere": False, "lon_0": 0.0, "lat_0": 0.0,
        "min_lat": -90.0, "max_lat": 90.0, "lon_halfspan": 180.0,
        "region": [-104.75, -94.62, 39.76, 43.24],
        "limits": [-104.75, -94.62, 39.76, 43.24], "zoom": 3.41,
        "layers": [
            ["continents", dict(lines, edgecolor="#000000", linewidth=0.48,
                                zorder=1.6)],
            ["land", {"facecolor": "#e3e3e3", "edgecolor": "none",
                      "zorder": 0.35}],
            ["counties", lines]],
        "points": True, "point_scale": 0.3, "frame_width": 0.8,
        "horizon": None,
    }
    if kind == "locator":
        xs, ys = _ring(*LOCATOR_VIEW)
        export["box"] = {"target": "inset", "x": xs, "y": ys,
                         "color": "#d62728", "width": 1.2}
    elif kind == "zoom":
        region = [-80.0, -70.0, 38.0, 45.0]
        xs, ys = _ring(*region)
        export.update(rect=[0.68, 0.02, 0.3, 0.3], region=region,
                      limits=region,
                      box={"target": "main", "x": xs, "y": ys,
                           "color": "#1f77b4", "width": 1.2})
    else:
        radius = 6378137.0
        angles = [2 * math.pi * i / 36 for i in range(37)]
        xs, ys = _ring(-60000.0, 60000.0, -55000.0, 55000.0)
        xs[3] = ys[3] = None  # a point beyond the horizon
        export.update(
            rect=[0.68, 0.02, 0.3, 0.43], projection="Globe (Orthographic)",
            crs=GLOBE_CRS, hemisphere=True, lon_0=-97.0, lat_0=41.0,
            limits=[-6633252.4, 6633252.4, -6633252.4, 6633252.4], zoom=0.0,
            horizon=[[radius * math.sin(a) for a in angles],
                     [radius * math.cos(a) for a in angles]],
            box={"target": "inset", "x": xs, "y": ys, "color": "#d62728",
                 "width": 1.2})
    return export


def inset_state(kind="locator", position="lower right"):
    view = ZOOM_VIEW if kind == "zoom" else LOCATOR_VIEW
    state = make_state(
        map={"projection": "Equirectangular", "graticule": "Off",
             "inset": {"show": True, "position": position}},
        view={"xlim": list(view[:2]), "ylim": list(view[2:])})
    state["inset_export"] = inset_export(kind)
    return state


def drawn_python_inset(state, entries=()):
    """Run the exported draw_inset on an Agg figure; the inset's Natural
    Earth layers are left out (geopandas is stubbed). Returns (namespace,
    figure, main axes, inset axes)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    ns = exec_python(codegen.generate_code(state, list(entries), "Python"))
    if ns["INSET"] is not None:
        ns["INSET"]["layers"] = []
    fig = Figure(figsize=ns["FIGSIZE"], dpi=100)
    FigureCanvasAgg(fig)
    left, bottom, right, top = ns["MARGINS"]
    ax = fig.add_axes([left, bottom, right - left, top - bottom])
    ax.set_autoscale_on(False)
    ax.set_xlim(*ns["VIEW"][:2])
    ax.set_ylim(*ns["VIEW"][2:])
    iax = ns["draw_inset"](fig, ax)
    fig.canvas.draw()
    return ns, fig, ax, iax


def test_inset_is_exported_only_when_the_app_hands_it_over():
    # States from before the inset (or a map without one) export none.
    for state in (make_state(), dict(make_state(), inset_export=None)):
        assert codegen.build_config(state, [])["inset"] is None
        assert "\nINSET = None\n" in codegen.generate_code(state, [],
                                                           "Python")
        assert "\nINSET <- NULL\n" in codegen.generate_code(state, [], "R")

    inset = codegen.build_config(inset_state(), [])["inset"]
    assert inset["rect"] == [0.68, 0.02, 0.3, 0.15]
    assert inset["limits"] == [-104.75, -94.62, 39.76, 43.24]
    assert inset["box"]["target"] == "inset"
    # Each layer is a Natural Earth archive at the inset's own zoom, like
    # the main map's, in draw order.
    assert [layer["key"] for layer in inset["layers"]] == [
        "land", "counties", "continents"]
    land, counties, continents = inset["layers"]
    scale, _category, name, _member = layers_config._source_archive(
        "land", 3.41)
    assert (land["scale"], land["name"]) == (scale, name)
    assert (land["kind"], land["color"]) == ("fill", "#e3e3e3")
    assert (counties["scale"], counties["name"]) == ("10m",
                                                     "admin_2_counties")
    assert (counties["kind"], counties["width"]) == ("line", 0.21)
    assert continents["kind"] == "continents"
    assert continents["name"] == "admin_0_countries"
    # A legend in the inset's corner sits above it.
    assert inset["clear"] == ("lower right", pytest.approx(0.185))


def test_inset_layers_are_clipped_like_the_app():
    state = inset_state("globe")
    assert codegen.build_config(state, [])["inset"]["clip_cap"] == (
        -97.0, 41.0, 88.0)
    # A world projection that blows up at the poles: a symmetric band.
    state["inset_export"].update(crs="+proj=merc", hemisphere=False,
                                 min_lat=-85.0, max_lat=85.0, horizon=None)
    inset = codegen.build_config(state, [])["inset"]
    assert (inset["clip_cap"], inset["band"]) == (None, (-85.0, 85.0))
    # A regional one: its own latitude band.
    state["inset_export"].update(min_lat=15.0, max_lat=80.0,
                                 lon_halfspan=90.0)
    assert codegen.build_config(state, [])["inset"]["band"] == (15.0, 80.0)
    # Plain lon/lat is drawn as it is.
    inset = codegen.build_config(inset_state(), [])["inset"]
    assert (inset["clip_cap"], inset["band"]) == (None, None)


def test_dragged_inset_leaves_the_legend_alone():
    state = inset_state()
    state["map"]["inset"].update(anchor_x=0.4, anchor_y=0.4)
    assert codegen.build_config(state, [])["inset"]["clear"] is None


def test_python_draws_a_locator_inset():
    _ns, _fig, ax, iax = drawn_python_inset(inset_state(), [manual_entry()])
    assert ax.child_axes == [iax]
    assert iax.get_zorder() == 4.5
    assert iax.get_xlim() == pytest.approx((-104.75, -94.62))
    assert iax.get_ylim() == pytest.approx((39.76, 43.24))
    # At its rect in the map's axes fraction.
    box = ax.transAxes.inverted().transform(iax.get_window_extent())
    assert box.ravel() == pytest.approx([0.68, 0.02, 0.98, 0.17], abs=1e-3)
    assert not len(iax.get_xticks()) and not len(iax.get_yticks())
    assert all(spine.get_visible() and spine.get_linewidth() == 0.8
               for spine in iax.spines.values())
    # The box marking the map's view is on the inset, none on the map.
    line, = iax.lines
    assert line.get_color() == "#d62728"
    assert line.get_xydata()[0] == pytest.approx(LOCATOR_VIEW[::2])
    assert not ax.lines
    # The points, at the inset's smaller size.
    sizes = [size for coll in iax.collections for size in coll.get_sizes()]
    assert sizes == pytest.approx([45.0 * 0.3])


def test_python_boxes_a_zoomed_inset_on_the_main_map():
    _ns, _fig, ax, iax = drawn_python_inset(inset_state("zoom"))
    assert not iax.lines
    line, = ax.lines
    assert line.get_color() == "#1f77b4"
    assert line.get_zorder() == 2.5
    assert line.get_xydata()[:, 0].min() == pytest.approx(-80.0)
    # The main map keeps its view.
    assert ax.get_xlim() == pytest.approx(ZOOM_VIEW[:2])


def test_python_draws_a_globe_inset_as_a_disk():
    import numpy as np

    _ns, _fig, ax, iax = drawn_python_inset(inset_state("globe"),
                                            [manual_entry()])
    assert not any(spine.get_visible() for spine in iax.spines.values())
    assert iax.get_facecolor()[3] == 0.0
    disk, = iax.patches
    assert tuple(disk.get_facecolor()[:3]) == (1.0, 1.0, 1.0)
    horizon, box = iax.lines
    assert (horizon.get_color(), horizon.get_zorder()) == ("#000000", 1.9)
    # The point beyond the horizon breaks the box.
    assert box.get_color() == "#d62728"
    assert np.isnan(box.get_xydata()[3]).all()
    # Of the two sites, the one in Australia is on the far side.
    offsets, = [np.asarray(coll.get_offsets(), dtype=float)
                for coll in iax.collections]
    assert np.isfinite(offsets).all(axis=1).sum() == 1
    assert not ax.lines


def test_python_draws_no_inset_for_an_old_state():
    _ns, _fig, ax, iax = drawn_python_inset(make_state())
    assert iax is None and not ax.child_axes


def test_exported_legend_clears_the_inset_in_its_corner(tmp_path):
    state = inset_state()
    state["legend"]["location"] = "lower right"
    ns = exec_python(codegen.generate_code(state, [], "Python"))
    fig = ns["plt"].figure(figsize=(6, 4))
    ax = fig.add_axes([0.05, 0.05, 0.9, 0.9])
    placement = ns["legend_placement"](ax)
    assert placement["loc"] == "lower right"
    assert placement["bbox_to_anchor"] == pytest.approx((1.0, 0.185))
    ns["LEGEND"]["location"] = "upper right"
    assert ns["legend_placement"](ax) == {"loc": "upper right"}
    ns["plt"].close(fig)

    r = codegen.generate_code(state, [], "R")
    run_r_harness(tmp_path, r, """
stopifnot(identical(INSET$clear$corner, "lower right"),
          abs(INSET$clear$y - 0.185) < 1e-9)
""")


@pytest.mark.parametrize("kind", ["locator", "zoom", "globe"])
def test_r_inset_layers(tmp_path, kind):
    code = codegen.generate_code(inset_state(kind), [manual_entry()], "R")
    run_r_harness(tmp_path, code, """
# The Natural Earth layers would need downloads; the rest is drawn.
INSET$layers <- list()
layers <- inset_layers()
stopifnot(length(layers) == 1,
          inherits(layers[[1]]$geom, "GeomCustomAnn"))
args <- layers[[1]]$geom_params
lo <- axes_to_data(INSET$rect[1], INSET$rect[2])
hi <- axes_to_data(INSET$rect[1] + INSET$rect[3],
                   INSET$rect[2] + INSET$rect[4])
stopifnot(isTRUE(all.equal(c(args$xmin, args$xmax, args$ymin, args$ymax),
                           c(lo[[1]], hi[[1]], lo[[2]], hi[[2]]))))
inset <- inset_plot()
stopifnot(isTRUE(all.equal(inset$coordinates$limits$x, INSET$limits[1:2])),
          isTRUE(all.equal(inset$coordinates$limits$y, INSET$limits[3:4])))
geoms <- vapply(inset$layers, function(l) class(l$geom)[1], character(1))
main_box <- inset_box_layers()
if (identical(INSET$box$target, "main")) {
  stopifnot(length(main_box) == 1, !("GeomPath" %in% geoms))
} else {
  stopifnot(length(main_box) == 0, "GeomPath" %in% geoms)
}
if (INSET$hemisphere) {
  stopifnot("GeomPolygon" %in% geoms,
            inherits(inset$theme$panel.border, "element_blank"))
} else {
  stopifnot(identical(inset$theme$panel.border$colour, "#000000"))
}
# The points draw, minus any the inset's projection hides.
stopifnot("GeomSf" %in% geoms)
# The whole map builds with the inset on it.
NE_LAYERS <- list()
invisible(ggplotGrob(build_map()))
""")


def test_renderer_inset_reaches_the_exported_script():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from pymappr.geo.layers import LayerStore
    from pymappr.renderer import MapRenderer
    from pymappr.styling.decorations import InsetOptions

    store = LayerStore()
    if store.check_data():
        pytest.skip("map data not downloaded")
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    renderer = MapRenderer(fig, store)
    renderer.set_layer("countries", True)
    renderer.set_extent(LOCATOR_VIEW)
    options = InsetOptions(show=True, region="state", states=True)
    renderer.set_inset(options)
    export = renderer.inset_export()
    xlim, ylim = renderer.get_view()
    state = make_state(map={"projection": "Equirectangular",
                            "inset": options.to_dict()},
                       view={"xlim": list(xlim), "ylim": list(ylim)})
    state["inset_export"] = export
    ns = exec_python(codegen.generate_code(state, [], "Python"))
    assert ns["INSET"]["rect"] == pytest.approx(export["rect"])
    assert ns["INSET"]["limits"] == pytest.approx(export["limits"])
    assert len(ns["INSET"]["layers"]) == len(export["layers"])
    assert ns["INSET"]["box"]["target"] == export["box"]["target"]


def test_code_export_dialog_hands_over_the_inset():
    from pymappr.ui.code_export import CodeExportDialog

    app = types.SimpleNamespace(
        _collect_state=make_state,
        renderer=types.SimpleNamespace(inset_export=inset_export))
    dialog = types.SimpleNamespace(app=app)
    state = CodeExportDialog._state(dialog)
    assert state["inset_export"] == inset_export()


@run_r
@pytest.mark.parametrize("kind", ["zoom", "globe"])
def test_exported_r_script_draws_an_inset(tmp_path, kind):
    state = r_run_state("Equirectangular")
    view = ZOOM_VIEW if kind == "zoom" else LOCATOR_VIEW
    state["view"] = {"xlim": list(view[:2]), "ylim": list(view[2:])}
    state["map"]["inset"] = {"show": True}
    state["inset_export"] = inset_export(kind)
    result = run_exported_r(tmp_path, state, [cities_entry()])
    assert_r_map_saved(tmp_path, result)
