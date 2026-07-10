"""Modal dialog shown on every data import.

The user must pick which column is Longitude and which is Latitude, and
choose any number of name columns (used for grouping and the legend).
The first row is not assumed to be headers: a checkbox controls whether
it is treated as column names or as data to plot (the initial state is
guessed from the file). Spreadsheets with several worksheets get a
worksheet selector. Name labels can either keep the original headers or
fall back to the generic "Name 1", "Name 2", ... numbering.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import pandas as pd

from pymappr.data_loader import ColumnMapping, guess_mapping

_UNSET = "(choose\N{HORIZONTAL ELLIPSIS})"
PREVIEW_ROWS = 8

# reread(headers, sheet) -> DataFrame: re-reads the source file with the
# first row treated as headers (True) or data (False), from the given
# worksheet (None outside spreadsheets).
Reread = Callable[[bool, "str | None"], pd.DataFrame]


class ColumnMapperDialog(tk.Toplevel):
    """Returns the chosen mapping in ``self.result`` (None if cancelled)
    and the frame it applies to in ``self.frame`` (it changes when the
    header checkbox or worksheet selection is toggled)."""

    def __init__(self, master, frame: pd.DataFrame, guess: ColumnMapping,
                 reread: Reread | None = None, headers: bool = True,
                 sheets: list[str] | None = None):
        super().__init__(master)
        self.title("Choose columns")
        self.resizable(False, False)
        self.transient(master)
        self.result: ColumnMapping | None = None
        self.frame = frame
        self._reread = reread
        self._columns: list[str] = []
        self._coord_vars: dict[str, tk.StringVar] = {}
        self._name_vars: dict[str, tk.BooleanVar] = {}

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        if sheets and len(sheets) > 1:
            row = ttk.Frame(body)
            row.pack(fill="x", pady=(0, 6))
            ttk.Label(row, text="Worksheet:").pack(side="left")
            self._sheet_var = tk.StringVar(value=sheets[0])
            box = ttk.Combobox(row, textvariable=self._sheet_var,
                               values=list(sheets), state="readonly",
                               width=28)
            box.pack(side="left", padx=(6, 0))
            box.bind("<<ComboboxSelected>>", lambda _e: self._reload())
        else:
            self._sheet_var = None

        self._headers_var = tk.BooleanVar(value=headers)
        check = ttk.Checkbutton(
            body, text="First row contains column headers",
            variable=self._headers_var, command=self._reload)
        check.pack(anchor="w")
        if reread is None:
            check.state(["disabled"])
        ttk.Label(body, text="(untick if the first row is data that "
                             "should be plotted)",
                  foreground="#666666").pack(anchor="w", pady=(0, 6))

        ttk.Label(body, text="Select the coordinate columns (required):",
                  font=("", 9, "bold")).pack(anchor="w")
        self._picker = ttk.Frame(body)
        self._picker.pack(fill="x", pady=(3, 0))

        ttk.Label(body, text="Select the name columns (for grouping and "
                             "the legend):", font=("", 9, "bold")).pack(
            anchor="w", pady=(10, 0))
        self._names_frame = ttk.Frame(body)
        self._names_frame.pack(fill="x", pady=(3, 0))

        self._use_headers_var = tk.BooleanVar(value=True)
        self._use_headers_check = ttk.Checkbutton(
            body, text="Use the column headers as name labels\n"
                       "(instead of Name 1, Name 2, Name 3, "
                       "\N{HORIZONTAL ELLIPSIS})",
            variable=self._use_headers_var)
        self._use_headers_check.pack(anchor="w", pady=(6, 0))

        ttk.Label(body, text="File preview:").pack(anchor="w", pady=(12, 3))
        self._preview = ttk.Frame(body)
        self._preview.pack(fill="both", expand=True)

        self._error = ttk.Label(body, text="", foreground="#b00020")
        self._error.pack(anchor="w", pady=(6, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(
            side="right", padx=(6, 0))
        ttk.Button(buttons, text="Import", command=self._accept).pack(
            side="right")

        self._populate(frame, guess)

        self.bind("<Return>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    # ------------------------------------------------------------- internal

    def _reload(self) -> None:
        """Re-read the file after the header checkbox or sheet changed."""
        if self._reread is None:
            return
        headers = self._headers_var.get()
        sheet = self._sheet_var.get() if self._sheet_var else None
        try:
            frame = self._reread(headers, sheet)
            guess = guess_mapping(frame)
        except Exception as exc:  # noqa: BLE001 - show any read error
            self._error.config(text=str(exc))
            return
        self._error.config(text="")
        self.frame = frame
        self._populate(frame, guess)

    def _populate(self, frame: pd.DataFrame, guess: ColumnMapping) -> None:
        """(Re)build the column pickers and preview for *frame*."""
        self._columns = list(frame.columns)

        for child in self._picker.winfo_children():
            child.destroy()
        self._coord_vars = {}
        for row, (label, key, initial) in enumerate([
                ("Latitude", "latitude", guess.latitude),
                ("Longitude", "longitude", guess.longitude)]):
            ttk.Label(self._picker, text=label + ":").grid(
                row=row, column=0, sticky="w", pady=3, padx=(0, 8))
            var = tk.StringVar(value=initial or _UNSET)
            ttk.Combobox(self._picker, textvariable=var,
                         values=self._columns, state="readonly",
                         width=28).grid(row=row, column=1, sticky="ew",
                                        pady=3)
            self._coord_vars[key] = var

        for child in self._names_frame.winfo_children():
            child.destroy()
        self._name_vars = {}
        guessed_names = set(guess.names)
        for i, col in enumerate(self._columns):
            var = tk.BooleanVar(value=col in guessed_names)
            ttk.Checkbutton(self._names_frame, text=col, variable=var).grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 12))
            self._name_vars[col] = var

        # Generic "Column N" headers make poor labels; prefer Name 1, 2...
        headers_on = self._headers_var.get()
        self._use_headers_var.set(headers_on)
        self._use_headers_check.state(
            ["!disabled"] if headers_on else ["disabled"])

        for child in self._preview.winfo_children():
            child.destroy()
        tree = ttk.Treeview(self._preview, columns=self._columns,
                            show="headings",
                            height=max(min(PREVIEW_ROWS, len(frame)), 1))
        for col in self._columns:
            tree.heading(col, text=col)
            tree.column(col, width=110, stretch=False)
        for _, row in frame.head(PREVIEW_ROWS).iterrows():
            tree.insert("", "end", values=[str(v) for v in row])
        xscroll = ttk.Scrollbar(self._preview, orient="horizontal",
                                command=tree.xview)
        tree.configure(xscrollcommand=xscroll.set)
        tree.pack(fill="x")
        xscroll.pack(fill="x")

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
            use_headers=(self._headers_var.get()
                         and self._use_headers_var.get()))
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
