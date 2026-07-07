"""Scrollable side panel holding every map control.

The panel owns the Tk variables and forwards changes to the app's handler
methods; the app owns the renderer and the data.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ezmaps.layers import CONTINENT_EXTENTS

PANEL_WIDTH = 300

GRATICULE_CHOICES = {"Off": None, "1\N{DEGREE SIGN}": 1.0,
                     "5\N{DEGREE SIGN}": 5.0, "10\N{DEGREE SIGN}": 10.0}
HEATMAP_CMAPS = ["hot", "viridis", "plasma", "inferno", "magma", "cividis",
                 "cool", "spring", "summer", "autumn", "winter", "turbo",
                 "jet", "YlOrRd", "YlGnBu", "RdPu", "Reds", "Blues",
                 "Greens", "Purples"]
HEATMAP_LEVELS = ["Continuous", "3", "4", "5", "6", "7", "8", "9"]
PATREON_URL = "https://www.patreon.com/cw/CalebHendren"
LEGEND_LOCATIONS = ["best", "upper right", "upper left", "lower left",
                    "lower right", "center right"]
DPI_CHOICES = ["100", "150", "200", "300"]

LAYER_ROWS = [
    ("countries", "Countries"),
    ("states", "States/Provinces"),
    ("counties", "US Counties"),
    ("lakes_outline", "Lakes (outlines)"),
    ("rivers", "Rivers"),
    ("roads", "Roads"),
]
LABEL_ROWS = [
    ("countries", "Countries"),
    ("states", "States/Provinces"),
    ("counties", "US Counties"),
    ("lakes", "Lakes"),
    ("rivers", "Rivers"),
]


class ControlPanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        canvas = tk.Canvas(self, width=PANEL_WIDTH, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        self.inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner, anchor="nw",
                             width=PANEL_WIDTH)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._bind_mousewheel(canvas)

        self._build_data_section()
        self._build_view_section()
        self._build_layers_section()
        self._build_labels_section()
        self._build_graticule_section()
        self._build_heatmap_section()
        self._build_export_section()
        self._build_support_section()

    # ------------------------------------------------------------- sections

    def _section(self, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self.inner, text=title, padding=(8, 4))
        frame.pack(fill="x", padx=6, pady=4)
        return frame

    def _build_data_section(self) -> None:
        sec = self._section("Data")
        ttk.Button(sec, text="Open CSV\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_open_csv).pack(fill="x", pady=2)
        self.file_label = ttk.Label(sec, text="No data loaded",
                                    wraplength=PANEL_WIDTH - 40,
                                    foreground="#666666")
        self.file_label.pack(anchor="w", pady=(0, 4))

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Group by:").pack(side="left")
        self.group_by_var = tk.StringVar(value="None")
        self.group_by_box = ttk.Combobox(
            row, textvariable=self.group_by_var, state="readonly",
            values=["None"], width=18)
        self.group_by_box.pack(side="right")
        self.group_by_box.bind("<<ComboboxSelected>>",
                               lambda _e: self.app.on_group_by())

        self.legend_show_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(sec, text="Show legend",
                        variable=self.legend_show_var,
                        command=self.app.on_legend_options).pack(anchor="w")
        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Legend position:").pack(side="left")
        self.legend_loc_var = tk.StringVar(value="best")
        box = ttk.Combobox(row, textvariable=self.legend_loc_var,
                           state="readonly", values=LEGEND_LOCATIONS,
                           width=12)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>",
                 lambda _e: self.app.on_legend_options())
        ttk.Button(sec, text="Customize legend\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_edit_styles).pack(fill="x", pady=2)

    def _build_view_section(self) -> None:
        sec = self._section("View")
        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Limit to:").pack(side="left")
        self.continent_var = tk.StringVar(value="World")
        box = ttk.Combobox(row, textvariable=self.continent_var,
                           state="readonly",
                           values=list(CONTINENT_EXTENTS), width=16)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda _e: self.app.on_continent())

        ttk.Label(sec, text="Basemap:").pack(anchor="w", pady=(4, 0))
        self.basemap_var = tk.StringVar(value="simple")
        ttk.Radiobutton(sec, text="Simple (black country borders)",
                        variable=self.basemap_var, value="simple",
                        command=self.app.on_basemap).pack(anchor="w")
        ttk.Radiobutton(sec, text="Satellite (full color)",
                        variable=self.basemap_var, value="satellite",
                        command=self.app.on_basemap).pack(anchor="w")

    def _build_layers_section(self) -> None:
        sec = self._section("Layers")
        self.layer_vars: dict[str, tk.BooleanVar] = {}
        for key, text in LAYER_ROWS:
            var = tk.BooleanVar(value=key == "countries")
            ttk.Checkbutton(sec, text=text, variable=var,
                            command=lambda k=key: self.app.on_layer(k)).pack(
                anchor="w")
            self.layer_vars[key] = var

        ttk.Label(sec, text="Lakes fill:").pack(anchor="w", pady=(6, 0))
        self.lake_fill_var = tk.StringVar(value="none")
        row = ttk.Frame(sec)
        row.pack(fill="x")
        for value, text in (("none", "None"), ("grey", "Greyscale"),
                            ("blue", "Blue")):
            ttk.Radiobutton(row, text=text, variable=self.lake_fill_var,
                            value=value,
                            command=self.app.on_lake_fill).pack(side="left",
                                                                padx=(0, 8))

        ttk.Label(sec, text="Oceans:").pack(anchor="w", pady=(6, 0))
        self.ocean_var = tk.StringVar(value="none")
        row = ttk.Frame(sec)
        row.pack(fill="x")
        for value, text in (("none", "None"), ("grey", "Greyscale"),
                            ("blue", "Blue")):
            ttk.Radiobutton(row, text=text, variable=self.ocean_var,
                            value=value,
                            command=self.app.on_ocean).pack(side="left",
                                                            padx=(0, 8))

    def _build_labels_section(self) -> None:
        sec = self._section("Labels")
        self.label_vars: dict[str, tk.BooleanVar] = {}
        for key, text in LABEL_ROWS:
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(sec, text=text, variable=var,
                            command=lambda k=key: self.app.on_label(k)).pack(
                anchor="w")
            self.label_vars[key] = var

    def _build_graticule_section(self) -> None:
        sec = self._section("Graticule (grid)")
        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Grid spacing:").pack(side="left")
        self.graticule_var = tk.StringVar(value="Off")
        box = ttk.Combobox(row, textvariable=self.graticule_var,
                           state="readonly",
                           values=list(GRATICULE_CHOICES), width=8)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda _e: self.app.on_graticule())
        self.hide_grid_labels_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec, text="Hide grid labels",
                        variable=self.hide_grid_labels_var,
                        command=self.app.on_graticule).pack(anchor="w")

    def _build_heatmap_section(self) -> None:
        sec = self._section("Heatmap")
        self.heatmap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec, text="Show as heatmap",
                        variable=self.heatmap_var,
                        command=self.app.on_heatmap).pack(anchor="w")
        self.heatmap_points_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec, text="Show data points on top",
                        variable=self.heatmap_points_var,
                        command=self.app.on_heatmap).pack(anchor="w")
        self.heatmap_bloom_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sec, text="Bloom (soft outer glow)",
                        variable=self.heatmap_bloom_var,
                        command=self.app.on_heatmap).pack(anchor="w")

        def scale(label: str, var, lo, hi, resolution=1.0):
            ttk.Label(sec, text=label).pack(anchor="w", pady=(4, 0))
            tk.Scale(sec, from_=lo, to=hi, orient="horizontal", variable=var,
                     showvalue=True, resolution=resolution,
                     command=lambda _v: self.app.on_heatmap()).pack(fill="x")

        self.heatmap_radius_var = tk.DoubleVar(value=10.0)
        scale("Radius / bandwidth:", self.heatmap_radius_var, 2, 40)

        self.heatmap_blur_var = tk.DoubleVar(value=0.0)
        scale("Blur / smoothing:", self.heatmap_blur_var, 0, 20)

        self.heatmap_intensity_var = tk.DoubleVar(value=1.0)
        scale("Intensity / weight:", self.heatmap_intensity_var,
              0.2, 3.0, resolution=0.1)

        self.heatmap_threshold_var = tk.DoubleVar(value=0.0)
        scale("Threshold (% of peak):", self.heatmap_threshold_var, 0, 90)

        self.heatmap_opacity_var = tk.DoubleVar(value=70.0)
        scale("Opacity (%):", self.heatmap_opacity_var, 10, 100)

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Color palette:").pack(side="left")
        self.heatmap_cmap_var = tk.StringVar(value="hot")
        box = ttk.Combobox(row, textvariable=self.heatmap_cmap_var,
                           state="readonly", values=HEATMAP_CMAPS, width=10)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda _e: self.app.on_heatmap())

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Classes:").pack(side="left")
        self.heatmap_levels_var = tk.StringVar(value="Continuous")
        box = ttk.Combobox(row, textvariable=self.heatmap_levels_var,
                           state="readonly", values=HEATMAP_LEVELS, width=10)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda _e: self.app.on_heatmap())

    def heatmap_levels(self) -> int:
        """Selected number of classification levels; 0 = continuous."""
        value = self.heatmap_levels_var.get()
        return 0 if value == "Continuous" else int(value)

    def _build_export_section(self) -> None:
        sec = self._section("Export")
        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Resolution (DPI):").pack(side="left")
        self.dpi_var = tk.StringVar(value="200")
        ttk.Combobox(row, textvariable=self.dpi_var, state="readonly",
                     values=DPI_CHOICES, width=6).pack(side="right")
        ttk.Button(sec, text="Save map as PNG\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_save_png).pack(fill="x", pady=2)

    def _build_support_section(self) -> None:
        sec = self._section("Support Me")
        ttk.Label(sec, text="Enjoying EzMaps? Support development:",
                  wraplength=PANEL_WIDTH - 40).pack(anchor="w")
        ttk.Button(sec, text="\N{BLACK HEART SUIT} Support on Patreon",
                   command=self._open_patreon).pack(fill="x", pady=2)

    def _open_patreon(self) -> None:
        import webbrowser

        webbrowser.open(PATREON_URL)

    # -------------------------------------------------------------- helpers

    def _bind_mousewheel(self, canvas: tk.Canvas) -> None:
        def on_wheel(event):
            delta = -1 if (event.num == 4 or event.delta > 0) else 1
            canvas.yview_scroll(delta, "units")

        def bind_all(_e):
            canvas.bind_all("<MouseWheel>", on_wheel)
            canvas.bind_all("<Button-4>", on_wheel)
            canvas.bind_all("<Button-5>", on_wheel)

        def unbind_all(_e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", bind_all)
        canvas.bind("<Leave>", unbind_all)

    def graticule_interval(self) -> float | None:
        return GRATICULE_CHOICES[self.graticule_var.get()]

    def set_group_by_choices(self, choices: list[str], selected: str) -> None:
        self.group_by_box.configure(values=choices)
        self.group_by_var.set(selected)

    def set_file_info(self, text: str) -> None:
        self.file_label.config(text=text, foreground="#333333")
