"""Scale bar, compass and inset map options, and the maths behind a scale
bar's length.

The decorations sit in the same place conceptually - a small annotation
pinned to a corner of the map - so they share a corner vocabulary and the
placement helper below. The renderer draws them; this module only decides
*what* to draw, which is what lets the app, the exported Python script and
the tests agree without any of them importing matplotlib.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from pymappr.styling.options import values_from_dict

__all__ = ["CORNERS", "SCALE_UNITS", "SCALE_STYLES", "LENGTH_MODES",
           "COMPASS_STYLES", "INSET_REGIONS", "INSET_PROJECTIONS",
           "INSET_OCEANS", "ScaleBarOptions", "CompassOptions",
           "InsetOptions", "METRES_PER_MILE", "corner_anchor",
           "inset_box_target", "nice_length", "unit_metres",
           "format_length"]

# Where a decoration can sit, and the axes-fraction point each corner maps to.
# The pad is deliberately larger at the bottom-left than the compass's old
# hard-coded 0.975 so a scale bar's label does not touch the frame.
CORNERS = ["lower left", "lower right", "upper left", "upper right"]

SCALE_UNITS = ["km", "mi", "both"]
SCALE_STYLES = ["segmented", "plain"]
LENGTH_MODES = ["auto", "fixed"]
COMPASS_STYLES = ["arrow", "triangle"]

METRES_PER_MILE = 1609.344

# Round numbers a scale bar is allowed to show. Anything else reads as
# arbitrary: a bar labelled "237 km" tells the reader nothing at a glance.
_NICE = (1.0, 2.0, 3.0, 5.0)


def unit_metres(units: str) -> float:
    """Metres in one unit of *units* ("both" measures in km)."""
    return METRES_PER_MILE if units == "mi" else 1000.0


def corner_anchor(corner: str, pad: float = 0.03) -> tuple[float, float]:
    """The axes-fraction point a decoration in *corner* is anchored to.

    The returned point is the outer corner of the decoration's box; the
    renderer grows the drawing inwards from it, so the same anchor works for
    a left-aligned and a right-aligned decoration.
    """
    if corner not in CORNERS:
        corner = "lower left"
    vertical, horizontal = corner.split()
    x = pad if horizontal == "left" else 1.0 - pad
    y = pad if vertical == "lower" else 1.0 - pad
    return x, y


def nice_length(metres: float, units: str) -> float:
    """A round bar length, in metres, at or just below *metres*.

    Snapping down rather than to the nearest value keeps the bar inside the
    width it was budgeted, so a long label can never run off the map.
    """
    per_unit = unit_metres(units)
    value = metres / per_unit
    if not math.isfinite(value) or value <= 0:
        return 0.0
    decade = 10.0 ** math.floor(math.log10(value))
    for candidate in reversed(_NICE):
        if candidate * decade <= value:
            return candidate * decade * per_unit
    # value sits below the smallest nice number in its own decade.
    return _NICE[-1] * decade / 10.0 * per_unit


def format_length(metres: float, units: str) -> str:
    """A bar's label, e.g. ``"500 km"``. ``"both"`` is handled by the caller,
    which draws one label per unit.

    A metric bar shorter than a kilometre is labelled in metres: zoomed in on
    a single locality, "500 m" is what a reader expects to see and "0.5 km"
    is not.
    """
    if units != "mi" and metres < 1000.0:
        return f"{metres:g} m"
    per_unit = unit_metres(units)
    value = metres / per_unit
    text = f"{value:g}" if value >= 1 else f"{value:.3g}"
    return f"{text} {'mi' if units == 'mi' else 'km'}"


@dataclass
class ScaleBarOptions:
    """Everything the user can set about the scale bar.

    ``show`` defaults off so an existing project, which stores none of these
    keys, opens looking exactly as it did before the scale bar existed.
    """

    show: bool = False
    units: str = "km"                 # km | mi | both
    position: str = "lower left"      # one of CORNERS
    style: str = "segmented"          # segmented | plain
    length_mode: str = "auto"         # auto | fixed
    fixed_length: float | None = None  # in `units`; None means auto
    segments: int = 4
    width: float = 0.22               # target bar length, axes fraction
    fontsize: float = 8.0
    color: str = "#1a1a1a"
    draggable: bool = False
    # Axes-fraction position after a drag; None keeps it in `position`.
    anchor_x: float | None = None
    anchor_y: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "ScaleBarOptions":
        return cls(**values_from_dict(cls, data))

    @property
    def anchor(self) -> tuple[float, float] | None:
        if self.anchor_x is None or self.anchor_y is None:
            return None
        return float(self.anchor_x), float(self.anchor_y)

    def units_shown(self) -> list[str]:
        """The unit(s) to label, in draw order."""
        return ["km", "mi"] if self.units == "both" else [self.units]


@dataclass
class CompassOptions:
    """The north arrow's placement and look.

    The defaults reproduce the fixed arrow the app drew before any of this
    was configurable, so projects saved earlier are unchanged by the upgrade.
    """

    show: bool = False
    position: str = "upper right"     # one of CORNERS
    style: str = "arrow"              # arrow | triangle
    size: float = 1.0                 # multiplier on the original size
    color: str = "#1a1a1a"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "CompassOptions":
        return cls(**values_from_dict(cls, data))


# What an inset can show, besides a continent name (CONTINENT_EXTENTS).
# "state" and "country" follow the map: the one holding the view's centre.
INSET_REGIONS = ["state", "country", "around", "custom"]
INSET_PROJECTIONS = ["same", "Equirectangular", "Robinson", "Globe"]
INSET_OCEANS = ["none", "grey", "blue"]


@dataclass
class InsetOptions:
    """A small second map in a corner of the main one.

    Either a locator - a wider area, with a box marking what the main map
    shows - or a zoom - a smaller area blown up, with the box drawn on the
    main map instead. Which one follows from the two extents (see
    :func:`inset_box_target`), so the user only picks the region.

    Every field is a scalar so a project stores it as plain JSON; the custom
    extent is four numbers rather than a tuple for the same reason.
    """

    show: bool = False
    position: str = "lower right"     # one of CORNERS
    size: float = 0.3                 # width, as a fraction of the map box
    # state | country | around | custom, or a CONTINENT_EXTENTS name.
    region: str = "state"
    zoom_out: float = 6.0             # "around": the view's span times this
    lon_min: float | None = None      # "custom"
    lon_max: float | None = None
    lat_min: float | None = None
    lat_max: float | None = None
    projection: str = "same"          # one of INSET_PROJECTIONS
    countries: bool = True
    states: bool = False
    counties: bool = False
    land: bool = True
    ocean: str = "none"               # one of INSET_OCEANS
    points: bool = True
    box: bool = True
    box_color: str = "#d62728"
    draggable: bool = False
    # Axes-fraction position of its lower-left corner after a drag; None
    # keeps it in `position`.
    anchor_x: float | None = None
    anchor_y: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "InsetOptions":
        return cls(**values_from_dict(cls, data))

    @property
    def anchor(self) -> tuple[float, float] | None:
        if self.anchor_x is None or self.anchor_y is None:
            return None
        return float(self.anchor_x), float(self.anchor_y)

    @property
    def custom_extent(self) -> tuple[float, float, float, float] | None:
        """The typed-in extent, or None until all four sides are set and
        make a box."""
        sides = (self.lon_min, self.lon_max, self.lat_min, self.lat_max)
        if any(v is None or not math.isfinite(v) for v in sides):
            return None
        lon0, lon1, lat0, lat1 = (float(v) for v in sides)
        if lon1 <= lon0 or lat1 <= lat0:
            return None
        return lon0, lon1, max(lat0, -90.0), min(lat1, 90.0)

    def follows_view(self) -> bool:
        """Whether the inset's region changes as the main map moves."""
        return (self.region in ("state", "country", "around")
                or self.projection == "Globe")


def _area(extent) -> float:
    lon0, lon1, lat0, lat1 = extent
    return max(lon1 - lon0, 0.0) * max(lat1 - lat0, 0.0)


def _overlap(a, b) -> float:
    return _area((max(a[0], b[0]), min(a[1], b[1]),
                  max(a[2], b[2]), min(a[3], b[3])))


def inset_box_target(inset_extent, view_extent) -> str | None:
    """Where the box linking the two maps goes, given both lon/lat extents.

    ``"inset"`` when the inset shows a wider area around the map (a
    locator: the box marks the map's view on it), ``"main"`` when it shows
    a smaller area inside the map (a zoom: the box marks that area on the
    map), and None when the two hardly overlap - nothing to link.
    """
    inset_area, view_area = _area(inset_extent), _area(view_extent)
    if inset_area <= 0 or view_area <= 0:
        return None
    shared = _overlap(inset_extent, view_extent)
    # Two areas about the same size would only box each other's edges.
    if inset_area >= 1.5 * view_area and shared >= 0.5 * view_area:
        return "inset"
    if inset_area * 1.5 <= view_area and shared >= 0.5 * inset_area:
        return "main"
    return None
