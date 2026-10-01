"""Project path/name/dirty state around open, rename, delete and Save As.

The app and dialog are lightweight stand-ins that run the real methods.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pymappr import app as app_module
from pymappr.app import UNTITLED, PyMapprApp
from pymappr.files import projects
from pymappr.ui import projects_dialog
from pymappr.ui.projects_dialog import ProjectsDialog


class _StubApp:
    """Just enough app to run the project methods for real."""

    def __init__(self):
        self.state = {"entries": ["mine"], "settings": "mine"}
        self.project_path = Path("Survey.pymappr")
        self.project_name = "Survey"
        self.titles: list[str] = []
        self.status = ""
        self.root = None
        self._default_state = {"entries": [], "settings": "default"}
        self.fail_on: set[str] = set()
        self._clean_snapshot = None
        self._mark_clean()

    def _collect_state(self):
        return json.loads(json.dumps(self.state))

    def _apply_state(self, state):
        # Half-applies, then raises, like a corrupt file would.
        self.state["entries"] = state["entries"]
        if state["settings"] in self.fail_on:
            raise KeyError("settings")
        self.state["settings"] = state["settings"]

    def _set_title(self):
        self.titles.append(self.project_name)

    def set_status(self, text):
        self.status = text

    _snapshot = PyMapprApp._snapshot
    _mark_clean = PyMapprApp._mark_clean
    _confirm_discard = PyMapprApp._confirm_discard
    _open_project_path = PyMapprApp._open_project_path
    _restore_after_failed_open = PyMapprApp._restore_after_failed_open
    _follow_dialog_changes = PyMapprApp._follow_dialog_changes
    on_save_project_as = PyMapprApp.on_save_project_as
    on_save_project = PyMapprApp.on_save_project


@pytest.fixture
def errors(monkeypatch):
    shown = []
    monkeypatch.setattr(app_module.messagebox, "showerror",
                        lambda *a, **k: shown.append(a))
    return shown


def _stub_load(monkeypatch, state):
    monkeypatch.setattr(projects, "load_project",
                        lambda path: ("Other", state))


def test_failed_open_restores_the_previous_project(monkeypatch, errors):
    app = _StubApp()
    _stub_load(monkeypatch, {"entries": ["theirs"], "settings": "bad"})
    app.fail_on = {"bad"}
    app._open_project_path("Other.pymappr")
    assert errors
    assert app.state == {"entries": ["mine"], "settings": "mine"}
    assert app.project_path == Path("Survey.pymappr")
    assert app.project_name == "Survey"
    assert app._snapshot() == app._clean_snapshot


def test_failed_open_keeps_unsaved_changes_unsaved(monkeypatch, errors):
    app = _StubApp()
    app.state["settings"] = "edited"
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel",
                        lambda *a, **k: False)
    _stub_load(monkeypatch, {"entries": ["theirs"], "settings": "bad"})
    app.fail_on = {"bad"}
    app._open_project_path("Other.pymappr")
    assert app.state["settings"] == "edited"
    assert app._snapshot() != app._clean_snapshot


def test_failed_open_that_cannot_restore_starts_blank(monkeypatch, errors):
    app = _StubApp()
    # Re-applying the old state fails as well as applying the new one.
    app.fail_on = {"bad", "mine"}
    _stub_load(monkeypatch, {"entries": ["theirs"], "settings": "bad"})
    app._open_project_path("Other.pymappr")
    assert errors
    assert app.project_path is None
    assert app.project_name == UNTITLED
    assert app.state["entries"] == []


def _dialog():
    return SimpleNamespace(renamed={}, deleted=set())


def _real_dialog(path):
    dialog = _dialog()
    dialog._record_rename = lambda o, n: ProjectsDialog._record_rename(
        dialog, o, n)
    dialog._record_delete = lambda p: ProjectsDialog._record_delete(
        dialog, p)
    dialog._selected = lambda: path
    dialog._refresh = lambda: None
    return dialog


def test_dialog_records_rename_chains_and_deletes(monkeypatch, tmp_path):
    a = tmp_path / "A.pymappr"
    a.write_text("{}")
    dialog = _real_dialog(a)
    answers = iter(["B", "C"])
    monkeypatch.setattr(projects_dialog.simpledialog, "askstring",
                        lambda *x, **k: next(answers))
    ProjectsDialog._rename(dialog)
    dialog._selected = lambda: tmp_path / "B.pymappr"
    ProjectsDialog._rename(dialog)
    assert dialog.renamed == {a: tmp_path / "C.pymappr"}
    monkeypatch.setattr(projects_dialog.messagebox, "askyesno",
                        lambda *x, **k: True)
    dialog._selected = lambda: tmp_path / "C.pymappr"
    ProjectsDialog._delete(dialog)
    assert dialog.renamed == {}
    assert dialog.deleted == {a}


def test_dialog_does_not_record_failed_changes(monkeypatch, tmp_path):
    a = tmp_path / "A.pymappr"
    dialog = _real_dialog(a)  # A does not exist: rename and delete fail
    shown = []
    monkeypatch.setattr(projects_dialog.messagebox, "showerror",
                        lambda *x, **k: shown.append(x))
    monkeypatch.setattr(projects_dialog.simpledialog, "askstring",
                        lambda *x, **k: "B")
    monkeypatch.setattr(projects_dialog.messagebox, "askyesno",
                        lambda *x, **k: True)
    ProjectsDialog._rename(dialog)
    ProjectsDialog._delete(dialog)
    assert len(shown) == 2
    assert dialog.renamed == {} and dialog.deleted == set()


def test_renaming_the_open_project_follows_it(tmp_path):
    app = _StubApp()
    app.project_path = tmp_path / "Survey.pymappr"
    dialog = _dialog()
    dialog.renamed = {tmp_path / "Survey.pymappr":
                      tmp_path / "Survey 2024.pymappr"}
    app._follow_dialog_changes(dialog)
    assert app.project_path == tmp_path / "Survey 2024.pymappr"
    assert app.project_name == "Survey 2024"
    assert app.titles[-1] == "Survey 2024"


def test_deleting_the_open_project_detaches_and_marks_dirty(tmp_path):
    app = _StubApp()
    app.project_path = tmp_path / "Survey.pymappr"
    dialog = _dialog()
    dialog.deleted = {tmp_path / "sub" / ".." / "Survey.pymappr"}
    app._follow_dialog_changes(dialog)
    assert app.project_path is None
    assert app.project_name == "Survey"
    assert app._snapshot() != app._clean_snapshot


def test_changes_to_other_projects_leave_the_open_one_alone(tmp_path):
    app = _StubApp()
    app.project_path = tmp_path / "Survey.pymappr"
    dialog = _dialog()
    dialog.renamed = {tmp_path / "X.pymappr": tmp_path / "Y.pymappr"}
    dialog.deleted = {tmp_path / "Z.pymappr"}
    app._follow_dialog_changes(dialog)
    assert app.project_path == tmp_path / "Survey.pymappr"
    assert app.project_name == "Survey"


def test_failed_save_as_leaves_path_name_and_title(monkeypatch, tmp_path):
    monkeypatch.setattr(projects, "projects_dir", lambda: tmp_path)
    app = _StubApp()
    monkeypatch.setattr(app_module.simpledialog, "askstring",
                        lambda *a, **k: "New name")
    shown = []
    monkeypatch.setattr(app_module.messagebox, "showerror",
                        lambda *a, **k: shown.append(a))

    def boom(*args):
        raise OSError("read-only folder")
    monkeypatch.setattr(projects, "save_project", boom)
    assert app.on_save_project_as() is False
    assert shown
    assert app.project_path == Path("Survey.pymappr")
    assert app.project_name == "Survey"
    assert app.titles[-1] == "Survey"


def test_opening_another_project_after_renaming_the_open_one(
        monkeypatch, tmp_path):
    old, new = tmp_path / "Survey.pymappr", tmp_path / "Survey 2024.pymappr"
    app = _StubApp()
    app.project_path = old
    app.state["settings"] = "edited"
    app.root = SimpleNamespace(wait_window=lambda dialog: None)
    app.on_projects = lambda: PyMapprApp.on_projects(app)
    dialog = _dialog()
    dialog.renamed = {old: new}
    dialog.open_path = tmp_path / "Other.pymappr"
    monkeypatch.setattr(app_module, "ProjectsDialog", lambda root: dialog)
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel",
                        lambda *a, **k: True)
    saved = []
    monkeypatch.setattr(projects, "save_project",
                        lambda path, name, state: saved.append(path))
    _stub_load(monkeypatch, {"entries": ["theirs"], "settings": "theirs"})
    app.on_projects()
    assert saved == [new]
    assert app.project_path == dialog.open_path
