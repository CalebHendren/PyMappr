"""Renderer tests: the globe projection - spinning it, keeping it centred and
whole."""

from __future__ import annotations

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from renderer_helpers import (  # noqa: E402
    _disk_frame, _renderer, _live_box_aspect, _view_aspect, _FakeToolbar,
    _MouseEvent)


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
