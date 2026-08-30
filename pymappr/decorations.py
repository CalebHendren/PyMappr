"""Scale bar and compass options, and the maths behind a scale bar's length.

Both decorations sit in the same place conceptually - a small annotation
pinned to a corner of the map - so they share a corner vocabulary and the
placement helper below. The renderer draws them; this module only decides
*what* to draw, which is what lets the app, the exported Python script and
the tests agree without any of them importing matplotlib.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from pymappr.options import values_from_dict

__all__ = ["CORNERS", "SCALE_UNITS", "SCALE_STYLES", "LENGTH_MODES",
           "COMPASS_STYLES", "ScaleBarOptions", "CompassOptions",
           "METRES_PER_MILE", "corner_anchor", "nice_length", "unit_metres",
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
