"""Tabbed side panel holding every map control.

With ~30 layer toggles the panel is organized as a notebook of five
scrollable tabs - Data (CSV, styling), Legend, Map (view, projection,
graticule, compass, export), Layers (every Natural Earth layer, grouped),
and Labels. The panel owns the Tk variables and forwards changes to the
app's handler methods; the app owns the renderer and the data.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import colorchooser, ttk

from pymappr.geo.layers import CONTINENT_EXTENTS
from pymappr.geo.projections import (PROJECTIONS, default_origin,
                                     has_custom_origin, normalize_origin)
from pymappr.styling.decorations import (CORNERS, CompassOptions,
                                         ScaleBarOptions)
from pymappr.styling.legend import (COUNT_FORMATS, ENTRY_ORDERS, FONT_FAMILIES,
                                    GROUP_SWATCHES, HIERARCHY_MODES,
                                    LEGEND_LOCATIONS, TITLE_ALIGNMENTS,
                                    LegendOptions)
from pymappr.styling.styles import (DEFAULT_PALETTE_NAME, PALETTES,
                                    POINT_EDGE_COLOR, POINT_EDGE_WIDTH,
                                    palette_for)
from pymappr.ui.save_image import AS_ON_SCREEN

PANEL_WIDTH = 320
# How long typing has to pause before a text or number box redraws the map.
TYPING_PAUSE_MS = 300

GRATICULE_CHOICES = {"Off": None, "1\N{DEGREE SIGN}": 1.0,
                     "5\N{DEGREE SIGN}": 5.0, "10\N{DEGREE SIGN}": 10.0}
# Display label -> renderer orientation key.
ORIENTATION_LABELS = {"Landscape": "landscape", "Portrait": "portrait"}
# Display label -> ScaleBarOptions.units / .style / .length_mode value.
SCALE_UNIT_LABELS = {"Kilometres": "km", "Miles": "mi", "Both": "both"}
SCALE_STYLE_LABELS = {"Segmented": "segmented", "Plain bar": "plain"}
SCALE_LENGTH_LABELS = {"Automatic": "auto", "Fixed": "fixed"}
COMPASS_STYLE_LABELS = {"Arrow with N": "arrow", "Filled triangle": "triangle"}

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


# Every legend setting, grouped as the Legend tab shows it: (section title,
# expanded, rows), where expanded is None for an always-open section and
# otherwise whether the foldable section starts open. A row is
# (LegendOptions field, kind, label, extra):
#   check  - a tick box
#   combo  - a drop-down of stored values (extra: the values)
#   choice - a drop-down of display names (extra: {name: stored value})
#   text   - a text box (extra: its width); blank means the default
#   number - a spin box (extra: (low, high, step)), clamped when read
#   color  - a colour swatch
#   style  - Bold / Italic / Underline toggles for <field>_bold and so on
#   note   - grey help text (label is the text; no field)
# Building the widgets, reading them and restoring them all walk this one
# table, so a new setting is one row here plus its LegendOptions field.
LEGEND_ROWS = [
    ("Legend", None, [
        ("show", "check", "Show legend", None),
        ("location", "combo", "Position:", LEGEND_LOCATIONS),
        ("show_title", "check", "Show a title", None),
        ("title", "text", "Title:", 18),
        (None, "note", "(blank = use the Group by column name)", None),
    ]),
    ("Rows and order", True, [
        ("hierarchy", "choice", "Hierarchy:", HIERARCHY_MODES),
        (None, "note", "Nesting also lets shapes repeat across colour "
                       "groups, so a hierarchy needs fewer of them.", None),
        ("order", "choice", "Order:", ENTRY_ORDERS),
        ("counts", "check", "Show point counts", None),
        ("count_format", "choice", "Counts look like:", COUNT_FORMATS),
        ("blank_label", "text", "Blank values:", 12),
        ("section_titles", "check", "Show section titles", None),
        ("title_separator", "text", "Title separator:", 8),
        ("dataset_prefix", "check",
         "Prefix sections with the dataset name", None),
        ("empty_groups", "check", "Keep groups with no visible rows", None),
    ]),
    ("Nested keys", False, [
        ("indent", "number", "Indent (spaces):", (0, 12, 1)),
        ("bold_groups", "check", "Bold the group rows", None),
        ("group_spacer", "check", "Blank row between groups", None),
        ("group_swatch", "choice", "Group swatch:", GROUP_SWATCHES),
        ("symbol_swatch_color", "color", "Crossed symbol colour:", None),
        (None, "note", "Used only when the columns cross, where a shape "
                       "appears in every colour.", None),
    ]),
    ("Layout", False, [
        ("columns", "number", "Columns:", (1, 6, 1)),
        ("label_spacing", "number", "Row spacing:", (0.0, 4.0, 0.1)),
        ("column_spacing", "number", "Column spacing:", (0.0, 8.0, 0.5)),
        # Scales the sample symbols in the legend, not the map's points.
        ("marker_scale", "number", "Marker size:", (0.1, 6.0, 0.25)),
        ("handle_text_pad", "number", "Swatch gap:", (0.0, 4.0, 0.1)),
        (None, "note", "(blank = automatic)", None),
        ("handle_length", "number", "Swatch width:", (0.0, 8.0, 0.5)),
        ("border_pad", "number", "Inner padding:", (0.0, 4.0, 0.1)),
    ]),
    ("Frame", False, [
        ("frame", "check", "Draw legend frame", None),
        ("frame_color", "color", "Fill:", None),
        ("frame_alpha", "number", "Fill opacity:", (0.0, 1.0, 0.05)),
        ("frame_edge_color", "color", "Border:", None),
        ("frame_width", "number", "Border width:", (0.0, 6.0, 0.2)),
        ("rounded", "check", "Rounded corners", None),
        ("shadow", "check", "Drop shadow", None),
    ]),
    ("Text", False, [
        ("fontsize", "number", "Font size:", (4, 32, 1)),
        ("title_fontsize", "number", "Title font size:", (4, 40, 1)),
        ("font_family", "choice", "Font:", FONT_FAMILIES),
        ("title_align", "choice", "Title align:", TITLE_ALIGNMENTS),
        ("label_color", "color", "Label colour:", None),
        ("title_color", "color", "Title colour:", None),
        ("label", "style", "Label text:", None),
        ("title", "style", "Title text:", None),
    ]),
]


def _style_fields(prefix: str) -> list[tuple[str, str]]:
    return [(f"{prefix}_{name}", text) for name, text
            in (("bold", "B"), ("italic", "I"), ("underline", "U"))]


def _legend_fields() -> list[tuple[str, str, object]]:
    """(field, kind, extra) for every LegendOptions field on the panel."""
    fields = []
    for _title, _expanded, rows in LEGEND_ROWS:
        for field, kind, _label, extra in rows:
            if kind == "style":
                fields += [(name, "check", None)
                           for name, _text in _style_fields(field)]
            elif kind != "note":
                fields.append((field, kind, extra))
    return fields


def name_for(names: dict, value) -> str:
    """The display name a ``{name: stored value}`` mapping shows for
    *value*, falling back to the first name."""
    for name, stored in names.items():
        if stored == value:
            return name
    return next(iter(names))


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

        self._build_presets_section(data_tab)
        self._build_data_section(data_tab)
        self._build_legend_section(legend_tab)

        self._build_view_section(map_tab)
        self._build_decorations_section(map_tab)
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

    def _after_typing(self, command, delay_ms: int = TYPING_PAUSE_MS):
        """A key handler that calls *command* once typing pauses, rather
        than on every keystroke - each call redraws the map."""
        pending: list[str] = []

        def schedule(_event=None) -> None:
            if pending:
                self.after_cancel(pending.pop())
            pending.append(self.after(
                delay_ms, lambda: (pending.clear(), command())))

        return schedule

    def _spin_row(self, parent, label: str, var: tk.StringVar, from_, to,
                  increment, command, width: int = 6):
        """A labelled spinbox that reports at once on an arrow click and
        once typing pauses."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        spin = ttk.Spinbox(row, from_=from_, to=to, increment=increment,
                           width=width, textvariable=var, command=command)
        spin.pack(side="right")
        spin.bind("<KeyRelease>", self._after_typing(command))
        return spin

    def _entry_row(self, parent, label: str, var: tk.StringVar, command,
                   width: int = 14):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        entry = ttk.Entry(row, textvariable=var, width=width)
        entry.pack(side="right")
        entry.bind("<KeyRelease>", self._after_typing(command))
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

    # ------------------------------------------------------------ data tab

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
        ttk.Label(sec, text="A preset keeps every setting except your data "
                            "and zoom. Standard: black & white outlined "
                            "points, an italic boxed legend, and 600 DPI "
                            "export 17 cm wide, the Zootaxa / Phytotaxa "
                            "page.",
                  wraplength=PANEL_WIDTH - 60,
                  foreground="#666666").pack(anchor="w")

    def set_preset_names(self, names: list[str], selected: str) -> None:
        self.preset_box.configure(values=names)
        self.preset_var.set(selected if selected in names else names[0])

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
                   command=self.app.on_open_kofi).pack(fill="x", pady=(2, 0))
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
