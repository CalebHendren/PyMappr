"""Tests for the map canvas that holds still while the window is resized.

These build a real Tk canvas, so they skip wherever Tk cannot open a
display (a headless Linux runner, typically).
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from types import SimpleNamespace

import pytest
from matplotlib.figure import Figure

from pymappr.ui.map_canvas import DebouncedFigureCanvasTkAgg


@pytest.fixture(scope="module")
def tk_root():
    """One Tk root for the whole module (see test_control_panel)."""
    try:
        root = tk.Tk()
    except tk.TclError as exc:                      # pragma: no cover
        pytest.skip(f"no Tk display: {exc}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def canvas(tk_root):
    canvas = DebouncedFigureCanvasTkAgg(Figure(figsize=(3, 2), dpi=100),
                                        master=tk_root)
    canvas.RESIZE_DELAY_MS = 10
    applied = []
    real = canvas._resize_figure_for_canvas_size

    def recording(width, height):
        applied.append((width, height))
        real(width, height)

    canvas._resize_figure_for_canvas_size = recording
    canvas.applied = applied
    yield canvas
    canvas.get_tk_widget().destroy()


def _resize(canvas, width, height):
    canvas.resize(SimpleNamespace(width=width, height=height))


def _flush(root, canvas):
    """Run Tk's event loop until the canvas has no resize pending."""
    deadline = time.monotonic() + 2
    while canvas._resize_after_id is not None:
        assert time.monotonic() < deadline, "resize never flushed"
        root.update()
        time.sleep(0.005)


def test_first_resize_applies_immediately(tk_root, canvas):
    _resize(canvas, 400, 300)
    assert canvas.applied == [(400, 300)]
    assert canvas._resize_after_id is None


def test_rapid_resizes_collapse_to_one_figure_resize(tk_root, canvas):
    _resize(canvas, 400, 300)                        # the startup Configure
    canvas.applied.clear()

    for step in range(10):
        _resize(canvas, 410 + step * 10, 300 + step * 5)
    assert canvas.applied == []                      # nothing yet: held still

    _flush(tk_root, canvas)
    assert canvas.applied == [(500, 345)]            # only the last size
    assert canvas.figure.get_size_inches().tolist() == [5.0, 3.45]


def test_later_burst_is_debounced_again(tk_root, canvas):
    _resize(canvas, 400, 300)
    _resize(canvas, 420, 300)
    _flush(tk_root, canvas)
    canvas.applied.clear()

    _resize(canvas, 600, 400)
    _resize(canvas, 620, 400)
    _flush(tk_root, canvas)
    assert canvas.applied == [(620, 400)]


def _wait(root, ms):
    """Run Tk's event loop for *ms* milliseconds."""
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)


def test_the_held_picture_is_centred_on_whole_pixels(tk_root, canvas):
    # As matplotlib places it, so the held picture does not jump half a
    # pixel when the real resize lands.
    _resize(canvas, 400, 300)
    _resize(canvas, 401, 301)
    assert canvas._tkcanvas.coords(canvas._tkcanvas_image_region) == [
        200.0, 150.0]


@pytest.mark.skipif(sys.platform == "darwin",
                    reason="Tk reports no pixel ratio on macOS")
def test_a_pixel_ratio_resize_cancels_a_waiting_one(tk_root, canvas):
    # Mapping the window on a screen of another scale resizes the figure
    # straight away; a resize still waiting from before must not land on
    # top of it with a stale size.
    _resize(canvas, 400, 300)
    _resize(canvas, 420, 310)
    assert canvas._resize_after_id is not None
    canvas.applied.clear()
    canvas._device_pixel_ratio = 3.0          # as if the scale had changed
    canvas._update_device_pixel_ratio()
    assert canvas._resize_after_id is None
    _wait(tk_root, 4 * canvas.RESIZE_DELAY_MS)
    assert (420, 310) not in canvas.applied


def test_without_the_resize_internals_it_resizes_at_once(tk_root,
                                                         monkeypatch):
    # matplotlib before 3.11 has no _resize_figure_for_canvas_size (the
    # requirement is >= 3.8): the canvas then resizes the plain way, at once.
    from matplotlib.backends import _backend_tk

    monkeypatch.delattr(_backend_tk.FigureCanvasTk,
                        "_resize_figure_for_canvas_size")
    plain = []
    monkeypatch.setattr(_backend_tk.FigureCanvasTk, "resize",
                        lambda self, event: plain.append((event.width,
                                                          event.height)))
    canvas = DebouncedFigureCanvasTkAgg(Figure(figsize=(3, 2), dpi=100),
                                        master=tk_root)
    try:
        _resize(canvas, 400, 300)
        _resize(canvas, 420, 310)
        assert plain == [(400, 300), (420, 310)]
        assert canvas._resize_after_id is None
    finally:
        canvas.get_tk_widget().destroy()
