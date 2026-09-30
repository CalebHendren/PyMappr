"""Tests for the map canvas that holds still while the window is resized.

These build a real Tk canvas, so they skip wherever Tk cannot open a
display (a headless Linux runner, typically).
"""

from __future__ import annotations

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
