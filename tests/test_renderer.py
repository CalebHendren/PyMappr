"""Tests for the map-orientation geometry helpers in the renderer.

These cover the pure functions that turn an orientation into an axes box
and that crop a letterboxed (portrait) map for export - no matplotlib
canvas or map data required.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pymappr.layers import LayerStore  # noqa: E402
from pymappr.renderer import (MARGINS_PLAIN, MARGINS_WITH_TICKS,  # noqa: E402
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


class _FakeToolbar:
    """A stand-in matplotlib toolbar with an active tool (``mode`` set), plus
    the one hook the Agg draw path calls when a toolbar is present."""

    def __init__(self, mode="pan/zoom"):
        self.mode = mode

    def _wait_cursor_for_draw_cm(self):
        import contextlib

        return contextlib.nullcontext()


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
    rect = _oriented_axes_rect(MARGINS_PLAIN, 9.0, 6.5, None)
    left, bottom, right, top = MARGINS_PLAIN
    assert rect == (left, bottom, right - left, top - bottom)


def test_portrait_narrows_and_centres_a_wide_canvas():
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 9.0, 6.5
    rect = _oriented_axes_rect(MARGINS_PLAIN, fig_w, fig_h, aspect)
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
    rect = _oriented_axes_rect(MARGINS_PLAIN, fig_w, fig_h, aspect)
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
    left, bottom, right, top = MARGINS_PLAIN
    pos = (left, bottom, right - left, top - bottom)
    (size, rect) = _export_geometry(pos, 9.0, 6.5, MARGINS_PLAIN)
    assert size == pytest.approx((9.0, 6.5))
    assert rect == pytest.approx(pos)


def test_export_crops_a_portrait_letterbox_without_distortion():
    aspect = ORIENTATION_ASPECT["portrait"]
    fig_w, fig_h = 9.0, 6.5
    rect = _oriented_axes_rect(MARGINS_PLAIN, fig_w, fig_h, aspect)
    (exp_w, exp_h), out = _export_geometry(rect, fig_w, fig_h, MARGINS_PLAIN)
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
    rect = _oriented_axes_rect(MARGINS_WITH_TICKS, fig_w, fig_h, aspect)
    (exp_w, exp_h), out = _export_geometry(rect, fig_w, fig_h,
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


# ------------------------------------------------------- legend text formatting


def test_legend_text_formatting_applies_and_collects_underlines():
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("Alpha", PointStyle(color="#d62728"),
                         np.array([-60.0]), np.array([-15.0]))])
    r.set_legend(True, title="Sites", label_bold=True, label_italic=True,
                 label_underline=True, title_bold=True, title_italic=False,
                 title_underline=True)
    leg = r.ax.get_legend()
    text = leg.get_texts()[0]
    assert text.get_fontweight() == "bold"
    assert text.get_fontstyle() == "italic"
    title = leg.get_title()
    assert title.get_fontweight() == "bold"
    assert title.get_fontstyle() == "normal"
    # The label and the title are both flagged for underlining.
    assert set(r._legend_underline_texts) == {text, title}


def test_legend_underlines_cleared_when_hidden():
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("Alpha", PointStyle(color="#d62728"),
                         np.array([-60.0]), np.array([-15.0]))])
    r.set_legend(True, label_underline=True)
    assert r._legend_underline_texts
    r.set_legend(False, label_underline=True)  # legend hidden: nothing to draw
    assert r._legend_underline_texts == []


# --------------------------------------------------------------- globe spinning


def test_dragging_the_globe_recentres_the_projection():
    from pymappr.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.fig.canvas.draw()
    seen = []
    r.set_globe_rotate_callback(lambda lon0, lat0: seen.append((lon0, lat0)))
    r._on_canvas_press(_MouseEvent(r.ax, 400, 300, button=1))
    assert r._globe_drag is not None
    r._on_canvas_motion(_MouseEvent(r.ax, 460, 260))
    # Dragging moved the centre off (0, 0), and the callback fired in step.
    assert (r.proj.lon_0, r.proj.lat_0) != (0.0, 0.0)
    assert seen and seen[-1] == (r.proj.lon_0, r.proj.lat_0)
    r._on_canvas_release(_MouseEvent(r.ax, 460, 260))
    assert r._globe_drag is None


def test_non_globe_projection_does_not_spin():
    r = _renderer(9.0, 6.5)  # Equirectangular is not a hemisphere
    r._on_canvas_press(_MouseEvent(r.ax, 400, 300, button=1))
    assert r._globe_drag is None


def test_globe_spins_when_the_pan_tool_is_active():
    # Panning the globe should spin it, not slide the disk: the globe grabs
    # the drag even while the toolbar pan tool is active, and matplotlib's
    # axes pan/zoom is disabled so the two never fight.
    from pymappr.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.fig.canvas.draw()
    r.fig.canvas.toolbar = _FakeToolbar()
    assert r.ax.can_pan() is False and r.ax.can_zoom() is False
    r._on_canvas_press(_MouseEvent(r.ax, 400, 300, button=1))
    assert r._globe_drag is not None
    r._on_canvas_motion(_MouseEvent(r.ax, 460, 260))
    assert (r.proj.lon_0, r.proj.lat_0) != (0.0, 0.0)


def test_switching_off_the_globe_restores_panning():
    from pymappr.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    assert "can_pan" in r.ax.__dict__
    r.set_projection("Equirectangular")
    assert "can_pan" not in r.ax.__dict__ and "can_zoom" not in r.ax.__dict__


def test_globe_view_is_circular_not_stretched():
    # The globe's projected bounds are a square disk. In the wide map axes the
    # view must be re-fit so map units stay square (aspect == the box aspect),
    # or the disk renders as an ellipse. This guards the "stretched globe" bug.
    from pymappr.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    assert _view_aspect(r) == pytest.approx(_live_box_aspect(r), rel=1e-3)
    # Re-centring (a spin) must keep it circular, not reset to raw bounds.
    r.set_projection(GLOBE, -100.0, 40.0)
    assert _view_aspect(r) == pytest.approx(_live_box_aspect(r), rel=1e-3)


def _disk_frame(renderer):
    """Where the globe's disk sits in the view: ``(centre x fraction, centre
    y fraction, diameter / view height)``."""
    x0, x1 = renderer.ax.get_xlim()
    y0, y1 = renderer.ax.get_ylim()
    cx, cy, radius = renderer._globe_disk()
    return ((cx - x0) / (x1 - x0), (cy - y0) / (y1 - y0),
            2 * radius / abs(y1 - y0))


def test_globe_sits_centred_with_a_margin_not_filling_the_canvas():
    from pymappr.projections import GLOBE
    from pymappr.renderer import _GLOBE_FILL

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    frac_x, frac_y, fill = _disk_frame(r)
    assert frac_x == pytest.approx(0.5) and frac_y == pytest.approx(0.5)
    # The disk spans the box's short side only partly, leaving a margin.
    assert fill == pytest.approx(_GLOBE_FILL)
    assert fill < 1.0


@pytest.mark.parametrize("extent", ["World", "Europe", "South America"])
def test_spinning_the_globe_never_shifts_or_resizes_it(extent):
    # The bug: the view was rebuilt from the extent request on every spin, and
    # a lon/lat box's projected bounding box lurches sideways and changes width
    # as parts of it swing behind the horizon - so the globe jumped left and
    # right mid-drag. The disk must stay dead centre at a constant size.
    from pymappr.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_extent(extent)
    r.set_projection(GLOBE, 0.0, 0.0)
    start_fill = _disk_frame(r)[2]
    for lon0 in range(-180, 180, 30):
        for lat0 in (-66.0, -17.0, 0.0, 40.0, 89.0):
            r.set_projection(GLOBE, float(lon0), lat0)
            frac_x, frac_y, fill = _disk_frame(r)
            assert frac_x == pytest.approx(0.5), (lon0, lat0)
            assert frac_y == pytest.approx(0.5), (lon0, lat0)
            assert fill == pytest.approx(start_fill), (lon0, lat0)
            assert _view_aspect(r) == pytest.approx(_live_box_aspect(r),
                                                    rel=1e-3)


def test_spinning_the_globe_preserves_the_zoom_level():
    from pymappr.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.zoom(2.0)
    span = r.ax.get_xlim()[1] - r.ax.get_xlim()[0]
    r.set_projection(GLOBE, 25.0, 10.0)
    assert r.ax.get_xlim()[1] - r.ax.get_xlim()[0] == pytest.approx(span)
    assert _disk_frame(r)[0] == pytest.approx(0.5)


def test_zooming_the_globe_keeps_it_centred():
    # Zooming about the cursor would slide the disk off centre and the next
    # spin would snap it back; on the globe the cursor is ignored.
    from pymappr.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.zoom(1.5, (4.0e6, -3.0e6))
    frac_x, frac_y, _fill = _disk_frame(r)
    assert frac_x == pytest.approx(0.5) and frac_y == pytest.approx(0.5)


def test_globe_stays_centred_and_whole_in_portrait():
    from pymappr.projections import GLOBE
    from pymappr.renderer import _GLOBE_FILL

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.set_orientation("portrait")
    x0, x1 = r.ax.get_xlim()
    cx, _cy, radius = r._globe_disk()
    # Portrait's short side is the width, so the disk is fitted across it.
    assert (cx - x0) / (x1 - x0) == pytest.approx(0.5)
    assert 2 * radius / abs(x1 - x0) == pytest.approx(_GLOBE_FILL)
    assert _disk_frame(r)[1] == pytest.approx(0.5)
    r.set_orientation("landscape")
    assert _disk_frame(r)[2] == pytest.approx(_GLOBE_FILL)


def test_globe_survives_a_window_resize():
    from pymappr.projections import GLOBE
    from pymappr.renderer import _GLOBE_FILL

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.fig.set_size_inches(5.0, 8.0)
    r._on_resize(None)
    frac_x, frac_y, _fill = _disk_frame(r)
    assert frac_x == pytest.approx(0.5) and frac_y == pytest.approx(0.5)
    x0, x1 = r.ax.get_xlim()
    assert 2 * r._globe_disk()[2] / abs(x1 - x0) == pytest.approx(_GLOBE_FILL)


def test_empty_layer_does_not_crash_plotting():
    # A layer that clips to nothing in the current projection (e.g. a regional
    # layer on the far side of the globe) must not raise when it is drawn.
    import geopandas as gpd

    r = _renderer(9.0, 6.5)
    empty = gpd.GeoDataFrame(geometry=[])
    assert r._plot_gdf_copies(empty, zorder=1, facecolor="none") == []


# ---------------------------------------------------------- nested legend


def _beetle_sections(**kwargs):
    import pandas as pd

    from pymappr.styles import (attribute_style_maps, legend_counts,
                                legend_sections)
    path = (Path(__file__).resolve().parent.parent / "sample_data"
            / "south_america_beetles.csv")
    frame = pd.read_csv(path).rename(columns={"Genus": "name1",
                                              "Species": "name2"})
    cmap, smap = attribute_style_maps(frame, "name1", "name2")
    counts = (legend_counts(frame, "name1", "name2")
              if kwargs.pop("counts", False) else None)
    return frame, legend_sections(frame, "name1", "name2", cmap, smap,
                                  "Genus", "Species", counts=counts,
                                  **kwargs)


def _legend_rows(renderer):
    legend = renderer.ax.get_legend()
    return [(t.get_text(), t.get_fontweight()) for t in legend.get_texts()]


def test_nested_legend_indents_species_under_their_genus():
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(True, None, "upper right")
    rows = _legend_rows(r)
    texts = [text for text, _weight in rows]
    assert "   Eleusis" in texts          # genus: one indent
    assert "      chapadensis" in texts   # species: two


def test_nested_legend_bolds_the_genus_rows_only():
    # Every swatch sits in the same column, so indentation alone reads too
    # weakly - the group rows take the header weight as well.
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(True, None, "upper right", title_bold=True,
                 label_bold=False)
    weights = dict(_legend_rows(r))
    assert weights["   Eleusis"] == "bold"
    assert weights["      chapadensis"] == "normal"


def test_crossed_legend_keeps_every_row_at_one_indent():
    import pandas as pd

    from pymappr.styles import attribute_style_maps, legend_sections
    frame = pd.DataFrame({
        "name1": ["forest", "forest", "scrub", "scrub"],
        "name2": ["male", "female", "male", "female"],
        "lon": [1.0, 2.0, 3.0, 4.0], "lat": [1.0, 2.0, 3.0, 4.0],
    })
    cmap, smap = attribute_style_maps(frame, "name1", "name2")
    sections = legend_sections(frame, "name1", "name2", cmap, smap,
                               "Habitat", "Sex")
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(True, None, "upper right", title_bold=True, label_bold=False)
    rows = _legend_rows(r)
    entries = [(text, weight) for text, weight in rows if text.strip()
               and text not in ("Habitat", "Sex")]
    assert all(text.startswith("   ") and not text.startswith("      ")
               for text, _w in entries)
    # Only the two section titles are bold here, never the value rows.
    assert all(weight == "normal" for _t, weight in entries)


def test_legacy_two_tuple_entries_still_draw():
    # Plain-mode sections are (label, style) pairs; they must keep working
    # alongside the (label, style, depth) rows a nested key emits.
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend([("Dataset", [("Site A", PointStyle())])])
    r.set_legend(True, None, "upper right")
    assert "   Site A" in [text for text, _w in _legend_rows(r)]
