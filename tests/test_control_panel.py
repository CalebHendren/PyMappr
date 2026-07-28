"""Tests for the control panel's legend settings.

These build a real Tk widget tree, so they skip wherever Tk cannot open a
display (a headless Linux runner, typically).
"""

from __future__ import annotations

import tkinter as tk

import pytest

from pymappr.legend import LegendOptions
from pymappr.ui.control_panel import ControlPanel


class _FakeApp:
    """Swallows every handler the panel wires its widgets to."""

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


@pytest.fixture(scope="module")
def tk_root():
    """One Tk root for the whole module.

    Creating and destroying a root per test makes Tcl fall over part way
    through the run ("Can't find a usable init.tcl"), which showed up as
    tests quietly skipping rather than failing.
    """
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


def test_legend_gets_its_own_tab(panel):
    titles = [panel.notebook.tab(i, "text")
              for i in range(panel.notebook.index("end"))]
    assert titles == ["Data", "Legend", "Map", "Layers", "Labels"]


def test_panel_defaults_match_the_dataclass_defaults(panel):
    # A widget seeded with the wrong default would silently change every
    # legend the first time the panel is read.
    assert panel.legend_options() == LegendOptions()


def test_every_option_round_trips_through_the_widgets(panel):
    custom = LegendOptions(
        show=False, title="Key", location="lower left", hierarchy="never",
        order="count_desc", counts=True, count_format="%",
        blank_label="(none)", section_titles=False, title_separator=" > ",
        dataset_prefix=False, empty_groups=True, indent=1, bold_groups=False,
        group_spacer=False, group_swatch="child",
        symbol_swatch_color="#112233", columns=3, label_spacing=1.2,
        column_spacing=3.0, handle_text_pad=1.1, handle_length=4.0,
        border_pad=0.9, marker_scale=2.0, frame=False, frame_color="#010203",
        frame_alpha=0.4, frame_edge_color="#040506", frame_width=2.0,
        rounded=False, shadow=True, fontsize=14.0, title_fontsize=18.0,
        font_family="serif", label_color="#070809", title_color="#0a0b0c",
        label_bold=True, label_italic=True, label_underline=True,
        title_bold=False, title_italic=True, title_underline=True,
        title_align="left")
    panel.set_legend_options(custom)
    assert panel.legend_options() == custom


def test_a_blank_swatch_gap_means_automatic(panel):
    panel.legend_handle_pad_var.set("")
    assert panel.legend_options().handle_text_pad is None
    panel.legend_handle_pad_var.set("1.5")
    assert panel.legend_options().handle_text_pad == pytest.approx(1.5)


def test_half_typed_numbers_fall_back_instead_of_raising(panel):
    # Spinboxes report on every keystroke, so "" and "-" are ordinary
    # states the panel has to survive rather than error on.
    for partial in ("", "-", ".", "abc"):
        panel.legend_fontsize_var.set(partial)
        panel.legend_columns_var.set(partial)
        options = panel.legend_options()
        assert options.fontsize == LegendOptions().fontsize
        assert options.columns == LegendOptions().columns


def test_numbers_are_clamped_to_their_range(panel):
    panel.legend_fontsize_var.set("999")
    assert panel.legend_options().fontsize == 32.0
    panel.legend_columns_var.set("0")
    assert panel.legend_options().columns == 1


def test_colour_swatches_repaint_when_options_are_restored(panel):
    panel.set_legend_options(LegendOptions(frame_color="#abcdef"))
    button = panel._color_buttons[str(panel.legend_frame_color_var)]
    assert button.cget("bg") == "#abcdef"
