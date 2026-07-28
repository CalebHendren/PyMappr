"""Legend content and options.

Two things live here:

* :class:`LegendOptions` - every setting that controls how the legend is
  built and drawn, in one dataclass. It travels from the control panel
  through the app to the renderer, into saved projects, and into exported
  scripts, so a new option is one field rather than one more parameter on
  a function that already had fifteen.
* the builders that turn a styled dataset into legend rows.

Splitting the rows out of :mod:`pymappr.styles` keeps that module about
styling points; this one is about describing them. Everything here is
pure - it returns rows, it never touches matplotlib - which is what lets
the app, the exported Python script and the tests share one implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields

import pandas as pd

from pymappr.styles import (PointStyle, apply_override, owner_map,
                            resolve_nesting)

__all__ = ["NEUTRAL_MARKER_COLOR", "LEGEND_LOCATIONS", "HIERARCHY_MODES",
           "ENTRY_ORDERS", "COUNT_FORMATS", "GROUP_SWATCHES", "FONT_FAMILIES",
           "TITLE_ALIGNMENTS", "LegendOptions", "legend_counts",
           "legend_sections", "order_labels", "ROW_SEP", "row_key",
           "apply_override", "override_label", "is_hidden", "manual_order"]

# Legend rows are identified by a tagged key - the same tagging
# :func:`legend_counts` uses - so a value that appears in both the color and
# the symbol column cannot have one row's customization land on the other.
# NUL separates the parts because it cannot occur in a data value, unlike
# "/" or ":" which routinely do.
ROW_SEP = "\x00"


def row_key(kind: str, *parts: str) -> str:
    """A legend row's identity: ``row_key("pair", genus, species)``.

    *kind* is ``"group"`` (a group-by row), ``"color"``, ``"symbol"``, or
    ``"pair"`` (a nested key's leaf).
    """
    return ROW_SEP.join((kind,) + tuple(str(p) for p in parts))

# Marker color used in the legend's "symbol" key, where shape (not color)
# carries the meaning. Only meaningful for crossed data, where a shape really
# does appear in every color; nested data draws its symbols in the color of
# the group they belong to.
NEUTRAL_MARKER_COLOR = "#555555"

# Every location matplotlib accepts. "best" keeps out of the way of the data;
# the rest pin the legend to an edge or corner. Dragging overrides all of them.
LEGEND_LOCATIONS = ["best", "upper right", "upper left", "lower left",
                    "lower right", "upper center", "lower center",
                    "center left", "center right", "center"]

# Display name -> stored value, for the control panel's combo boxes. Storing
# the short value keeps saved projects readable and independent of wording.
HIERARCHY_MODES = {"Auto (detect)": "auto",
                   "Always nest": "always",
                   "Never nest": "never"}

ENTRY_ORDERS = {"As in data": "data",
                "A \N{EN DASH} Z": "az",
                "Z \N{EN DASH} A": "za",
                "Count, high to low": "count_desc",
                "Count, low to high": "count_asc",
                "Manual": "manual"}

# Keys are samples rather than descriptions - the shape of the result is
# easier to pick from than a name for it.
COUNT_FORMATS = {"(12)": "(n)", "12": "n", "(12, 34%)": "(n, %)", "34%": "%"}

GROUP_SWATCHES = {"Circle": "circle",
                  "Match first child": "child",
                  "No swatch": "none"}

FONT_FAMILIES = {"Default": "", "Sans-serif": "sans-serif",
                 "Serif": "serif", "Monospace": "monospace"}

TITLE_ALIGNMENTS = {"Left": "left", "Centre": "center", "Right": "right"}


_UNSET = object()


def _coerce(value, annotation):
    """A stored value as the type its field declares, or ``_UNSET`` when it
    cannot be read that way and the default should stand.

    Annotations are strings here (``from __future__ import annotations``), so
    this matches on the text rather than the type object.
    """
    text = str(annotation)
    optional = "None" in text
    if value is None:
        return None if optional else _UNSET
    try:
        if text.startswith("bool"):
            return bool(value)
        if text.startswith("int"):
            return int(float(value))
        if text.startswith("float"):
            return float(value)
        return str(value)
    except (TypeError, ValueError):
        return _UNSET


@dataclass
class LegendOptions:
    """Everything the user can set about the legend.

    Defaults reproduce the legend as it was before any of this was
    configurable, so an existing project that stores none of these keys
    draws exactly as it always did.
    """

    # -- what is shown at all. "show" rather than "visible" so projects and
    #    exported scripts written before this dataclass keep loading.
    show: bool = True
    title: str | None = None
    location: str = "best"

    # -- content: these change the rows themselves, so a change here has to
    #    rebuild the groups rather than merely restyle the legend.
    hierarchy: str = "auto"          # auto | always | never
    order: str = "data"              # data | az | za | count_desc | count_asc
    counts: bool = False
    count_format: str = "(n)"        # (n) | n | (n, %) | %
    blank_label: str = "(blank)"
    section_titles: bool = True
    title_separator: str = " / "
    dataset_prefix: bool = True
    empty_groups: bool = False

    # -- nested keys
    indent: int = 3
    bold_groups: bool = True
    group_spacer: bool = True
    group_swatch: str = "circle"     # circle | child | none
    symbol_swatch_color: str = NEUTRAL_MARKER_COLOR

    # -- layout
    columns: int = 1
    label_spacing: float = 0.5
    column_spacing: float = 2.0
    # None = match the legend kind, which is what the two draw paths did
    # before this was settable: tighter for a sectioned key, matplotlib's
    # roomier default for a plain one.
    handle_text_pad: float | None = None
    handle_length: float = 2.0
    border_pad: float = 0.4
    marker_scale: float = 1.0

    # -- frame
    frame: bool = True
    frame_color: str = "#ffffff"
    frame_alpha: float = 0.85
    frame_edge_color: str = "#cccccc"
    frame_width: float = 0.8
    rounded: bool = True
    shadow: bool = False

    # -- text
    fontsize: float = 8.0
    title_fontsize: float = 9.0
    font_family: str = ""            # "" = inherit matplotlib's default
    label_color: str = "#000000"
    title_color: str = "#000000"
    label_bold: bool = False
    label_italic: bool = False
    label_underline: bool = False
    title_bold: bool = True
    title_italic: bool = False
    title_underline: bool = False
    title_align: str = "center"      # left | center | right

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "LegendOptions":
        """Build from a stored dict, ignoring keys we no longer know and
        defaulting the ones an older project never wrote.

        Values are coerced to the field's type: projects saved before this
        dataclass existed hold the raw Tk variable values, where a font size
        is the string ``"8"`` rather than a number.
        """
        data = dict(data or {})
        values = {}
        for field in fields(cls):
            if field.name not in data:
                continue
            coerced = _coerce(data[field.name], field.type)
            if coerced is not _UNSET:
                values[field.name] = coerced
        return cls(**values)

    # -- derived helpers ---------------------------------------------------

    @property
    def orders_by_count(self) -> bool:
        """Count-based ordering needs the counts even when they are not
        shown, so the app has to compute them either way."""
        return self.order in ("count_desc", "count_asc")

    def indent_for(self, depth: int) -> str:
        return " " * (self.indent * (depth + 1))

    def pad_for(self, sectioned: bool) -> float:
        if self.handle_text_pad is not None:
            return float(self.handle_text_pad)
        return 0.4 if sectioned else 0.8


# --------------------------------------------------------------- overrides

# A per-row customization is a plain dict so it serializes straight into a
# project file. Every field is optional: an absent one means "whatever the
# styling rules worked out", which is what keeps a customized row following
# a palette change it did not ask to opt out of.
#
#   label  - replacement text, or None/"" to use the data value
#   hidden - leave the row out of the legend (the points still draw)
#   order  - position under manual ordering
#   color / marker / size - style overrides

def override_label(override: dict | None) -> str | None:
    """A row's replacement text, or None to use the data value."""
    if not override:
        return None
    label = override.get("label")
    return str(label) if label else None


def is_hidden(override: dict | None) -> bool:
    return bool(override and override.get("hidden"))


def manual_order(override: dict | None) -> int:
    """Where a row sits under manual ordering; unplaced rows sort last."""
    if not override or override.get("order") is None:
        return 1 << 30
    try:
        return int(override["order"])
    except (TypeError, ValueError):
        return 1 << 30


# ------------------------------------------------------------------ counts

def legend_counts(frame: pd.DataFrame, color_key: str | None,
                  symbol_key: str | None) -> dict:
    """Point counts for legend rows.

    Keys are tagged by which channel they count - ``("color", value)``,
    ``("symbol", value)``, and ``("pair", color, symbol)`` for the leaf rows
    of a nested key - so a value that appears in both columns (two "unknown"s,
    say) cannot have one count overwrite the other. ``("total",)`` carries the
    row count the percentages are taken against.

    Pass the frame that is actually drawn (the filtered one, in the app) so
    the numbers agree with the map.
    """
    counts: dict = {}
    if frame.empty:
        return counts
    counts[("total",)] = int(len(frame))
    for tag, key in (("color", color_key), ("symbol", symbol_key)):
        if key and key in frame.columns:
            for value, n in frame[key].fillna("").value_counts().items():
                counts[(tag, value)] = int(n)
    if (color_key and symbol_key and color_key in frame.columns
            and symbol_key in frame.columns):
        pairs = frame[[color_key, symbol_key]].fillna("")
        for (cval, sval), n in pairs.value_counts().items():
            counts[("pair", cval, sval)] = int(n)
    return counts


def _legend_label(value: str, counts: dict, key, options: LegendOptions,
                  override: dict | None = None) -> str:
    """A legend row's text: the value (or the name the user gave it, or a
    stand-in when it is blank), with its count appended in the chosen
    format. A renamed row still gets its count - the rename is about what
    the row is called, not about dropping its numbers."""
    label = override_label(override) or value or options.blank_label
    if not options.counts:
        return label
    n = counts.get(key)
    if n is None:
        return label
    total = counts.get(("total",), 0)
    pct = (100.0 * n / total) if total else 0.0
    if options.count_format == "n":
        return f"{label} {n}"
    if options.count_format == "(n, %)":
        return f"{label} ({n}, {pct:.0f}%)"
    if options.count_format == "%":
        return f"{label} {pct:.0f}%"
    return f"{label} ({n})"


# ----------------------------------------------------------------- ordering

def order_labels(values, order: str, count_of=None) -> list:
    """Sort legend row values.

    Only the legend is reordered, never the color or symbol maps: those are
    keyed by first appearance and reshuffling them would repaint the map.
    Ties in a count sort fall back to the label so the result is stable.
    """
    values = list(values)
    if order == "az":
        return sorted(values, key=lambda v: (v or "").casefold())
    if order == "za":
        return sorted(values, key=lambda v: (v or "").casefold(), reverse=True)
    if order in ("count_desc", "count_asc"):
        count_of = count_of or (lambda _v: 0)
        sign = -1 if order == "count_desc" else 1
        return sorted(values,
                      key=lambda v: (sign * count_of(v), (v or "").casefold()))
    return values


def _ordered_rows(values, options: LegendOptions, count_of, override_of):
    """Legend row values in display order.

    Manual order is separate from the sort modes: it is whatever the user
    dragged the rows into, and rows they never touched fall to the end in
    their original order.
    """
    values = list(values)
    if options.order == "manual":
        return sorted(values, key=lambda v: (manual_order(override_of(v)),
                                             values.index(v)))
    return order_labels(values, options.order, count_of)


# ----------------------------------------------------------------- sections

def legend_sections(frame: pd.DataFrame, color_key: str | None,
                    symbol_key: str | None, color_map: dict[str, str],
                    symbol_map: dict[str, str], color_label: str,
                    symbol_label: str, shown_colors: set | None = None,
                    shown_symbols: set | None = None,
                    counts: dict | None = None, prefix: str = "",
                    options: LegendOptions | None = None,
                    overrides: dict | None = None) -> list:
    """Legend sections for a dataset styled by a color and a symbol column.

    Returns ``[(title, [(label, PointStyle | None, depth), ...]), ...]``,
    where *depth* indents a row beneath the one above it and a ``None`` style
    means the row takes no swatch.

    When the symbol column nests inside the color column (genus/species) the
    result is a single nested key: each symbol value sits under the color
    group it belongs to, drawn in the marker and color it has on the map.
    Two independent keys would imply ``colors x symbols`` combinations when
    only ``symbols`` of them exist, and would leave the reader to work out
    which color each symbol goes with by hunting for a point on the map.

    When the columns genuinely cross, the two keys stay independent and the
    symbol swatches are neutral - there a shape really does appear in every
    color, so no single color would be honest.

    Whether the columns count as nesting is the user's call via
    ``options.hierarchy``; ``"auto"`` detects it as before.

    *shown_colors* / *shown_symbols* limit the rows to the values still
    visible under a filter (None = no filtering).

    *overrides* maps a :func:`row_key` to that row's customization - a
    replacement label, a hidden flag, a manual position, and pinned
    color/marker/size.
    """
    options = options or LegendOptions()
    counts = counts or {}
    overrides = overrides or {}
    if resolve_nesting(frame, color_key, symbol_key, options.hierarchy):
        return _nested_sections(frame, color_key, symbol_key, color_map,
                                symbol_map, shown_colors, shown_symbols,
                                counts, prefix, color_label, symbol_label,
                                options, overrides)
    return _crossed_sections(color_map, symbol_map, shown_colors,
                             shown_symbols, counts, prefix, color_label,
                             symbol_label, options, overrides)


def _group_swatch(color: str, kids: list, symbol_map: dict,
                  options: LegendOptions):
    """The swatch for a nested key's group row: a plain circle, the shape of
    its first child, or nothing at all."""
    if options.group_swatch == "none":
        return None
    marker = "Circle"
    if options.group_swatch == "child" and kids:
        marker = symbol_map.get(kids[0], "Circle")
    return PointStyle(color=color, marker=marker)


def _nested_sections(frame, color_key, symbol_key, color_map, symbol_map,
                     shown_colors, shown_symbols, counts, prefix,
                     color_label, symbol_label, options, overrides) -> list:
    owner = owner_map(frame, symbol_key, color_key)
    children: dict[str, list[str]] = {value: [] for value in color_map}
    for value in symbol_map:
        if shown_symbols is None or value in shown_symbols:
            children.setdefault(owner.get(value, ""), []).append(value)
    entries: list = []
    parent_of = {v: overrides.get(row_key("color", v)) for v in color_map}
    parents = _ordered_rows(color_map.keys(), options,
                            lambda v: counts.get(("color", v), 0),
                            parent_of.get)
    # A childless group means the filter hid everything inside it, so it goes
    # too - but only when a filter is actually running. Forcing nesting onto
    # crossed columns also leaves groups childless, because each symbol value
    # is claimed by the first group it appears under; dropping those would
    # take colours off the legend that are still drawn on the map.
    filtering = shown_symbols is not None
    for value in parents:
        color = color_map[value]
        parent = parent_of.get(value)
        kids = children.get(value, [])
        if shown_colors is not None and value not in shown_colors:
            continue
        if not kids and filtering and not options.empty_groups:
            continue
        leaf_of = {k: overrides.get(row_key("pair", value, k)) for k in kids}
        kids = _ordered_rows(kids, options,
                             lambda k, p=value: counts.get(("pair", p, k), 0),
                             leaf_of.get)
        # Hiding a group hides the block it heads: its children are drawn in
        # its colour, so leaving them behind would orphan them.
        if is_hidden(parent):
            continue
        visible = [k for k in kids if not is_hidden(leaf_of.get(k))]
        entries.append(
            (_legend_label(value, counts, ("color", value), options, parent),
             apply_override(
                 _group_swatch(color, visible, symbol_map, options), parent),
             0))
        entries += [
            (_legend_label(kid, counts, ("pair", value, kid), options,
                           leaf_of.get(kid)),
             apply_override(PointStyle(color=color, marker=symbol_map[kid]),
                            leaf_of.get(kid)),
             1)
            for kid in visible]
    if not entries:
        return []
    return [(_section_title(options, prefix, color_label, symbol_label),
             entries)]


def _section_title(options: LegendOptions, prefix: str, *parts: str) -> str:
    """A section's heading, or "" when headings are switched off.

    The dataset prefix rides on the heading, so with headings off it has
    nothing to attach to and must go too - otherwise the section is titled
    with a bare "beetles: ".
    """
    if not options.section_titles:
        return ""
    joined = options.title_separator.join(p for p in parts if p)
    return prefix + (joined or "Key")


def _crossed_sections(color_map, symbol_map, shown_colors, shown_symbols,
                      counts, prefix, color_label, symbol_label,
                      options, overrides) -> list:
    sections = []

    def build(source, kind, shown, base_style, label):
        picked = [v for v in source if shown is None or v in shown]
        of = {v: overrides.get(row_key(kind, v)) for v in picked}
        picked = _ordered_rows(picked, options,
                               lambda v: counts.get((kind, v), 0), of.get)
        entries = [(_legend_label(v, counts, (kind, v), options, of.get(v)),
                    apply_override(base_style(v), of.get(v)), 0)
                   for v in picked if not is_hidden(of.get(v))]
        if entries:
            sections.append((_section_title(options, prefix, label), entries))

    if color_map:
        build(color_map, "color", shown_colors,
              lambda v: PointStyle(color=color_map[v], marker="Circle"),
              color_label or "Color")
    if symbol_map:
        build(symbol_map, "symbol", shown_symbols,
              lambda v: PointStyle(color=options.symbol_swatch_color,
                                   marker=symbol_map[v]),
              symbol_label or "Symbol")
    return sections
