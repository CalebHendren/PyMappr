"""Renderer tests: scroll-wheel zooming, its preview, and the toolbar history."""

from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from renderer_helpers import (  # noqa: E402
    _disk_frame, _buffer_xy, _renderer, _MouseEvent, _pan_renderer,
    _red_centre, _axes_centre, _count_draws, _fire, _fire_zoom_pause,
    _axes_rgb)


def test_scroll_notches_render_nothing_until_the_wheel_rests():
    r = _pan_renderer()
    draws = _count_draws(r)
    cx, cy = _axes_centre(r)
    for _ in range(5):
        r.zoom_interactive(1.25, (cx + 80, cy - 40))
    assert len(draws) == 0
    timer = r._zoom_gesture["timer"]
    assert timer.interval == 150 and timer.single_shot
    _fire_zoom_pause(r)
    assert len(draws) == 1
    assert r._zoom_gesture is None


def test_the_first_notch_renders_once_when_there_is_no_snapshot():
    r = _renderer(9.0, 6.5)
    draws = _count_draws(r)
    for _ in range(3):
        r.zoom_interactive(1.25)
    assert len(draws) == 1


_CURSOR_PATHS = {
    # (factor, cursor offset from the axes centre in pixels) per notch.
    "in at one point": [(1.25, (80, -40))] * 5,
    "in and out as the cursor moves": [(1.25, (80, -40)), (1.25, (-30, 50)),
                                       (1 / 1.25, (120, 10)),
                                       (1.25, (0, 0)), (1.25, (-90, -70))],
    # The scales cancel, leaving the view shifted rather than zoomed.
    "in at one point, out at another": [(1.25, (80, -40)),
                                        (1 / 1.25, (-60, 30))],
    "the zoom buttons": [(1.5, None), (1.5, None), (1 / 1.5, None)],
}


@pytest.mark.parametrize("path", _CURSOR_PATHS.values(), ids=_CURSOR_PATHS)
def test_a_zoom_burst_ends_where_the_same_zooms_one_by_one_would(path):
    r = _pan_renderer()
    start = r.get_view()
    cx, cy = _axes_centre(r)
    for factor, offset in path:
        if offset is None:
            r.zoom(factor)
        else:
            # The map point under the cursor, as each notch finds it.
            r.zoom(factor, r.ax.transData.inverted().transform(
                (cx + offset[0], cy + offset[1])))
    expected = r.get_view()
    r.set_view(*start)
    r.fig.canvas.draw()
    for factor, offset in path:
        r.zoom_interactive(factor, None if offset is None
                           else (cx + offset[0], cy + offset[1]))
    _fire_zoom_pause(r)
    width = abs(expected[0][1] - expected[0][0])
    for got, want in zip(r.get_view(), expected):
        assert got == pytest.approx(want, abs=width * 1e-9)


def test_the_zoom_preview_scales_the_map_about_the_cursor():
    r = _pan_renderer()
    before = np.array(_red_centre(r.fig.canvas))
    cx, cy = _axes_centre(r)
    cursor = (cx - 150, cy + 40)
    anchor = np.array(_buffer_xy(r, *cursor))
    r.zoom_interactive(1.25, cursor)
    np.testing.assert_allclose(_red_centre(r.fig.canvas),
                               anchor + 1.25 * (before - anchor), atol=1.0)
    r.zoom_interactive(1.25, cursor)
    preview = np.array(_red_centre(r.fig.canvas))
    np.testing.assert_allclose(preview, anchor + 1.5625 * (before - anchor),
                               atol=1.0)
    # The render the pause brings puts the marker where the preview had it,
    # give or take the snapping of the marker to whole pixels, which the
    # preview scales up along with the rest of the snapshot.
    _fire_zoom_pause(r)
    np.testing.assert_allclose(_red_centre(r.fig.canvas), preview, atol=2.0)


def test_every_zoom_preview_scales_the_gestures_first_snapshot():
    # Scaling the previous preview instead would compound the resampling:
    # out and back in again would come back blurred, not as it started.
    r = _pan_renderer()
    before = _axes_rgb(r.fig.canvas, r.ax).copy()
    cx, cy = _axes_centre(r)
    r.zoom_interactive(1 / 1.25, (cx + 60, cy + 30))
    assert not np.array_equal(_axes_rgb(r.fig.canvas, r.ax), before)
    r.zoom_interactive(1.25, (cx + 60, cy + 30))
    assert np.array_equal(_axes_rgb(r.fig.canvas, r.ax), before)


def test_zooming_out_fills_the_uncovered_border_with_the_facecolour():
    r = _pan_renderer()
    r.ax.set_facecolor("#204060")
    r.fig.canvas.draw()
    r.zoom_interactive(1 / 1.5)
    interior = _axes_rgb(r.fig.canvas, r.ax)
    # A third of the box is uncovered, split evenly; take a band well
    # inside the left one.
    band = interior[:, :interior.shape[1] // 8]
    assert (band == (0x20, 0x40, 0x60)).all()


def test_zooming_the_globe_interactively_keeps_it_centred():
    from pymappr.geo.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.fig.canvas.draw()
    span = abs(r.ax.get_xlim()[1] - r.ax.get_xlim()[0])
    bbox = r.ax.bbox
    for _ in range(2):
        r.zoom_interactive(1.5, (bbox.x0 + 40, bbox.y0 + 30))
    _fire_zoom_pause(r)
    frac_x, frac_y, _fill = _disk_frame(r)
    assert frac_x == pytest.approx(0.5) and frac_y == pytest.approx(0.5)
    assert abs(r.ax.get_xlim()[1] - r.ax.get_xlim()[0]) == pytest.approx(
        span / 2.25)


def test_a_pan_press_applies_a_pending_zoom_first():
    # The pan shifts the snapshot of the last render, so a zoom still
    # waiting on its timer is applied and rendered before the drag begins.
    r = _pan_renderer()
    cx, cy = _axes_centre(r)
    start = r.ax.get_xlim()
    for _ in range(2):
        r.zoom_interactive(1.25, (cx + 80, cy - 40))
    draws = _count_draws(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    assert len(draws) == 1
    assert r._zoom_gesture is None
    x0, x1 = r.ax.get_xlim()
    assert x1 - x0 == pytest.approx((start[1] - start[0]) / 1.5625)
    bbox = r.ax.bbox
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 40, cy))
    r._on_canvas_release(_MouseEvent(r.ax, cx + 40, cy))
    assert len(draws) == 2
    assert r.ax.get_xlim()[0] - x0 == pytest.approx(
        -(x1 - x0) / bbox.width * 40)


def test_a_globe_press_applies_a_pending_zoom_first():
    from pymappr.geo.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.fig.canvas.draw()
    span = abs(r.ax.get_xlim()[1] - r.ax.get_xlim()[0])
    for _ in range(2):
        r.zoom_interactive(1.25)
    assert r._zoom_gesture is not None
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy, button=1))
    assert r._zoom_gesture is None
    assert r._globe_drag is not None
    assert abs(r.ax.get_xlim()[1] - r.ax.get_xlim()[0]) == pytest.approx(
        span / 1.5625)


def test_the_wheel_is_ignored_during_a_pan_drag():
    r = _pan_renderer()
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    assert r._pan_drag is not None
    draws = _count_draws(r)
    r.zoom_interactive(1.25, (cx, cy))
    assert r._zoom_gesture is None
    assert not draws


def _start_a_zoom(r):
    """Scroll twice and leave the gesture waiting on its timer; returns the
    timer so a test can fire it after the gesture should be gone."""
    cx, cy = _axes_centre(r)
    for _ in range(2):
        r.zoom_interactive(1.25, (cx + 80, cy - 40))
    assert r._zoom_gesture is not None
    return r._zoom_gesture["timer"]


_VIEW_CHANGES = {
    "set_view": lambda r, start: r.set_view(*start),
    "set_extent": lambda r, start: r.set_extent("Africa"),
    "set_projection": lambda r, start: r.set_projection("Robinson"),
}


@pytest.mark.parametrize("change", _VIEW_CHANGES.values(), ids=_VIEW_CHANGES)
def test_an_explicit_view_change_cancels_a_pending_zoom(change):
    # Within the pause after a scroll, a restored session, a preset extent or
    # a new projection must win: the zoom left waiting would otherwise land
    # on top of it when its timer fires.
    reference = _pan_renderer()
    change(reference, reference.get_view())
    r = _pan_renderer()
    start = r.get_view()
    timer = _start_a_zoom(r)
    change(r, start)
    assert r._zoom_gesture is None
    # Dropped, not applied: the view is the change's alone.
    assert r.get_view() == reference.get_view()
    _fire(timer)                      # a timer that already went off
    assert r.get_view() == reference.get_view()


def _toolbar_renderer():
    from matplotlib.backend_bases import NavigationToolbar2

    r = _renderer(9.0, 6.5)
    r.set_extent("World")
    r.fig.canvas.draw()
    toolbar = NavigationToolbar2(r.fig.canvas)
    toolbar.push_current()            # Home: the world
    r.zoom(2.0)
    toolbar.push_current()
    return r, toolbar


@pytest.mark.parametrize("button", ["home", "back", "forward"])
def test_the_toolbar_history_cancels_a_pending_zoom(button):
    r, toolbar = _toolbar_renderer()
    zoomed = r.get_view()
    toolbar.back()
    world = r.get_view()
    if button == "forward":
        expected = zoomed
    else:
        toolbar.forward()
        expected = world
    timer = _start_a_zoom(r)
    getattr(toolbar, button)()
    assert r._zoom_gesture is None
    assert r.get_view() == expected
    _fire(timer)
    assert r.get_view() == expected
