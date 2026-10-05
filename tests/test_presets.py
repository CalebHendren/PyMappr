"""Presets: every setting but the data and the zoom, saved to reuse in
another project."""

from __future__ import annotations

import json

import pytest

from pymappr.files import presets
from pymappr.files.presets import (apply_dataset_style, list_presets,
                                   load_preset, save_preset,
                                   settings_from_state)

from test_open_symbols import harvestmen


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setattr(presets, "config_dir", lambda: tmp_path)
    return tmp_path


def test_a_preset_reads_back_as_saved():
    settings = {"map": {"projection": "Robinson"}, "point_alpha": 0.5}
    save_preset(presets.preset_path("Mine"), "Mine", settings)
    assert load_preset(presets.preset_path("Mine")) == ("Mine", settings)


def test_a_preset_is_named_by_its_file_but_listed_by_its_name():
    path = presets.preset_path("Fig. 1: maps?")
    assert path.name == "Fig. 1_ maps_" + presets.PRESET_EXTENSION
    save_preset(path, "Fig. 1: maps?", {})
    assert list_presets() == [("Fig. 1: maps?", path)]


def test_presets_list_by_name_and_skip_unreadable_files(config_home):
    for name in ("beta", "Alpha", "gamma"):
        save_preset(presets.preset_path(name), name, {})
    (presets.presets_dir() / ("broken" + presets.PRESET_EXTENSION)
     ).write_text("{", encoding="utf-8")
    assert [name for name, _path in list_presets()] == ["Alpha", "beta",
                                                        "gamma"]


def test_a_deleted_preset_is_no_longer_listed():
    save_preset(presets.preset_path("Mine"), "Mine", {})
    presets.delete_preset(presets.preset_path("Mine"))
    assert list_presets() == []


def test_deleting_the_built_in_preset_is_remembered_and_lists_nothing():
    save_preset(presets.preset_path("Mine"), "Mine", {})
    assert not presets.built_in_deleted()
    presets.delete_built_in()
    assert presets.built_in_deleted()
    assert [name for name, _path in list_presets()] == ["Mine"]


def test_a_project_file_is_not_a_preset(tmp_path):
    path = tmp_path / "project.pymappr-preset"
    path.write_text(json.dumps({"format": "pymappr-project", "state": {}}),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="Not a PyMappr preset"):
        load_preset(path)


def test_a_preset_from_a_newer_pymappr_is_refused():
    path = presets.preset_path("Future")
    save_preset(path, "Future", {})
    document = json.loads(path.read_text(encoding="utf-8"))
    document["format_version"] = 99
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="newer PyMappr"):
        load_preset(path)


def test_a_preset_leaves_out_the_data_and_the_zoom():
    entry = harvestmen(color_by="Type status", vary_symbols=True)
    entry.legend_overrides = {"group:Nebulobunus alpha": {"color": "#ff0000"}}
    state = {"datasets": [{"rows": []}], "active": 0,
             "view": {"xlim": [0, 1], "ylim": [0, 1]},
             "map": {"projection": "Robinson"}, "legend": {"fontsize": 9.0},
             "point_alpha": 0.7, "point_edge": {"color": "#000000"}}
    settings = settings_from_state(state, entry)
    assert set(settings) == {"map", "legend", "point_alpha", "point_edge",
                             "dataset"}
    assert settings["dataset"]["group_by"] == "Species"
    assert settings["dataset"]["color_by"] == "Type status"
    assert settings["dataset"]["vary_symbols"] is True
    assert settings["dataset"]["legend_overrides"] == entry.legend_overrides
    assert settings_from_state(state, None)["dataset"] == {}


def test_a_dataset_style_applies_where_the_columns_exist():
    source = harvestmen(color_by="Type status", vary_symbols=True,
                        open_by="Type status", open_values=["Holotype"])
    style = settings_from_state({}, source)["dataset"]
    target = harvestmen(group_by="")
    assert apply_dataset_style(target, style) == []
    assert (target.group_by, target.color_by, target.open_by,
            target.open_values, target.vary_symbols) == (
        "Species", "Type status", "Type status", ["Holotype"], True)


def test_a_missing_column_is_left_alone_and_reported():
    target = harvestmen()
    skipped = apply_dataset_style(target, {"group_by": "Genus Species",
                                           "color_by": ""})
    assert skipped == ["Group by \N{LEFT DOUBLE QUOTATION MARK}Genus "
                       "Species\N{RIGHT DOUBLE QUOTATION MARK}"]
    assert target.group_by == "Species"
    assert target.color_by == ""


def test_legend_row_edits_merge_with_the_presets_winning():
    target = harvestmen()
    target.legend_overrides = {"group:a": {"label": "A", "color": "#111111"},
                               "group:b": {"hidden": True}}
    apply_dataset_style(target, {"legend_overrides": {
        "group:a": {"color": "#222222"}, "group:c": {"size": 40.0}}})
    assert target.legend_overrides == {
        "group:a": {"label": "A", "color": "#222222"},
        "group:b": {"hidden": True}, "group:c": {"size": 40.0}}


def test_an_empty_style_changes_nothing():
    target = harvestmen(color_by="Type status")
    assert apply_dataset_style(target, {}) == []
    assert target.color_by == "Type status"
