"""Everything a project stores: the datasets, the map and legend settings
and the view gathered into one dict, and put back from one."""

from __future__ import annotations

import tkinter as tk

from pymappr.files import projects
from pymappr.styling.decorations import (
    CompassOptions, InsetOptions, ScaleBarOptions)
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import (
    DEFAULT_PALETTE_NAME, POINT_EDGE_COLOR, POINT_EDGE_WIDTH)
from pymappr.ui.save_image import AS_ON_SCREEN


class StateMixin:
    """Collecting and applying a project's state."""

    def _collect_state(self) -> dict:
        """Everything a project stores, as a JSON-safe dict."""
        p = self.panel
        xlim, ylim = self.renderer.get_view()
        return {
            "datasets": [projects.entry_to_dict(e) for e in self.entries],
            "active": self.active,
            "map": {
                "projection": p.projection_var.get(),
                "proj_lon0": p.proj_lon0_var.get(),
                "proj_lat0": p.proj_lat0_var.get(),
                "basemap": p.basemap_var.get(),
                "continent": p.continent_var.get(),
                "orientation": p.orientation_var.get(),
                "compass": p.compass_var.get(),
                "compass_options": p.compass_options().to_dict(),
                "scale_bar": p.scale_bar_options(
                    self.renderer.scale_bar_anchor()).to_dict(),
                "inset": p.inset_options(
                    self.renderer.inset_anchor()).to_dict(),
                "palette": p.palette_var.get(),
                "graticule": p.graticule_var.get(),
                "hide_grid_labels": p.hide_grid_labels_var.get(),
                "line_width": p.line_width_var.get(),
                "dpi": p.dpi_var.get(),
                "export_width": p.export_width_var.get(),
                "ocean": p.ocean_var.get(),
                "lake_fill": p.lake_fill_var.get(),
                "bathymetry": p.bathymetry_var.get(),
                "capitals_only": p.capitals_only_var.get(),
                "lines": {k: v.get() for k, v in p.layer_vars.items()},
                "fills": {k: v.get() for k, v in p.fill_vars.items()},
                "points": {k: v.get() for k, v in p.point_vars.items()},
                "labels": {k: v.get() for k, v in p.label_vars.items()},
            },
            # Dragging state is not a legend *option* - it is where the user
            # last put the thing - but it belongs in the same section so a
            # reopened project finds the legend where it was left.
            "legend": {
                **p.legend_options().to_dict(),
                "draggable": p.legend_drag_var.get(),
                "anchor": list(self.renderer.legend_anchor() or ()) or None,
            },
            "point_alpha": p.point_alpha_var.get(),
            "point_edge": dict(zip(("color", "width"), p.point_edge())),
            "view": {"xlim": list(xlim), "ylim": list(ylim)},
        }

    def _apply_state(self, state: dict) -> None:
        """Restore a collected state: datasets, map settings, and view."""
        self.entries = [projects.entry_from_dict(d)
                        for d in state.get("datasets", [])]
        active = state.get("active")
        if not (isinstance(active, int) and 0 <= active < len(self.entries)):
            active = 0 if self.entries else None
        self.active = active

        self._apply_settings(state)

        view = dict(state.get("view", {}))
        xlim, ylim = view.get("xlim"), view.get("ylim")
        if (isinstance(xlim, (list, tuple)) and len(xlim) == 2
                and isinstance(ylim, (list, tuple)) and len(ylim) == 2):
            self.renderer.set_view(xlim, ylim)
        self.toolbar.update()

        self._sync_dataset_ui()
        self._push_points()

    def _apply_settings(self, state: dict) -> None:
        """Restore every map, legend and point setting in *state* - all of
        it but the datasets and the view - to the panel and the map."""
        p = self.panel
        defaults = self._default_state

        m = {**defaults["map"], **dict(state.get("map", {}))}
        legend = {**defaults["legend"], **dict(state.get("legend", {}))}

        p.projection_var.set(m["projection"])
        p.proj_lon0_var.set(m.get("proj_lon0", ""))
        p.proj_lat0_var.set(m.get("proj_lat0", ""))
        p.update_projection_origin(m["projection"])
        basemap = m["basemap"]
        if basemap == "satellite":
            basemap = "relief"  # migrate legacy value
        p.basemap_var.set(basemap)
        p.continent_var.set(m["continent"])
        p.orientation_var.set(m.get("orientation", "Landscape"))
        # "compass" is the original bare flag; the options dict arrived
        # later, so an older project has only the flag and defaults the rest.
        compass = CompassOptions.from_dict(m.get("compass_options"))
        compass.show = bool(m.get("compass", compass.show))
        p.set_compass_options(compass)
        bar = ScaleBarOptions.from_dict(m.get("scale_bar"))
        p.set_scale_bar_options(bar)
        self._scale_bar_corner = bar.position
        self._scale_bar_anchor = bar.anchor
        # Projects saved before insets existed have none, so show none.
        inset = InsetOptions.from_dict(m.get("inset"))
        p.set_inset_options(inset)
        self._inset_corner = inset.position
        self._inset_anchor = inset.anchor
        p.palette_var.set(m.get("palette", DEFAULT_PALETTE_NAME))
        p.graticule_var.set(m["graticule"])
        p.hide_grid_labels_var.set(m["hide_grid_labels"])
        p.line_width_var.set(m["line_width"])
        p.dpi_var.set(m["dpi"])
        p.export_width_var.set(m.get("export_width", AS_ON_SCREEN))
        p.ocean_var.set(m["ocean"])
        p.lake_fill_var.set(m["lake_fill"])
        p.bathymetry_var.set(m["bathymetry"])
        p.capitals_only_var.set(m["capitals_only"])
        for section, vars_ in (("lines", p.layer_vars),
                               ("fills", p.fill_vars),
                               ("points", p.point_vars),
                               ("labels", p.label_vars)):
            stored = {**defaults["map"][section], **dict(m.get(section, {}))}
            for key, var in vars_.items():
                var.set(bool(stored.get(key, False)))
        p.set_legend_options(LegendOptions.from_dict(legend))
        p.legend_drag_var.set(bool(legend.get("draggable", False)))
        self.renderer.set_legend_dragging(p.legend_drag_var.get())
        anchor = legend.get("anchor")
        self.renderer.set_legend_anchor(
            tuple(anchor) if isinstance(anchor, (list, tuple))
            and len(anchor) == 2 else None)
        p.set_point_alpha(state.get("point_alpha", defaults["point_alpha"]))
        # Projects saved before the outline was settable used white.
        edge = dict(state.get("point_edge") or {})
        try:
            edge_width = float(edge.get("width", POINT_EDGE_WIDTH))
        except (TypeError, ValueError):
            edge_width = POINT_EDGE_WIDTH
        p.set_point_edge(str(edge.get("color") or POINT_EDGE_COLOR),
                         edge_width)

        self._busy(True)
        try:
            renderer = self.renderer
            lon0, lat0 = p.projection_origin()
            renderer.set_projection(p.projection_var.get(), lon0, lat0)
            renderer.set_basemap(p.basemap_var.get())
            renderer.set_orientation(p.orientation())
            renderer.set_extent(p.continent_var.get())
            for setter, vars_ in ((renderer.set_layer, p.layer_vars),
                                  (renderer.set_fill_layer, p.fill_vars),
                                  (renderer.set_point_layer, p.point_vars)):
                for key, var in vars_.items():
                    self._apply_layer(setter, key, var.get(), var)
            renderer.set_bathymetry(p.bathymetry_var.get())
            renderer.set_capitals_only(p.capitals_only_var.get())
            renderer.set_ocean(p.ocean_var.get())
            renderer.set_lake_fill(p.lake_fill_var.get())
            for key, var in p.label_vars.items():
                renderer.set_labels(key, var.get())
            renderer.set_compass(p.compass_options())
            renderer.set_scale_bar(p.scale_bar_options(
                self._scale_bar_anchor))
            renderer.set_inset(p.inset_options(self._inset_anchor))
            renderer.set_graticule(
                p.graticule_interval(),
                show_labels=not p.hide_grid_labels_var.get())
            renderer.set_line_width_scale(p.line_width_var.get())
            renderer.set_point_alpha(p.point_alpha_var.get())
            renderer.set_point_edge(*p.point_edge())
        finally:
            self._busy(False)

    def _apply_layer(self, setter, key: str, visible: bool,
                     var: tk.BooleanVar):
        """Show or hide one layer, unticking *var* when it cannot be drawn.

        Optional external layers (biodiversity, ecoregions) may not be
        downloaded, and any layer's data could be missing or corrupt. Returns
        None when it worked, ``"missing"`` when the data is not downloaded,
        or the exception that stopped it - the caller decides whether to
        say so (a toggle does, a project restore stays quiet)."""
        if visible and not self.store.has_layer_data(key):
            var.set(False)
            return "missing"
        try:
            setter(key, visible)
        except Exception as exc:  # noqa: BLE001 - a bad layer must not crash
            var.set(False)
            try:
                setter(key, False)  # drop any half-built artists
            except Exception:  # noqa: BLE001
                pass
            return exc
        return None
