"""The map settings: basemap, projection, layers, north arrow, scale bar,
inset map, palette, labels and graticule, plus image and code export."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from pymappr.ui.control_panel import INSET_REGION_LABELS, name_for


class MapSettingsMixin:
    """The map settings and export."""

    def on_basemap(self) -> None:
        mode = self.panel.basemap_var.get()
        if mode != "simple" and not self.store.has_basemap(mode):
            self.panel.basemap_var.set("simple")
            messagebox.showinfo(
                "Basemap not downloaded",
                f"The {mode.replace('_', ' ')} raster is not available.\n\n"
                "Run 'python scripts/fetch_data.py' to download additional "
                "basemap rasters, then select it again.",
                parent=self.root)
            return
        self._busy(True)
        try:
            self.renderer.set_basemap(mode)
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_continent(self) -> None:
        self.renderer.set_extent(self.panel.continent_var.get())
        self.toolbar.update()
        self.renderer.redraw()

    def on_orientation(self) -> None:
        self.renderer.set_orientation(self.panel.orientation())
        self.toolbar.update()  # re-frame becomes the toolbar's Home
        self.renderer.redraw()

    def on_projection(self) -> None:
        name = self.panel.projection_var.get()
        # A newly chosen Lambert projection seeds its preset origin; other
        # projections disable the origin controls.
        self.panel.update_projection_origin(name, reset=True)
        lon0, lat0 = self.panel.projection_origin()
        self.set_status(f"Reprojecting to {name}\N{HORIZONTAL ELLIPSIS}")
        self._busy(True)
        try:
            self.renderer.set_projection(name, lon0, lat0)
        finally:
            self._busy(False)
        self.toolbar.update()
        self.set_status("Ready.")
        self.renderer.redraw()

    def on_projection_origin(self) -> None:
        """Re-centre a Lambert projection on an edited point of natural
        origin (central meridian / latitude of origin). A no-op for the
        world projections, whose origin controls are disabled."""
        name = self.panel.projection_var.get()
        lon0, lat0 = self.panel.projection_origin()
        self._busy(True)
        try:
            self.renderer.set_projection(name, lon0, lat0)
        finally:
            self._busy(False)
        self.toolbar.update()
        self.renderer.redraw()

    def on_line_width(self) -> None:
        self.renderer.set_line_width_scale(self.panel.line_width_var.get())
        self.renderer.redraw()

    def _toggle_layer(self, key: str, visible: bool, setter,
                      var: tk.BooleanVar) -> None:
        """A layer checkbox changed: draw it with a busy cursor, and explain
        (and untick) when it cannot be drawn."""
        if visible:
            self.set_status(f"Loading {key.replace('_', ' ')} layer"
                            f"\N{HORIZONTAL ELLIPSIS}")
            self._busy(True)
        try:
            problem = self._apply_layer(setter, key, visible, var)
        finally:
            if visible:
                self._busy(False)
                self.set_status("Ready.")
        if problem == "missing":
            self._optional_layer_missing(key)
        elif problem is not None:
            self._layer_load_error(key, problem)
        else:
            self.renderer.redraw()

    def _optional_layer_missing(self, key: str) -> None:
        label = key.replace("_", " ")
        messagebox.showinfo(
            "Layer not downloaded",
            f"The {label} layer is an optional dataset that has not been "
            "downloaded yet.\n\nRun 'python scripts/fetch_data.py' to fetch "
            "the biodiversity and ecoregion layers, then tick the box again.",
            parent=self.root)
        self.set_status(f"{label.capitalize()} layer not available.")

    def _layer_load_error(self, key: str, exc: Exception) -> None:
        messagebox.showwarning(
            "Could not load layer",
            f"The {key.replace('_', ' ')} layer could not be loaded:\n\n{exc}",
            parent=self.root)
        self.set_status("Ready.")

    def on_layer(self, key: str) -> None:
        self._toggle_layer(key, self.panel.layer_vars[key].get(),
                           self.renderer.set_layer,
                           self.panel.layer_vars[key])

    def on_fill_layer(self, key: str) -> None:
        self._toggle_layer(key, self.panel.fill_vars[key].get(),
                           self.renderer.set_fill_layer,
                           self.panel.fill_vars[key])

    def on_point_layer(self, key: str) -> None:
        self._toggle_layer(key, self.panel.point_vars[key].get(),
                           self.renderer.set_point_layer,
                           self.panel.point_vars[key])

    def on_bathymetry(self) -> None:
        self._toggle_layer(
            "bathymetry", self.panel.bathymetry_var.get(),
            lambda _key, visible: self.renderer.set_bathymetry(visible),
            self.panel.bathymetry_var)

    def on_capitals_only(self) -> None:
        self.renderer.set_capitals_only(self.panel.capitals_only_var.get())
        self.renderer.redraw()

    def on_compass(self) -> None:
        self.renderer.set_compass(self.panel.compass_options())
        self.renderer.redraw()

    def on_scale_bar(self) -> None:
        """Any scale bar setting changed. A dragged position survives unless
        the user picked a different corner, which is a request to move it."""
        self.panel.update_scale_length_state()
        anchor = self.renderer.scale_bar_anchor()
        if self.panel.scale_position_var.get() != self._scale_bar_corner:
            self._scale_bar_corner = self.panel.scale_position_var.get()
            anchor = None
        self.renderer.set_scale_bar(self.panel.scale_bar_options(anchor))
        self.renderer.redraw()
        note = self.renderer.scale_bar_note()
        if note:
            self.set_status(note)

    def on_reset_scale_bar(self) -> None:
        """Send a dragged scale bar back to its chosen corner."""
        self.renderer.set_scale_bar(self.panel.scale_bar_options(None))
        self.renderer.redraw()

    def on_inset(self) -> None:
        """Any inset setting changed. As with the scale bar, a dragged
        position survives unless the user picked a different corner."""
        self.panel.update_inset_state()
        anchor = self.renderer.inset_anchor()
        if self.panel.inset_position_var.get() != self._inset_corner:
            self._inset_corner = self.panel.inset_position_var.get()
            anchor = None
        self._busy(True)
        try:
            self.renderer.set_inset(self.panel.inset_options(anchor))
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_reset_inset(self) -> None:
        """Send a dragged inset back to its chosen corner."""
        self.renderer.set_inset(self.panel.inset_options(None))
        self.renderer.redraw()

    def on_inset_from_view(self) -> None:
        """Make the inset show the area now on screen: zoom in on it, click,
        and zoom back out to leave the inset as a close-up."""
        extent, _centre = self.renderer.view_lonlat()
        self.panel.set_inset_extent(extent)
        self.panel.inset_region_var.set(name_for(
            INSET_REGION_LABELS, "custom"))
        self.on_inset()
        self.set_status("The inset now shows this view. Zoom out to see it "
                        "as a close-up.")

    def _palette(self) -> list[str]:
        """The colour palette groups are styled from."""
        return self.panel.palette()

    def on_palette(self) -> None:
        """The colour palette changed: restyle every dataset's groups.
        Colours pinned per legend row live in ``legend_overrides`` and stay
        pinned."""
        # White points vanish inside a white outline, so a palette with
        # white in it brings a black outline along.
        color, width = self.panel.point_edge()
        if ("#ffffff" in self._palette()
                and color.lower() in ("#ffffff", "white")):
            self.panel.set_point_edge("#000000", width)
            self.renderer.set_point_edge(*self.panel.point_edge())
            self.set_status("Point outline set to black so white points "
                            "stay visible.")
        self._push_points()

    def on_lake_fill(self) -> None:
        self._busy(True)
        try:
            self.renderer.set_lake_fill(self.panel.lake_fill_var.get())
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_ocean(self) -> None:
        self._busy(True)
        try:
            self.renderer.set_ocean(self.panel.ocean_var.get())
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_label(self, key: str) -> None:
        self._busy(True)
        try:
            self.renderer.set_labels(key, self.panel.label_vars[key].get())
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_label_drag_toggle(self) -> None:
        self.renderer.set_label_dragging(
            self.panel.label_drag_var.get())

    def on_legend_drag_toggle(self) -> None:
        self.renderer.set_legend_dragging(
            self.panel.legend_drag_var.get())

    def on_graticule(self) -> None:
        interval = self.panel.graticule_interval()
        self.renderer.set_graticule(
            interval, show_labels=not self.panel.hide_grid_labels_var.get())
        self.renderer.redraw()

    def on_save_image(self) -> None:
        """Open the "Save map as..." dialog (format, resolution and DPI)."""
        from pymappr.ui.save_image import SaveImageDialog

        SaveImageDialog(self.root, self)

    def on_export_code(self) -> None:
        """Show the map as ready-to-run Python or R code (assembled from
        pre-made function templates, not an AI model)."""
        from pymappr.ui.code_export import CodeExportDialog

        CodeExportDialog(self.root, self)
