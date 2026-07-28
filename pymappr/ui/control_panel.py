"""Tabbed side panel holding every map control.

With ~30 layer toggles the panel is organized as a notebook of five
scrollable tabs - Data (CSV, styling), Legend, Map (view, projection,
graticule, compass, export), Layers (every Natural Earth layer, grouped),
and Labels. The panel owns the Tk variables and forwards changes to the
app's handler methods; the app owns the renderer and the data.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from pymappr.layers import CONTINENT_EXTENTS
from pymappr.legend import (COUNT_FORMATS, ENTRY_ORDERS, FONT_FAMILIES,
                            GROUP_SWATCHES, HIERARCHY_MODES, LEGEND_LOCATIONS,
                            TITLE_ALIGNMENTS, LegendOptions)
from pymappr.projections import (PROJECTIONS, default_origin,
                                 has_custom_origin)

PANEL_WIDTH = 320

GRATICULE_CHOICES = {"Off": None, "1\N{DEGREE SIGN}": 1.0,
                     "5\N{DEGREE SIGN}": 5.0, "10\N{DEGREE SIGN}": 10.0}
# Display label -> renderer orientation key.
ORIENTATION_LABELS = {"Landscape": "landscape", "Portrait": "portrait"}
KOFI_URL = "https://ko-fi.com/calebhendren"

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
        # Colour swatch buttons, keyed by the Tk name of the var they set
        # (StringVar itself is unhashable), so restoring a project can
        # repaint them to match the values it loaded.
        self._color_buttons: dict[str, tk.Button] = {}

        self.notebook = ttk.Notebook(self, width=PANEL_WIDTH)
        # The footer packs to the bottom edge first so the notebook fills
        # whatever height remains above it.
        self._build_footer()
        self.notebook.pack(fill="both", expand=True)

        data_tab = self._scroll_tab("Data")
        # The legend carries enough settings now to want its own tab rather
        # than a very long scroll under the data controls.
        legend_tab = self._scroll_tab("Legend")
        map_tab = self._scroll_tab("Map")
        layers_tab = self._scroll_tab("Layers")
        labels_tab = self._scroll_tab("Labels")

        self._build_data_section(data_tab)
        self._build_legend_section(legend_tab)

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
        bg = ttk.Style().lookup("TFrame", "background") or "white"
        canvas = tk.Canvas(outer, width=PANEL_WIDTH, highlightthickness=0,
                           background=bg)
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

    def _collapsible(self, parent, title: str, expanded: bool = False):
        """A section that folds away, so a tab can carry many settings
        without becoming an endless scroll. ttk has no expander widget, so
        this is a header button that packs and forgets the body frame.

        Returns the body frame to put controls in.
        """
        outer = ttk.Frame(parent)
        outer.pack(fill="x", padx=6, pady=(4, 0))
        header = ttk.Button(outer, style="Toolbutton")
        header.pack(fill="x")
        body = ttk.LabelFrame(outer, padding=(8, 4))
        state = {"open": bool(expanded)}

        def render() -> None:
            arrow = ("\N{BLACK DOWN-POINTING SMALL TRIANGLE}" if state["open"]
                     else "\N{BLACK RIGHT-POINTING SMALL TRIANGLE}")
            header.config(text=f"{arrow}  {title}")
            if state["open"]:
                body.pack(fill="x", pady=(2, 0))
            else:
                body.pack_forget()

        def toggle() -> None:
            state["open"] = not state["open"]
            render()

        header.config(command=toggle)
        render()
        return body

    def _spin_row(self, parent, label: str, var: tk.StringVar, from_, to,
                  increment, command, width: int = 6):
        """A labelled spinbox that reports on both arrow clicks and typing."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        spin = ttk.Spinbox(row, from_=from_, to=to, increment=increment,
                           width=width, textvariable=var, command=command)
        spin.pack(side="right")
        spin.bind("<KeyRelease>", lambda _e: command())
        return spin

    def _entry_row(self, parent, label: str, var: tk.StringVar, command,
                   width: int = 14):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        entry = ttk.Entry(row, textvariable=var, width=width)
        entry.pack(side="right")
        entry.bind("<KeyRelease>", lambda _e: command())
        return entry

    def _color_row(self, parent, label: str, var: tk.StringVar, command):
        """A labelled colour swatch button opening the system colour picker.

        The chosen colour lives in *var* as a hex string, so it saves and
        restores with everything else.
        """
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        button = tk.Button(row, width=4, relief="ridge",
                           bg=var.get() or "#ffffff",
                           activebackground=var.get() or "#ffffff")
        button.pack(side="right")

        def pick() -> None:
            _rgb, chosen = colorchooser.askcolor(
                color=var.get() or "#ffffff", parent=self, title=label)
            if chosen:
                var.set(chosen)
                button.config(bg=chosen, activebackground=chosen)
                command()

        button.config(command=pick)
        self._color_buttons[str(var)] = button
        return button

    def _named_combo(self, parent, label: str, var: tk.StringVar,
                     names: dict, command, width: int = 16):
        """A combo box over a display-name -> stored-value mapping."""
        return self._combo_row(parent, label, var, list(names), command,
                               width=width)

    def _build_text_style_row(self, parent, label: str,
                              bold_var: tk.BooleanVar,
                              italic_var: tk.BooleanVar,
                              underline_var: tk.BooleanVar) -> None:
        """A row of Bold / Italic / Underline toggles for a legend text
        element, wired to the legend-options handler."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(2, 0))
        ttk.Label(row, text=label).pack(side="left")
        for text, var in (("B", bold_var), ("I", italic_var),
                          ("U", underline_var)):
            ttk.Checkbutton(row, text=text, variable=var, width=3,
                            command=self.app.on_legend_options).pack(
                side="left", padx=(4, 0))

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

        self.vary_symbols_var = tk.BooleanVar(value=False)
        self._check(sec, "Vary symbols per group", self.vary_symbols_var,
                    self.app.on_style_scheme)

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
        # Two handlers, and which one a control uses matters. Anything that
        # changes the row *text* or the set of rows is content and has to
        # re-derive the groups; anything that only changes how they look can
        # restyle the existing legend in place.
        restyle = self.app.on_legend_options
        rebuild = self.app.on_legend_content
        defaults = LegendOptions()

        sec = self._section(tab, "Legend")
        self.legend_show_var = tk.BooleanVar(value=defaults.show)
        self._check(sec, "Show legend", self.legend_show_var, restyle)

        self.legend_loc_var = tk.StringVar(value=defaults.location)
        self._combo_row(sec, "Position:", self.legend_loc_var,
                        LEGEND_LOCATIONS, self.app.on_legend_position,
                        width=14)

        self.legend_title_var = tk.StringVar(value="")
        self._entry_row(sec, "Title:", self.legend_title_var, restyle,
                        width=18)
        ttk.Label(sec, text="(blank = use the Group by column name)",
                  foreground="#666666").pack(anchor="w")

        self._build_legend_content_group(tab, rebuild, defaults)
        self._build_legend_nesting_group(tab, restyle, rebuild, defaults)
        self._build_legend_layout_group(tab, restyle, defaults)
        self._build_legend_frame_group(tab, restyle, defaults)
        self._build_legend_text_group(tab, restyle, defaults)
        self._build_legend_placement_group(tab)

    # ------------------------------------------------- legend sub-sections

    def _build_legend_content_group(self, tab, rebuild, defaults) -> None:
        sec = self._collapsible(tab, "Rows and order", expanded=True)

        self.legend_hierarchy_var = tk.StringVar(
            value=self._name_for(HIERARCHY_MODES, defaults.hierarchy))
        self._named_combo(sec, "Hierarchy:", self.legend_hierarchy_var,
                          HIERARCHY_MODES, rebuild)
        ttk.Label(sec, text="Nesting also lets shapes repeat across colour "
                            "groups, so a hierarchy needs fewer of them.",
                  wraplength=PANEL_WIDTH - 70,
                  foreground="#666666").pack(anchor="w")

        self.legend_order_var = tk.StringVar(
            value=self._name_for(ENTRY_ORDERS, defaults.order))
        self._named_combo(sec, "Order:", self.legend_order_var,
                          ENTRY_ORDERS, rebuild)

        # Counts are built into the legend rows themselves, so changing this
        # has to re-derive the groups rather than just restyle the legend.
        self.legend_counts_var = tk.BooleanVar(value=defaults.counts)
        self._check(sec, "Show point counts", self.legend_counts_var, rebuild)

        self.legend_count_format_var = tk.StringVar(
            value=self._name_for(COUNT_FORMATS, defaults.count_format))
        self._named_combo(sec, "Counts look like:",
                          self.legend_count_format_var, COUNT_FORMATS,
                          rebuild, width=12)

        self.legend_blank_label_var = tk.StringVar(value=defaults.blank_label)
        self._entry_row(sec, "Blank values:", self.legend_blank_label_var,
                        rebuild, width=12)

        self.legend_section_titles_var = tk.BooleanVar(
            value=defaults.section_titles)
        self._check(sec, "Show section titles",
                    self.legend_section_titles_var, rebuild)

        self.legend_title_separator_var = tk.StringVar(
            value=defaults.title_separator)
        self._entry_row(sec, "Title separator:",
                        self.legend_title_separator_var, rebuild, width=8)

        self.legend_dataset_prefix_var = tk.BooleanVar(
            value=defaults.dataset_prefix)
        self._check(sec, "Prefix sections with the dataset name",
                    self.legend_dataset_prefix_var, rebuild)

        self.legend_empty_groups_var = tk.BooleanVar(
            value=defaults.empty_groups)
        self._check(sec, "Keep groups with no visible rows",
                    self.legend_empty_groups_var, rebuild)

    def _build_legend_nesting_group(self, tab, restyle, rebuild,
                                    defaults) -> None:
        sec = self._collapsible(tab, "Nested keys")

        self.legend_indent_var = tk.StringVar(value=str(defaults.indent))
        self._spin_row(sec, "Indent (spaces):", self.legend_indent_var,
                       0, 12, 1, restyle)

        self.legend_bold_groups_var = tk.BooleanVar(value=defaults.bold_groups)
        self._check(sec, "Bold the group rows", self.legend_bold_groups_var,
                    restyle)

        self.legend_group_spacer_var = tk.BooleanVar(
            value=defaults.group_spacer)
        self._check(sec, "Blank row between groups",
                    self.legend_group_spacer_var, restyle)

        self.legend_group_swatch_var = tk.StringVar(
            value=self._name_for(GROUP_SWATCHES, defaults.group_swatch))
        self._named_combo(sec, "Group swatch:", self.legend_group_swatch_var,
                          GROUP_SWATCHES, rebuild)

        self.legend_symbol_color_var = tk.StringVar(
            value=defaults.symbol_swatch_color)
        self._color_row(sec, "Crossed symbol colour:",
                        self.legend_symbol_color_var, rebuild)
        ttk.Label(sec, text="Used only when the columns cross, where a shape "
                            "appears in every colour.",
                  wraplength=PANEL_WIDTH - 70,
                  foreground="#666666").pack(anchor="w")

    def _build_legend_layout_group(self, tab, restyle, defaults) -> None:
        sec = self._collapsible(tab, "Layout")

        self.legend_columns_var = tk.StringVar(value=str(defaults.columns))
        self._spin_row(sec, "Columns:", self.legend_columns_var, 1, 6, 1,
                       restyle)

        self.legend_label_spacing_var = tk.StringVar(
            value=f"{defaults.label_spacing:g}")
        self._spin_row(sec, "Row spacing:", self.legend_label_spacing_var,
                       0.0, 4.0, 0.1, restyle)

        self.legend_column_spacing_var = tk.StringVar(
            value=f"{defaults.column_spacing:g}")
        self._spin_row(sec, "Column spacing:",
                       self.legend_column_spacing_var, 0.0, 8.0, 0.5, restyle)

        # Marker size scales the sample symbols shown in the legend
        # (markerscale), independent of the point sizes on the map.
        self.legend_marker_scale_var = tk.StringVar(
            value=f"{defaults.marker_scale:g}")
        self._spin_row(sec, "Marker size:", self.legend_marker_scale_var,
                       0.1, 6.0, 0.25, restyle)

        self.legend_handle_pad_var = tk.StringVar(value="")
        self._spin_row(sec, "Swatch gap:", self.legend_handle_pad_var,
                       0.0, 4.0, 0.1, restyle)
        ttk.Label(sec, text="(blank = automatic)",
                  foreground="#666666").pack(anchor="w")

        self.legend_handle_length_var = tk.StringVar(
            value=f"{defaults.handle_length:g}")
        self._spin_row(sec, "Swatch width:", self.legend_handle_length_var,
                       0.0, 8.0, 0.5, restyle)

        self.legend_border_pad_var = tk.StringVar(
            value=f"{defaults.border_pad:g}")
        self._spin_row(sec, "Inner padding:", self.legend_border_pad_var,
                       0.0, 4.0, 0.1, restyle)

    def _build_legend_frame_group(self, tab, restyle, defaults) -> None:
        sec = self._collapsible(tab, "Frame")

        self.legend_frame_var = tk.BooleanVar(value=defaults.frame)
        self._check(sec, "Draw legend frame", self.legend_frame_var, restyle)

        self.legend_frame_color_var = tk.StringVar(value=defaults.frame_color)
        self._color_row(sec, "Fill:", self.legend_frame_color_var, restyle)

        self.legend_frame_alpha_var = tk.StringVar(
            value=f"{defaults.frame_alpha:g}")
        self._spin_row(sec, "Fill opacity:", self.legend_frame_alpha_var,
                       0.0, 1.0, 0.05, restyle)

        self.legend_frame_edge_var = tk.StringVar(
            value=defaults.frame_edge_color)
        self._color_row(sec, "Border:", self.legend_frame_edge_var, restyle)

        self.legend_frame_width_var = tk.StringVar(
            value=f"{defaults.frame_width:g}")
        self._spin_row(sec, "Border width:", self.legend_frame_width_var,
                       0.0, 6.0, 0.2, restyle)

        self.legend_rounded_var = tk.BooleanVar(value=defaults.rounded)
        self._check(sec, "Rounded corners", self.legend_rounded_var, restyle)

        self.legend_shadow_var = tk.BooleanVar(value=defaults.shadow)
        self._check(sec, "Drop shadow", self.legend_shadow_var, restyle)

    def _build_legend_text_group(self, tab, restyle, defaults) -> None:
        sec = self._collapsible(tab, "Text")

        self.legend_fontsize_var = tk.StringVar(value=f"{defaults.fontsize:g}")
        self._spin_row(sec, "Font size:", self.legend_fontsize_var,
                       4, 32, 1, restyle)

        self.legend_title_fontsize_var = tk.StringVar(
            value=f"{defaults.title_fontsize:g}")
        self._spin_row(sec, "Title font size:",
                       self.legend_title_fontsize_var, 4, 40, 1, restyle)

        self.legend_font_family_var = tk.StringVar(
            value=self._name_for(FONT_FAMILIES, defaults.font_family))
        self._named_combo(sec, "Font:", self.legend_font_family_var,
                          FONT_FAMILIES, restyle, width=12)

        self.legend_title_align_var = tk.StringVar(
            value=self._name_for(TITLE_ALIGNMENTS, defaults.title_align))
        self._named_combo(sec, "Title align:", self.legend_title_align_var,
                          TITLE_ALIGNMENTS, restyle, width=12)

        self.legend_label_color_var = tk.StringVar(value=defaults.label_color)
        self._color_row(sec, "Label colour:", self.legend_label_color_var,
                        restyle)
        self.legend_title_color_var = tk.StringVar(value=defaults.title_color)
        self._color_row(sec, "Title colour:", self.legend_title_color_var,
                        restyle)

        # Text styling for the labels and the title (bold / italic /
        # underline), applied independently to each.
        self.legend_label_bold_var = tk.BooleanVar(value=defaults.label_bold)
        self.legend_label_italic_var = tk.BooleanVar(
            value=defaults.label_italic)
        self.legend_label_underline_var = tk.BooleanVar(
            value=defaults.label_underline)
        self.legend_title_bold_var = tk.BooleanVar(value=defaults.title_bold)
        self.legend_title_italic_var = tk.BooleanVar(
            value=defaults.title_italic)
        self.legend_title_underline_var = tk.BooleanVar(
            value=defaults.title_underline)
        self._build_text_style_row(
            sec, "Label text:", self.legend_label_bold_var,
            self.legend_label_italic_var, self.legend_label_underline_var)
        self._build_text_style_row(
            sec, "Title text:", self.legend_title_bold_var,
            self.legend_title_italic_var, self.legend_title_underline_var)

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

    @staticmethod
    def _name_for(names: dict, value) -> str:
        """The display name for a stored value, for seeding a combo box."""
        for name, stored in names.items():
            if stored == value:
                return name
        return next(iter(names))

    def _open_kofi(self) -> None:
        import webbrowser

        webbrowser.open(KOFI_URL)

    # ------------------------------------------------------------- map tab

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
        # Persisted default DPI (also saved in the project). The picker in
        # the "Save map as..." dialog reads and updates it; format,
        # resolution and DPI are all chosen there.
        self.dpi_var = tk.StringVar(value="200")
        ttk.Button(sec, text="Save map as\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_save_image).pack(fill="x", pady=2)
        ttk.Button(sec, text="Export as code (Python/R)"
                            "\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_export_code).pack(fill="x", pady=2)

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

    # -------------------------------------------------------------- footer

    def _build_footer(self) -> None:
        """Persistent bar pinned to the bottom edge of the panel (below the
        notebook, so it shows on every tab): support and update actions."""
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=6, pady=(2, 4))
        ttk.Button(bar, text="\N{BLACK HEART SUIT} Support on Ko-fi",
                   command=self._open_kofi).pack(fill="x", pady=(2, 0))
        ttk.Button(bar, text="Check for updates\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_check_updates).pack(fill="x",
                                                           pady=(2, 0))

    # --------------------------------------------------------------- theme

    def update_theme(self) -> None:
        """Refresh non-ttk widgets after a theme switch."""
        style = ttk.Style()
        bg = style.lookup("TFrame", "background") or "white"
        fg = style.lookup("TLabel", "foreground") or "black"
        sel = style.lookup("TButton", "background", ["active"]) or "#005fb8"
        # Canvas backgrounds in every scrollable tab.
        for tab_id in self.notebook.tabs():
            outer = self.nametowidget(tab_id)
            for child in outer.winfo_children():
                if isinstance(child, tk.Canvas):
                    child.configure(background=bg)
        # Dataset listbox.
        self.dataset_list.configure(
            background=bg, foreground=fg,
            selectbackground=sel, selectforeground="white")

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

        def _num(var):
            try:
                return float(var.get())
            except (TypeError, ValueError):
                return None

        return _num(self.proj_lon0_var), _num(self.proj_lat0_var)

    def graticule_interval(self) -> float | None:
        return GRATICULE_CHOICES[self.graticule_var.get()]

    def orientation(self) -> str:
        """The renderer orientation key for the selected label."""
        return ORIENTATION_LABELS.get(self.orientation_var.get(), "landscape")

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

    @staticmethod
    def _value_of(names: dict, var: tk.StringVar, fallback):
        return names.get(var.get(), fallback)

    def legend_options(self) -> LegendOptions:
        """Every legend setting, as one options object for the renderer,
        the project file and the code export."""
        d = LegendOptions()
        return LegendOptions(
            show=self.legend_show_var.get(),
            title=self.legend_title_var.get().strip() or None,
            location=self.legend_loc_var.get(),
            hierarchy=self._value_of(HIERARCHY_MODES,
                                     self.legend_hierarchy_var, d.hierarchy),
            order=self._value_of(ENTRY_ORDERS, self.legend_order_var, d.order),
            counts=self.legend_counts_var.get(),
            count_format=self._value_of(COUNT_FORMATS,
                                        self.legend_count_format_var,
                                        d.count_format),
            blank_label=self.legend_blank_label_var.get() or d.blank_label,
            section_titles=self.legend_section_titles_var.get(),
            title_separator=self.legend_title_separator_var.get(),
            dataset_prefix=self.legend_dataset_prefix_var.get(),
            empty_groups=self.legend_empty_groups_var.get(),
            indent=int(self._number(self.legend_indent_var, 0, 12, d.indent)),
            bold_groups=self.legend_bold_groups_var.get(),
            group_spacer=self.legend_group_spacer_var.get(),
            group_swatch=self._value_of(GROUP_SWATCHES,
                                        self.legend_group_swatch_var,
                                        d.group_swatch),
            symbol_swatch_color=self.legend_symbol_color_var.get(),
            columns=int(self._number(self.legend_columns_var, 1, 6,
                                     d.columns)),
            label_spacing=self._number(self.legend_label_spacing_var, 0.0,
                                       4.0, d.label_spacing),
            column_spacing=self._number(self.legend_column_spacing_var, 0.0,
                                        8.0, d.column_spacing),
            handle_text_pad=self._optional_number(self.legend_handle_pad_var,
                                                  0.0, 4.0),
            handle_length=self._number(self.legend_handle_length_var, 0.0,
                                       8.0, d.handle_length),
            border_pad=self._number(self.legend_border_pad_var, 0.0, 4.0,
                                    d.border_pad),
            marker_scale=self._number(self.legend_marker_scale_var, 0.1, 6.0,
                                      d.marker_scale),
            frame=self.legend_frame_var.get(),
            frame_color=self.legend_frame_color_var.get(),
            frame_alpha=self._number(self.legend_frame_alpha_var, 0.0, 1.0,
                                     d.frame_alpha),
            frame_edge_color=self.legend_frame_edge_var.get(),
            frame_width=self._number(self.legend_frame_width_var, 0.0, 6.0,
                                     d.frame_width),
            rounded=self.legend_rounded_var.get(),
            shadow=self.legend_shadow_var.get(),
            fontsize=self._number(self.legend_fontsize_var, 4.0, 32.0,
                                  d.fontsize),
            title_fontsize=self._number(self.legend_title_fontsize_var, 4.0,
                                        40.0, d.title_fontsize),
            font_family=self._value_of(FONT_FAMILIES,
                                       self.legend_font_family_var,
                                       d.font_family),
            label_color=self.legend_label_color_var.get(),
            title_color=self.legend_title_color_var.get(),
            label_bold=self.legend_label_bold_var.get(),
            label_italic=self.legend_label_italic_var.get(),
            label_underline=self.legend_label_underline_var.get(),
            title_bold=self.legend_title_bold_var.get(),
            title_italic=self.legend_title_italic_var.get(),
            title_underline=self.legend_title_underline_var.get(),
            title_align=self._value_of(TITLE_ALIGNMENTS,
                                       self.legend_title_align_var,
                                       d.title_align),
        )

    def set_legend_options(self, options: LegendOptions) -> None:
        """Push a stored options object back into the widgets."""
        self.legend_show_var.set(options.show)
        self.legend_title_var.set(options.title or "")
        self.legend_loc_var.set(options.location)
        self.legend_hierarchy_var.set(
            self._name_for(HIERARCHY_MODES, options.hierarchy))
        self.legend_order_var.set(self._name_for(ENTRY_ORDERS, options.order))
        self.legend_counts_var.set(options.counts)
        self.legend_count_format_var.set(
            self._name_for(COUNT_FORMATS, options.count_format))
        self.legend_blank_label_var.set(options.blank_label)
        self.legend_section_titles_var.set(options.section_titles)
        self.legend_title_separator_var.set(options.title_separator)
        self.legend_dataset_prefix_var.set(options.dataset_prefix)
        self.legend_empty_groups_var.set(options.empty_groups)
        self.legend_indent_var.set(str(options.indent))
        self.legend_bold_groups_var.set(options.bold_groups)
        self.legend_group_spacer_var.set(options.group_spacer)
        self.legend_group_swatch_var.set(
            self._name_for(GROUP_SWATCHES, options.group_swatch))
        self.legend_columns_var.set(str(options.columns))
        self.legend_label_spacing_var.set(f"{options.label_spacing:g}")
        self.legend_column_spacing_var.set(f"{options.column_spacing:g}")
        self.legend_handle_pad_var.set(
            "" if options.handle_text_pad is None
            else f"{options.handle_text_pad:g}")
        self.legend_handle_length_var.set(f"{options.handle_length:g}")
        self.legend_border_pad_var.set(f"{options.border_pad:g}")
        self.legend_marker_scale_var.set(f"{options.marker_scale:g}")
        self.legend_frame_var.set(options.frame)
        self.legend_frame_alpha_var.set(f"{options.frame_alpha:g}")
        self.legend_frame_width_var.set(f"{options.frame_width:g}")
        self.legend_rounded_var.set(options.rounded)
        self.legend_shadow_var.set(options.shadow)
        self.legend_fontsize_var.set(f"{options.fontsize:g}")
        self.legend_title_fontsize_var.set(f"{options.title_fontsize:g}")
        self.legend_font_family_var.set(
            self._name_for(FONT_FAMILIES, options.font_family))
        self.legend_label_bold_var.set(options.label_bold)
        self.legend_label_italic_var.set(options.label_italic)
        self.legend_label_underline_var.set(options.label_underline)
        self.legend_title_bold_var.set(options.title_bold)
        self.legend_title_italic_var.set(options.title_italic)
        self.legend_title_underline_var.set(options.title_underline)
        self.legend_title_align_var.set(
            self._name_for(TITLE_ALIGNMENTS, options.title_align))
        # Colours last: the swatch buttons have to be repainted, not just set.
        for var, value in ((self.legend_symbol_color_var,
                            options.symbol_swatch_color),
                           (self.legend_frame_color_var, options.frame_color),
                           (self.legend_frame_edge_var,
                            options.frame_edge_color),
                           (self.legend_label_color_var, options.label_color),
                           (self.legend_title_color_var, options.title_color)):
            var.set(value)
            button = self._color_buttons.get(str(var))
            if button is not None and value:
                button.config(bg=value, activebackground=value)

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
