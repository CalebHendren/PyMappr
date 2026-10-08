"""Project files: new, open, save, import and export, the projects folder,
and the session saved on exit and restored at the next launch."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from pymappr.files import projects
from pymappr.files.projects import PROJECT_EXTENSION
from pymappr.ui.projects_dialog import ProjectsDialog

UNTITLED = "Untitled"
PROJECT_FILETYPES = [("PyMappr project", "*" + PROJECT_EXTENSION),
                     ("All files", "*.*")]


class ProjectFilesMixin:
    """Project files and the session."""

    def _snapshot(self) -> str:
        return json.dumps(self._collect_state(), sort_keys=True, default=str)

    def _mark_clean(self) -> None:
        self._clean_snapshot = self._snapshot()

    def _confirm_discard(self) -> bool:
        """Offer to save unsaved changes; False means the user cancelled."""
        if self._snapshot() == self._clean_snapshot:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save changes to \N{LEFT DOUBLE QUOTATION MARK}"
            f"{self.project_name}\N{RIGHT DOUBLE QUOTATION MARK} first?",
            parent=self.root)
        if answer is None:
            return False
        if answer:
            return self.on_save_project()
        return True

    def on_new_project(self) -> None:
        if not self._confirm_discard():
            return
        self._apply_state(json.loads(json.dumps(self._default_state)))
        self.project_path = None
        self.project_name = UNTITLED
        self._mark_clean()
        self._set_title()
        self.set_status("Started a new project.")

    def on_projects(self) -> None:
        """Open the project manager (open / rename / delete)."""
        dialog = ProjectsDialog(self.root)
        self.root.wait_window(dialog)
        self._follow_dialog_changes(dialog)
        if dialog.open_path is not None:
            self._open_project_path(dialog.open_path)

    def _follow_dialog_changes(self, dialog: ProjectsDialog) -> None:
        """Keep the open project's path in step with renames and deletes."""
        if self.project_path is None:
            return
        current = self.project_path.resolve()
        for old, new in dialog.renamed.items():
            if old.resolve() == current:
                self.project_path = new
                self.project_name = new.stem
                self._set_title()
                return
        if any(path.resolve() == current for path in dialog.deleted):
            # The file is gone: Ctrl+S must ask for a name, and New or
            # Open must offer to save, even after a restart (the session
            # remembers that it is unsaved).
            self.project_path = None
            self._clean_snapshot = None
            self._set_title()

    def _open_project_path(self, path: Path | str) -> None:
        if not self._confirm_discard():
            return
        try:
            _name, state = projects.load_project(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open project", str(exc), parent=self.root)
            return
        before = self._collect_state()
        was_clean = (json.dumps(before, sort_keys=True, default=str)
                     == self._clean_snapshot)
        try:
            self._apply_state(state)
        except Exception as exc:  # noqa: BLE001 - corrupt/edited file
            self._restore_after_failed_open(before, was_clean)
            messagebox.showerror(
                "Open project",
                f"Could not open the project:\n{exc}", parent=self.root)
            return
        self.project_path = Path(path)
        self.project_name = self.project_path.stem
        self._mark_clean()
        self._set_title()
        self.set_status(f"Opened project {self.project_name}.")

    def _restore_after_failed_open(self, before: dict,
                                   was_clean: bool) -> None:
        """Undo a part-applied project so it is never paired with a path."""
        try:
            self._apply_state(before)
        except Exception:  # noqa: BLE001 - fall back to a blank project
            self.project_path = None
            self.project_name = UNTITLED
            self._set_title()
            self._apply_state(json.loads(json.dumps(self._default_state)))
            self._mark_clean()
            return
        if was_clean:
            self._mark_clean()
        else:
            self._clean_snapshot = None

    def on_save_project(self) -> bool:
        if self.project_path is None:
            return self.on_save_project_as()
        try:
            projects.save_project(self.project_path, self.project_name,
                                  self._collect_state())
        except OSError as exc:
            messagebox.showerror("Save project", str(exc), parent=self.root)
            return False
        self._mark_clean()
        self.set_status(f"Saved project to {self.project_path}.")
        return True

    def on_save_project_as(self) -> bool:
        name = simpledialog.askstring(
            "Save project", "Project name:",
            initialvalue="" if self.project_name == UNTITLED
            else self.project_name, parent=self.root)
        if not name or not name.strip():
            return False
        name = name.strip()
        path = (projects.projects_dir()
                / (projects.safe_filename(name) + PROJECT_EXTENSION))
        if path.exists() and path != self.project_path:
            if not messagebox.askyesno(
                    "Save project",
                    f"A project named \N{LEFT DOUBLE QUOTATION MARK}{name}"
                    f"\N{RIGHT DOUBLE QUOTATION MARK} already exists. "
                    "Overwrite it?", parent=self.root):
                return False
        old_path, old_name = self.project_path, self.project_name
        self.project_path = path
        self.project_name = name
        self._set_title()
        if self.on_save_project():
            return True
        self.project_path, self.project_name = old_path, old_name
        self._set_title()
        return False

    def on_import_project(self) -> None:
        """Copy a shared project file into the projects folder and open it."""
        source = filedialog.askopenfilename(
            parent=self.root, title="Import project",
            filetypes=PROJECT_FILETYPES)
        if not source:
            return
        try:
            projects.load_project(source)  # validate before copying
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import project", str(exc),
                                 parent=self.root)
            return
        folder = projects.projects_dir()
        base = projects.safe_filename(Path(source).stem)
        target = folder / (base + PROJECT_EXTENSION)
        counter = 2
        while target.exists():
            target = folder / f"{base} ({counter}){PROJECT_EXTENSION}"
            counter += 1
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            messagebox.showerror("Import project", str(exc),
                                 parent=self.root)
            return
        self._open_project_path(target)

    def on_export_project(self) -> None:
        """Save the current project anywhere, for sharing."""
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export project",
            defaultextension=PROJECT_EXTENSION,
            initialfile=(projects.safe_filename(self.project_name)
                         + PROJECT_EXTENSION),
            filetypes=PROJECT_FILETYPES)
        if not path:
            return
        try:
            projects.save_project(path, self.project_name,
                                  self._collect_state())
        except OSError as exc:
            messagebox.showerror("Export project", str(exc),
                                 parent=self.root)
            return
        self.set_status(f"Exported project to {path}")

    def on_set_projects_folder(self) -> None:
        folder = filedialog.askdirectory(
            parent=self.root, title="Choose the folder to save projects in",
            initialdir=str(projects.projects_dir()))
        if not folder:
            return
        projects.set_projects_dir(folder)
        self.set_status(f"Projects are now saved in {folder}")

    def on_exit(self) -> None:
        self._save_session()
        self.root.destroy()

    # -------------------------------------------------------------- session

    def _save_session(self) -> None:
        """Autosave everything so the next launch resumes where we left off."""
        try:
            state = self._collect_state()
            # Unsaved changes stay unsaved across a restart, so New or Open
            # after relaunching still offers to save them.
            unsaved = (json.dumps(state, sort_keys=True, default=str)
                       != self._clean_snapshot)
            state["project_path"] = (str(self.project_path)
                                     if self.project_path else "")
            state["project_name"] = self.project_name
            state["geometry"] = self.root.geometry()
            state["unsaved"] = unsaved
            projects.save_project(projects.session_path(),
                                  self.project_name, state)
        except Exception:  # noqa: BLE001 - never block closing the app
            pass

    def _restore_session(self) -> None:
        path = projects.session_path()
        if not path.exists():
            return
        try:
            _name, state = projects.load_project(path)
            geometry = state.get("geometry")
            if geometry:
                self.root.geometry(str(geometry))
            self._apply_state(state)
            stored = str(state.get("project_path") or "")
            self.project_path = (Path(stored)
                                 if stored and Path(stored).exists()
                                 else None)
            self.project_name = (str(state.get("project_name") or "")
                                 or UNTITLED)
            if state.get("unsaved"):
                self._clean_snapshot = None
            else:
                self._mark_clean()
            self._set_title()
            if self.entries:
                self.set_status("Restored your previous session.")
        except Exception:  # noqa: BLE001 - a bad session must not block startup
            pass
