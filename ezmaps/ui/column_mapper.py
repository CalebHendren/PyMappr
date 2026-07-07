"""Modal dialog shown on every CSV import.

The user must pick which column is Longitude and which is Latitude, and
choose any number of name columns (used for grouping and the legend).
Name labels can either keep the original CSV headers or fall back to the
generic "Name 1", "Name 2", ... numbering.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ezmaps.data_loader import ColumnMapping

_UNSET = "(choose\N{HORIZONTAL ELLIPSIS})"
PREVIEW_ROWS = 8


class ColumnMapperDialog(tk.Toplevel):
    """Returns the chosen mapping in ``self.result`` (None if cancelled)."""

    def __init__(self, master, frame: pd.DataFrame, guess: ColumnMapping):
        super().__init__(master)
        self.title("Choose CSV columns")
        self.resizable(False, False)
        self.transient(master)
        self.result: ColumnMapping | None = None
        self._columns = list(frame.columns)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Select the coordinate columns (required):",
                  font=("", 9, "bold")).pack(anchor="w")
        picker = ttk.Frame(body)
        picker.pack(fill="x", pady=(3, 0))
        self._coord_vars: dict[str, tk.StringVar] = {}
        for row, (label, key, initial) in enumerate([
                ("Latitude", "latitude", guess.latitude),
                ("Longitude", "longitude", guess.longitude)]):
            ttk.Label(picker, text=label + ":").grid(
                row=row, column=0, sticky="w", pady=3, padx=(0, 8))
            var = tk.StringVar(value=initial or _UNSET)
            ttk.Combobox(picker, textvariable=var, values=self._columns,
                         state="readonly", width=28).grid(
                row=row, column=1, sticky="ew", pady=3)
            self._coord_vars[key] = var

        ttk.Label(body, text="Select the name columns (for grouping and "
                             "the legend):", font=("", 9, "bold")).pack(
            anchor="w", pady=(10, 0))
        names_frame = ttk.Frame(body)
        names_frame.pack(fill="x", pady=(3, 0))
        self._name_vars: dict[str, tk.BooleanVar] = {}
        guessed_names = set(guess.names)
        for i, col in enumerate(self._columns):
            var = tk.BooleanVar(value=col in guessed_names)
            ttk.Checkbutton(names_frame, text=col, variable=var).grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 12))
            self._name_vars[col] = var

        self._use_headers_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body, text="Use the CSV column headers as name labels\n"
                       "(instead of Name 1, Name 2, Name 3, "
                       "\N{HORIZONTAL ELLIPSIS})",
            variable=self._use_headers_var).pack(anchor="w", pady=(6, 0))

        ttk.Label(body, text="File preview:").pack(anchor="w", pady=(12, 3))
        preview = ttk.Frame(body)
        preview.pack(fill="both", expand=True)
        tree = ttk.Treeview(preview, columns=self._columns, show="headings",
                            height=min(PREVIEW_ROWS, len(frame)))
        for col in self._columns:
            tree.heading(col, text=col)
            tree.column(col, width=110, stretch=False)
        for _, row in frame.head(PREVIEW_ROWS).iterrows():
            tree.insert("", "end", values=[str(v) for v in row])
        xscroll = ttk.Scrollbar(preview, orient="horizontal",
                                command=tree.xview)
        tree.configure(xscrollcommand=xscroll.set)
        tree.pack(fill="x")
        xscroll.pack(fill="x")

        self._error = ttk.Label(body, text="", foreground="#b00020")
        self._error.pack(anchor="w", pady=(6, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(
            side="right", padx=(6, 0))
        ttk.Button(buttons, text="Import", command=self._accept).pack(
            side="right")

        self.bind("<Return>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _accept(self) -> None:
        lat = self._coord_vars["latitude"].get()
        lon = self._coord_vars["longitude"].get()
        if lat == _UNSET or lon == _UNSET:
            self._error.config(
                text="Select the latitude and longitude columns first.")
            return
        if lon == lat:
            self._error.config(
                text="Longitude and latitude must be different columns.")
            return
        names = [c for c in self._columns
                 if self._name_vars[c].get() and c not in (lon, lat)]
        self.result = ColumnMapping(
            longitude=lon, latitude=lat, names=names,
            use_headers=self._use_headers_var.get())
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
