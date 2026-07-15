"""Tabbed side panel holding every map control.

With ~30 layer toggles the panel is organized as a notebook of four
scrollable tabs - Data (CSV, styling, legend), Map (view, projection,
graticule, compass, export), Layers (every Natural Earth layer, grouped),
and Labels. The panel owns the Tk variables and forwards changes to the
app's handler methods; the app owns the renderer and the data.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from pymappr import projects
from pymappr.layers import CONTINENT_EXTENTS
from pymappr.projections import (PROJECTIONS, is_lambert,
                                 lambert_default_origin)

PANEL_WIDTH = 320

GRATICULE_CHOICES = {"Off": None, "1\N{DEGREE SIGN}": 1.0,
                     "5\N{DEGREE SIGN}": 5.0, "10\N{DEGREE SIGN}": 10.0}
KOFI_URL = "https://ko-fi.com/calebhendren"
LEGEND_LOCATIONS = ["best", "upper right", "upper left", "lower left",
                    "lower right", "center right"]
DPI_CHOICES = ["100", "150", "200", "300"]

# Gate for the experimental (dev-only) features. Deliberately a plain
# constant: anyone reading the source is qualified to flip the switch.
EXPERIMENTAL_PASSWORD = "admin"

# Layer toggles, grouped by panel section. Each row is (key, text, kind)
# where kind picks the renderer call: "line" (vector outlines), "fill"
# (filled polygons), "point" (markers), or a special handler.
BOUNDARY_ROWS = [
    ("countries", "Countries", "line"),
    ("states", "States/Provinces", "line"),
    ("counties", "US Counties", "line"),
    ("sovereignty", "Sovereign states", "line"),
    ("map_units", "Map units", "line"),
    ("subunits", "Map subunits", "line"),
    ("dependencies", "Dependencies", "line"),
    ("disputed", "Disputed areas", "fill"),
    ("disputed_lines", "Disputed boundaries", "line"),
    ("timezones", "Time zones", "line"),
]
WATER_ROWS = [
    ("rivers", "Rivers", "line"),
    ("wadis", "Wadis / intermittent rivers", "line"),
    ("maritime", "Maritime boundaries", "line"),
    ("eez", "EEZ / 200 nm limits", "line"),
    ("reefs", "Reefs", "line"),
]
PHYSICAL_ROWS = [
    ("land", "Land polygons (fill)", "fill"),
    ("glaciers", "Glaciers", "fill"),
    ("ice_shelves", "Antarctic ice shelves", "fill"),
    ("playas", "Playas", "fill"),
    ("deserts", "Deserts", "fill"),
    ("regions", "Geographic regions", "line"),
]
CULTURE_ROWS = [
    ("urban", "Urban areas", "fill"),
    ("airports", "Airports", "point"),
    ("ports", "Ports", "point"),
    ("parks", "Parks & protected areas", "fill"),
    ("roads", "Roads", "line"),
]
BIODIVERSITY_ROWS = [
    ("biodiversity", "Biodiversity hotspots", "fill"),
    ("ecoregions", "Terrestrial ecoregions", "fill"),
    ("marine_ecoregions", "Marine ecoregions", "fill"),
]
LABEL_ROWS = [
    ("countries", "Countries"),
    ("states", "States/Provinces"),
    ("counties", "US Counties"),
    ("cities", "Major cities"),
    ("airports", "Airports"),
    ("ports", "Ports"),
    ("lakes", "Lakes"),
    ("rivers", "Rivers"),
    ("regions", "Geographic regions"),
    ("timezones", "Time zones"),
]


class ControlPanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.layer_vars: dict[str, tk.BooleanVar] = {}
        self.fill_vars: dict[str, tk.BooleanVar] = {}
        self.point_vars: dict[str, tk.BooleanVar] = {}
        self.label_vars: dict[str, tk.BooleanVar] = {}

        self.notebook = ttk.Notebook(self, width=PANEL_WIDTH)
        # The experimental bar packs to the bottom edge first so the
        # notebook fills whatever height remains above it.
        self._build_experimental_bar()
        self.notebook.pack(fill="both", expand=True)

        data_tab = self._scroll_tab("Data")
        map_tab = self._scroll_tab("Map")
        layers_tab = self._scroll_tab("Layers")
        labels_tab = self._scroll_tab("Labels")

        self._build_data_section(data_tab)
        self._build_legend_section(data_tab)
        self._build_support_section(data_tab)

        self._build_view_section(map_tab)
        self._build_graticule_section(map_tab)
        self._build_export_section(map_tab)

        self._build_layers_tab(layers_tab)
        self._build_labels_tab(labels_tab)

    # ---------------------------------------------------------------- tabs

    def _scroll_tab(self, title: str) -> ttk.Frame:
        """Add a notebook tab wrapping a vertically scrollable frame."""
        outer = ttk.Frame(self.notebook)
        self.notebook.add(outer, text=title)
        canvas = tk.Canvas(outer, width=PANEL_WIDTH, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw",
                             width=PANEL_WIDTH - 18)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._bind_mousewheel(canvas)
        return inner

    def _section(self, parent, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=(8, 4))
        frame.pack(fill="x", padx=6, pady=4)
        return frame

    def _combo_row(self, parent, label: str, var: tk.StringVar,
                   values, command, width: int = 14) -> ttk.Combobox:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        box = ttk.Combobox(row, textvariable=var, state="readonly",
                           values=list(values), width=width)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda _e: command())
        return box

    def _check(self, parent, text: str, var: tk.BooleanVar, command) -> None:
        ttk.Checkbutton(parent, text=text, variable=var,
                        command=command).pack(anchor="w")

    # ------------------------------------------------------------ data tab

    def _build_data_section(self, tab) -> None:
        sec = self._section(tab, "Datasets")
        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Add data file\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_add_file).pack(
            side="left", fill="x", expand=True)
        ttk.Button(row, text="Manual entry\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_manual_entry).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

        list_frame = ttk.Frame(sec)
        list_frame.pack(fill="x", pady=2)
        self.dataset_list = tk.Listbox(list_frame, height=5,
                                       exportselection=False,
                                       activestyle="dotbox")
        scroll = ttk.Scrollbar(list_frame, orient="vertical",
                               command=self.dataset_list.yview)
        self.dataset_list.configure(yscrollcommand=scroll.set)
        self.dataset_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.dataset_list.bind(
            "<<ListboxSelect>>",
            lambda _e: self.app.on_select_dataset(self.selected_dataset()))

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Edit\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_edit_dataset).pack(
            side="left", fill="x", expand=True)
        ttk.Button(row, text="Remove",
                   command=self.app.on_remove_dataset).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

        self.dataset_visible_var = tk.BooleanVar(value=True)
        self._check(sec, "Show this dataset on the map",
                    self.dataset_visible_var, self.app.on_dataset_visible)

        self.file_label = ttk.Label(sec, text="No data loaded",
                                    wraplength=PANEL_WIDTH - 60,
                                    foreground="#666666")
        self.file_label.pack(anchor="w", pady=(0, 4))

        sec = self._section(tab, "Styling (selected dataset)")
        self.group_by_var = tk.StringVar(value="None")
        self.group_by_box = self._combo_row(
            sec, "Group by:", self.group_by_var, ["None"],
            self.app.on_group_by, width=18)

        # Color by: groups sharing a value in this column share a color
        # while their symbols vary - e.g. group by Animal, color by Family
        # keeps all felines one color and all canines another.
        self.color_by_var = tk.StringVar(value="None")
        self.color_by_box = self._combo_row(
            sec, "Color by:", self.color_by_var, ["None"],
            self.app.on_style_scheme, width=18)

        # Symbol by: encode a second column as marker shape. Combined with
        # Color by this styles two levels of a hierarchy at once (e.g. color
        # by Order, symbol by Family) and switches the legend to a compact
        # color + symbol key instead of one row per group.
        self.symbol_by_var = tk.StringVar(value="None")
        self.symbol_by_box = self._combo_row(
            sec, "Symbol by:", self.symbol_by_var, ["None"],
            self.app.on_style_scheme, width=18)
        ttk.Label(sec, text="(Symbol by = compact color/symbol legend)",
                  foreground="#666666").pack(anchor="w")

        self.vary_symbols_var = tk.BooleanVar(value=False)
        self._check(sec, "Vary symbols per group", self.vary_symbols_var,
                    self.app.on_style_scheme)

        ttk.Label(sec, text="Point opacity:").pack(anchor="w", pady=(6, 0))
        self.point_alpha_var = tk.DoubleVar(value=1.0)
        tk.Scale(sec, from_=0.1, to=1.0, orient="horizontal",
                 variable=self.point_alpha_var, showvalue=True,
                 resolution=0.05,
                 command=lambda _v: self.app.on_point_alpha()).pack(fill="x")

    def _build_legend_section(self, tab) -> None:
        sec = self._section(tab, "Legend")
        self.legend_show_var = tk.BooleanVar(value=True)
        self._check(sec, "Show legend", self.legend_show_var,
                    self.app.on_legend_options)
        self.legend_frame_var = tk.BooleanVar(value=True)
        self._check(sec, "Draw legend frame", self.legend_frame_var,
                    self.app.on_legend_options)

        self.legend_loc_var = tk.StringVar(value="best")
        self._combo_row(sec, "Position:", self.legend_loc_var,
                        LEGEND_LOCATIONS, self.app.on_legend_options,
                        width=12)

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Font size:").pack(side="left")
        self.legend_fontsize_var = tk.StringVar(value="8")
        spin = ttk.Spinbox(row, from_=5, to=20, increment=1, width=5,
                           textvariable=self.legend_fontsize_var,
                           command=self.app.on_legend_options)
        spin.pack(side="right")
        spin.bind("<KeyRelease>", lambda _e: self.app.on_legend_options())

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Title font size:").pack(side="left")
        self.legend_title_fontsize_var = tk.StringVar(value="9")
        spin = ttk.Spinbox(row, from_=5, to=24, increment=1, width=5,
                           textvariable=self.legend_title_fontsize_var,
                           command=self.app.on_legend_options)
        spin.pack(side="right")
        spin.bind("<KeyRelease>", lambda _e: self.app.on_legend_options())

        # Marker size scales the sample symbols shown in the legend
        # (markerscale), independent of the point sizes on the map.
        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Marker size:").pack(side="left")
        self.legend_marker_scale_var = tk.StringVar(value="1.0")
        spin = ttk.Spinbox(row, from_=0.5, to=4.0, increment=0.25, width=5,
                           textvariable=self.legend_marker_scale_var,
                           command=self.app.on_legend_options)
        spin.pack(side="right")
        spin.bind("<KeyRelease>", lambda _e: self.app.on_legend_options())

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Row spacing:").pack(side="left")
        self.legend_label_spacing_var = tk.StringVar(value="0.5")
        spin = ttk.Spinbox(row, from_=0.2, to=2.0, increment=0.1, width=5,
                           textvariable=self.legend_label_spacing_var,
                           command=self.app.on_legend_options)
        spin.pack(side="right")
        spin.bind("<KeyRelease>", lambda _e: self.app.on_legend_options())

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Columns:").pack(side="left")
        self.legend_columns_var = tk.StringVar(value="1")
        spin = ttk.Spinbox(row, from_=1, to=6, increment=1, width=5,
                           textvariable=self.legend_columns_var,
                           command=self.app.on_legend_options)
        spin.pack(side="right")
        spin.bind("<KeyRelease>", lambda _e: self.app.on_legend_options())

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Title:").pack(side="left")
        self.legend_title_var = tk.StringVar(value="")
        entry = ttk.Entry(row, textvariable=self.legend_title_var, width=18)
        entry.pack(side="right")
        entry.bind("<KeyRelease>", lambda _e: self.app.on_legend_options())
        ttk.Label(sec, text="(blank = use the Group by column name)",
                  foreground="#666666").pack(anchor="w")

        ttk.Button(sec, text="Customize legend\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_edit_styles).pack(fill="x", pady=2)

    def _build_support_section(self, tab) -> None:
        sec = self._section(tab, "Support Me")
        ttk.Label(sec, text="Enjoying PyMappr? Support development:",
                  wraplength=PANEL_WIDTH - 60).pack(anchor="w")
        ttk.Button(sec, text="\N{BLACK HEART SUIT} Support on Ko-fi",
                   command=self._open_kofi).pack(fill="x", pady=2)
        ttk.Button(sec, text="Check for updates\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_check_updates).pack(fill="x", pady=2)

    def _open_kofi(self) -> None:
        import webbrowser

        webbrowser.open(KOFI_URL)

    # ------------------------------------------------------------- map tab

    def _build_view_section(self, tab) -> None:
        sec = self._section(tab, "View")
        self.continent_var = tk.StringVar(value="World")
        self._combo_row(sec, "Limit to:", self.continent_var,
                        CONTINENT_EXTENTS, self.app.on_continent, width=16)

        self.projection_var = tk.StringVar(value="Equirectangular")
        self._combo_row(sec, "Projection:", self.projection_var,
                        PROJECTIONS, self.app.on_projection, width=16)

        # Point of natural origin for the Lambert projections: enabled only
        # while a Lambert projection is selected.
        self.proj_lon0_var = tk.StringVar(value="")
        self.proj_lat0_var = tk.StringVar(value="")
        self.origin_frame = ttk.Frame(sec)
        self.origin_frame.pack(fill="x", pady=(2, 0))
        self.origin_spins: list[ttk.Spinbox] = []
        for label, var, lo, hi in (("Center lon:", self.proj_lon0_var,
                                    -180, 180),
                                   ("Center lat:", self.proj_lat0_var,
                                    -90, 90)):
            row = ttk.Frame(self.origin_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label).pack(side="left")
            spin = ttk.Spinbox(row, from_=lo, to=hi, increment=5, width=8,
                               textvariable=var,
                               command=self.app.on_projection_origin)
            spin.pack(side="right")
            spin.bind("<Return>", lambda _e: self.app.on_projection_origin())
            spin.bind("<FocusOut>", lambda _e: self.app.on_projection_origin())
            self.origin_spins.append(spin)
        self.origin_hint = ttk.Label(
            self.origin_frame,
            text="Point of natural origin (Lambert projections).",
            wraplength=PANEL_WIDTH - 60, foreground="#666666")
        self.origin_hint.pack(anchor="w")
        self.update_projection_origin(self.projection_var.get(), reset=True)

        ttk.Label(sec, text="Basemap:").pack(anchor="w", pady=(4, 0))
        self.basemap_var = tk.StringVar(value="simple")
        ttk.Radiobutton(sec, text="Simple (white with borders)",
                        variable=self.basemap_var, value="simple",
                        command=self.app.on_basemap).pack(anchor="w")
        ttk.Radiobutton(sec, text="Satellite (full color, slower)",
                        variable=self.basemap_var, value="satellite",
                        command=self.app.on_basemap).pack(anchor="w")

        self.compass_var = tk.BooleanVar(value=False)
        ttk.Separator(sec, orient="horizontal").pack(fill="x", pady=4)
        self._check(sec, "Show compass (north arrow)", self.compass_var,
                    self.app.on_compass)

    def _build_graticule_section(self, tab) -> None:
        sec = self._section(tab, "Graticule (grid)")
        self.graticule_var = tk.StringVar(value="Off")
        self._combo_row(sec, "Grid spacing:", self.graticule_var,
                        GRATICULE_CHOICES, self.app.on_graticule, width=8)
        self.hide_grid_labels_var = tk.BooleanVar(value=False)
        self._check(sec, "Hide grid labels", self.hide_grid_labels_var,
                    self.app.on_graticule)

    def _build_export_section(self, tab) -> None:
        sec = self._section(tab, "Export")
        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Resolution (DPI):").pack(side="left")
        self.dpi_var = tk.StringVar(value="200")
        ttk.Combobox(row, textvariable=self.dpi_var, state="readonly",
                     values=DPI_CHOICES, width=6).pack(side="right")
        ttk.Button(sec, text="Save map as PNG\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_save_png).pack(fill="x", pady=2)
        ttk.Button(sec, text="Export as code (Python/R)"
                            "\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_export_code).pack(fill="x", pady=2)
        ttk.Label(sec, text="(a ready-to-run script that recreates this "
                            "map in an IDE)",
                  foreground="#666666",
                  wraplength=PANEL_WIDTH - 60).pack(anchor="w")

    # ---------------------------------------------------------- layers tab

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
        ttk.Label(sec, text="Optional overlays (Conservation International, "
                  "RESOLVE, WWF/TNC). Run fetch_data.py to download them.",
                  wraplength=PANEL_WIDTH - 60,
                  foreground="#666666").pack(anchor="w")

        sec = self._section(tab, "Lines")
        ttk.Label(sec, text="Line thickness:").pack(anchor="w")
        self.line_width_var = tk.DoubleVar(value=1.0)
        tk.Scale(sec, from_=0.25, to=3.0, orient="horizontal",
                 variable=self.line_width_var, showvalue=True,
                 resolution=0.25,
                 command=lambda _v: self.app.on_line_width()).pack(fill="x")

    # ---------------------------------------------------------- labels tab

    def _build_labels_tab(self, tab) -> None:
        sec = self._section(tab, "Labels")
        for key, text in LABEL_ROWS:
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(sec, text=text, variable=var,
                            command=lambda k=key: self.app.on_label(k)).pack(
                anchor="w")
            self.label_vars[key] = var
        ttk.Label(
            sec, text="Labels are scale-dependent: more appear as you zoom "
            "in, and overlapping labels are hidden automatically. Drag any "
            "label to reposition it; right-click to snap it back.",
            wraplength=PANEL_WIDTH - 60,
            foreground="#666666").pack(anchor="w", pady=(6, 0))

    # -------------------------------------------- experimental (dev only)

    def _build_experimental_bar(self) -> None:
        """A quiet toggle at the very bottom of the panel. The features
        behind it are intentionally absent from the normal UI and the
        README; the password is asked once and the state persists."""
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=6, pady=(2, 4))
        self.experimental_var = tk.BooleanVar(
            value=bool(projects.load_settings().get(
                "experimental_enabled")))
        ttk.Checkbutton(bar, text="Enable experimental features "
                                  "(dev only)",
                        variable=self.experimental_var,
                        command=self._on_experimental_toggle).pack(
            anchor="w")
        self._llm_button = ttk.Button(
            bar, text="LLM Assist\N{HORIZONTAL ELLIPSIS}",
            command=self._open_llm_assist)
        self._sync_experimental_bar()

    def _sync_experimental_bar(self) -> None:
        if self.experimental_var.get():
            self._llm_button.pack(fill="x", pady=(2, 0))
        else:
            self._llm_button.pack_forget()

    def _on_experimental_toggle(self) -> None:
        if self.experimental_var.get():
            password = simpledialog.askstring(
                "Experimental features",
                "Experimental features are unsupported and may change "
                "or break at any time.\n\nPassword:",
                show="*", parent=self)
            if password != EXPERIMENTAL_PASSWORD:
                self.experimental_var.set(False)
                if password is not None:
                    messagebox.showerror("Experimental features",
                                         "Wrong password.", parent=self)
        settings = projects.load_settings()
        settings["experimental_enabled"] = self.experimental_var.get()
        projects.save_settings(settings)
        self._sync_experimental_bar()

    def _open_llm_assist(self) -> None:
        from pymappr.ui.llm_assist import LLMAssistDialog

        LLMAssistDialog(self.app.root, self.app)

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

    def update_projection_origin(self, name: str, reset: bool = False) -> None:
        """Enable the origin spinboxes for Lambert projections (seeding the
        preset default when *reset*) and disable them otherwise."""
        if is_lambert(name):
            if reset or not self.proj_lon0_var.get().strip():
                lon0, lat0 = lambert_default_origin(name)
                self.proj_lon0_var.set(f"{lon0:g}")
                self.proj_lat0_var.set(f"{lat0:g}")
            state = "normal"
            self.origin_hint.configure(foreground="#666666")
        else:
            state = "disabled"
            self.origin_hint.configure(foreground="#999999")
        for spin in self.origin_spins:
            spin.configure(state=state)

    def projection_origin(self) -> tuple[float | None, float | None]:
        """The (lon_0, lat_0) origin for a Lambert projection, or (None, None)
        for any other projection or unparseable input (uses the default)."""
        if not is_lambert(self.projection_var.get()):
            return None, None

        def _num(var):
            try:
                return float(var.get())
            except (TypeError, ValueError):
                return None

        return _num(self.proj_lon0_var), _num(self.proj_lat0_var)

    def graticule_interval(self) -> float | None:
        return GRATICULE_CHOICES[self.graticule_var.get()]

    def legend_fontsize(self) -> float:
        try:
            return max(min(float(self.legend_fontsize_var.get()), 32.0), 4.0)
        except ValueError:
            return 8.0

    def legend_title_fontsize(self) -> float:
        try:
            return max(min(float(self.legend_title_fontsize_var.get()),
                           40.0), 4.0)
        except ValueError:
            return 9.0

    def legend_marker_scale(self) -> float:
        try:
            return max(min(float(self.legend_marker_scale_var.get()), 6.0),
                       0.2)
        except ValueError:
            return 1.0

    def legend_label_spacing(self) -> float:
        try:
            return max(min(float(self.legend_label_spacing_var.get()), 4.0),
                       0.0)
        except ValueError:
            return 0.5

    def legend_columns(self) -> int:
        try:
            return max(min(int(self.legend_columns_var.get()), 6), 1)
        except ValueError:
            return 1

    def set_dataset_list(self, rows: list[tuple[str, bool]],
                         active: int | None) -> None:
        """Rebuild the dataset list: *rows* is (name, visible) per dataset."""
        self.dataset_list.delete(0, "end")
        for name, visible in rows:
            mark = ("\N{BALLOT BOX WITH CHECK}" if visible
                    else "\N{BALLOT BOX}")
            self.dataset_list.insert("end", f"{mark} {name}")
        if active is not None and 0 <= active < len(rows):
            self.dataset_list.selection_set(active)
            self.dataset_list.see(active)
            self.dataset_visible_var.set(rows[active][1])

    def selected_dataset(self) -> int | None:
        selection = self.dataset_list.curselection()
        return int(selection[0]) if selection else None

    def set_dataset_controls(self, choices: list[str], group_by: str,
                             color_by: str, symbol_by: str,
                             vary_symbols: bool) -> None:
        """Point the styling controls at the selected dataset's settings
        (no change callbacks fire; combos only fire on user selection)."""
        for box, var, value in ((self.group_by_box, self.group_by_var,
                                 group_by),
                                (self.color_by_box, self.color_by_var,
                                 color_by),
                                (self.symbol_by_box, self.symbol_by_var,
                                 symbol_by)):
            box.configure(values=choices)
            var.set(value if value in choices else "None")
        self.vary_symbols_var.set(vary_symbols)

    def set_file_info(self, text: str) -> None:
        color = "#666666" if text == "No data loaded" else "#333333"
        self.file_label.config(text=text, foreground=color)
