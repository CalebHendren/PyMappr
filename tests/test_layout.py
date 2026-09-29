"""Tests for pymappr.layout: what every dataset draws, shared by the app
and the code export."""

from __future__ import annotations

import json

from pymappr import projects
from pymappr.data_loader import build_manual_dataset, load_csv
from pymappr.layout import (column_key, editor_rows, layout_points,
                            with_default_title)
from pymappr.legend import LegendOptions
from pymappr.projects import DatasetEntry
from pymappr.styles import DEFAULT_PALETTE, OKABE_ITO, row_key

SAMPLE = "sample_data/south_america_beetles.csv"


def beetles(**kwargs) -> DatasetEntry:
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / SAMPLE
    return DatasetEntry(dataset=load_csv(str(path)), name="beetles",
                        **{"group_by": "Genus", **kwargs})


def manual(name="spiders", **kwargs) -> DatasetEntry:
    dataset = build_manual_dataset(name, "38,-100\n-25,140\n")
    return DatasetEntry(dataset=dataset, name=name,
                        **{"group_by": "Legend", **kwargs})


def colors(layout):
    return [style.color for _label, style, _rows in layout.groups]


def test_group_by_draws_one_group_per_value_from_the_palette():
    layout = layout_points([beetles()], LegendOptions(), DEFAULT_PALETTE)
    assert [label for label, *_ in layout.groups] == [
        "Eleusis", "Xanthopygus", "Plociopterus"]
    assert colors(layout) == DEFAULT_PALETTE[:3]
    assert layout.sections is None
    assert layout.row_order == ["Eleusis", "Xanthopygus", "Plociopterus"]


def test_a_pinned_row_keeps_its_style_and_the_rest_follow_the_palette():
    entry = beetles(legend_overrides={row_key("group", "Eleusis"): {
        "color": "#123456", "marker": "Star", "size": 45.0}})
    layout = layout_points([entry], LegendOptions(), OKABE_ITO)
    first, second, _third = (style for _l, style, _r in layout.groups)
    assert (first.color, first.marker, first.size) == ("#123456", "Star",
                                                        45.0)
    assert second.color == OKABE_ITO[1]


def test_reopening_a_project_does_not_pin_the_palette(tmp_path):
    # Saving used to write every group's resolved style and reading pinned
    # them all, so after a reopen (or an app restart, via the autosaved
    # session) changing the palette recoloured nothing.
    entry = beetles()
    data = json.loads(json.dumps(projects.entry_to_dict(entry)))
    reopened = projects.entry_from_dict(data)
    layout = layout_points([reopened], LegendOptions(), OKABE_ITO)
    assert colors(layout) == OKABE_ITO[:3]


def test_a_manual_datasets_chosen_style_is_what_gets_drawn():
    # The Manual entry dialog's colour/shape/size used to be dropped on the
    # first redraw; it is now a pinned row like any other.
    entry = manual(legend_overrides={row_key("group", "spiders"): {
        "color": "#123456", "marker": "Star", "size": 45.0}})
    (_label, style, rows), = layout_points(
        [entry], LegendOptions(), DEFAULT_PALETTE).groups
    assert (style.color, style.marker, style.size) == ("#123456", "Star",
                                                        45.0)
    assert len(rows) == 2


def test_several_datasets_are_told_apart_and_take_their_own_colours():
    a, b = manual("Alpha", group_by=""), manual("Beta", group_by="")
    layout = layout_points([a, b], LegendOptions(), DEFAULT_PALETTE)
    # A lone "All points" group takes the dataset's name ...
    assert [label for label, *_ in layout.groups] == ["Alpha", "Beta"]
    # ... and the second dataset's colours start after the first's.
    assert colors(layout) == DEFAULT_PALETTE[:2]
    assert layout.datasets[1].palette_offset == 1


def test_hidden_rows_keep_their_points_but_leave_the_legend():
    entry = beetles(legend_overrides={
        row_key("group", "Xanthopygus"): {"hidden": True}})
    layout = layout_points([entry], LegendOptions(), DEFAULT_PALETTE)
    assert len(layout.groups) == 3
    assert layout.row_order == ["Eleusis", "Plociopterus"]


def test_counts_and_ordering_apply_to_the_plain_legend():
    options = LegendOptions(counts=True, order="count_desc")
    layout = layout_points([beetles()], options, DEFAULT_PALETTE)
    counts = [int(text.rsplit("(", 1)[1].rstrip(")"))
              for text in layout.row_order]
    assert counts == sorted(counts, reverse=True)
    assert sum(counts) == 50


def test_the_filter_limits_what_is_drawn_but_not_the_colours():
    entry = beetles()
    frame = entry.dataset.frame
    only = frame[frame["name1"] == "Xanthopygus"]
    layout = layout_points([entry], LegendOptions(), DEFAULT_PALETTE,
                           shown=lambda _entry: only)
    (label, style, rows), = layout.groups
    assert label == "Xanthopygus"
    assert style.color == DEFAULT_PALETTE[1]  # still its unfiltered colour
    assert len(rows) == len(only)


def test_symbol_by_gives_a_sectioned_legend_and_one_group_per_pair():
    entry = beetles(group_by="", color_by="Genus", symbol_by="Species")
    layout = layout_points([entry], LegendOptions(), DEFAULT_PALETTE)
    assert layout.row_order is None
    (title, rows), = layout.sections
    assert title == "Genus / Species"
    assert [depth for _label, _style, depth in rows][:2] == [0, 1]
    assert len(layout.groups) == entry.dataset.frame[
        ["name1", "name2"]].drop_duplicates().shape[0]


def test_default_title_is_the_group_by_column_for_one_plain_dataset():
    assert with_default_title([beetles()], LegendOptions()).title == "Genus"
    assert with_default_title([beetles()],
                              LegendOptions(title="Key")).title == "Key"
    two = [beetles(), manual()]
    assert with_default_title(two, LegendOptions()).title is None


def test_editor_rows_match_the_drawn_colours():
    entry = beetles()
    rows = editor_rows(entry, LegendOptions(), DEFAULT_PALETTE,
                       palette_offset=1)
    assert [value for _key, value, _style, _depth in rows] == [
        "Eleusis", "Xanthopygus", "Plociopterus"]
    assert rows[0][2].color == DEFAULT_PALETTE[1]


def test_column_key_maps_labels_to_frame_columns():
    entry = beetles()
    assert column_key(entry, "Species") == "name2"
    assert column_key(entry, "None") is None
    assert column_key(entry, "") is None
