"""Reading and setting the panel's values: what the app reads its
settings from, and how a project or preset puts them back."""

from __future__ import annotations

import math
import tkinter as tk

from pymappr.geo.projections import (default_origin, has_custom_origin,
                                     normalize_origin)
from pymappr.styling.decorations import CompassOptions, ScaleBarOptions
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import (POINT_EDGE_COLOR, POINT_EDGE_WIDTH,
                                    palette_for)
from pymappr.ui.control_panel.tables import (COMPASS_STYLE_LABELS,
                                             GRATICULE_CHOICES,
                                             ORIENTATION_LABELS,
                                             SCALE_LENGTH_LABELS,
                                             SCALE_STYLE_LABELS,
                                             SCALE_UNIT_LABELS,
                                             _legend_fields, name_for)


class ValuesMixin:
    """Getters and setters over the panel's Tk variables."""

    def update_projection_origin(self, name: str, reset: bool = False) -> None:
        """Enable the origin spinboxes for the Globe and the Lambert
        projections (seeding the preset default when *reset*) and disable
        them otherwise."""
        if has_custom_origin(name):
            if reset or not self.proj_lon0_var.get().strip():
                lon0, lat0 = default_origin(name)
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
        """The (lon_0, lat_0) centre for the Globe or a Lambert projection,
        or (None, None) for any other projection or unparseable input
        (uses the default)."""
        if not has_custom_origin(self.projection_var.get()):
            return None, None

        def _num(var, fix):
            try:
                value = float(var.get())
            except (TypeError, ValueError):
                return None
            if not math.isfinite(value):
                return None
            fixed = fix(value)
            if fixed != value:
                # Show what will actually be used, and use what is shown, so
                # the next read builds the same projection. ":g" kept only 6
                # digits, which moved the centre on the next Enter.
                shown = f"{fixed:.15g}"
                var.set(shown)
                fixed = float(shown)
            return fixed

        return (_num(self.proj_lon0_var,
                     lambda v: normalize_origin(v, 0.0)[0]),
                _num(self.proj_lat0_var,
                     lambda v: normalize_origin(0.0, v)[1]))

    def graticule_interval(self) -> float | None:
        return GRATICULE_CHOICES[self.graticule_var.get()]

    def orientation(self) -> str:
        """The renderer orientation key for the selected label."""
        return ORIENTATION_LABELS.get(self.orientation_var.get(), "landscape")

    def palette(self) -> list[str]:
        """The colour palette the user picked, for styling new groups."""
        return palette_for(self.palette_var.get())

    def point_edge(self) -> tuple[str, float]:
        """(colour, width) of the outline around filled markers."""
        return (self.point_edge_color_var.get() or POINT_EDGE_COLOR,
                self._number(self.point_edge_width_var, 0.0, 3.0,
                             POINT_EDGE_WIDTH))

    def set_point_edge(self, color: str, width: float) -> None:
        self._set_color(self.point_edge_color_var, color)
        self.point_edge_width_var.set(f"{float(width):g}")

    def set_point_alpha(self, alpha: float) -> None:
        """Set the opacity slider, keeping its number label in step."""
        self.point_alpha_var.set(alpha)
        self._alpha_label.config(text=f"{float(alpha):.2g}")

    def _set_color(self, var: tk.StringVar, value: str) -> None:
        """Set a colour variable and repaint its swatch button to match."""
        var.set(value)
        button = self._color_buttons.get(str(var))
        if button is not None and value:
            button.config(bg=value, activebackground=value)

    def compass_options(self) -> CompassOptions:
        return CompassOptions(
            show=self.compass_var.get(),
            position=self.compass_position_var.get(),
            style=COMPASS_STYLE_LABELS.get(self.compass_style_var.get(),
                                           "arrow"),
            size=self._number(self.compass_size_var, 0.5, 3.0, 1.0))

    def set_compass_options(self, options: CompassOptions) -> None:
        self.compass_var.set(options.show)
        self.compass_position_var.set(options.position)
        self.compass_style_var.set(name_for(COMPASS_STYLE_LABELS,
                                            options.style))
        self.compass_size_var.set(f"{options.size:g}")

    def set_scale_bar_options(self, options: ScaleBarOptions) -> None:
        """Show stored scale bar options; the dragged anchor is the
        renderer's to keep."""
        self.scale_bar_var.set(options.show)
        self.scale_units_var.set(name_for(SCALE_UNIT_LABELS, options.units))
        self.scale_position_var.set(options.position)
        self.scale_style_var.set(name_for(SCALE_STYLE_LABELS, options.style))
        self.scale_length_mode_var.set(name_for(SCALE_LENGTH_LABELS,
                                                options.length_mode))
        self.scale_fixed_length_var.set(
            "" if options.fixed_length is None
            else f"{options.fixed_length:g}")
        self.scale_draggable_var.set(options.draggable)
        self.update_scale_length_state()

    def scale_bar_options(self, anchor=None) -> ScaleBarOptions:
        """The scale bar as configured. *anchor* keeps a dragged position,
        which the panel itself has no widget for."""
        mode = SCALE_LENGTH_LABELS.get(self.scale_length_mode_var.get(),
                                       "auto")
        fixed = self._optional_number(self.scale_fixed_length_var,
                                      0.001, 1e6)
        return ScaleBarOptions(
            show=self.scale_bar_var.get(),
            units=SCALE_UNIT_LABELS.get(self.scale_units_var.get(), "km"),
            position=self.scale_position_var.get(),
            style=SCALE_STYLE_LABELS.get(self.scale_style_var.get(),
                                         "segmented"),
            length_mode=mode,
            fixed_length=fixed,
            draggable=self.scale_draggable_var.get(),
            anchor_x=None if anchor is None else anchor[0],
            anchor_y=None if anchor is None else anchor[1])

    @staticmethod
    def _number(var: tk.StringVar, low: float, high: float,
                fallback: float) -> float:
        """A spinbox's value, clamped, falling back when it is mid-edit or
        nonsense. Typing into a spinbox fires on every keystroke, so ""
        and "-" are ordinary states rather than errors."""
        try:
            return max(min(float(var.get()), high), low)
        except ValueError:
            return fallback

    @staticmethod
    def _optional_number(var: tk.StringVar, low: float,
                         high: float) -> float | None:
        """Like :meth:`_number` but blank means "leave it automatic"."""
        if not var.get().strip():
            return None
        try:
            return max(min(float(var.get()), high), low)
        except ValueError:
            return None

    def legend_options(self) -> LegendOptions:
        """Every legend setting, as one options object for the renderer,
        the project file and the code export. Half-typed or out-of-range
        numbers fall back or clamp rather than raise."""
        defaults = LegendOptions()
        values = {}
        for field, kind, extra in _legend_fields():
            var, default = self.legend_vars[field], getattr(defaults, field)
            if kind == "choice":
                value = extra.get(var.get(), default)
            elif kind == "number" and default is None:
                value = self._optional_number(var, *extra[:2])
            elif kind == "number":
                value = type(default)(self._number(var, *extra[:2],
                                                   default))
            elif kind == "text" and default is None:
                value = var.get().strip() or None   # the title
            elif kind in ("text", "color", "combo"):
                value = var.get() or default
            else:
                value = bool(var.get())
            values[field] = value
        return LegendOptions(**values)

    def set_legend_options(self, options: LegendOptions) -> None:
        """Push a stored options object back into the widgets."""
        for field, kind, extra in _legend_fields():
            var, value = self.legend_vars[field], getattr(options, field)
            if kind == "choice":
                var.set(name_for(extra, value))
            elif kind == "number":
                var.set("" if value is None else f"{value:g}")
            elif kind == "color":
                self._set_color(var, value)
            elif kind == "text":
                var.set(value or "")
            else:
                var.set(value)

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

    def set_open_controls(self, choices: list[str], open_by: str,
                          values: list[str], chosen: str) -> None:
        """Point the open-symbol controls at the selected dataset: the
        column choices, and that column's values with *chosen* selected."""
        self.open_by_box.configure(values=choices)
        self.open_by_var.set(open_by if open_by in choices else "None")
        self.open_value_box.configure(values=values)
        self.open_value_var.set(chosen if chosen in values else "")

    def set_file_info(self, text: str) -> None:
        color = "#666666" if text == "No data loaded" else "#333333"
        self.file_label.config(text=text, foreground=color)

    # ------------------------------------------------ ttk.Scale callbacks

    def _on_alpha_scale(self, value: str) -> None:
        snapped = round(float(value) * 20) / 20  # snap to 0.05
        self.point_alpha_var.set(snapped)
        self._alpha_label.config(text=f"{snapped:.2g}")
        self.app.on_point_alpha()

    def _on_lw_scale(self, value: str) -> None:
        snapped = round(float(value) * 4) / 4  # snap to 0.25
        self.line_width_var.set(snapped)
        self._lw_label.config(text=f"{snapped:.2g}")
        self.app.on_line_width()
