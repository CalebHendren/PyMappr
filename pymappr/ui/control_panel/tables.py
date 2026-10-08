"""The control panel's fixed tables: its width, the display names
of each choice, and the rows of the Layers, Labels and Legend tabs."""

from __future__ import annotations

from pymappr.geo.layers import CONTINENT_EXTENTS
from pymappr.styling.legend import (COUNT_FORMATS, ENTRY_ORDERS, FONT_FAMILIES,
                                    GROUP_SWATCHES, HIERARCHY_MODES,
                                    LEGEND_LOCATIONS, TITLE_ALIGNMENTS)

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
# Display label -> InsetOptions.region / .projection / .ocean value.
INSET_REGION_LABELS = {
    "State / province": "state", "Country": "country",
    "Around the map": "around",
    **{name: name for name in CONTINENT_EXTENTS},
    "Custom": "custom"}
INSET_PROJECTION_LABELS = {"Same as map": "same",
                           "Equirectangular": "Equirectangular",
                           "Robinson": "Robinson",
                           "Globe": "Globe"}
INSET_OCEAN_LABELS = {"None": "none", "Grey": "grey", "Blue": "blue"}

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
