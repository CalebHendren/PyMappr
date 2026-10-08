"""The Layers and Labels tabs: a checkbox for every Natural Earth
layer and for each set of place-name labels."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pymappr.ui.control_panel.tables import (BIODIVERSITY_ROWS, BOUNDARY_ROWS,
                                             CULTURE_ROWS, LABEL_ROWS,
                                             PANEL_WIDTH, PHYSICAL_ROWS,
                                             WATER_ROWS)


class LayersTabMixin:
    """Builds the Layers and Labels tabs."""

    def _layer_rows(self, sec, rows) -> None:
        for key, text, kind in rows:
            var = tk.BooleanVar(value=key == "countries")
            if kind == "line":
                self.layer_vars[key] = var
                command = lambda k=key: self.app.on_layer(k)  # noqa: E731
            elif kind == "fill":
                self.fill_vars[key] = var
                command = lambda k=key: self.app.on_fill_layer(k)  # noqa: E731
            else:
                self.point_vars[key] = var
                command = lambda k=key: self.app.on_point_layer(k)  # noqa: E731
            ttk.Checkbutton(sec, text=text, variable=var,
                            command=command).pack(anchor="w")

    def _build_layers_tab(self, tab) -> None:
        note = ttk.Label(
            tab, text="Detail follows the zoom: layers draw from Natural "
            "Earth 110m/50m/10m data as you zoom in.",
            wraplength=PANEL_WIDTH - 40, foreground="#666666")
        note.pack(anchor="w", padx=8, pady=(4, 0))

        sec = self._section(tab, "Borders & areas")
        self._layer_rows(sec, BOUNDARY_ROWS)

        sec = self._section(tab, "Cities & places")
        self.cities_var = tk.BooleanVar(value=False)
        self.point_vars["cities"] = self.cities_var
        ttk.Checkbutton(sec, text="Populated places (city markers)",
                        variable=self.cities_var,
                        command=lambda: self.app.on_point_layer(
                            "cities")).pack(anchor="w")
        self.capitals_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec, text="Capitals only", variable=self.capitals_only_var,
                        command=self.app.on_capitals_only).pack(anchor="w",
                                                                padx=(18, 0))
        ttk.Label(sec, text="Cities appear as you zoom in "
                  "(biggest cities first).",
                  wraplength=PANEL_WIDTH - 60,
                  foreground="#666666").pack(anchor="w")

        sec = self._section(tab, "Water & marine")
        ttk.Label(sec, text="Oceans:").pack(anchor="w")
        self.ocean_var = tk.StringVar(value="none")
        row = ttk.Frame(sec)
        row.pack(fill="x")
        for value, text in (("none", "None"), ("grey", "Greyscale"),
                            ("blue", "Blue")):
            ttk.Radiobutton(row, text=text, variable=self.ocean_var,
                            value=value,
                            command=self.app.on_ocean).pack(side="left",
                                                            padx=(0, 8))
        self.bathymetry_var = tk.BooleanVar(value=False)
        self._check(sec, "Bathymetry (ocean depth, slower)",
                    self.bathymetry_var, self.app.on_bathymetry)

        var = tk.BooleanVar(value=False)
        self.layer_vars["lakes_outline"] = var
        ttk.Checkbutton(sec, text="Lakes (outlines)", variable=var,
                        command=lambda: self.app.on_layer(
                            "lakes_outline")).pack(anchor="w", pady=(4, 0))
        ttk.Label(sec, text="Lakes fill:").pack(anchor="w")
        self.lake_fill_var = tk.StringVar(value="none")
        row = ttk.Frame(sec)
        row.pack(fill="x")
        for value, text in (("none", "None"), ("grey", "Greyscale"),
                            ("blue", "Blue")):
            ttk.Radiobutton(row, text=text, variable=self.lake_fill_var,
                            value=value,
                            command=self.app.on_lake_fill).pack(side="left",
                                                                padx=(0, 8))
        self._layer_rows(sec, WATER_ROWS)

        sec = self._section(tab, "Physical features")
        self._layer_rows(sec, PHYSICAL_ROWS)

        sec = self._section(tab, "Culture & infrastructure")
        self._layer_rows(sec, CULTURE_ROWS)

        sec = self._section(tab, "Biodiversity & ecoregions")
        self._layer_rows(sec, BIODIVERSITY_ROWS)

        sec = self._section(tab, "Lines")
        row = ttk.Frame(sec)
        row.pack(fill="x")
        ttk.Label(row, text="Line thickness:").pack(side="left")
        self._lw_label = ttk.Label(row, text="1.0")
        self._lw_label.pack(side="right")
        self.line_width_var = tk.DoubleVar(value=1.0)
        ttk.Scale(sec, from_=0.25, to=3.0, orient="horizontal",
                  variable=self.line_width_var,
                  command=self._on_lw_scale).pack(fill="x")

    # ---------------------------------------------------------- labels tab

    def _build_labels_tab(self, tab) -> None:
        sec = self._section(tab, "Labels")
        for key, text in LABEL_ROWS:
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(sec, text=text, variable=var,
                            command=lambda k=key: self.app.on_label(k)).pack(
                anchor="w")
            self.label_vars[key] = var
        ttk.Separator(sec, orient="horizontal").pack(fill="x", pady=4)
        self.label_drag_var = tk.BooleanVar(value=False)
        self._check(sec, "Allow dragging labels",
                    self.label_drag_var, self.app.on_label_drag_toggle)
        ttk.Label(
            sec, text="Drag any label to reposition it; right-click to "
            "snap it back.",
            wraplength=PANEL_WIDTH - 60,
            foreground="#666666").pack(anchor="w")
