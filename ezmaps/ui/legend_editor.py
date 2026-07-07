"""Legend style editor: per-group color, marker symbol, and size.

Changes apply to the map immediately via the *on_change* callback.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from ezmaps.styles import MARKERS, PointStyle


class LegendEditorDialog(tk.Toplevel):
    def __init__(self, master, styles: dict[str, PointStyle], on_change):
        super().__init__(master)
        self.title("Legend styles")
        self.transient(master)
        self.styles = styles
        self.on_change = on_change

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        for col, text, width in ((0, "Group", 24), (1, "Color", 6),
                                 (2, "Symbol", 10), (3, "Size", 6)):
            ttk.Label(header, text=text, width=width,
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=0, column=col, sticky="w", padx=4)

        # Scrollable list of style rows.
        canvas = tk.Canvas(outer, height=min(34 * max(len(styles), 1), 400),
                           highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        rows = ttk.Frame(canvas)
        rows.bind("<Configure>",
                  lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._color_buttons: dict[str, tk.Button] = {}
        for row_idx, (label, style) in enumerate(styles.items()):
            ttk.Label(rows, text=label, width=24).grid(
                row=row_idx, column=0, sticky="w", padx=4, pady=3)

            color_btn = tk.Button(
                rows, width=4, bg=style.color, relief="ridge",
                activebackground=style.color,
                command=lambda lb=label: self._pick_color(lb))
            color_btn.grid(row=row_idx, column=1, padx=4, pady=3)
            self._color_buttons[label] = color_btn

            marker_var = tk.StringVar(value=style.marker)
            marker_box = ttk.Combobox(rows, textvariable=marker_var,
                                      values=list(MARKERS),
                                      state="readonly", width=9)
            marker_box.grid(row=row_idx, column=2, padx=4, pady=3)
            marker_box.bind("<<ComboboxSelected>>",
                            lambda _e, lb=label, v=marker_var:
                            self._set_marker(lb, v.get()))

            size_var = tk.StringVar(value=f"{style.size:g}")
            spin = ttk.Spinbox(rows, from_=4, to=400, increment=4, width=6,
                               textvariable=size_var,
                               command=lambda lb=label, v=size_var:
                               self._set_size(lb, v.get()))
            spin.grid(row=row_idx, column=3, padx=4, pady=3)
            spin.bind("<KeyRelease>", lambda _e, lb=label, v=size_var:
                      self._set_size(lb, v.get()))

        ttk.Button(self, text="Close", command=self.destroy).pack(
            pady=(0, 10))
        self.grab_set()

    def _pick_color(self, label: str) -> None:
        current = self.styles[label].color
        _rgb, hex_color = colorchooser.askcolor(color=current, parent=self,
                                                title=f"Color for {label}")
        if hex_color:
            self.styles[label].color = hex_color
            btn = self._color_buttons[label]
            btn.config(bg=hex_color, activebackground=hex_color)
            self.on_change()

    def _set_marker(self, label: str, marker: str) -> None:
        self.styles[label].marker = marker
        self.on_change()

    def _set_size(self, label: str, raw: str) -> None:
        try:
            size = float(raw)
        except ValueError:
            return
        if 1 <= size <= 1000:
            self.styles[label].size = size
            self.on_change()
