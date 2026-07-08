"""Parsing of geographic coordinates in decimal degrees or DMS notation.

Accepted forms (whitespace-tolerant, case-insensitive hemisphere letters):

    -122.4194                decimal degrees
    122.4194 W               decimal degrees with hemisphere
    122°25'10.5"W            degrees minutes seconds
    W 122° 25' 10.5"         hemisphere prefix
    122d 25m 10.5s W         d/m/s letter markers
    122 25 10.5 W            bare numbers
    122:25:10.5W             colon separated
    37°46.493'N              degrees + decimal minutes
"""

from __future__ import annotations

import re

__all__ = ["CoordinateError", "parse_coordinate", "parse_longitude", "parse_latitude"]


class CoordinateError(ValueError):
    """Raised when a coordinate string cannot be parsed or is out of range."""


_HEMI_SIGN = {"N": 1, "S": -1, "E": 1, "W": -1}

# Degree / minute / second markers, including the unicode variants commonly
# produced by GPS tools and spreadsheets.
_DEG_MARK = "[°ºd]|deg(?:rees)?"
_MIN_MARK = "[′ʹ']|m(?:in(?:utes)?)?"
_SEC_MARK = "[″ʺ\"]|''|s(?:ec(?:onds)?)?"

_NUM = r"\d+(?:[.,]\d+)?"

_DMS_RE = re.compile(
    rf"""^
    (?P<deg>{_NUM})\s*(?:{_DEG_MARK})?
    (?:[\s:]*(?P<min>{_NUM})\s*(?:{_MIN_MARK})?)?
    (?:[\s:]*(?P<sec>{_NUM})\s*(?:{_SEC_MARK})?)?
    \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


def parse_coordinate(value: object, kind: str = "longitude") -> float:
    """Parse *value* into signed decimal degrees.

    *kind* is ``"longitude"`` or ``"latitude"``; it selects the valid
    hemisphere letters and the allowed range.
    """
    if kind not in ("longitude", "latitude"):
        raise ValueError(f"kind must be 'longitude' or 'latitude', got {kind!r}")
    hemis = "EW" if kind == "longitude" else "NS"
    limit = 180.0 if kind == "longitude" else 90.0

    if isinstance(value, (int, float)):
        result = float(value)
        if result != result:  # NaN
            raise CoordinateError(f"missing {kind}")
        if not -limit <= result <= limit:
            raise CoordinateError(f"{kind} {result} out of range ±{limit}")
        return result

    text = str(value).strip()
    if not text:
        raise CoordinateError(f"missing {kind}")

    # Pull out an optional hemisphere letter from either end.
    sign = None
    m = re.match(rf"^([NSEW])\s*(.*)$", text, re.IGNORECASE)
    if m:
        sign = _HEMI_SIGN[m.group(1).upper()]
        hemi_letter = m.group(1).upper()
        text = m.group(2)
    else:
        m = re.match(rf"^(.*?)\s*([NSEW])$", text, re.IGNORECASE)
        if m:
            sign = _HEMI_SIGN[m.group(2).upper()]
            hemi_letter = m.group(2).upper()
            text = m.group(1)
        else:
            hemi_letter = None
    if hemi_letter is not None and hemi_letter not in hemis:
        raise CoordinateError(
            f"hemisphere {hemi_letter!r} is not valid for a {kind}"
        )

    # An explicit numeric sign; cannot be combined with a hemisphere letter.
    neg = False
    text = text.strip()
    if text[:1] in "+-":
        if sign is not None:
            raise CoordinateError(
                f"cannot combine a sign and a hemisphere letter in {value!r}"
            )
        neg = text[0] == "-"
        text = text[1:].strip()

    # Plain decimal degrees.
    try:
        degrees = _to_float(text)
    except ValueError:
        m = _DMS_RE.match(text)
        if not m:
            raise CoordinateError(f"cannot parse {kind} {value!r}") from None
        degrees = _to_float(m.group("deg"))
        minutes = _to_float(m.group("min")) if m.group("min") else 0.0
        seconds = _to_float(m.group("sec")) if m.group("sec") else 0.0
        if minutes >= 60 or seconds >= 60:
            raise CoordinateError(
                f"minutes/seconds must be < 60 in {value!r}"
            ) from None
        degrees = degrees + minutes / 60.0 + seconds / 3600.0

    if neg:
        degrees = -degrees
    if sign is not None:
        degrees = abs(degrees) * sign

    if not -limit <= degrees <= limit:
        raise CoordinateError(f"{kind} {degrees:g} out of range ±{limit}")
    return degrees


def parse_longitude(value: object) -> float:
    return parse_coordinate(value, "longitude")


def parse_latitude(value: object) -> float:
    return parse_coordinate(value, "latitude")
