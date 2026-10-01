"""Tests for app handlers, each run on a stand-in for the app that holds
only what the handler reads, so no main window is built.

The publication-style test builds a real control panel, so it skips
wherever Tk cannot open a display (a headless Linux runner, typically).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import matplotlib
import pytest

from pymappr.app import PyMapprApp
from pymappr.files.data_loader import combine_name_columns, load_csv
from pymappr.files.projects import DatasetEntry
from pymappr.ui.control_panel import ControlPanel

# Importing the app selects TkAgg; the other modules draw on Agg.
matplotlib.use("Agg")

SAMPLE = Path(__file__).resolve().parent.parent / \
    "sample_data/south_america_beetles.csv"


class _ZoomRecorder:
    def __init__(self):
        self.calls = []

    def zoom_interactive(self, factor, center_px=None):
        self.calls.append((factor, center_px))


def _scroll_app():
    return SimpleNamespace(renderer=_ZoomRecorder())


def _scroll(button="up", inaxes=True, x=123.5, y=45.25):
    # xdata/ydata differ from x/y, so passing the wrong pair shows.
    return SimpleNamespace(button=button, inaxes=object() if inaxes else None,
                           x=x, y=y, xdata=-70.0, ydata=10.0)


@pytest.mark.parametrize("button, factor", [("up", 1.25),
                                            ("down", 1 / 1.25)])
def test_a_scroll_zooms_about_the_cursor_in_display_pixels(button, factor):
    app = _scroll_app()
    PyMapprApp._on_scroll_zoom(app, _scroll(button))
    assert app.renderer.calls == [(factor, (123.5, 45.25))]


def test_a_scroll_off_the_map_does_nothing():
    app = _scroll_app()
    PyMapprApp._on_scroll_zoom(app, _scroll(inaxes=False))
    assert app.renderer.calls == []


def test_a_scroll_with_no_cursor_position_does_nothing():
    app = _scroll_app()
    PyMapprApp._on_scroll_zoom(app, _scroll(x=None, y=None))
    assert app.renderer.calls == []


# ------------------------------------------------------- publication style

class _FakeApp:
    """Swallows every handler the panel wires its widgets to."""

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


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
def panel(tk_root):
    widget = ControlPanel(tk_root, _FakeApp())
    widget.pack()
    tk_root.update_idletasks()
    yield widget
    widget.destroy()


def _species(**kwargs) -> DatasetEntry:
    """The sample beetles grouped by a "Genus Species" column."""
    entry = DatasetEntry(dataset=load_csv(str(SAMPLE)), name="beetles")
    entry.dataset, entry.group_by = combine_name_columns(
        entry.dataset, ["Genus", "Species"])
    for name, value in kwargs.items():
        setattr(entry, name, value)
    return entry


def _publication_app(panel, entries, active):
    return SimpleNamespace(
        panel=panel, entries=entries,
        _active_entry=lambda: active,
        renderer=SimpleNamespace(set_point_alpha=lambda alpha: None,
                                 set_point_edge=lambda *edge: None),
        _push_points=lambda: None, set_status=lambda text: None)


@pytest.mark.parametrize("chosen, shown", [("", "Genus"),
                                           ("Species", "Species")])
def test_publication_style_shows_the_colour_by_it_draws(panel, chosen,
                                                        shown):
    # The style shades the dataset by genus unless a Color by was chosen;
    # the panel must show what the map is coloured by, or the next change
    # made in the panel would put its stale "None" back.
    entry = _species(color_by=chosen)
    panel.color_by_var.set(chosen or "None")
    PyMapprApp.on_publication_style(_publication_app(panel, [entry], entry))
    assert entry.color_by == shown
    assert panel.color_by_var.get() == shown


def test_publication_style_leaves_the_colour_by_alone_with_no_dataset(panel):
    panel.color_by_var.set("None")
    PyMapprApp.on_publication_style(_publication_app(panel, [], None))
    assert panel.color_by_var.get() == "None"
