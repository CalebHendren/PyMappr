import json

import pytest

from pymappr import projects
from pymappr.data_loader import build_manual_dataset, load_csv
from pymappr.projects import DatasetEntry
from pymappr.styles import PointStyle


def make_entry():
    dataset = build_manual_dataset(
        "Pardosa distincta", "38,-100, Site A\n-25,140, Site B\n")
    return DatasetEntry(
        dataset=dataset, name="Pardosa distincta", visible=True,
        group_by="Legend", color_by="", symbol_by="", vary_symbols=False,
        styles={"Pardosa distincta": PointStyle(color="#123456",
                                                marker="Star", size=45.0)},
        manual={"text": "38,-100, Site A\n-25,140, Site B", "order": "lat,lon"})


def test_entry_roundtrip():
    entry = make_entry()
    restored = projects.entry_from_dict(
        json.loads(json.dumps(projects.entry_to_dict(entry))))
    assert restored.name == entry.name
    assert restored.visible is True
    assert restored.group_by == "Legend"
    assert restored.manual == entry.manual
    assert restored.dataset.name_labels == ["Legend", "Label"]
    assert len(restored.dataset) == 2
    assert restored.dataset.frame.iloc[0]["lon"] == pytest.approx(-100)
    assert restored.dataset.frame.iloc[0]["lat"] == pytest.approx(38)
    assert list(restored.dataset.frame["name2"]) == ["Site A", "Site B"]
    style = restored.styles["Pardosa distincta"]
    assert (style.color, style.marker, style.size) == ("#123456", "Star", 45.0)


def test_entry_roundtrip_from_csv(tmp_path):
    path = tmp_path / "points.csv"
    path.write_text("City,Longitude,Latitude\nAustin,-97.7,30.3\n",
                    encoding="utf-8")
    dataset = load_csv(str(path))
    entry = DatasetEntry(dataset=dataset, name="points.csv", group_by="City")
    restored = projects.entry_from_dict(projects.entry_to_dict(entry))
    assert restored.dataset.source_path == str(path)
    assert restored.dataset.name_labels == ["City"]
    assert restored.dataset.frame.iloc[0]["name1"] == "Austin"
    assert restored.dataset.frame.iloc[0]["lat"] == pytest.approx(30.3)


def test_save_and_load_project(tmp_path):
    path = tmp_path / ("Spiders" + projects.PROJECT_EXTENSION)
    state = {"datasets": [projects.entry_to_dict(make_entry())],
             "map": {"projection": "Robinson"}}
    projects.save_project(path, "Spiders", state)
    name, loaded = projects.load_project(path)
    assert name == "Spiders"
    assert loaded["map"]["projection"] == "Robinson"
    entry = projects.entry_from_dict(loaded["datasets"][0])
    assert len(entry.dataset) == 2


def test_load_project_rejects_other_files(tmp_path):
    not_json = tmp_path / ("bad" + projects.PROJECT_EXTENSION)
    not_json.write_text("definitely not json", encoding="utf-8")
    with pytest.raises(ValueError):
        projects.load_project(not_json)
    wrong_format = tmp_path / ("wrong" + projects.PROJECT_EXTENSION)
    wrong_format.write_text(json.dumps({"format": "something-else"}),
                            encoding="utf-8")
    with pytest.raises(ValueError):
        projects.load_project(wrong_format)


def test_load_project_rejects_newer_format(tmp_path):
    path = tmp_path / ("future" + projects.PROJECT_EXTENSION)
    path.write_text(json.dumps({
        "format": "pymappr-project", "format_version": 999,
        "app_version": "99.0.0", "state": {},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="newer PyMappr"):
        projects.load_project(path)


def test_list_rename_delete_projects(tmp_path):
    a = tmp_path / ("A" + projects.PROJECT_EXTENSION)
    b = tmp_path / ("B" + projects.PROJECT_EXTENSION)
    projects.save_project(a, "A", {})
    projects.save_project(b, "B", {})
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    listed = projects.list_projects(tmp_path)
    assert sorted(p.stem for p in listed) == ["A", "B"]

    renamed = projects.rename_project(a, "Renamed")
    assert renamed.stem == "Renamed"
    assert not a.exists()
    with pytest.raises(FileExistsError):
        projects.rename_project(renamed, "B")

    projects.delete_project(b)
    assert [p.stem for p in projects.list_projects(tmp_path)] == ["Renamed"]


def test_safe_filename():
    assert projects.safe_filename('sp: "wolf/spider"?') == "sp_ _wolf_spider__"
    assert projects.safe_filename("  ") == "Untitled"
    assert projects.safe_filename("plain name") == "plain name"


def test_settings_and_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(projects.sys, "platform", "linux")
    assert projects.load_settings() == {}
    target = tmp_path / "My Projects"
    projects.set_projects_dir(target)
    assert projects.load_settings()["projects_dir"] == str(target)
    assert projects.projects_dir() == target
    assert target.is_dir()  # created lazily
    assert projects.session_path().parent == projects.config_dir()
