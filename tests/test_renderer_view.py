"""Tests for the renderer's view: the orientation geometry, cropping a
letterboxed (portrait) map for export, resizing, plotting layers, and
framing across the antimeridian.
"""

from __future__ import annotations

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pymappr.geo.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.renderer.geometry import (  # noqa: E402
    export_geometry, oriented_axes_rect, refit_xlim)
from pymappr.renderer.tables import (  # noqa: E402
    MARGINS_PLAIN, MARGINS_WITH_TICKS, ORIENTATION_ASPECT)
from renderer_helpers import (  # noqa: E402
    _box_aspect, _renderer, _live_box_aspect, _view_aspect)


def test_landscape_keeps_the_full_margin_box():
    rect = oriented_axes_rect(MARGINS_PLAIN, 9.0, 6.5, None)
    left, bottom, right, top = MARGINS_PLAIN
    assert rect == (left, bottom, right - left, top - bottom)


def test_portrait_narrows_and_centres_a_wide_canvas():
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 9.0, 6.5
    rect = oriented_axes_rect(MARGINS_PLAIN, fig_w, fig_h, aspect)
    left, _bottom, width, height = rect
    # The axes box now has the requested width:height ratio.
    assert _box_aspect(rect, fig_w, fig_h) == pytest.approx(aspect, rel=1e-6)
    # It is narrower than, and horizontally centred within, the base box.
    base_left, _b, base_right, _t = MARGINS_PLAIN
    base_width = base_right - base_left
    assert width < base_width
    assert height == pytest.approx(MARGINS_PLAIN[3] - MARGINS_PLAIN[1])
    assert left + width / 2 == pytest.approx(base_left + base_width / 2)


def test_portrait_shortens_a_tall_canvas():
    # A canvas already taller than the portrait aspect loses height, not
    # width, so the box still ends at the requested ratio.
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 6.0, 12.0
    rect = oriented_axes_rect(MARGINS_PLAIN, fig_w, fig_h, aspect)
    _left, bottom, width, height = rect
    assert _box_aspect(rect, fig_w, fig_h) == pytest.approx(aspect, rel=1e-6)
    assert width == pytest.approx(MARGINS_PLAIN[2] - MARGINS_PLAIN[0])
    base_bottom, base_top = MARGINS_PLAIN[1], MARGINS_PLAIN[3]
    assert bottom + height / 2 == pytest.approx((base_bottom + base_top) / 2)


def test_portrait_refit_crops_the_sides_keeping_the_vertical_span():
    # A South-America-ish view (65 wide, 73 tall) fit to a portrait box
    # narrows horizontally about its centre; the y-span is untouched.
    xlim, ylim = (-95.0, -30.0), (-58.0, 15.0)
    box_ratio = ORIENTATION_ASPECT["portrait"]
    new_x0, new_x1 = refit_xlim(box_ratio, xlim, ylim, 360.0, clamp=True)
    assert (new_x0 + new_x1) / 2 == pytest.approx((xlim[0] + xlim[1]) / 2)
    assert (new_x1 - new_x0) < (xlim[1] - xlim[0])          # cropped
    height = ylim[1] - ylim[0]
    assert (new_x1 - new_x0) == pytest.approx(height * box_ratio)


def test_landscape_refit_widens_and_is_reversible():
    xlim, ylim = (-88.9, -36.1), (-58.0, 15.0)   # a portrait view
    height = ylim[1] - ylim[0]
    wide = refit_xlim(1.4, xlim, ylim, 360.0, clamp=True)
    assert (wide[1] - wide[0]) > (xlim[1] - xlim[0])        # widened
    # Round-tripping back to the same ratio restores the same width.
    back = refit_xlim(ORIENTATION_ASPECT["portrait"], wide, ylim, 360.0,
                      clamp=True)
    assert (back[1] - back[0]) == pytest.approx(
        height * ORIENTATION_ASPECT["portrait"])


def test_refit_clamps_landscape_to_the_world_width():
    # A full-height view whose fitted width would exceed the world is
    # clamped (here 180 * 2.5 = 450 -> 360).
    xlim, ylim = (-30.0, 30.0), (-90.0, 90.0)
    wide = refit_xlim(2.5, xlim, ylim, 360.0, clamp=True)
    assert (wide[1] - wide[0]) == pytest.approx(360.0)
    # A hemisphere (globe) view isn't clamped.
    unclamped = refit_xlim(2.5, xlim, ylim, 360.0, clamp=False)
    assert (unclamped[1] - unclamped[0]) == pytest.approx(180.0 * 2.5)


def test_export_leaves_a_full_canvas_unchanged():
    left, bottom, right, top = MARGINS_PLAIN
    pos = (left, bottom, right - left, top - bottom)
    (size, rect) = export_geometry(pos, 9.0, 6.5, MARGINS_PLAIN)
    assert size == pytest.approx((9.0, 6.5))
    assert rect == pytest.approx(pos)


def test_export_crops_a_portrait_letterbox_without_distortion():
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 9.0, 6.5
    rect = oriented_axes_rect(MARGINS_PLAIN, fig_w, fig_h, aspect)
    (exp_w, exp_h), out = export_geometry(rect, fig_w, fig_h, MARGINS_PLAIN)
    # The cropped file is narrower but the same height, and its axes box has
    # identical inches to the on-screen box (so nothing stretches).
    assert exp_w < fig_w
    assert exp_h == pytest.approx(fig_h)
    assert out[2] * exp_w == pytest.approx(rect[2] * fig_w)
    assert out[3] * exp_h == pytest.approx(rect[3] * fig_h)


def test_export_preserves_tick_label_gutter_in_inches():
    # A portrait crop must keep the label gutter at its on-screen inches, or
    # tick labels would crowd off the narrower figure. The left gutter in
    # inches must equal the on-screen margin gutter, not shrink with width.
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 9.0, 6.5
    rect = oriented_axes_rect(MARGINS_WITH_TICKS, fig_w, fig_h, aspect)
    (exp_w, exp_h), out = export_geometry(rect, fig_w, fig_h,
                                          MARGINS_WITH_TICKS)
    left, bottom, right, top = MARGINS_WITH_TICKS
    assert out[0] * exp_w == pytest.approx(left * fig_w)          # left gutter
    assert (1.0 - (out[0] + out[2])) * exp_w == pytest.approx(
        (1.0 - right) * fig_w)                                    # right edge
    assert out[1] * exp_h == pytest.approx(bottom * fig_h)        # bottom
    # The map box itself is unchanged in inches.
    assert out[2] * exp_w == pytest.approx(rect[2] * fig_w)


# --------------------------------------------------------------- resize / view


def test_resize_keeps_portrait_box_aspect():
    # Regression: the oriented axes box is a figure fraction, so resizing the
    # figure (maximising the window, or the first layout after a restored
    # session) used to leave a portrait box at a stale, wide aspect - the map
    # rendered as "landscape but shrunk". The resize handler must re-derive it.
    r = _renderer(9.0, 6.5)
    r.set_extent("South America")
    r.set_orientation("portrait")
    target = ORIENTATION_ASPECT["portrait"]
    assert _live_box_aspect(r) == pytest.approx(target, rel=1e-3)
    for size in ((19.0, 8.0), (7.0, 9.0), (16.0, 6.0)):
        r.fig.set_size_inches(*size, forward=False)
        r._on_resize(None)
        assert _live_box_aspect(r) == pytest.approx(target, rel=1e-3)
        # Map units stay square: the view's data aspect matches the box.
        assert _view_aspect(r) == pytest.approx(target, rel=1e-3)


def test_resize_keeps_landscape_square():
    # Landscape fills the canvas; on resize the map must not stretch, i.e. the
    # data aspect tracks the (changing) box aspect instead of staying fixed.
    r = _renderer(9.0, 6.5)
    r.set_extent("South America")
    for size in ((16.0, 6.0), (6.0, 12.0)):
        r.fig.set_size_inches(*size, forward=False)
        r._on_resize(None)
        assert _view_aspect(r) == pytest.approx(_live_box_aspect(r), rel=1e-3)


def test_resize_suspended_during_export_crop():
    # While the figure is temporarily resized for a cropped export, the resize
    # handler must not re-fit the on-screen view to the export geometry.
    r = _renderer(9.0, 6.5)
    r.set_extent("South America")
    r.set_orientation("portrait")
    with r._cropped_for_export():
        assert r._suspend_resize is True
    assert r._suspend_resize is False


def test_empty_layer_does_not_crash_plotting():
    # A layer that clips to nothing in the current projection (e.g. a regional
    # layer on the far side of the globe) must not raise when it is drawn.
    import geopandas as gpd

    r = _renderer(9.0, 6.5)
    empty = gpd.GeoDataFrame(geometry=[])
    assert r._plot_gdf_copies(empty, zorder=1, facecolor="none") == []


def test_plotting_a_layer_leaves_the_axes_unlabelled():
    # geopandas 1.2+ labels the axes after the CRS; on a map that label
    # only crops into the edge of every exported image.
    import geopandas as gpd
    from shapely.geometry import box

    r = _renderer(9.0, 6.5)
    land = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10)], crs="EPSG:4326")
    assert r._plot_gdf_copies(land, zorder=1, facecolor="none")
    assert (r.ax.get_xlabel(), r.ax.get_ylabel()) == ("", "")


def test_labels_that_stay_in_view_keep_their_text_artists():
    store = LayerStore()
    if store.check_data():
        pytest.skip("map data not downloaded")
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, store)
    r.set_labels("countries", True)
    r.set_extent("Europe")
    before = {t.get_text(): t for t in r._label_texts["countries"]}
    x0, x1 = r.ax.get_xlim()
    r.ax.set_xlim(x0 + 0.5, x1 + 0.5)   # a small pan
    after = {t.get_text(): t for t in r._label_texts["countries"]}
    kept = set(before) & set(after)
    assert kept and all(before[name] is after[name] for name in kept)
    assert all(t.axes is r.ax for t in after.values())


def test_an_unknown_layer_key_is_rejected_before_it_is_recorded():
    # The toggles used to note the key first and look it up second, so a bad
    # key left the visible set holding a name nothing can draw - and every
    # later pan raised on it.
    r = _renderer(9.0, 6.5)
    for setter, state in ((r.set_layer, r._line_visible),
                          (r.set_fill_layer, r._fill_visible),
                          (r.set_point_layer, r._point_layers_visible)):
        with pytest.raises(KeyError):
            setter("nonesuch", True)
        assert not state
    x0, x1 = r.ax.get_xlim()
    r.ax.set_xlim(x0 + 1.0, x1 + 1.0)   # fires _on_limits_changed
    assert r.ax.get_xlim()[0] == pytest.approx(x0 + 1.0)


@pytest.mark.parametrize("lons, expected", [
    ([177.9, 179.2, -179.98, -172.4, -171.7], (177.9, 188.3)),
    ([-95.0, -80.0, -88.0], (-95.0, -80.0)),
    ([10.0], (10.0, 10.0)),
    ([-100.0, 100.0, 0.0], (-100.0, 100.0)),  # no shorter way round
    ([-170.0, 170.0, 0.0], (0.0, 190.0)),
])
def test_lon_span_takes_the_short_way_round(lons, expected):
    from pymappr.renderer.geometry import lon_span
    assert lon_span(lons) == pytest.approx(expected)


@pytest.mark.parametrize("projection", ["Equirectangular", "Robinson",
                                        "Mercator"])
def test_an_extent_across_the_antimeridian_frames_just_that(projection):
    r = _renderer(9.0, 6.5)
    r.set_projection(projection)
    r.set_extent((175.0, 191.0, -23.5, -11.0))
    x0, x1 = r.ax.get_xlim()
    # A small window onto the Pacific, not the whole world.
    assert (x1 - x0) < r.proj.world_width / 8
