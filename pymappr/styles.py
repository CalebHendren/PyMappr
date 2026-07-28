"""Point styling: per-group color / marker / size used for map and legend."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

__all__ = ["PointStyle", "MARKERS", "OPEN_SUFFIX", "DEFAULT_PALETTE",
           "group_points", "default_styles", "attribute_style_maps",
           "style_by_attributes", "NEUTRAL_MARKER_COLOR",
           "LEGIBLE_MARKER_LIMIT", "nests_within", "marker_load",
           "legend_counts", "legend_sections"]

# Marker color used in the legend's "symbol" key, where shape (not color)
# carries the meaning. Only meaningful for crossed data, where a shape really
# does appear in every color; nested data draws its symbols in the color of
# the group they belong to.
NEUTRAL_MARKER_COLOR = "#555555"

# How many distinct shapes stay tellable apart at map point sizes. MARKER_CYCLE
# runs much longer, but past roughly this many the tail (triangle down, thin
# diamond, octagon...) is guesswork in a crowded cluster, so the app says so
# rather than quietly drawing an unreadable map.
LEGIBLE_MARKER_LIMIT = 6

# Display name -> matplotlib marker. Every shape comes in a solid and an
# open (outline-only) version; openness is a fill style, not a different
# matplotlib marker, so both names map to the same marker code.
OPEN_SUFFIX = " (open)"

_BASE_MARKERS = {
    "Circle": "o",
    "Square": "s",
    "Triangle": "^",
    "Triangle down": "v",
    "Triangle left": "<",
    "Triangle right": ">",
    "Diamond": "D",
    "Thin diamond": "d",
    "Star": "*",
    "Plus": "P",
    "X": "X",
    "Pentagon": "p",
    "Hexagon": "h",
    "Octagon": "8",
    "Dot": ".",
}

MARKERS = dict(_BASE_MARKERS)
MARKERS.update({name + OPEN_SUFFIX: marker
                for name, marker in _BASE_MARKERS.items()})

# Marker cycle used when symbols vary per group (color-by grouping or the
# "vary symbols" option): visually distinct shapes first.
MARKER_CYCLE = ["Circle", "Square", "Triangle", "Diamond", "Star", "Plus",
                "X", "Pentagon", "Triangle down", "Hexagon", "Thin diamond",
                "Triangle left", "Octagon", "Triangle right"]

DEFAULT_PALETTE = [
    "#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd",
    "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f",
]


@dataclass
class PointStyle:
    color: str = "#d62728"
    marker: str = "Circle"  # key into MARKERS
    size: float = 30.0      # matplotlib scatter area (points^2)

    @property
    def mpl_marker(self) -> str:
        return MARKERS.get(self.marker, "o")

    @property
    def is_open(self) -> bool:
        """Open markers draw only the outline in the style's color."""
        return self.marker.endswith(OPEN_SUFFIX)


def group_points(frame: pd.DataFrame, group_by: str | None):
    """Split a point frame into ordered (label, sub_frame) pairs.

    *group_by* is a name column key (``"name1"``, ``"name2"``, ``"name3"``,
    ...) or ``None`` (single group). Groups are ordered by first appearance
    in the file.
    """
    if frame.empty:
        return []
    if group_by is None or group_by not in frame.columns:
        return [("All points", frame)]
    values = frame[group_by].fillna("")
    labels = list(dict.fromkeys(values))
    groups = []
    for label in labels:
        sub = frame[values == label]
        groups.append((label if label else "(blank)", sub))
    return groups


def default_styles(labels: list[str],
                   color_keys: list[str] | None = None,
                   vary_symbols: bool = False,
                   palette_offset: int = 0) -> dict[str, PointStyle]:
    """Assign default styles to the given group labels.

    Without *color_keys*, palette colors are assigned round-robin and every
    group uses a circle (symbols also cycle if *vary_symbols* is set).

    With *color_keys* (one value per label, e.g. the "Color by" column),
    groups sharing a color key share a color - Felines one color, Canines
    another - while the symbol cycles within each color group, so domestic
    cats, lions and cheetahs each get their own shape.

    *palette_offset* starts the color rotation further into the palette,
    so several datasets shown on one map get distinct default colors.
    """
    if color_keys is None:
        return {
            label: PointStyle(
                color=DEFAULT_PALETTE[(i + palette_offset)
                                      % len(DEFAULT_PALETTE)],
                marker=(MARKER_CYCLE[i % len(MARKER_CYCLE)]
                        if vary_symbols else "Circle"))
            for i, label in enumerate(labels)
        }

    color_order = list(dict.fromkeys(color_keys))
    seen_in_group: dict[str, int] = {}
    styles: dict[str, PointStyle] = {}
    for label, key in zip(labels, color_keys):
        shape_idx = seen_in_group.get(key, 0)
        seen_in_group[key] = shape_idx + 1
        color_idx = color_order.index(key) + palette_offset
        styles[label] = PointStyle(
            color=DEFAULT_PALETTE[color_idx % len(DEFAULT_PALETTE)],
            marker=MARKER_CYCLE[shape_idx % len(MARKER_CYCLE)])
    return styles


def nests_within(frame: pd.DataFrame, outer_key: str | None,
                 inner_key: str | None) -> bool:
    """True when every value of *inner_key* occurs under exactly one value of
    *outer_key* - a hierarchy (genus/species), not a cross-product.

    Nesting is what makes it safe to reuse shapes across color groups and to
    draw the legend as one nested list instead of two independent keys.
    """
    if not outer_key or not inner_key or frame.empty:
        return False
    if outer_key not in frame.columns or inner_key not in frame.columns:
        return False
    outer = frame[outer_key].fillna("")
    inner = frame[inner_key].fillna("")
    return bool(outer.groupby(inner.values).nunique().max() <= 1)


def marker_load(frame: pd.DataFrame, color_key: str | None,
                symbol_key: str | None) -> int:
    """How many shapes the reader has to tell apart on the map.

    Under nesting that is the largest number of symbol values inside any one
    color group (shapes restart per group); otherwise every symbol value needs
    its own shape. Compare against :data:`LEGIBLE_MARKER_LIMIT`.
    """
    if not symbol_key or symbol_key not in frame.columns or frame.empty:
        return 0
    symbols = frame[symbol_key].fillna("")
    if not nests_within(frame, color_key, symbol_key):
        return int(symbols.nunique())
    colors = frame[color_key].fillna("")
    return int(symbols.groupby(colors.values).nunique().max())


def attribute_style_maps(frame: pd.DataFrame, color_key: str | None,
                         symbol_key: str | None):
    """Value -> color and value -> marker maps for two-attribute styling.

    Colors are assigned to the *color_key* column's values (round-robin
    through the palette) and markers to the *symbol_key* column's values,
    both ordered by first appearance. Deriving these from the full dataset
    keeps the legend and colors stable while points are filtered. Either
    key may be None, giving an empty map for that channel.

    When the symbol column nests inside the color column the marker cycle
    restarts for each color group, exactly as :func:`default_styles` does for
    group-by mode: three genera of three species each then need three shapes
    rather than nine, and the colors keep the pairs apart. A flat map still
    describes that, because nesting means each symbol value has exactly one
    color - so the render path needs no notion of the hierarchy at all.
    """
    color_map: dict[str, str] = {}
    if color_key and color_key in frame.columns:
        for value in dict.fromkeys(frame[color_key].fillna("")):
            color_map[value] = DEFAULT_PALETTE[len(color_map)
                                               % len(DEFAULT_PALETTE)]
    symbol_map: dict[str, str] = {}
    if symbol_key and symbol_key in frame.columns:
        nested = nests_within(frame, color_key, symbol_key)
        # Shapes may only repeat when a color tells the repeats apart.
        owner = (dict(zip(frame[symbol_key].fillna(""),
                          frame[color_key].fillna("")))
                 if nested else {})
        seen_in_group: dict[str, int] = {}
        for value in dict.fromkeys(frame[symbol_key].fillna("")):
            group = owner.get(value, "")
            index = seen_in_group.get(group, 0)
            seen_in_group[group] = index + 1
            symbol_map[value] = MARKER_CYCLE[index % len(MARKER_CYCLE)]
    return color_map, symbol_map


def style_by_attributes(frame: pd.DataFrame, color_key: str | None,
                        symbol_key: str | None,
                        color_map: dict[str, str],
                        symbol_map: dict[str, str]):
    """Split *frame* into render groups by (color value, symbol value).

    Returns ``(label, PointStyle, sub_frame)`` for each distinct
    combination present, colored/marked from *color_map*/*symbol_map*. One
    scatter call per combination keeps rendering fast even with hundreds of
    species, while the legend is built separately from the two maps so it
    stays compact.
    """
    if frame.empty:
        return []
    ckey = color_key if (color_key and color_key in frame.columns) else None
    skey = symbol_key if (symbol_key and symbol_key in frame.columns) else None
    blank = pd.Series([""] * len(frame), index=frame.index)
    cvals = frame[ckey].fillna("") if ckey else blank
    svals = frame[skey].fillna("") if skey else blank
    default_color = (next(iter(color_map.values()), None)
                     or DEFAULT_PALETTE[0])
    groups = []
    for cval, sval in dict.fromkeys(zip(cvals, svals)):
        sub = frame[(cvals == cval) & (svals == sval)]
        label = " / ".join(p for p in (cval, sval) if p) or "All points"
        style = PointStyle(color=color_map.get(cval, default_color),
                           marker=symbol_map.get(sval, "Circle"))
        groups.append((label, style, sub))
    return groups


def legend_counts(frame: pd.DataFrame, color_key: str | None,
                  symbol_key: str | None) -> dict:
    """Point counts for legend rows.

    Keys are tagged by which channel they count - ``("color", value)``,
    ``("symbol", value)``, and ``("pair", color, symbol)`` for the leaf rows
    of a nested key - so a value that appears in both columns (two "unknown"s,
    say) cannot have one count overwrite the other.

    Pass the frame that is actually drawn (the filtered one, in the app) so
    the numbers agree with the map.
    """
    counts: dict = {}
    if frame.empty:
        return counts
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


def _legend_label(value: str, counts: dict, key) -> str:
    """A legend row's text, with its point count appended when counting."""
    label = value or "(blank)"
    n = counts.get(key)
    return label if n is None else f"{label} ({n})"


def legend_sections(frame: pd.DataFrame, color_key: str | None,
                    symbol_key: str | None, color_map: dict[str, str],
                    symbol_map: dict[str, str], color_label: str,
                    symbol_label: str, shown_colors: set | None = None,
                    shown_symbols: set | None = None,
                    counts: dict | None = None, prefix: str = "") -> list:
    """Legend sections for a dataset styled by a color and a symbol column.

    Returns ``[(title, [(label, PointStyle, depth), ...]), ...]``, where
    *depth* indents a row beneath the one above it.

    When the symbol column nests inside the color column (genus/species) the
    result is a single nested key: each symbol value sits under the color
    group it belongs to, drawn in the marker and color it has on the map.
    Two independent keys would imply ``colors x symbols`` combinations when
    only ``symbols`` of them exist, and would leave the reader to work out
    which color each symbol goes with by hunting for a point on the map.

    When the columns genuinely cross, the two keys stay independent and the
    symbol swatches are neutral - there a shape really does appear in every
    color, so no single color would be honest.

    *shown_colors* / *shown_symbols* limit the rows to the values still
    visible under a filter (None = no filtering).
    """
    counts = counts or {}
    if nests_within(frame, color_key, symbol_key):
        return _nested_sections(frame, color_key, symbol_key, color_map,
                                symbol_map, shown_colors, shown_symbols,
                                counts, prefix, color_label, symbol_label)
    return _crossed_sections(color_map, symbol_map, shown_colors,
                             shown_symbols, counts, prefix, color_label,
                             symbol_label)


def _nested_sections(frame, color_key, symbol_key, color_map, symbol_map,
                     shown_colors, shown_symbols, counts, prefix,
                     color_label, symbol_label) -> list:
    owner = dict(zip(frame[symbol_key].fillna(""),
                     frame[color_key].fillna("")))
    children: dict[str, list[str]] = {value: [] for value in color_map}
    for value in symbol_map:
        if shown_symbols is None or value in shown_symbols:
            children.setdefault(owner.get(value, ""), []).append(value)
    entries: list = []
    for value, color in color_map.items():
        kids = children.get(value, [])
        hidden = shown_colors is not None and value not in shown_colors
        if not kids or hidden:
            continue
        entries.append((_legend_label(value, counts, ("color", value)),
                        PointStyle(color=color, marker="Circle"), 0))
        entries += [(_legend_label(kid, counts, ("pair", value, kid)),
                     PointStyle(color=color, marker=symbol_map[kid]), 1)
                    for kid in kids]
    if not entries:
        return []
    title = " / ".join(p for p in (color_label, symbol_label) if p) or "Key"
    return [(prefix + title, entries)]


def _crossed_sections(color_map, symbol_map, shown_colors, shown_symbols,
                      counts, prefix, color_label, symbol_label) -> list:
    sections = []
    if color_map:
        entries = [(_legend_label(value, counts, ("color", value)),
                    PointStyle(color=color, marker="Circle"), 0)
                   for value, color in color_map.items()
                   if shown_colors is None or value in shown_colors]
        if entries:
            sections.append((prefix + (color_label or "Color"), entries))
    if symbol_map:
        entries = [(_legend_label(value, counts, ("symbol", value)),
                    PointStyle(color=NEUTRAL_MARKER_COLOR, marker=marker), 0)
                   for value, marker in symbol_map.items()
                   if shown_symbols is None or value in shown_symbols]
        if entries:
            sections.append((prefix + (symbol_label or "Symbol"), entries))
    return sections
