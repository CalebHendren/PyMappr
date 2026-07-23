"""Tests for the map-orientation geometry helpers in the renderer.

These cover the pure functions that turn an orientation into an axes box
and that crop a letterboxed (portrait) map for export - no matplotlib
canvas or map data required.
"""

from __future__ import annotations

import pytest

from pymappr.renderer import (_MARGINS_PLAIN, _MARGINS_WITH_TICKS,
                              ORIENTATION_ASPECT, _export_geometry,
                              _oriented_axes_rect)


def _box_aspect(rect, fig_w, fig_h):
    _left, _bottom, width, height = rect
    return (width * fig_w) / (height * fig_h)


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
