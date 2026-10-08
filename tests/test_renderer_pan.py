"""Renderer tests: the basemap crop and dragging the map with the pan tool."""

from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pymappr.geo.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styling.decorations import ScaleBarOptions  # noqa: E402
from pymappr.styling.legend import LegendOptions  # noqa: E402
from pymappr.styling.styles import PointStyle  # noqa: E402
from renderer_helpers import (  # noqa: E402
    _FakeToolbar, _MouseEvent, _pan_renderer, _red_centre, _axes_centre,
    _count_draws, _fire_pause, _axes_rgb)


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


def test_exporting_leaves_the_screen_snapshot_alone():
    # A high-dpi export would otherwise leave its full-size copy of the
    # pixels referenced by the snapshot until the next screen render.
    from io import BytesIO

    r = _pan_renderer()
    before = r._snapshot.region
    assert before is not None
    r.fig.savefig(BytesIO(), format="png", dpi=200)
    assert r._snapshot.region is before


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
