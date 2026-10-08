"""Shared fixtures and fake events for the renderer test files."""

from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pymappr.geo.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402


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


def _disk_frame(renderer):
    """Where the globe's disk sits in the view: ``(centre x fraction, centre
    y fraction, diameter / view height)``."""
    x0, x1 = renderer.ax.get_xlim()
    y0, y1 = renderer.ax.get_ylim()
    cx, cy, radius = renderer._globe_disk()
    return ((cx - x0) / (x1 - x0), (cy - y0) / (y1 - y0),
            2 * radius / abs(y1 - y0))


def _buffer_xy(r, x, y):
    """Display pixel *x, y* (y counting up) as a canvas buffer position
    (column, row), rows counting down."""
    height = np.asarray(r.fig.canvas.buffer_rgba()).shape[0]
    return x, height - y
