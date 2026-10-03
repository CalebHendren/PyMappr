"""Open symbols for marked rows: type localities drawn as the outline of
their species' symbol, with one legend row saying what they mark."""

from __future__ import annotations

import types

import numpy as np
import pytest

from pymappr.export import codegen
from pymappr.files.projects import (DatasetEntry, entry_from_dict,
                                    entry_to_dict)
from pymappr.styling.layout import (OPEN_GROUP_PREFIX, holotype_marking,
                                    layout_points)
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import DEFAULT_PALETTE, OPEN_SUFFIX

from test_codegen import (assert_r_map_saved, exec_python, make_state,
                          r_run_state, run_exported_r, run_r, run_r_harness)

ROWS = [
    ["Nebulobunus alpha", "Holotype", -90.0, 15.0],
    ["Nebulobunus alpha", "Paratype", -90.5, 15.2],
    ["Nebulobunus alpha", "Other material", -91.0, 15.4],
    ["Nebulobunus beta", "Holotype", -85.0, 12.0],
    ["Nebulobunus beta", "", -85.5, 12.3],
]


def harvestmen(**kwargs) -> DatasetEntry:
    entry = entry_from_dict({
        "name": "harvestmen", "columns": ["name1", "name2", "lon", "lat"],
        "name_labels": ["Species", "Type status"], "rows": ROWS,
        "group_by": "Species"})
    for name, value in kwargs.items():
        setattr(entry, name, value)
    return entry


def marked(**kwargs) -> DatasetEntry:
    return harvestmen(open_by="Type status", open_values=["Holotype"],
                      **kwargs)


def test_marked_rows_draw_in_the_open_form_of_their_groups_symbol():
    layout = layout_points([marked()], LegendOptions(), DEFAULT_PALETTE)
    dataset = layout.datasets[0]
    assert [len(rows) for _l, _s, rows in dataset.groups] == [2, 1]
    opened = dataset.open_groups
    assert [label for label, _s, _r in opened] == [
        OPEN_GROUP_PREFIX + "Nebulobunus alpha",
        OPEN_GROUP_PREFIX + "Nebulobunus beta"]
    for (_l, style, _r), (_ol, open_style, rows) in zip(dataset.groups,
                                                         opened):
        assert open_style.marker == style.marker + OPEN_SUFFIX
        assert open_style.color == style.color
        assert open_style.fill == "#ffffff"  # shows over filled symbols
        assert list(rows["name2"]) == ["Holotype"]
    # Drawn last, on top; the legend keeps one row per species plus a note.
    assert layout.groups[-2:] == opened
    assert layout.row_order == ["Nebulobunus alpha", "Nebulobunus beta"]
    label, note_style = layout.open_note
    assert label == "Holotype" and note_style.is_open


def test_without_marked_rows_nothing_changes():
    plain = layout_points([harvestmen()], LegendOptions(), DEFAULT_PALETTE)
    unmatched = layout_points([harvestmen(open_by="Type status",
                                          open_values=["Neotype"])],
                              LegendOptions(), DEFAULT_PALETTE)
    for layout in (plain, unmatched):
        assert layout.open_note is None
        assert not layout.datasets[0].open_groups
        assert [len(r) for _l, _s, r in layout.datasets[0].groups] == [3, 2]


def test_open_symbols_survive_saving():
    restored = entry_from_dict(entry_to_dict(marked()))
    assert restored.open_by == "Type status"
    assert restored.open_values == ["Holotype"]
    old = entry_to_dict(harvestmen())
    del old["open_by"], old["open_values"]
    assert entry_from_dict(old).open_by == ""


def test_holotypes_are_found_by_their_type_status_column():
    assert holotype_marking(harvestmen()) == ("Type status", "Holotype")
    entry = harvestmen()
    entry.dataset.frame.attrs["name_labels"] = ["Species", "Remarks"]
    assert holotype_marking(entry) is None


@pytest.mark.parametrize("symbol_by", ["", "Type status"])
def test_the_legend_closes_with_the_open_symbol_note(symbol_by):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from pymappr.geo.layers import LayerStore
    from pymappr.renderer import MapRenderer

    entry = marked(symbol_by=symbol_by)
    layout = layout_points([entry], LegendOptions(), DEFAULT_PALETTE)
    fig = Figure(figsize=(6, 4))
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, LayerStore())
    r.set_points([(label, style, rows["lon"].to_numpy(),
                   rows["lat"].to_numpy())
                  for label, style, rows in layout.groups],
                 layout.sections, layout.row_order, LegendOptions(),
                 [layout.open_note])
    texts = [t.get_text().strip()
             for t in r.ax.get_legend().get_texts()]
    assert texts[-1] == "Holotype"
    assert not any(OPEN_GROUP_PREFIX in t for t in texts)


def test_exported_python_draws_open_symbols_and_the_note():
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    state = make_state(map={"projection": "Equirectangular"})
    ns = exec_python(codegen.generate_code(state, [marked()], "Python"))
    spec = ns["DATASETS"][0]
    assert spec["open_col"] == "Type status"
    assert spec["open_values"] == ["Holotype"]
    calls = []
    ax = types.SimpleNamespace(scatter=lambda xs, ys, **kw: calls.append(
        (sorted(ys), kw["c"])))
    ns["plot_dataset"](ax, spec)
    assert all(face != "none" for _ys, face in calls)
    assert sorted(len(ys) for ys, _f in calls) == [1, 2]
    calls.clear()
    ns["plot_dataset"](ax, spec, opened=True)
    assert sorted(ys for ys, _f in calls) == [[12.0], [15.0]]
    # White-filled, so they show over filled symbols at the same place.
    assert {face for _ys, face in calls} == {"#ffffff"}
    fig = matplotlib.figure.Figure()
    axes = fig.add_subplot(111)
    ns["add_legend"](axes)
    texts = [t.get_text() for t in axes.get_legend().get_texts()]
    assert texts == ["Nebulobunus alpha", "Nebulobunus beta", "Holotype"]


def test_exported_r_keys_open_rows_and_ends_the_legend_with_the_note(
        tmp_path):
    state = make_state(map={"projection": "Equirectangular"})
    r = codegen.generate_code(state, [marked()], "R")
    assert 'OPEN_KEY_SUFFIX <- " [open]"' in r
    out = run_r_harness(tmp_path, r, """
pts <- load_all_points()
stopifnot(sum(endsWith(as.character(pts$key), OPEN_KEY_SUFFIX)) == 2)
stopifnot(identical(tail(LEGEND_ROWS, 1), "[open symbols]"))
stopifnot(STYLE_SHAPES[["Nebulobunus alpha [open]"]] == 21)
stopifnot(STYLE_FILLS[["Nebulobunus alpha [open]"]] == "#ffffff")
stopifnot(STYLE_LABELS[["[open symbols]"]] == "Holotype")
""")
    assert "HARNESS OK" in out


@run_r
def test_exported_r_script_with_open_symbols(tmp_path):
    state = r_run_state("Mercator")
    result = run_exported_r(tmp_path, state, [marked()])
    assert_r_map_saved(tmp_path, result)


def test_open_groups_keep_their_rows_out_of_the_closed_ones():
    layout = layout_points([marked()], LegendOptions(), DEFAULT_PALETTE)
    drawn = sum(len(rows) for _l, _s, rows in layout.groups)
    assert drawn == len(ROWS)
    lats = np.concatenate([rows["lat"].to_numpy()
                           for _l, _s, rows in layout.groups])
    assert sorted(lats) == sorted(row[3] for row in ROWS)
