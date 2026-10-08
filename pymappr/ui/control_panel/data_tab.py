"""The Data and Legend tabs: presets, the loaded datasets and their
point styling, and every legend setting."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import (DEFAULT_PALETTE_NAME, PALETTES,
                                    POINT_EDGE_COLOR, POINT_EDGE_WIDTH)
from pymappr.ui.control_panel.tables import (LEGEND_ROWS, PANEL_WIDTH,
                                             _style_fields, name_for)


class DataTabMixin:
    """Builds the Data and Legend tabs."""

    def _build_presets_section(self, tab) -> None:
        """Saved settings to carry from one project to the next. First on
        the Data tab, so a new project can pick its look in one click."""
        sec = self._section(tab, "Presets")
        self.preset_var = tk.StringVar()
        self.preset_box = ttk.Combobox(sec, textvariable=self.preset_var,
                                       state="readonly")
        self.preset_box.pack(fill="x", pady=2)
        row = ttk.Frame(sec)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Apply", command=self.app.on_apply_preset).pack(
            side="left", fill="x", expand=True)
        ttk.Button(row, text="Save current as\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_save_preset).pack(
            side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(row, text="Delete", command=self.app.on_delete_preset).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

    def set_preset_names(self, names: list[str],
                         selected: str | None = None) -> None:
        self.preset_box.configure(values=names)
        self.preset_var.set(selected if selected in names
                            else names[0] if names else "")

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
        style = ttk.Style()
        lb_bg = style.lookup("TFrame", "background") or "white"
        lb_fg = style.lookup("TLabel", "foreground") or "black"
        lb_sel = style.lookup("TButton", "background", ["active"]) or "#005fb8"
        self.dataset_list = tk.Listbox(
            list_frame, height=5, exportselection=False,
            activestyle="dotbox", relief="flat", borderwidth=1,
            background=lb_bg, foreground=lb_fg,
            selectbackground=lb_sel, selectforeground="white",
            highlightthickness=0)
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

        # Open symbols: rows holding a chosen value (Type status = Holotype)
        # draw as the outline of their group's symbol - the usual way to
        # pick out type localities - with a legend row saying so.
        self.open_by_var = tk.StringVar(value="None")
        self.open_by_box = self._combo_row(
            sec, "Open symbols for:", self.open_by_var, ["None"],
            self.app.on_open_by, width=18)
        self.open_value_var = tk.StringVar(value="")
        self.open_value_box = self._combo_row(
            sec, "where it is:", self.open_value_var, [],
            self.app.on_open_symbols, width=18)
        # Joins e.g. Genus + Species into one "Genus Species" column, so a
        # legend row can carry the full name.
        ttk.Button(sec, text="Combine columns\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_combine_columns).pack(fill="x",
                                                             pady=(4, 0))

        self.vary_symbols_var = tk.BooleanVar(value=False)
        self._check(sec, "Vary symbols per group", self.vary_symbols_var,
                    self.app.on_style_scheme)

        # The palette new groups are coloured from. Changing it re-styles
        # every dataset, but leaves colours pinned per legend row alone.
        self.palette_var = tk.StringVar(value=DEFAULT_PALETTE_NAME)
        self._combo_row(sec, "Palette:", self.palette_var, list(PALETTES),
                        self.app.on_palette, width=18)

        # Outline around filled markers: white by default, black for the
        # white-and-black-dot look of a printed figure.
        self.point_edge_color_var = tk.StringVar(value=POINT_EDGE_COLOR)
        self._color_row(sec, "Point outline:", self.point_edge_color_var,
                        self.app.on_point_edge)
        self.point_edge_width_var = tk.StringVar(value=f"{POINT_EDGE_WIDTH:g}")
        self._spin_row(sec, "Outline width:", self.point_edge_width_var,
                       0.0, 3.0, 0.1, self.app.on_point_edge)

        row = ttk.Frame(sec)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Point opacity:").pack(side="left")
        self._alpha_label = ttk.Label(row, text="1.0")
        self._alpha_label.pack(side="right")
        self.point_alpha_var = tk.DoubleVar(value=1.0)
        ttk.Scale(sec, from_=0.1, to=1.0, orient="horizontal",
                  variable=self.point_alpha_var,
                  command=self._on_alpha_scale).pack(fill="x")

    def _build_legend_section(self, tab) -> None:
        defaults = LegendOptions()
        self.legend_vars: dict[str, tk.Variable] = {}
        for title, expanded, rows in LEGEND_ROWS:
            sec = (self._section(tab, title) if expanded is None
                   else self._collapsible(tab, title, expanded))
            for field, kind, label, extra in rows:
                self._legend_control(sec, field, kind, label, extra,
                                     defaults)
        self._build_legend_placement_group(tab)

    def _legend_control(self, sec, field, kind, label, extra,
                        defaults: LegendOptions) -> None:
        """One legend setting's widget, wired to redraw the legend."""
        command = (self.app.on_legend_position if field == "location"
                   else self.app.on_legend_options)
        if kind == "note":
            ttk.Label(sec, text=label, wraplength=PANEL_WIDTH - 70,
                      foreground="#666666").pack(anchor="w")
            return
        if kind == "style":
            row = ttk.Frame(sec)
            row.pack(fill="x", pady=(2, 0))
            ttk.Label(row, text=label).pack(side="left")
            for name, text in _style_fields(field):
                var = tk.BooleanVar(value=getattr(defaults, name))
                ttk.Checkbutton(row, text=text, variable=var, width=3,
                                command=command).pack(side="left",
                                                      padx=(4, 0))
                self.legend_vars[name] = var
            return
        default = getattr(defaults, field)
        if kind == "check":
            var = tk.BooleanVar(value=default)
            self._check(sec, label, var, command)
        elif kind == "combo":
            var = tk.StringVar(value=default)
            self._combo_row(sec, label, var, extra, command, width=14)
        elif kind == "choice":
            var = tk.StringVar(value=name_for(extra, default))
            self._named_combo(sec, label, var, extra, command, width=14)
        elif kind == "text":
            var = tk.StringVar(value=default or "")
            self._entry_row(sec, label, var, command, width=extra)
        elif kind == "number":
            var = tk.StringVar(value="" if default is None
                               else f"{default:g}")
            self._spin_row(sec, label, var, *extra, command)
        else:  # color
            var = tk.StringVar(value=default)
            self._color_row(sec, label, var, command)
        self.legend_vars[field] = var

    def _build_legend_placement_group(self, tab) -> None:
        sec = self._section(tab, "Placement")
        self.legend_drag_var = tk.BooleanVar(value=False)
        self._check(sec, "Allow dragging the legend",
                    self.legend_drag_var, self.app.on_legend_drag_toggle)
        ttk.Label(
            sec, text="Drag the legend anywhere (no limits); right-click it "
            "to snap back to the position above.",
            wraplength=PANEL_WIDTH - 60,
            foreground="#666666").pack(anchor="w")

        ttk.Button(sec, text="Customize legend\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_edit_styles).pack(fill="x", pady=2)
