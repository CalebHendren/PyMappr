"""Tests for the control panel's legend settings.

These build a real Tk widget tree, so they skip wherever Tk cannot open a
display (a headless Linux runner, typically).
"""

from __future__ import annotations

import tkinter as tk

import pytest

from pymappr.legend import LegendOptions, row_key
from pymappr.styles import PointStyle
from pymappr.ui.legend_editor import LegendEditorDialog
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


# ----------------------------------------------------- legend row editor


def _rows():
    return [(row_key("color", "Eleusis"), "Eleusis",
             PointStyle(color="#d62728", marker="Circle"), 0),
            (row_key("pair", "Eleusis", "andina"), "andina",
             PointStyle(color="#d62728", marker="Triangle"), 1),
            (row_key("pair", "Eleusis", "chapadensis"), "chapadensis",
             PointStyle(color="#d62728", marker="Square"), 1),
            (row_key("color", "Xanthopygus"), "Xanthopygus",
             PointStyle(color="#1f77b4", marker="Circle"), 0)]


@pytest.fixture
def editor(tk_root):
    overrides: dict = {}
    changes: list = []
    dialog = LegendEditorDialog(tk_root, _rows(), overrides,
                                lambda: changes.append("change"))
    tk_root.update_idletasks()
    yield dialog, overrides, changes
    if dialog.winfo_exists():
        dialog.destroy()


def test_editor_opens_for_attribute_mode_rows(editor):
    # It used to refuse outright whenever Symbol by was set, which left
    # nested and crossed rows uncustomizable in any way.
    dialog, _overrides, _changes = editor
    assert len(dialog.rows) == 4


def test_setting_a_field_records_only_that_field(editor):
    dialog, overrides, changes = editor
    key = row_key("pair", "Eleusis", "andina")
    dialog._set(key, "label", "A. andina")
    assert overrides[key] == {"label": "A. andina"}
    assert changes  # the map is told to redraw


def test_clearing_a_field_drops_the_override_entirely(editor):
    # A row back at its defaults should leave nothing behind in the project.
    dialog, overrides, _changes = editor
    key = row_key("color", "Eleusis")
    dialog._set(key, "label", "Genus E")
    assert key in overrides
    dialog._set(key, "label", "")
    assert key not in overrides


def test_hiding_and_unhiding_a_row(editor):
    dialog, overrides, _changes = editor
    key = row_key("color", "Eleusis")
    dialog._set(key, "hidden", True)
    assert overrides[key]["hidden"] is True
    dialog._set(key, "hidden", False)
    assert key not in overrides


def test_a_half_typed_size_is_ignored(editor):
    dialog, overrides, _changes = editor
    key = row_key("color", "Eleusis")
    var = tk.StringVar(value="")
    dialog._set_size(key, var)
    assert key not in overrides
    var.set("55")
    dialog._set_size(key, var)
    assert overrides[key]["size"] == 55.0


def test_moving_a_row_writes_a_position_for_every_row(tk_root):
    # A partial ordering would let untouched rows fall to the end, which is
    # not what moving one row up should do.
    overrides: dict = {}
    dialog = LegendEditorDialog(tk_root, _rows(), overrides, lambda: None)
    dialog._move(2, -1)          # chapadensis above andina
    tk_root.update_idletasks()
    assert len(overrides) == 4
    order = {key: value["order"] for key, value in overrides.items()}
    assert order[row_key("pair", "Eleusis", "chapadensis")] < \
        order[row_key("pair", "Eleusis", "andina")]


def test_a_child_cannot_be_moved_out_of_its_parents_block(tk_root):
    # Swapping across the depth boundary would file a species under the
    # wrong genus.
    overrides: dict = {}
    dialog = LegendEditorDialog(tk_root, _rows(), overrides, lambda: None)
    dialog._move(1, -1)          # andina is the first child; up is its genus
    tk_root.update_idletasks()
    assert overrides == {}


def test_reset_clears_every_override(tk_root):
    overrides = {row_key("color", "Eleusis"): {"label": "x"}}
    dialog = LegendEditorDialog(tk_root, _rows(), overrides, lambda: None)
    dialog._reset_all()
    tk_root.update_idletasks()
    assert overrides == {}
