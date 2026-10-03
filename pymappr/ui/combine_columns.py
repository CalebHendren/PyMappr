"""Combine-columns dialog: join name columns into one, e.g. Genus + Species.

The joined column ("Genus Species") is added to the dataset like any other
name column, so the legend can show "Eleusis chapadensis" on a single row
without editing the source file.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


_GENUS_NAMES = ("genus",)
_SPECIES_NAMES = ("species", "specific epithet", "specificepithet",
                  "epithet", "species epithet", "sp.", "sp")


def default_columns(labels: list[str]) -> list[str]:
    """The columns that start ticked: Genus and Species when they are
    named so - in any position, since a table often goes on to Type
    status or Country after them - and otherwise the last two, where
    Genus and Species usually sit (after Family, say)."""
    lowered = {label: label.strip().lower() for label in labels}
    genus = next((label for label in labels
                  if lowered[label] in _GENUS_NAMES), None)
    species = next((label for label in labels
                    if lowered[label] in _SPECIES_NAMES), None)
    if genus and species:
        return [genus, species]
    return labels[-2:]


class CombineColumnsDialog(tk.Toplevel):
    """``self.result`` is ``(labels, separator)``, or None when cancelled.

    *preview(labels, separator)* returns the first row's joined value, shown
    live so the user can see what the legend will read.
    """

    def __init__(self, master, labels: list[str], preview):
        super().__init__(master)
        self.title("Combine columns")
        self.transient(master)
        self.resizable(False, False)
        self.result: tuple[list[str], str] | None = None
        self._labels = list(labels)
        self._preview = preview

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Join these name columns, in this order:").pack(
            anchor="w")
        self._vars = {}
        ticked = default_columns(self._labels)
        for label in self._labels:
            var = tk.BooleanVar(value=label in ticked)
            ttk.Checkbutton(body, text=label, variable=var,
                            command=self._update).pack(anchor="w", padx=(8, 0))
            self._vars[label] = var

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Separator:").pack(side="left")
        self._separator_var = tk.StringVar(value=" ")
        entry = ttk.Entry(row, textvariable=self._separator_var, width=6)
        entry.pack(side="left", padx=(6, 0))
        entry.bind("<KeyRelease>", lambda _e: self._update())

        self._example = ttk.Label(body, text="", foreground="#666666")
        self._example.pack(anchor="w", pady=(8, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="right", padx=(6, 0))
        self._ok = ttk.Button(buttons, text="Add column", command=self._accept)
        self._ok.pack(side="right")

        self.bind("<Return>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._update()
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _chosen(self) -> list[str]:
        return [label for label in self._labels if self._vars[label].get()]

    def _update(self) -> None:
        chosen = self._chosen()
        if len(chosen) < 2:
            self._ok.state(["disabled"])
            self._example.config(text="Tick at least two columns.")
            return
        self._ok.state(["!disabled"])
        sample = self._preview(chosen, self._separator_var.get())
        self._example.config(text=f"First row: {sample}" if sample else "")

    def _accept(self) -> None:
        chosen = self._chosen()
        if len(chosen) < 2:
            return
        self.result = (chosen, self._separator_var.get())
        self.destroy()
