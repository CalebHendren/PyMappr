"""The Map tab: view and projection, the compass and scale bar, the
inset map, the graticule and export."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pymappr.geo.layers import CONTINENT_EXTENTS
from pymappr.geo.projections import PROJECTIONS
from pymappr.styling.decorations import CORNERS, InsetOptions
from pymappr.ui.control_panel.tables import (COMPASS_STYLE_LABELS,
                                             GRATICULE_CHOICES,
                                             INSET_OCEAN_LABELS,
                                             INSET_PROJECTION_LABELS,
                                             INSET_REGION_LABELS,
                                             ORIENTATION_LABELS, PANEL_WIDTH,
                                             SCALE_LENGTH_LABELS,
                                             SCALE_STYLE_LABELS,
                                             SCALE_UNIT_LABELS, name_for)
from pymappr.ui.save_image import AS_ON_SCREEN


class MapTabMixin:
    """Builds the Map tab, and reads and sets the inset's options."""

    def _build_view_section(self, tab) -> None:
        sec = self._section(tab, "View")
        self.continent_var = tk.StringVar(value="World")
        self._combo_row(sec, "Limit to:", self.continent_var,
                        CONTINENT_EXTENTS, self.app.on_continent, width=16)

        # Landscape fills the canvas; portrait frames tall regions (e.g.
        # South America) in a narrow box instead of a band of ocean.
        self.orientation_var = tk.StringVar(value="Landscape")
        self._combo_row(sec, "Orientation:", self.orientation_var,
                        list(ORIENTATION_LABELS), self.app.on_orientation,
                        width=16)

        self.projection_var = tk.StringVar(value="Equirectangular")
        self._combo_row(sec, "Projection:", self.projection_var,
                        PROJECTIONS, self.app.on_projection, width=16)

        # Map centre for the Globe and point of natural origin for the
        # Lambert projections: enabled only while one of those is selected.
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
            text="Map centre (Globe and Lambert projections).",
            wraplength=PANEL_WIDTH - 60, foreground="#666666")
        self.origin_hint.pack(anchor="w")
        self.update_projection_origin(self.projection_var.get(), reset=True)

        ttk.Label(sec, text="Basemap:").pack(anchor="w", pady=(4, 0))
        self.basemap_var = tk.StringVar(value="simple")
        for value, text in (("simple", "Simple (white with borders)"),
                            ("relief", "Relief"),
                            ("relief_alt", "Relief (alternate)"),
                            ("relief_grey", "Relief (greyscale)"),
                            ("blue_marble", "Blue Marble")):
            ttk.Radiobutton(sec, text=text, variable=self.basemap_var,
                            value=value,
                            command=self.app.on_basemap).pack(anchor="w")

    def _build_decorations_section(self, tab) -> None:
        """The compass and the scale bar: two small annotations pinned to a
        corner of the map, sharing a vocabulary of corners."""
        sec = self._section(tab, "Compass")
        self.compass_var = tk.BooleanVar(value=False)
        self._check(sec, "Show compass (north arrow)", self.compass_var,
                    self.app.on_compass)
        self.compass_position_var = tk.StringVar(value="upper right")
        self._combo_row(sec, "Position:", self.compass_position_var,
                        CORNERS, self.app.on_compass, width=12)
        self.compass_style_var = tk.StringVar(value="Arrow with N")
        self._named_combo(sec, "Style:", self.compass_style_var,
                          COMPASS_STYLE_LABELS, self.app.on_compass, width=14)
        self.compass_size_var = tk.StringVar(value="1.0")
        self._spin_row(sec, "Size:", self.compass_size_var, 0.5, 3.0, 0.1,
                       self.app.on_compass)

        sec = self._section(tab, "Scale bar")
        self.scale_bar_var = tk.BooleanVar(value=False)
        self._check(sec, "Show scale bar", self.scale_bar_var,
                    self.app.on_scale_bar)
        self.scale_units_var = tk.StringVar(value="Kilometres")
        self._named_combo(sec, "Units:", self.scale_units_var,
                          SCALE_UNIT_LABELS, self.app.on_scale_bar, width=12)
        self.scale_position_var = tk.StringVar(value="lower left")
        self._combo_row(sec, "Position:", self.scale_position_var,
                        CORNERS, self.app.on_scale_bar, width=12)
        self.scale_style_var = tk.StringVar(value="Segmented")
        self._named_combo(sec, "Style:", self.scale_style_var,
                          SCALE_STYLE_LABELS, self.app.on_scale_bar, width=12)
        self.scale_length_mode_var = tk.StringVar(value="Automatic")
        self._named_combo(sec, "Length:", self.scale_length_mode_var,
                          SCALE_LENGTH_LABELS, self.app.on_scale_bar,
                          width=12)
        self.scale_fixed_length_var = tk.StringVar(value="")
        self.scale_fixed_spin = self._spin_row(
            sec, "Fixed length:", self.scale_fixed_length_var, 0.1, 100000,
            10, self.app.on_scale_bar, width=8)
        self.scale_draggable_var = tk.BooleanVar(value=False)
        self._check(sec, "Drag to reposition", self.scale_draggable_var,
                    self.app.on_scale_bar)
        ttk.Button(sec, text="Reset position",
                   command=self.app.on_reset_scale_bar).pack(fill="x",
                                                             pady=(2, 0))
        ttk.Label(sec, text="On a world map the scale changes with latitude; "
                            "the bar is accurate where it stands.",
                  wraplength=PANEL_WIDTH - 60,
                  foreground="#666666").pack(anchor="w", pady=(2, 0))
        self.update_scale_length_state()

    def update_scale_length_state(self) -> None:
        """The fixed-length box only matters in Fixed mode."""
        fixed = SCALE_LENGTH_LABELS.get(
            self.scale_length_mode_var.get()) == "fixed"
        self.scale_fixed_spin.configure(
            state="normal" if fixed else "disabled")

    def _build_inset_section(self, tab) -> None:
        """A small second map in a corner: a locator showing where the map
        is, or a zoom on an area too small to see on it."""
        sec = self._section(tab, "Inset map")
        defaults = InsetOptions()
        self.inset_var = tk.BooleanVar(value=defaults.show)
        self._check(sec, "Show inset map", self.inset_var, self.app.on_inset)
        self.inset_region_var = tk.StringVar(
            value=name_for(INSET_REGION_LABELS, defaults.region))
        self._named_combo(sec, "Shows:", self.inset_region_var,
                          INSET_REGION_LABELS, self.app.on_inset, width=16)
        self.inset_zoom_out_var = tk.StringVar(value=f"{defaults.zoom_out:g}")
        self.inset_zoom_out_spin = self._spin_row(
            sec, "Times the map's area:", self.inset_zoom_out_var, 2, 50, 1,
            self.app.on_inset)
        # The custom area: typed in, or taken from the view - zoom in on the
        # area, click the button, and zoom back out.
        self.inset_extent_vars = [tk.StringVar() for _ in range(4)]
        self.inset_extent_spins = []
        for label, var, lo, hi in zip(
                ("West lon:", "East lon:", "South lat:", "North lat:"),
                self.inset_extent_vars, (-180, -180, -90, -90),
                (180, 180, 90, 90)):
            self.inset_extent_spins.append(self._spin_row(
                sec, label, var, lo, hi, 1, self.app.on_inset, width=8))
        self.inset_from_view_button = ttk.Button(
            sec, text="Use current view",
            command=self.app.on_inset_from_view)
        self.inset_from_view_button.pack(fill="x", pady=(2, 2))
        self.inset_projection_var = tk.StringVar(
            value=name_for(INSET_PROJECTION_LABELS, defaults.projection))
        self._named_combo(sec, "Projection:", self.inset_projection_var,
                          INSET_PROJECTION_LABELS, self.app.on_inset,
                          width=16)
        self.inset_position_var = tk.StringVar(value=defaults.position)
        self._combo_row(sec, "Position:", self.inset_position_var, CORNERS,
                        self.app.on_inset, width=12)
        self.inset_size_var = tk.StringVar(value=f"{defaults.size:g}")
        self._spin_row(sec, "Width (of map):", self.inset_size_var, 0.1,
                       0.6, 0.05, self.app.on_inset)
        self.inset_layer_vars = {}
        for field, text in (("countries", "Countries"),
                            ("states", "States/Provinces"),
                            ("counties", "US Counties"),
                            ("land", "Land fill"),
                            ("points", "Your points"),
                            ("box", "Box linking it to the map")):
            var = tk.BooleanVar(value=getattr(defaults, field))
            self.inset_layer_vars[field] = var
            self._check(sec, text, var, self.app.on_inset)
        self.inset_ocean_var = tk.StringVar(
            value=name_for(INSET_OCEAN_LABELS, defaults.ocean))
        self._named_combo(sec, "Ocean:", self.inset_ocean_var,
                          INSET_OCEAN_LABELS, self.app.on_inset, width=12)
        self.inset_box_color_var = tk.StringVar(value=defaults.box_color)
        self._color_row(sec, "Box colour:", self.inset_box_color_var,
                        self.app.on_inset)
        self.inset_draggable_var = tk.BooleanVar(value=defaults.draggable)
        self._check(sec, "Drag to reposition", self.inset_draggable_var,
                    self.app.on_inset)
        ttk.Button(sec, text="Reset position",
                   command=self.app.on_reset_inset).pack(fill="x",
                                                         pady=(2, 0))
        ttk.Label(sec, text="A wider area marks the map's view with the "
                            "box; a smaller one (Custom) is boxed on the "
                            "map instead.",
                  wraplength=PANEL_WIDTH - 60,
                  foreground="#666666").pack(anchor="w", pady=(2, 0))
        self.update_inset_state()

    def update_inset_state(self) -> None:
        """The zoom-out box only matters for Around the map, and the
        extent boxes only for Custom."""
        region = INSET_REGION_LABELS.get(self.inset_region_var.get())
        self.inset_zoom_out_spin.configure(
            state="normal" if region == "around" else "disabled")
        for spin in self.inset_extent_spins:
            spin.configure(state="normal" if region == "custom"
                           else "disabled")

    def inset_options(self, anchor=None) -> InsetOptions:
        """The inset as configured. *anchor* keeps a dragged position,
        which the panel itself has no widget for."""
        extent = [self._optional_number(var, lo, hi) for var, lo, hi in zip(
            self.inset_extent_vars, (-180, -180, -90, -90),
            (180, 180, 90, 90))]
        layers = {field: var.get()
                  for field, var in self.inset_layer_vars.items()}
        return InsetOptions(
            show=self.inset_var.get(),
            position=self.inset_position_var.get(),
            size=self._number(self.inset_size_var, 0.1, 0.6, 0.3),
            region=INSET_REGION_LABELS.get(self.inset_region_var.get(),
                                           "state"),
            zoom_out=self._number(self.inset_zoom_out_var, 2.0, 50.0, 6.0),
            lon_min=extent[0], lon_max=extent[1],
            lat_min=extent[2], lat_max=extent[3],
            projection=INSET_PROJECTION_LABELS.get(
                self.inset_projection_var.get(), "same"),
            ocean=INSET_OCEAN_LABELS.get(self.inset_ocean_var.get(), "none"),
            box_color=self.inset_box_color_var.get() or "#d62728",
            draggable=self.inset_draggable_var.get(),
            anchor_x=None if anchor is None else anchor[0],
            anchor_y=None if anchor is None else anchor[1],
            **layers)

    def set_inset_options(self, options: InsetOptions) -> None:
        """Show stored inset options; the dragged anchor is the renderer's
        to keep."""
        self.inset_var.set(options.show)
        self.inset_region_var.set(name_for(INSET_REGION_LABELS,
                                           options.region))
        self.inset_zoom_out_var.set(f"{options.zoom_out:g}")
        self.set_inset_extent((options.lon_min, options.lon_max,
                               options.lat_min, options.lat_max))
        self.inset_projection_var.set(name_for(INSET_PROJECTION_LABELS,
                                               options.projection))
        self.inset_position_var.set(options.position)
        self.inset_size_var.set(f"{options.size:g}")
        for field, var in self.inset_layer_vars.items():
            var.set(bool(getattr(options, field)))
        self.inset_ocean_var.set(name_for(INSET_OCEAN_LABELS, options.ocean))
        self._set_color(self.inset_box_color_var, options.box_color)
        self.inset_draggable_var.set(options.draggable)
        self.update_inset_state()

    def set_inset_extent(self, extent) -> None:
        """Fill the custom-area boxes (west, east, south, north); None
        leaves a box blank."""
        for var, value in zip(self.inset_extent_vars, extent):
            var.set("" if value is None else f"{round(float(value), 3):g}")

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
        # Persisted default DPI and print width (also saved in the
        # project). The "Save map as..." dialog reads and updates them;
        # format, print width and DPI are all chosen there.
        self.dpi_var = tk.StringVar(value="200")
        self.export_width_var = tk.StringVar(value=AS_ON_SCREEN)
        ttk.Button(sec, text="Save map as\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_save_image).pack(fill="x", pady=2)
        ttk.Button(sec, text="Export as code (Python/R)"
                            "\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_export_code).pack(fill="x", pady=2)
