"""Point styling: per-group color / marker / size used for map and legend."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

__all__ = ["PointStyle", "MARKERS", "OPEN_SUFFIX", "DEFAULT_PALETTE",
           "group_points", "default_styles", "attribute_style_maps",
           "style_by_attributes", "NEUTRAL_MARKER_COLOR"]

# Marker color used in the legend's "symbol" key, where shape (not color)
# carries the meaning.
NEUTRAL_MARKER_COLOR = "#555555"

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


def attribute_style_maps(frame: pd.DataFrame, color_key: str | None,
                         symbol_key: str | None):
    """Value -> color and value -> marker maps for two-attribute styling.

    Colors are assigned to the *color_key* column's values (round-robin
    through the palette) and markers to the *symbol_key* column's values,
    both ordered by first appearance. Deriving these from the full dataset
    keeps the legend and colors stable while points are filtered. Either
    key may be None, giving an empty map for that channel.
    """
    color_map: dict[str, str] = {}
    if color_key and color_key in frame.columns:
        for value in dict.fromkeys(frame[color_key].fillna("")):
            color_map[value] = DEFAULT_PALETTE[len(color_map)
                                               % len(DEFAULT_PALETTE)]
    symbol_map: dict[str, str] = {}
    if symbol_key and symbol_key in frame.columns:
        for value in dict.fromkeys(frame[symbol_key].fillna("")):
            symbol_map[value] = MARKER_CYCLE[len(symbol_map)
                                             % len(MARKER_CYCLE)]
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
