"""Manual coordinate entry dialog.

Type or paste one point per line ("38, -100"), give the set a legend
name, and pick its marker shape, size, and color - the familiar
SimpleMappr workflow. An optional third field on a line becomes a
per-point label. The same dialog re-opens for editing an existing
manually entered dataset.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from pymappr.styles import MARKERS, PointStyle

COORD_ORDERS = ["Latitude, Longitude", "Longitude, Latitude"]
SIZE_CHOICES = ["10", "20", "30", "45", "60", "90", "120"]


class ManualEntryDialog(tk.Toplevel):
    """Collects manual points; ``self.result`` is None when cancelled, else
    ``{"legend": str, "text": str, "order": "lat,lon"|"lon,lat",
    "style": PointStyle}``."""

    def __init__(self, master, legend: str = "", text: str = "",
                 order: str = "lat,lon", style: PointStyle | None = None):
        super().__init__(master)
        self.title("Manual coordinate entry")
        self.transient(master)
        self.resizable(False, True)
        self.result: dict | None = None
        style = style or PointStyle()

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        row = ttk.Frame(body)
        row.pack(fill="x")
        ttk.Label(row, text="Legend name:").pack(side="left")
        self._legend_var = tk.StringVar(value=legend)
        entry = ttk.Entry(row, textvariable=self._legend_var, width=32)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Coordinate order:").pack(side="left")
        self._order_var = tk.StringVar(
            value=COORD_ORDERS[0 if order == "lat,lon" else 1])
        ttk.Combobox(row, textvariable=self._order_var, values=COORD_ORDERS,
                     state="readonly", width=20).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="One point per line, e.g. 38, -100 "
                             "(optionally add a label: 38, -100, Site A). "
                             "Decimal degrees or DMS.",
                  foreground="#666666", wraplength=420).pack(
            anchor="w", pady=(8, 2))
        text_frame = ttk.Frame(body)
        text_frame.pack(fill="both", expand=True)
        self._text = tk.Text(text_frame, width=52, height=12, undo=True)
        scroll = ttk.Scrollbar(text_frame, orient="vertical",
                               command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)
        self._text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        if text:
            self._text.insert("1.0", text)

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Shape:").pack(side="left")
        self._marker_var = tk.StringVar(value=style.marker)
        ttk.Combobox(row, textvariable=self._marker_var,
                     values=list(MARKERS), state="readonly",
                     width=14).pack(side="left", padx=(4, 10))
        ttk.Label(row, text="Size:").pack(side="left")
        self._size_var = tk.StringVar(value=f"{style.size:g}")
        ttk.Combobox(row, textvariable=self._size_var, values=SIZE_CHOICES,
                     width=5).pack(side="left", padx=(4, 10))
        ttk.Label(row, text="Color:").pack(side="left")
        self._color = style.color
        self._color_button = tk.Button(row, width=4, bg=self._color,
                                       activebackground=self._color,
                                       relief="ridge",
                                       command=self._pick_color)
        self._color_button.pack(side="left", padx=(4, 0))

        self._error = ttk.Label(body, text="", foreground="#b00020",
                                wraplength=420)
        self._error.pack(anchor="w", pady=(6, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(
            side="right", padx=(6, 0))
        ttk.Button(buttons, text="OK", command=self._accept).pack(
            side="right")
        ttk.Button(buttons, text="Clear", command=self._clear).pack(
            side="left")

        self.bind("<Escape>", lambda _e: self._cancel())
        self.grab_set()
        self.wait_visibility()
        entry.focus_set()

    def _pick_color(self) -> None:
        _rgb, hex_color = colorchooser.askcolor(color=self._color,
                                                parent=self,
                                                title="Point color")
        if hex_color:
            self._color = hex_color
            self._color_button.config(bg=hex_color,
                                      activebackground=hex_color)

    def _clear(self) -> None:
        self._text.delete("1.0", "end")

    def _accept(self) -> None:
        legend = self._legend_var.get().strip()
        if not legend:
            self._error.config(text="Give the point set a legend name.")
            return
        text = self._text.get("1.0", "end").strip()
        if not text:
            self._error.config(text="Enter at least one coordinate line.")
            return
        try:
            size = max(min(float(self._size_var.get()), 1000.0), 1.0)
        except ValueError:
            size = 30.0
        order = ("lat,lon" if self._order_var.get() == COORD_ORDERS[0]
                 else "lon,lat")
        self.result = {
            "legend": legend,
            "text": text,
            "order": order,
            "style": PointStyle(color=self._color,
                                marker=self._marker_var.get(), size=size),
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
