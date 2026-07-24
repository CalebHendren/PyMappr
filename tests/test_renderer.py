"""Tests for the map-orientation geometry helpers in the renderer.

These cover the pure functions that turn an orientation into an axes box
and that crop a letterboxed (portrait) map for export - no matplotlib
canvas or map data required.
"""

from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pymappr.layers import LayerStore  # noqa: E402
from pymappr.renderer import (_MARGINS_PLAIN, _MARGINS_WITH_TICKS,  # noqa: E402
                              ORIENTATION_ASPECT, MapRenderer,
                              _export_geometry, _oriented_axes_rect,
                              _refit_xlim)
from pymappr.styles import PointStyle  # noqa: E402


def _box_aspect(rect, fig_w, fig_h):
    _left, _bottom, width, height = rect
    return (width * fig_w) / (height * fig_h)


def _renderer(fig_w: float = 9.0, fig_h: float = 6.5) -> MapRenderer:
    """A renderer on an Agg canvas. It never touches map-data layers, so the
    geometry and legend behaviour can be exercised without the Natural Earth
    download."""
    fig = Figure(figsize=(fig_w, fig_h), dpi=100)
    FigureCanvasAgg(fig)
    return MapRenderer(fig, LayerStore())


def _live_box_aspect(renderer: MapRenderer) -> float:
    pos = renderer.ax.get_position()
    fig_w, fig_h = renderer.fig.get_size_inches()
    return (pos.width * fig_w) / (pos.height * fig_h)


def _view_aspect(renderer: MapRenderer) -> float:
    x0, x1 = renderer.ax.get_xlim()
    y0, y1 = renderer.ax.get_ylim()
    return abs(x1 - x0) / abs(y1 - y0)


class _MouseEvent:
    """A stand-in for a matplotlib mouse event (pixel + data coords)."""

    def __init__(self, ax, x, y, button=1, xdata=0.0, ydata=0.0):
        self.inaxes = ax
        self.x = x
        self.y = y
        self.button = button
        self.xdata = xdata
        self.ydata = ydata


def test_landscape_keeps_the_full_margin_box():
    rect = _oriented_axes_rect(_MARGINS_PLAIN, 9.0, 6.5, None)
    left, bottom, right, top = _MARGINS_PLAIN
    assert rect == (left, bottom, right - left, top - bottom)


def test_portrait_narrows_and_centres_a_wide_canvas():
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 9.0, 6.5
    rect = _oriented_axes_rect(_MARGINS_PLAIN, fig_w, fig_h, aspect)
    left, _bottom, width, height = rect
    # The axes box now has the requested width:height ratio.
    assert _box_aspect(rect, fig_w, fig_h) == pytest.approx(aspect, rel=1e-6)
    # It is narrower than, and horizontally centred within, the base box.
    base_left, _b, base_right, _t = _MARGINS_PLAIN
    base_width = base_right - base_left
    assert width < base_width
    assert height == pytest.approx(_MARGINS_PLAIN[3] - _MARGINS_PLAIN[1])
    assert left + width / 2 == pytest.approx(base_left + base_width / 2)


def test_portrait_shortens_a_tall_canvas():
    # A canvas already taller than the portrait aspect loses height, not
    # width, so the box still ends at the requested ratio.
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 6.0, 12.0
    rect = _oriented_axes_rect(_MARGINS_PLAIN, fig_w, fig_h, aspect)
    _left, bottom, width, height = rect
    assert _box_aspect(rect, fig_w, fig_h) == pytest.approx(aspect, rel=1e-6)
    assert width == pytest.approx(_MARGINS_PLAIN[2] - _MARGINS_PLAIN[0])
    base_bottom, base_top = _MARGINS_PLAIN[1], _MARGINS_PLAIN[3]
    assert bottom + height / 2 == pytest.approx((base_bottom + base_top) / 2)


def test_portrait_refit_crops_the_sides_keeping_the_vertical_span():
    # A South-America-ish view (65 wide, 73 tall) fit to a portrait box
    # narrows horizontally about its centre; the y-span is untouched.
    xlim, ylim = (-95.0, -30.0), (-58.0, 15.0)
    box_ratio = ORIENTATION_ASPECT["portrait"]
    new_x0, new_x1 = _refit_xlim(box_ratio, xlim, ylim, 360.0, clamp=True)
    assert (new_x0 + new_x1) / 2 == pytest.approx((xlim[0] + xlim[1]) / 2)
    assert (new_x1 - new_x0) < (xlim[1] - xlim[0])          # cropped
    height = ylim[1] - ylim[0]
    assert (new_x1 - new_x0) == pytest.approx(height * box_ratio)


def test_landscape_refit_widens_and_is_reversible():
    xlim, ylim = (-88.9, -36.1), (-58.0, 15.0)   # a portrait view
    height = ylim[1] - ylim[0]
    wide = _refit_xlim(1.4, xlim, ylim, 360.0, clamp=True)
    assert (wide[1] - wide[0]) > (xlim[1] - xlim[0])        # widened
    # Round-tripping back to the same ratio restores the same width.
    back = _refit_xlim(ORIENTATION_ASPECT["portrait"], wide, ylim, 360.0,
                       clamp=True)
    assert (back[1] - back[0]) == pytest.approx(
        height * ORIENTATION_ASPECT["portrait"])


def test_refit_clamps_landscape_to_the_world_width():
    # A full-height view whose fitted width would exceed the world is
    # clamped (here 180 * 2.5 = 450 -> 360).
    xlim, ylim = (-30.0, 30.0), (-90.0, 90.0)
    wide = _refit_xlim(2.5, xlim, ylim, 360.0, clamp=True)
    assert (wide[1] - wide[0]) == pytest.approx(360.0)
    # A hemisphere (globe) view isn't clamped.
    unclamped = _refit_xlim(2.5, xlim, ylim, 360.0, clamp=False)
    assert (unclamped[1] - unclamped[0]) == pytest.approx(180.0 * 2.5)


def test_export_leaves_a_full_canvas_unchanged():
    left, bottom, right, top = _MARGINS_PLAIN
    pos = (left, bottom, right - left, top - bottom)
    (size, rect) = _export_geometry(pos, 9.0, 6.5, _MARGINS_PLAIN)
    assert size == pytest.approx((9.0, 6.5))
    assert rect == pytest.approx(pos)


def test_export_crops_a_portrait_letterbox_without_distortion():
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 9.0, 6.5
    rect = _oriented_axes_rect(_MARGINS_PLAIN, fig_w, fig_h, aspect)
    (exp_w, exp_h), out = _export_geometry(rect, fig_w, fig_h, _MARGINS_PLAIN)
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
    rect = _oriented_axes_rect(_MARGINS_WITH_TICKS, fig_w, fig_h, aspect)
    (exp_w, exp_h), out = _export_geometry(rect, fig_w, fig_h,
                                           _MARGINS_WITH_TICKS)
    left, bottom, right, top = _MARGINS_WITH_TICKS
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


# ------------------------------------------------------------- legend dragging


def _legend_renderer() -> MapRenderer:
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("A", PointStyle(color="#d62728"),
                         np.array([-60.0]), np.array([-15.0]))])
    r.set_legend(True, location="upper right")
    r.fig.canvas.draw()
    return r


def _legend_center_px(r: MapRenderer):
    bbox = r.ax.get_legend().get_window_extent()
    return (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2


def test_legend_drag_moves_and_anchors_without_a_jump():
    r = _legend_renderer()
    r.set_legend_dragging(True)
    before = r._legend_lowerleft_axes(r.ax.get_legend())
    cx, cy = _legend_center_px(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    # Grabbing an auto-placed legend pins it in place (no hop on press).
    assert r._legend_anchor is not None
    pinned = r._legend_lowerleft_axes(r.ax.get_legend())
    assert pinned == pytest.approx(before, abs=1e-3)
    # Dragging down-left moves the legend and stores the new anchor.
    r._on_canvas_motion(_MouseEvent(r.ax, cx - 120, cy - 120))
    r._on_canvas_release(_MouseEvent(r.ax, cx - 120, cy - 120))
    assert r._legend_drag is None
    after = r._legend_lowerleft_axes(r.ax.get_legend())
    assert after[0] < before[0]
    assert after[1] < before[1]


def test_legend_drag_ignored_when_disabled():
    r = _legend_renderer()
    r.set_legend_dragging(False)
    cx, cy = _legend_center_px(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    assert r._legend_drag is None
    assert r._legend_anchor is None


def test_legend_right_click_and_clear_reset_anchor():
    r = _legend_renderer()
    r.set_legend_dragging(True)
    cx, cy = _legend_center_px(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx - 40, cy - 40))
    r._on_canvas_release(_MouseEvent(r.ax, cx - 40, cy - 40))
    assert r._legend_anchor is not None
    # A right-click on the (now moved) legend restores automatic placement.
    ncx, ncy = _legend_center_px(r)
    r._on_canvas_press(_MouseEvent(r.ax, ncx, ncy, button=3))
    assert r._legend_anchor is None
    # Re-drag, then clearing (e.g. picking a preset position) also resets it.
    r._on_canvas_press(_MouseEvent(r.ax, *_legend_center_px(r)))
    r._on_canvas_motion(_MouseEvent(r.ax, cx - 30, cy - 30))
    r._on_canvas_release(_MouseEvent(r.ax, cx - 30, cy - 30))
    assert r._legend_anchor is not None
    r.clear_legend_anchor()
    assert r._legend_anchor is None
