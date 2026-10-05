"""Tests for app handlers, each run on a stand-in for the app that holds
only what the handler reads, so no main window is built.

The preset and publication-style tests build a real control panel, so
they skip wherever Tk cannot open a display (a headless Linux runner,
typically).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
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


# ----------------------------------------------------------------- presets

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


def _tab_widgets(panel, title):
    """Every widget on the panel's *title* tab, in the order it was made."""
    notebook = panel.notebook
    tab = next(panel.nametowidget(name) for name in notebook.tabs()
               if notebook.tab(name, "text") == title)
    found, pending = [], [tab]
    while pending:
        widget = pending.pop(0)
        found.append(widget)
        pending[:0] = widget.winfo_children()
    return found


def _sections(panel, title):
    return [w.cget("text") for w in _tab_widgets(panel, title)
            if isinstance(w, ttk.LabelFrame) and w.cget("text")]


def test_presets_come_first_on_the_data_tab(panel):
    assert _sections(panel, "Data")[0] == "Presets"
    texts = [w.cget("text") for w in _tab_widgets(panel, "Data")
             if isinstance(w, ttk.Button)]
    assert texts[:3] == ["Apply", "Save current as\N{HORIZONTAL ELLIPSIS}",
                         "Delete"]


def test_the_map_tab_no_longer_carries_a_publication_button(panel):
    texts = [w.cget("text") for w in _tab_widgets(panel, "Map")
             if isinstance(w, ttk.Button)]
    assert not any("publication" in str(text).lower() for text in texts)


def test_the_built_in_preset_is_listed_first_and_selected(panel):
    panel.set_preset_names(["Publication", "Mine"], "Gone")
    assert panel.preset_box.cget("values") == ("Publication", "Mine")
    assert panel.preset_var.get() == "Publication"
    panel.set_preset_names(["Publication", "Mine"], "Mine")
    assert panel.preset_var.get() == "Mine"


# ------------------------------------------------------- publication style

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


def test_publication_style_drops_a_default_title_but_keeps_a_typed_one(panel):
    entry = _species()
    panel.legend_vars["title"].set("")
    PyMapprApp.on_publication_style(_publication_app(panel, [entry], entry))
    assert panel.legend_options().show_title is False
    assert panel.export_width_var.get().startswith("17 cm")

    panel.legend_vars["show_title"].set(True)
    panel.legend_vars["title"].set("Nebulobunus")
    PyMapprApp.on_publication_style(_publication_app(panel, [entry], entry))
    assert panel.legend_options().show_title is True
    assert panel.legend_options().title == "Nebulobunus"
    panel.legend_vars["title"].set("")


def test_publication_style_marks_holotypes_with_open_symbols(panel):
    from test_open_symbols import harvestmen
    entry = harvestmen()
    PyMapprApp.on_publication_style(_publication_app(panel, [entry], entry))
    assert (entry.open_by, entry.open_values) == ("Type status", ["Holotype"])
    assert panel.open_by_var.get() == "Type status"
    assert panel.open_value_var.get() == "Holotype"
    # A choice the user already made is left alone.
    entry.open_by, entry.open_values = "Type status", ["Paratype"]
    PyMapprApp.on_publication_style(_publication_app(panel, [entry], entry))
    assert entry.open_values == ["Paratype"]
