"""Modal dialog for mapping CSV columns to Name 1 / Name 2 / Longitude /
Latitude, with a preview of the first rows."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ezmaps.data_loader import ColumnMapping

_NONE = "(none)"
PREVIEW_ROWS = 8


class ColumnMapperDialog(tk.Toplevel):
    """Returns the chosen mapping in ``self.result`` (None if cancelled)."""

    def __init__(self, master, frame: pd.DataFrame, guess: ColumnMapping):
        super().__init__(master)
        self.title("Choose CSV columns")
        self.resizable(False, False)
        self.transient(master)
        self.result: ColumnMapping | None = None

        columns = list(frame.columns)
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        picker = ttk.Frame(body)
        picker.pack(fill="x")
        self._vars: dict[str, tk.StringVar] = {}
        fields = [
            ("Name 1 (e.g. County)", "name1", guess.name1 or _NONE, True),
            ("Name 2 (e.g. City)", "name2", guess.name2 or _NONE, True),
            ("Longitude", "longitude", guess.longitude, False),
            ("Latitude", "latitude", guess.latitude, False),
        ]
        for row, (label, key, initial, optional) in enumerate(fields):
            ttk.Label(picker, text=label + ":").grid(
                row=row, column=0, sticky="w", pady=3, padx=(0, 8))
            var = tk.StringVar(value=initial)
            values = ([_NONE] + columns) if optional else columns
            ttk.Combobox(picker, textvariable=var, values=values,
                         state="readonly", width=28).grid(
                row=row, column=1, sticky="ew", pady=3)
            self._vars[key] = var

        ttk.Label(body, text="File preview:").pack(anchor="w", pady=(12, 3))
        preview = ttk.Frame(body)
        preview.pack(fill="both", expand=True)
        tree = ttk.Treeview(preview, columns=columns, show="headings",
                            height=min(PREVIEW_ROWS, len(frame)))
        for col in columns:
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
        lon = self._vars["longitude"].get()
        lat = self._vars["latitude"].get()
        name1 = self._vars["name1"].get()
        name2 = self._vars["name2"].get()
        if lon == lat:
            self._error.config(
                text="Longitude and latitude must be different columns.")
            return
        self.result = ColumnMapping(
            longitude=lon, latitude=lat,
            name1=None if name1 == _NONE else name1,
            name2=None if name2 == _NONE else name2)
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
