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

from pymappr.geo.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.renderer.geometry import (  # noqa: E402
    export_geometry, oriented_axes_rect, refit_xlim)
from pymappr.renderer.tables import (  # noqa: E402
    MARGINS_PLAIN, MARGINS_WITH_TICKS, ORIENTATION_ASPECT)
from pymappr.styling.decorations import ScaleBarOptions  # noqa: E402
from pymappr.styling.legend import LegendOptions  # noqa: E402
from pymappr.styling.styles import PointStyle  # noqa: E402


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


# ------------------------------------------------------------- legend dragging


def _legend_renderer() -> MapRenderer:
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("A", PointStyle(color="#d62728"),
                         np.array([-60.0]), np.array([-15.0]))])
    r.set_legend(LegendOptions(location="upper right"))
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
    r.set_legend(LegendOptions(
        title="Sites", label_bold=True, label_italic=True,
        label_underline=True, title_bold=True, title_italic=False,
        title_underline=True))
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
    r.set_legend(LegendOptions(label_underline=True))
    assert r._legend_underline_texts
    # Legend hidden: nothing left to draw an underline under.
    r.set_legend(LegendOptions(show=False, label_underline=True))
    assert r._legend_underline_texts == []


# --------------------------------------------------------------- globe spinning


def test_dragging_the_globe_recentres_the_projection():
    from pymappr.geo.projections import GLOBE

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
    from pymappr.geo.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.fig.canvas.draw()
    r.fig.canvas.toolbar = _FakeToolbar()
    assert r.ax.can_pan() is False and r.ax.can_zoom() is False
    r._on_canvas_press(_MouseEvent(r.ax, 400, 300, button=1))
    assert r._globe_drag is not None
    r._on_canvas_motion(_MouseEvent(r.ax, 460, 260))
    assert (r.proj.lon_0, r.proj.lat_0) != (0.0, 0.0)


def test_switching_off_the_globe_restores_the_zoom_tool_only():
    # Pan drags are handled here in every projection - the globe spins, the
    # rest blit - so matplotlib's axes pan stays switched off throughout.
    # Only its rubber-band zoom comes back off the globe.
    from pymappr.geo.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    assert "can_pan" in r.ax.__dict__ and "can_zoom" in r.ax.__dict__
    r.set_projection("Equirectangular")
    assert "can_pan" in r.ax.__dict__ and "can_zoom" not in r.ax.__dict__


def test_globe_view_is_circular_not_stretched():
    # The globe's projected bounds are a square disk. In the wide map axes the
    # view must be re-fit so map units stay square (aspect == the box aspect),
    # or the disk renders as an ellipse. This guards the "stretched globe" bug.
    from pymappr.geo.projections import GLOBE

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
    from pymappr.geo.projections import GLOBE
    from pymappr.renderer.view import _GLOBE_FILL

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
    from pymappr.geo.projections import GLOBE

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
    from pymappr.geo.projections import GLOBE

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
    from pymappr.geo.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.zoom(1.5, (4.0e6, -3.0e6))
    frac_x, frac_y, _fill = _disk_frame(r)
    assert frac_x == pytest.approx(0.5) and frac_y == pytest.approx(0.5)


def test_globe_stays_centred_and_whole_in_portrait():
    from pymappr.geo.projections import GLOBE
    from pymappr.renderer.view import _GLOBE_FILL

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
    from pymappr.geo.projections import GLOBE
    from pymappr.renderer.view import _GLOBE_FILL

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


def test_plotting_a_layer_leaves_the_axes_unlabelled():
    # geopandas 1.2+ labels the axes after the CRS; on a map that label
    # only crops into the edge of every exported image.
    import geopandas as gpd
    from shapely.geometry import box

    r = _renderer(9.0, 6.5)
    land = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10)], crs="EPSG:4326")
    assert r._plot_gdf_copies(land, zorder=1, facecolor="none")
    assert (r.ax.get_xlabel(), r.ax.get_ylabel()) == ("", "")


# ---------------------------------------------------------- nested legend


def _beetle_sections(**kwargs):
    import pandas as pd

    from pymappr.styling.legend import legend_counts, legend_sections
    from pymappr.styling.styles import attribute_style_maps
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
    r.set_legend(LegendOptions(location="upper right"))
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
    r.set_legend(LegendOptions(location="upper right", title_bold=True,
                               label_bold=False))
    weights = dict(_legend_rows(r))
    assert weights["   Eleusis"] == "bold"
    assert weights["      chapadensis"] == "normal"


def test_crossed_legend_keeps_every_row_at_one_indent():
    import pandas as pd

    from pymappr.styling.legend import legend_sections
    from pymappr.styling.styles import attribute_style_maps
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
    r.set_legend(LegendOptions(location="upper right", title_bold=True,
                               label_bold=False))
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
    r.set_legend(LegendOptions(location="upper right"))
    assert "   Site A" in [text for text, _w in _legend_rows(r)]


# ------------------------------------------------- legend option plumbing


def _legend_of(renderer):
    return renderer.ax.get_legend()


def test_default_options_reproduce_the_previous_legend_exactly():
    # The settings below were hard-coded before they became options. If a
    # default drifts, every existing project's legend silently changes, so
    # pin them here rather than trusting the dataclass.
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right"))
    leg = _legend_of(r)
    assert leg.get_frame().get_alpha() == pytest.approx(0.85)
    assert leg.get_frame().get_linewidth() == pytest.approx(0.8)
    # Three-space indent per level, group rows bold, blank spacer rows.
    texts = [t.get_text() for t in leg.get_texts()]
    assert "   Eleusis" in texts
    assert "      chapadensis" in texts
    assert " " in texts                       # the spacer between groups
    weights = {t.get_text(): t.get_fontweight() for t in leg.get_texts()}
    assert weights["   Eleusis"] == "bold"
    assert weights["      chapadensis"] == "normal"


def test_indent_width_is_configurable():
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right", indent=1))
    texts = [t.get_text() for t in _legend_of(r).get_texts()]
    assert " Eleusis" in texts
    assert "  chapadensis" in texts

    r.set_legend(LegendOptions(location="upper right", indent=0))
    texts = [t.get_text() for t in _legend_of(r).get_texts()]
    assert "Eleusis" in texts
    assert "chapadensis" in texts


def test_group_rows_can_lose_their_bold_and_their_spacer():
    _frame, sections = _beetle_sections()
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right", bold_groups=False,
                               group_spacer=False))
    leg = _legend_of(r)
    weights = {t.get_text(): t.get_fontweight() for t in leg.get_texts()}
    assert weights["   Eleusis"] == "normal"
    # Only the section title row is left; no blank rows between groups.
    assert [t.get_text() for t in leg.get_texts()].count(" ") == 0


def test_section_titles_off_removes_the_title_row():
    _frame, sections = _beetle_sections(
        options=LegendOptions(section_titles=False))
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend(sections)
    r.set_legend(LegendOptions(location="upper right"))
    texts = [t.get_text() for t in _legend_of(r).get_texts()]
    assert "Genus / Species" not in texts
    assert "   Eleusis" in texts


def test_frame_and_text_colours_reach_the_artists():
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("Alpha", PointStyle(), np.array([0.0]),
                         np.array([0.0]))])
    r.set_legend(LegendOptions(
        title="Key", location="upper right", frame_color="#102030",
        frame_edge_color="#405060", frame_width=2.5, frame_alpha=0.5,
        label_color="#a0b0c0", title_color="#d0e0f0"))
    leg = _legend_of(r)
    frame = leg.get_frame()
    assert frame.get_facecolor()[:3] == pytest.approx(
        (0x10 / 255, 0x20 / 255, 0x30 / 255), abs=1e-3)
    assert frame.get_edgecolor()[:3] == pytest.approx(
        (0x40 / 255, 0x50 / 255, 0x60 / 255), abs=1e-3)
    assert frame.get_linewidth() == pytest.approx(2.5)
    assert frame.get_alpha() == pytest.approx(0.5)
    assert leg.get_texts()[0].get_color() == "#a0b0c0"
    assert leg.get_title().get_color() == "#d0e0f0"


def test_font_family_applies_to_labels_and_title():
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("Alpha", PointStyle(), np.array([0.0]),
                         np.array([0.0]))])
    r.set_legend(LegendOptions(title="Key", font_family="monospace"))
    leg = _legend_of(r)
    assert leg.get_texts()[0].get_fontfamily() == ["monospace"]
    assert leg.get_title().get_fontfamily() == ["monospace"]


def test_a_row_with_no_swatch_still_draws():
    # group_swatch="none" emits a None style; the handle must be blank
    # rather than crash or fall back to a circle.
    r = _renderer(9.0, 6.5)
    r.set_point_groups([("x", PointStyle(), [0.0], [0.0])])
    r.set_structured_legend([("Key", [("Headline", None, 0),
                                      ("Child", PointStyle(), 1)])])
    r.set_legend(LegendOptions(location="upper right"))
    texts = [t.get_text() for t in _legend_of(r).get_texts()]
    assert "   Headline" in texts
    assert "      Child" in texts


def test_plain_legend_row_order_follows_the_app_and_not_draw_order():
    r = _renderer(9.0, 6.5)
    groups = [(name, PointStyle(), np.array([0.0]), np.array([0.0]))
              for name in ("Charlie", "Alpha", "Bravo")]
    r.set_point_groups(groups)
    r.set_legend(LegendOptions(location="upper right"))
    assert [t.get_text() for t in _legend_of(r).get_texts()] == [
        "Charlie", "Alpha", "Bravo"]

    r.set_legend_row_order(["Alpha", "Bravo", "Charlie"])
    assert [t.get_text() for t in _legend_of(r).get_texts()] == [
        "Alpha", "Bravo", "Charlie"]
    # Draw order is untouched: reordering the key must not restack points.
    assert [label for label, *_rest in r._point_groups] == [
        "Charlie", "Alpha", "Bravo"]


def test_legend_anchor_round_trips_for_saving():
    r = _renderer(9.0, 6.5)
    assert r.legend_anchor() is None
    r.set_legend_anchor((0.25, 0.75))
    assert r.legend_anchor() == (0.25, 0.75)
    r.set_legend_anchor(None)
    assert r.legend_anchor() is None


def test_point_outline_reaches_the_map_and_the_legend():
    from matplotlib.colors import to_hex

    r = _renderer(9.0, 6.5)
    white = PointStyle(color="#ffffff", marker="Square")
    hollow = PointStyle(color="#123456", marker="Circle (open)")
    r.set_point_groups([("white", white, [0.0], [0.0]),
                        ("open", hollow, [10.0], [10.0])])
    r.set_legend(LegendOptions(location="upper right"))
    # Unchanged by default: filled markers keep their white edge.
    assert to_hex(r._point_artists[0].get_edgecolors()[0]) == "#ffffff"

    r.set_point_edge("#000000", 0.8)
    filled, outlined = r._point_artists
    assert to_hex(filled.get_edgecolors()[0]) == "#000000"
    assert filled.get_linewidths()[0] == pytest.approx(0.8)
    # Open markers still outline in their own colour.
    assert to_hex(outlined.get_edgecolors()[0]) == "#123456"
    handle = _legend_of(r).legend_handles[0]
    assert handle.get_markeredgecolor() == "#000000"
    assert handle.get_markeredgewidth() == pytest.approx(0.8)


def test_a_legend_only_change_leaves_the_points_as_drawn():
    r = _renderer(9.0, 6.5)
    groups = [("a", PointStyle(), [0.0], [0.0]),
              ("b", PointStyle(color="#000000"), [5.0], [5.0])]
    r.set_points(groups, None, None, LegendOptions())
    drawn = list(r._point_artists)
    r.set_points(groups, None, ["b", "a"],
                 LegendOptions(location="upper left", counts=True))
    assert r._point_artists == drawn        # same scatter objects
    assert [t.get_text() for t in _legend_of(r).get_texts()] == ["b", "a"]
    moved = [("a", PointStyle(), [1.0], [0.0]), groups[1]]
    r.set_points(moved, None, None, LegendOptions())
    assert r._point_artists != drawn        # the points really changed


def test_a_globe_drag_reprojects_at_a_limited_rate_and_ends_where_released():
    from pymappr.geo.projections import GLOBE

    r = _renderer(9.0, 6.5)
    r.set_projection(GLOBE, 0.0, 0.0)
    r.fig.canvas.draw()
    seen = []
    r.set_globe_rotate_callback(lambda lon0, lat0: seen.append(lon0))
    r._on_canvas_press(_MouseEvent(r.ax, 400, 300, button=1))
    for x in range(410, 470, 5):   # a burst of motion events, no pause
        r._on_canvas_motion(_MouseEvent(r.ax, x, 300))
    assert 1 <= len(seen) < 12       # the first applies, the burst coalesces
    r._on_canvas_release(_MouseEvent(r.ax, 465, 300))
    # The release applies the last position the drag reached.
    assert seen[-1] == r.proj.lon_0
    r2 = _renderer(9.0, 6.5)
    r2.set_projection(GLOBE, 0.0, 0.0)
    r2.fig.canvas.draw()
    r2._on_canvas_press(_MouseEvent(r2.ax, 400, 300, button=1))
    r2._on_canvas_motion(_MouseEvent(r2.ax, 465, 300))
    assert r2.proj.lon_0 == pytest.approx(r.proj.lon_0)


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


def _basemap_renderer(extent="World", mode="relief"):
    """A renderer with a raster basemap, or a skip when the data is absent."""
    store = LayerStore()
    if not store.has_basemap(mode):
        pytest.skip("basemap raster not downloaded")
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, store)
    r.set_extent(extent)
    r.set_basemap(mode)
    r.fig.canvas.draw()
    return r


def _primary_raster(r, mode="relief"):
    """The un-wrapped basemap artist (offset 0), the one the view sits on."""
    for artist in r._artists[f"raster_{mode}"]:
        if not getattr(artist, "_pym_offset", 0.0):
            return artist
    raise AssertionError("no primary raster artist")


def test_basemap_is_cropped_to_the_view_not_the_world():
    # The whole point of the crop: imshow's cost tracks the pixels it is handed,
    # so a zoomed-in view must not be handed the whole world.
    r = _basemap_renderer("World")
    world = _primary_raster(r).get_array().shape
    full = r.store.basemap_pyramid("relief")[0].shape
    assert world[1] < full[1]            # the world view already draws coarser

    r.set_extent((-0.6, 0.6, 51.2, 51.8))
    r.fig.canvas.draw()
    city = _primary_raster(r).get_array().shape
    assert city[1] < world[1] / 10       # a city view is a tiny slice
    crop = _primary_raster(r)._pym_crop
    x0, x1 = sorted(r.ax.get_xlim())
    y0, y1 = sorted(r.ax.get_ylim())
    assert crop.covers((x0, x1, y0, y1))  # and it still covers what is shown


def test_projected_basemap_is_warped_over_the_view():
    r = _basemap_renderer("World")
    r.set_projection("Robinson")
    r.set_extent("World")
    r.fig.canvas.draw()
    world = _primary_raster(r)._pym_crop
    r.set_extent((-10, 40, 35, 62))
    r.fig.canvas.draw()
    zoomed = _primary_raster(r)._pym_crop
    # Same grid size either way - it tracks the screen, not the world - but the
    # zoomed warp covers far less ground, which is what makes it sharper.
    assert (zoomed.region[1] - zoomed.region[0]) < (world.region[1]
                                                    - world.region[0]) / 2


def test_a_small_pan_reuses_the_loaded_crop():
    r = _basemap_renderer((-10, 40, 35, 62))
    before = _primary_raster(r)._pym_crop
    x0, x1 = r.ax.get_xlim()
    r.ax.set_xlim(x0 + (x1 - x0) * 0.01, x1 + (x1 - x0) * 0.01)
    r.fig.canvas.draw()
    assert _primary_raster(r)._pym_crop is before   # margin absorbed it
    r.ax.set_xlim(x0 + (x1 - x0) * 0.9, x1 + (x1 - x0) * 0.9)
    r.fig.canvas.draw()
    assert _primary_raster(r)._pym_crop is not before  # left the crop behind


def test_export_dpi_raises_the_basemap_detail_then_restores_it():
    # savefig renders at its own dpi without touching fig.dpi, so without this
    # a high-dpi export would be written from the crop cut for the screen.
    r = _basemap_renderer("World")
    screen = _primary_raster(r).get_array().shape[1]
    with r.basemap_detail_for(600):
        assert _primary_raster(r).get_array().shape[1] > screen
    assert _primary_raster(r).get_array().shape[1] == screen


def _pan_renderer():
    """A renderer with the pan tool active and one marker to track."""
    r = _renderer(9.0, 6.5)
    r.fig.canvas.toolbar = _FakeToolbar()
    r.set_extent("World")
    # A plain data-coordinate artist, so these tests need no map download.
    r.ax.plot([-60.0], [20.0], marker="s", markersize=8, color="red")
    r.fig.canvas.draw()
    return r


def _red_centre(canvas):
    """Where the red marker sits in the canvas buffer (column, row)."""
    buf = np.asarray(canvas.buffer_rgba())[..., :3].astype(int)
    mask = (buf[..., 0] > 150) & (buf[..., 1] < 100) & (buf[..., 2] < 100)
    rows, cols = np.nonzero(mask)
    assert len(rows), "marker not found"
    return cols.mean(), rows.mean()


def _axes_centre(r):
    bbox = r.ax.bbox
    return (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2


def _count_draws(r) -> list:
    """Count full renders from here on. On Agg ``draw_idle`` draws straight
    away, so a deferred ``redraw()`` is counted too."""
    calls = []
    real = r.fig.canvas.draw

    def draw(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    r.fig.canvas.draw = draw
    return calls


def _fire(timer) -> None:
    """Run *timer*'s callbacks as the GUI loop would once it runs out. Agg's
    timers never fire by themselves."""
    for func, args, kwargs in list(timer.callbacks):
        func(*args, **kwargs)


def _fire_pause(r) -> None:
    """Run the drag's pause timer, as if the cursor had rested."""
    _fire(r._pan_drag["timer"])


def _fire_zoom_pause(r) -> None:
    """Run the zoom's timer, as if the scroll wheel had rested."""
    _fire(r._zoom_gesture["timer"])


def _axes_rgb(canvas, ax, inset: int = 4):
    """The axes interior in the canvas buffer (rows count down), less *inset*
    pixels at each edge where the frame line sits."""
    buf = np.asarray(canvas.buffer_rgba())[..., :3]
    height = buf.shape[0]
    x0, y0, x1, y1 = (int(v) for v in ax.bbox.extents)
    return buf[height - y1 + inset:height - y0 - inset,
               x0 + inset:x1 - inset]


def test_a_pan_drag_moves_the_view_by_the_dragged_distance():
    r = _pan_renderer()
    x0, x1 = r.ax.get_xlim()
    y0, y1 = r.ax.get_ylim()
    bbox = r.ax.bbox
    cx, cy = _axes_centre(r)
    dx, dy = 40, 25
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    assert r._pan_drag is not None
    r._on_canvas_motion(_MouseEvent(r.ax, cx + dx, cy + dy))
    r._on_canvas_release(_MouseEvent(r.ax, cx + dx, cy + dy))
    # The map follows the cursor, so the view moves the opposite way.
    assert r.ax.get_xlim()[0] - x0 == pytest.approx(
        -(x1 - x0) / bbox.width * dx)
    assert r.ax.get_ylim()[0] - y0 == pytest.approx(
        -(y1 - y0) / bbox.height * dy)
    assert r._pan_drag is None


def test_a_pan_press_without_a_drag_leaves_the_view_alone():
    r = _pan_renderer()
    before = (r.ax.get_xlim(), r.ax.get_ylim())
    bbox = r.ax.bbox
    r._on_canvas_press(_MouseEvent(r.ax, bbox.x0 + 50, bbox.y0 + 50))
    r._on_canvas_release(_MouseEvent(r.ax, bbox.x0 + 50, bbox.y0 + 50))
    assert (r.ax.get_xlim(), r.ax.get_ylim()) == before
    assert r._pan_drag is None


def test_panning_only_takes_the_drag_while_the_pan_tool_is_active():
    r = _pan_renderer()
    press = _MouseEvent(r.ax, *_axes_centre(r))
    for mode in ("", "zoom rect"):
        r.fig.canvas.toolbar = _FakeToolbar(mode)
        r._on_canvas_press(press)
        assert r._pan_drag is None, f"pan started with toolbar mode {mode!r}"


@pytest.mark.parametrize("graticule", [None, 10])
def test_the_blitted_drag_shifts_the_map_the_way_the_cursor_went(graticule):
    # Guards the sign of the blit offset: event y counts up, the cached
    # region's rows count down, so a mixed-up sign silently drags the map the
    # wrong way vertically. Graticule labels move the axes box off the
    # figure's vertical centre, which a mixed-up origin gets wrong too.
    r = _pan_renderer()
    r.set_graticule(graticule)
    r.fig.canvas.draw()
    before = _red_centre(r.fig.canvas)
    cx, cy = _axes_centre(r)
    dx, dy = 37, 21
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + dx, cy + dy))
    after = _red_centre(r.fig.canvas)
    assert after[0] - before[0] == pytest.approx(dx, abs=1.0)   # right with it
    assert after[1] - before[1] == pytest.approx(-dy, abs=1.0)  # and upwards


def test_a_pan_drag_renders_only_when_it_is_released():
    # A render is ~0.5 s with a basemap and a few layers, so one inside a
    # motion event is a visible hitch. Only the release (or a pause) renders.
    r = _pan_renderer()
    draws = _count_draws(r)
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    for step in range(1, 21):
        r._on_canvas_motion(_MouseEvent(r.ax, cx + 3 * step, cy + 2 * step))
    assert len(draws) == 0
    r._on_canvas_release(_MouseEvent(r.ax, cx + 60, cy + 40))
    assert len(draws) == 1


def test_a_pause_in_the_drag_renders_once_and_rebases_it():
    r = _pan_renderer()
    x0, x1 = r.ax.get_xlim()
    bbox = r.ax.bbox
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 40, cy))
    timer = r._pan_drag["timer"]
    assert timer.interval == 150 and timer.single_shot
    draws = _count_draws(r)
    _fire_pause(r)
    assert len(draws) == 1
    assert r.ax.get_xlim()[0] - x0 == pytest.approx(
        -(x1 - x0) / bbox.width * 40)
    # The next shift is measured from where the pause left the view.
    assert (r._pan_drag["x"], r._pan_drag["y"]) == (cx + 40, cy)
    assert r._pan_drag["pending"] is None
    # Nothing moved since the pause, so the release has nothing to render.
    r._on_canvas_release(_MouseEvent(r.ax, cx + 40, cy))
    assert len(draws) == 1


def test_pinned_overlays_stay_put_through_a_pause_render():
    # A pause render replaces the scale bar's artists (its length follows the
    # view). They must still stay out of the map snapshot, or the next shift
    # drags a copy of the bar along with the map.
    r = _pan_renderer()
    r.set_scale_bar(ScaleBarOptions(show=True))
    r.fig.canvas.draw()
    before = [a.get_window_extent().bounds for a in r._artists["scale_bar"]]
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 30, cy))
    _fire_pause(r)
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 60, cy))
    bars = r._artists["scale_bar"]
    assert [a.get_window_extent().bounds for a in bars] == before
    shifted = _axes_rgb(r.fig.canvas, r.ax).copy()
    r._on_canvas_release(_MouseEvent(r.ax, cx + 60, cy))
    final = _axes_rgb(r.fig.canvas, r.ax)

    def dark(rgb):
        return rgb.max(axis=-1) < 90

    assert dark(final).any(), "no scale bar drawn"
    assert np.array_equal(dark(shifted), dark(final))


def test_the_map_snapshot_holds_no_legend_or_underline():
    r = _pan_renderer()
    r.set_points([("a", PointStyle(color="#000000"), [100.0], [-40.0])],
                 None, None,
                 LegendOptions(location="upper left", label_underline=True))
    assert r._legend_underline_texts
    r.fig.canvas.draw()
    snapshot = np.asarray(r._map_background())[..., :3]
    frame = np.asarray(r.fig.canvas.buffer_rgba())[..., :3]
    height = frame.shape[0]
    ax_x0, _y0, _x1, ax_y1 = (int(v) for v in r.ax.bbox.extents)
    leg = r.ax.get_legend().get_window_extent()
    rows = slice(height - int(leg.y1) + 1, height - int(leg.y0) - 1)
    cols = slice(int(leg.x0) + 1, int(leg.x1) - 1)
    assert (frame[rows, cols].max(axis=-1) < 90).any(), "no legend text"
    # The snapshot is the map alone: plain white where the legend sits.
    top = height - ax_y1
    assert (snapshot[rows.start - top:rows.stop - top,
                     cols.start - ax_x0:cols.stop - ax_x0] == 255).all()


def test_the_legend_and_its_underline_stay_on_screen_while_dragging():
    # The underline is drawn from the draw_event, not by the legend, so a
    # composite that only redraws the legend loses it until the release.
    r = _pan_renderer()
    r.set_points([("a", PointStyle(color="#000000"), [100.0], [-40.0])],
                 None, None,
                 LegendOptions(location="upper left", label_underline=True))
    r.fig.canvas.draw()
    leg = r.ax.get_legend().get_window_extent()
    height = np.asarray(r.fig.canvas.buffer_rgba()).shape[0]
    rows = slice(height - int(leg.y1) - 2, height - int(leg.y0) + 2)
    cols = slice(int(leg.x0) - 2, int(leg.x1) + 2)

    def legend_area():
        return np.asarray(r.fig.canvas.buffer_rgba())[rows, cols].copy()

    before = legend_area()
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 30, cy - 20))
    assert np.array_equal(legend_area(), before)


def test_a_finished_drag_matches_a_fresh_render_of_the_view():
    r = _pan_renderer()
    r.set_scale_bar(ScaleBarOptions(show=True))
    r.set_points([("a", PointStyle(color="#000000"), [100.0], [-40.0])],
                 None, None,
                 LegendOptions(location="upper left", label_underline=True))
    r.fig.canvas.draw()
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 25, cy - 10))
    _fire_pause(r)
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 50, cy - 30))
    r._on_canvas_release(_MouseEvent(r.ax, cx + 50, cy - 30))
    dragged = bytes(r.fig.canvas.buffer_rgba())
    r.fig.canvas.draw()
    assert bytes(r.fig.canvas.buffer_rgba()) == dragged


def test_the_strip_a_drag_uncovers_is_the_axes_facecolour():
    from matplotlib.patches import Rectangle

    r = _pan_renderer()
    r.ax.set_facecolor("#204060")
    # Map content everywhere, so stale pixels left in the strip would show.
    r.ax.add_patch(Rectangle((-1e9, -1e9), 2e9, 2e9, color="#00ff00",
                             zorder=1))
    r.fig.canvas.draw()
    cx, cy = _axes_centre(r)
    dx = 40
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + dx, cy))
    interior = _axes_rgb(r.fig.canvas, r.ax)
    strip = interior[:, :dx - 6]
    assert (strip == (0x20, 0x40, 0x60)).all()
    assert (interior[:, dx + 2:] == (0, 255, 0)).all(axis=-1).mean() > 0.95


def test_a_render_at_another_dpi_is_never_the_pan_background(tmp_path):
    r = _pan_renderer()
    background = r._map_background()
    assert background is not None
    # A vector export draws nothing into the snapshot.
    r.save_image(str(tmp_path / "map.pdf"), "pdf")
    assert r._map_background() is background
    # A raster export at another dpi renders a snapshot of its own size; the
    # screen must not pick it up.
    r.save_image(str(tmp_path / "map.png"), "png", dpi=200)
    assert r._map_background() is None
    # So the press renders once to get a screen snapshot, then drags as usual.
    draws = _count_draws(r)
    r._on_canvas_press(_MouseEvent(r.ax, *_axes_centre(r)))
    assert len(draws) == 1
    assert r._map_background() is not None and r._pan_drag is not None


def _buffer_xy(r, x, y):
    """Display pixel *x, y* (y counting up) as a canvas buffer position
    (column, row), rows counting down."""
    height = np.asarray(r.fig.canvas.buffer_rgba()).shape[0]
    return x, height - y


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


def test_exporting_leaves_the_screen_snapshot_alone():
    # A high-dpi export would otherwise leave its full-size copy of the
    # pixels referenced by the snapshot until the next screen render.
    from io import BytesIO

    r = _pan_renderer()
    before = r._snapshot.region
    assert before is not None
    r.fig.savefig(BytesIO(), format="png", dpi=200)
    assert r._snapshot.region is before


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


def test_a_fractional_drag_renders_the_whole_pixels_it_previewed():
    # The preview can only shift the snapshot by whole pixels, so the render
    # must move the view by the same whole pixels, and the drag re-base on
    # them, or the map lands up to half a pixel off the preview at each
    # pause (HiDPI cursors report fractional positions).
    r = _pan_renderer()
    x0, x1 = r.ax.get_xlim()
    y0, y1 = r.ax.get_ylim()
    bbox = r.ax.bbox
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 40.4, cy + 20.6))
    _fire_pause(r)
    assert r.ax.get_xlim()[0] - x0 == pytest.approx(
        -(x1 - x0) / bbox.width * 40)
    assert r.ax.get_ylim()[0] - y0 == pytest.approx(
        -(y1 - y0) / bbox.height * 21)
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 80.8, cy + 41.2))
    r._on_canvas_release(_MouseEvent(r.ax, cx + 80.8, cy + 41.2))
    # The map ends under the cursor to the nearest pixel overall, not off
    # by the fraction dropped at the pause.
    assert r.ax.get_xlim()[0] - x0 == pytest.approx(
        -(x1 - x0) / bbox.width * 81)
    assert r.ax.get_ylim()[0] - y0 == pytest.approx(
        -(y1 - y0) / bbox.height * 41)


@pytest.mark.parametrize("graticule", [None, 10])
def test_a_shift_after_the_first_lands_where_the_cursor_went(graticule):
    # The first motion of a drag used to render, which hid a mis-placed
    # shift: graticule labels move the axes box off the figure's vertical
    # centre, and the shift then put the map 22 px off vertically. Only a
    # motion that shifts without rendering shows it, so this takes two.
    r = _pan_renderer()
    r.set_graticule(graticule)
    r.fig.canvas.draw()
    before = _red_centre(r.fig.canvas)
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 20, cy + 10))
    r._on_canvas_motion(_MouseEvent(r.ax, cx + 37, cy + 21))
    after = _red_centre(r.fig.canvas)
    assert after[0] - before[0] == pytest.approx(37, abs=1.0)
    assert after[1] - before[1] == pytest.approx(-21, abs=1.0)


def test_the_legend_underline_stays_on_screen_through_a_drag():
    # As above, the first motion used to render the whole frame, underline
    # and all; the underline has to survive the shifts that follow it too.
    r = _pan_renderer()
    r.set_points([("a", PointStyle(color="#000000"), [100.0], [-40.0])],
                 None, None,
                 LegendOptions(location="upper left", label_underline=True))
    r.fig.canvas.draw()
    leg = r.ax.get_legend().get_window_extent()
    height = np.asarray(r.fig.canvas.buffer_rgba()).shape[0]
    rows = slice(height - int(leg.y1) - 2, height - int(leg.y0) + 2)
    cols = slice(int(leg.x0) - 2, int(leg.x1) + 2)

    def legend_area():
        return np.asarray(r.fig.canvas.buffer_rgba())[rows, cols].copy()

    before = legend_area()
    cx, cy = _axes_centre(r)
    r._on_canvas_press(_MouseEvent(r.ax, cx, cy))
    for step in (1, 2, 3):
        r._on_canvas_motion(_MouseEvent(r.ax, cx + 15 * step,
                                        cy - 10 * step))
        assert np.array_equal(legend_area(), before), f"motion {step}"


# ------------------------------------------- features outside a Lambert region


def test_natural_earth_features_outside_a_lambert_region_are_dropped():
    # Lagos (3E, 6N) is south of Lambert: Europe's 30N edge: its label and
    # marker are dropped, not stacked along the edge with every other
    # out-of-region feature. Paris stays.
    import pandas as pd

    r = _renderer(9.0, 6.5)
    r.set_projection("Lambert: Europe")
    frame = pd.DataFrame({"x": [3.4, 2.35], "y": [6.45, 48.86],
                          "text": ["Lagos", "Paris"], "min_label": [1, 1],
                          "min_zoom": [1, 1]})
    r.store.label_points = lambda _key, region=None: frame
    r.store.point_features = lambda _key: frame
    for xs, ys in (r._label_xy("cities"), r._point_xy("cities")[:2]):
        assert np.isnan(xs[0]) and np.isnan(ys[0])
        assert np.isfinite(xs[1]) and np.isfinite(ys[1])


def test_the_lambert_graticule_draws_no_chords_across_the_region():
    # Parallels must run west to east around the centre: wrapping longitudes
    # into lon_0 +/- 180 must not send part of one back to the far edge.
    r = _renderer(9.0, 6.5)
    for name in ("Lambert: Europe", "Lambert: N. America"):
        r.set_projection(name)
        r.set_graticule(10)
        # Meridians every 10 degrees from -180 to 180 come first.
        parallels = r._artists["graticule"][0].get_segments()[37:]
        assert parallels
        for seg in parallels:
            assert (np.diff(seg[:, 0]) >= -1e-6).all(), name


def test_lambert_labels_sit_on_the_part_of_a_feature_on_the_map():
    # Norway's whole-country anchor is on Svalbard (79.8N), Russia's and
    # Kazakhstan's east of 65E: all off Lambert: Europe, yet most of each
    # country is on it. Their labels anchor on the part that is drawn.
    store = LayerStore()
    if store.check_data():
        pytest.skip("map data not downloaded")
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, store)
    world = store.label_points("countries")
    norway = world[world["text"] == "Norway"].iloc[0]
    assert norway["y"] > 72.0   # the unclipped anchor, unchanged
    r.set_projection("Lambert: Europe")
    points = r._label_points("countries")
    xs, ys = r._label_xy("countries")
    x0, x1, y0, y1 = r.proj.bounds
    names = list(points["text"])
    for name in ("Norway", "Russia", "Kazakhstan"):
        i = names.index(name)
        assert np.isfinite([xs[i], ys[i]]).all(), name
        assert x0 <= xs[i] <= x1 and y0 <= ys[i] <= y1, name
    assert points["y"].to_numpy()[names.index("Norway")] < 72.0
    assert "Nigeria" not in names
    # World projections keep the whole-feature anchors.
    r.set_projection("Robinson")
    assert r._label_points("countries") is world


def test_label_and_marker_caches_follow_the_region_not_just_the_crs():
    # Lambert: Africa and Lambert Azimuthal (custom) centred on (20, 5)
    # share a CRS but not a region: switching between them must not reuse
    # the other's anchors or out-of-region mask.
    store = LayerStore()
    if store.check_data():
        pytest.skip("map data not downloaded")
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, store)
    r.set_projection("Lambert: Africa")
    africa = r.proj
    r._label_xy("countries")
    r._point_xy("cities")
    r.set_projection("Lambert Azimuthal (custom)", 20.0, 5.0)
    assert r.proj.crs == africa.crs and r.proj != africa
    points = r._label_points("countries")
    xs, ys = r._label_xy("countries")
    assert len(xs) == len(points)
    ex, ey = r.proj.forward(points["x"].to_numpy(), points["y"].to_numpy(),
                            clamp=False)
    np.testing.assert_array_equal(xs, ex)
    np.testing.assert_array_equal(ys, ey)
    features = store.point_features("cities")
    px, _py, _zoom = r._point_xy("cities")
    fx, _fy = r.proj.forward(features["x"].to_numpy(),
                             features["y"].to_numpy(), clamp=False)
    np.testing.assert_array_equal(px, fx)
