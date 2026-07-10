"""Project manager dialog: open, rename, or delete saved projects.

Lists every project in the projects folder (newest first). Double-click
or the Open button opens one; ``self.open_path`` holds the chosen file
when the dialog closes (None otherwise).
"""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from pymappr import projects


class ProjectsDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Projects")
        self.transient(master)
        self.open_path: Path | None = None
        self._paths: list[Path] = []

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        self._folder_label = ttk.Label(body, foreground="#666666",
                                       wraplength=460)
        self._folder_label.pack(anchor="w", pady=(0, 6))

        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
        self._tree = ttk.Treeview(table, columns=("name", "saved"),
                                  show="headings", height=10,
                                  selectmode="browse")
        self._tree.heading("name", text="Project")
        self._tree.heading("saved", text="Last saved")
        self._tree.column("name", width=280)
        self._tree.column("saved", width=150)
        scroll = ttk.Scrollbar(table, orient="vertical",
                               command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._tree.bind("<Double-Button-1>", lambda _e: self._open())

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Open", command=self._open).pack(
            side="left")
        ttk.Button(buttons, text="Rename\N{HORIZONTAL ELLIPSIS}",
                   command=self._rename).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Delete", command=self._delete).pack(
            side="left", padx=(6, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(
            side="right")

        self._refresh()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_visibility()
        self._tree.focus_set()

    # ------------------------------------------------------------- internal

    def _refresh(self) -> None:
        folder = projects.projects_dir()
        self._folder_label.config(text=f"Projects folder: {folder}")
        self._tree.delete(*self._tree.get_children())
        self._paths = projects.list_projects(folder)
        for index, path in enumerate(self._paths):
            saved = time.strftime("%Y-%m-%d %H:%M",
                                  time.localtime(path.stat().st_mtime))
            self._tree.insert("", "end", iid=str(index),
                              values=(path.stem, saved))
        if self._paths:
            self._tree.selection_set("0")

    def _selected(self) -> Path | None:
        selection = self._tree.selection()
        if not selection:
            return None
        return self._paths[int(selection[0])]

    def _open(self) -> None:
        path = self._selected()
        if path is None:
            return
        self.open_path = path
        self.destroy()

    def _rename(self) -> None:
        path = self._selected()
        if path is None:
            return
        new_name = simpledialog.askstring(
            "Rename project", "New project name:",
            initialvalue=path.stem, parent=self)
        if not new_name or new_name.strip() == path.stem:
            return
        try:
            projects.rename_project(path, new_name.strip())
        except OSError as exc:
            messagebox.showerror("Rename project", str(exc), parent=self)
        self._refresh()

    def _delete(self) -> None:
        path = self._selected()
        if path is None:
            return
        if not messagebox.askyesno(
                "Delete project",
                f"Delete the project “{path.stem}”?\n\n"
                "This cannot be undone.", parent=self):
            return
        try:
            projects.delete_project(path)
        except OSError as exc:
            messagebox.showerror("Delete project", str(exc), parent=self)
        self._refresh()
