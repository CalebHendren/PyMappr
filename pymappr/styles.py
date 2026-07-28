"""Point styling: per-group color / marker / size used for map and legend."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

__all__ = ["PointStyle", "MARKERS", "OPEN_SUFFIX", "DEFAULT_PALETTE",
           "group_points", "default_styles", "attribute_style_maps",
           "style_by_attributes", "LEGIBLE_MARKER_LIMIT", "nests_within",
           "resolve_nesting", "owner_map", "marker_load"]

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


def resolve_nesting(frame: pd.DataFrame, color_key: str | None,
                    symbol_key: str | None, mode: str = "auto") -> bool:
    """Whether to treat the two columns as a hierarchy, honouring the user's
    choice: ``"auto"`` detects it, ``"always"`` forces it, ``"never"`` refuses.

    Every caller that cares about nesting goes through here, so the map's
    shape assignment and the legend's layout can never disagree about it.
    Forcing it on genuinely crossed data is allowed - the reader is warned
    elsewhere - but it still needs two columns to nest.
    """
    if not color_key or not symbol_key or frame.empty:
        return False
    if color_key not in frame.columns or symbol_key not in frame.columns:
        return False
    if mode == "never":
        return False
    if mode == "always":
        return True
    return nests_within(frame, color_key, symbol_key)


def owner_map(frame: pd.DataFrame, symbol_key: str, color_key: str) -> dict:
    """Symbol value -> the color group it belongs to, first occurrence wins.

    Under real nesting each symbol value has exactly one color, so the rule
    never bites. It only matters when nesting is forced onto crossed data,
    where taking the first occurrence makes the result depend on file order
    rather than on which row happened to be read last.
    """
    owner: dict = {}
    for symbol, color in zip(frame[symbol_key].fillna(""),
                             frame[color_key].fillna("")):
        owner.setdefault(symbol, color)
    return owner


def marker_load(frame: pd.DataFrame, color_key: str | None,
                symbol_key: str | None, hierarchy: str = "auto") -> int:
    """How many shapes the reader has to tell apart on the map.

    Under nesting that is the largest number of symbol values inside any one
    color group (shapes restart per group); otherwise every symbol value needs
    its own shape. Compare against :data:`LEGIBLE_MARKER_LIMIT`.
    """
    if not symbol_key or symbol_key not in frame.columns or frame.empty:
        return 0
    symbols = frame[symbol_key].fillna("")
    if not resolve_nesting(frame, color_key, symbol_key, hierarchy):
        return int(symbols.nunique())
    colors = frame[color_key].fillna("")
    return int(symbols.groupby(colors.values).nunique().max())


def attribute_style_maps(frame: pd.DataFrame, color_key: str | None,
                         symbol_key: str | None, hierarchy: str = "auto"):
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
        nested = resolve_nesting(frame, color_key, symbol_key, hierarchy)
        # Shapes may only repeat when a color tells the repeats apart.
        owner = (owner_map(frame, symbol_key, color_key)
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
