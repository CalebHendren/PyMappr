"""Export-as-code dialog: show and save the Python/R map script.

Selecting a language box pastes the pre-made functions from
``pymappr/codegen.py`` (filled in with the current map settings) into the
preview.

Two ways to take it away, both ready to run with no setup:

* **Save code as** writes a single, self-contained ``.py``/``.R`` file -
  point data embedded, missing packages installed on first run - so you
  can paste it into an IDE and click Run.
* **Save as working directory** writes a whole runnable project folder
  (the script, the point data as CSV, a dependency manifest, a README,
  and a ``.gitignore``) to point an IDE at.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pymappr import codegen, projects

WRAP = 560
NOTE = ("The script installs any missing packages on first run and "
        "downloads its base layers from Natural Earth, so you can just "
        "open it in an IDE and click Run. Save a single self-contained "
        "file, or a whole runnable project folder.")

# The R export reuses the Python code paths where it can, but some styling
# details do not map one-to-one; flag it as best effort in the picker.
LANGUAGE_LABELS = {"R": "R (best effort)"}


class CodeExportDialog(tk.Toplevel):
    """Show pre-made Python/R code that recreates the current map."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("Export map as code")
        self.transient(master)
        self.minsize(640, 520)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=NOTE, wraplength=WRAP,
                  justify="left", foreground="#333333").pack(anchor="w")

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(10, 4))
        ttk.Label(row, text="Language:").pack(side="left")
        stored = str(projects.load_settings().get("code_export_language",
                                                  ""))
        self._language_var = tk.StringVar(
            value=stored if stored in codegen.LANGUAGES else "Python")
        for language in codegen.LANGUAGES:
            ttk.Radiobutton(row, text=LANGUAGE_LABELS.get(language, language),
                            value=language,
                            variable=self._language_var,
                            command=self._refresh).pack(side="left",
                                                        padx=(8, 0))
        self._status = ttk.Label(row, text="", foreground="#666666")
        self._status.pack(side="right")

        out_frame = ttk.Frame(body)
        out_frame.pack(fill="both", expand=True)
        self._output = tk.Text(out_frame, height=22, width=80,
                               state="disabled", wrap="none")
        yscroll = ttk.Scrollbar(out_frame, orient="vertical",
                                command=self._output.yview)
        xscroll = ttk.Scrollbar(out_frame, orient="horizontal",
                                command=self._output.xview)
        self._output.configure(yscrollcommand=yscroll.set,
                               xscrollcommand=xscroll.set)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self._output.pack(side="left", fill="both", expand=True)

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Copy code",
                   command=self._copy).pack(side="left")
        ttk.Button(row, text="Save code as\N{HORIZONTAL ELLIPSIS}",
                   command=self._save).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Save as working directory"
                            "\N{HORIZONTAL ELLIPSIS}",
                   command=self._save_directory).pack(side="left",
                                                      padx=(6, 0))
        ttk.Button(row, text="Close",
                   command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda _e: self.destroy())
        self._refresh()

    # ------------------------------------------------------------- code

    def _figure_size(self) -> tuple[float, float] | None:
        """The app canvas size in inches, so the exported map keeps the
        same geometry (fonts and markers at the same relative scale)."""
        try:
            width, height = self.app.renderer.fig.get_size_inches()
            return float(width), float(height)
        except Exception:  # noqa: BLE001 - fall back to the default size
            return None

    def _generate(self) -> str:
        return codegen.generate_code(self.app._collect_state(),
                                     self.app.entries,
                                     self._language_var.get(),
                                     self.app.project_name,
                                     figure_size=self._figure_size())

    def _refresh(self) -> None:
        """Selecting a language box pastes that language's pre-made
        functions (with the current settings) into the preview."""
        language = self._language_var.get()
        settings = projects.load_settings()
        settings["code_export_language"] = language
        projects.save_settings(settings)
        try:
            code = self._generate()
        except Exception as exc:  # noqa: BLE001 - show any build error
            self._status.config(text=f"Could not generate code: {exc}")
            return
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.insert("1.0", code)
        self._output.configure(state="disabled")
        self._status.config(
            text=f"{language} \N{MIDDLE DOT} "
                 f"{len(code.splitlines())} lines")

    def _code_text(self) -> str:
        return self._output.get("1.0", "end").strip()

    def _copy(self) -> None:
        code = self._code_text()
        if not code:
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        self._status.config(text="Code copied to the clipboard.")

    def _save(self) -> None:
        code = self._code_text()
        if not code:
            return
        language = self._language_var.get()
        extension = codegen.CODE_EXTENSIONS[language]
        path = filedialog.asksaveasfilename(
            parent=self, title="Save map code",
            defaultextension=extension,
            initialfile="recreate_map" + extension,
            filetypes=[(f"{language} script", "*" + extension),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code + "\n")
        except OSError as exc:
            self._status.config(text=f"Could not save: {exc}")
            return
        self._status.config(text=f"Saved to {path}")

    def _save_directory(self) -> None:
        """Write a whole runnable project folder (script + data + README +
        dependency manifest) that an IDE can be pointed at directly."""
        language = self._language_var.get()
        try:
            files = codegen.generate_working_directory(
                self.app._collect_state(), self.app.entries, language,
                self.app.project_name, figure_size=self._figure_size())
        except Exception as exc:  # noqa: BLE001 - show any build error
            self._status.config(text=f"Could not build the project: {exc}")
            return
        target = filedialog.askdirectory(
            parent=self, mustexist=True,
            title="Choose a folder for the runnable project")
        if not target:
            return
        folder = Path(target)
        clashes = [rel for rel in files if (folder / rel).exists()]
        if clashes and not messagebox.askyesno(
                "Overwrite files?",
                f"{len(clashes)} file(s) already exist in\n{folder}\n"
                f"(e.g. {clashes[0]}).\n\nOverwrite them?", parent=self):
            return
        try:
            for rel, content in files.items():
                dest = folder / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
        except OSError as exc:
            self._status.config(text=f"Could not save the project: {exc}")
            return
        self._status.config(
            text=f"Saved a runnable {language} project to {folder}")
