"""The lon/lat area an inset map shows, worked out from where the main map is.

Kept apart from the renderer: it needs the layer data but no matplotlib, so
the app, the code export and the tests can all ask the same question.
"""

from __future__ import annotations

import math

from pymappr.geo.layers import CONTINENT_EXTENTS, LayerStore
from pymappr.styling.decorations import InsetOptions

__all__ = ["containing_extent", "around_extent", "inset_extent"]

# Room left around a state or country, as a fraction of its span, so its
# outline does not run along the inset's frame.
_PAD = 0.08
# Parts of a country kept with the one holding the point: those within this
# fraction of that part's span of it (but at least _NEARBY_MIN degrees).
# Japan keeps Hokkaido, France Corsica and the United States its contiguous
# states, without Alaska or Hawaii stretching the inset across the Pacific.
_NEARBY = 0.1
_NEARBY_MIN = 2.0
# A state wider than this (degrees of longitude) is cut to the part holding
# the point too: Alaska's Aleutians cross the antimeridian.
_WIDE_STATE = 40.0


def _parts(geometry) -> list:
    return list(getattr(geometry, "geoms", [geometry]))


def _pad(extent, fraction: float = _PAD) -> tuple[float, float, float, float]:
    lon0, lon1, lat0, lat1 = extent
    # At least a little room, so a tiny island state still gets some sea.
    dx = max((lon1 - lon0) * fraction, 0.05)
    dy = max((lat1 - lat0) * fraction, 0.05)
    return (max(lon0 - dx, -180.0), min(lon1 + dx, 180.0),
            max(lat0 - dy, -90.0), min(lat1 + dy, 90.0))


def containing_extent(store: LayerStore, key: str, lon: float,
                      lat: float) -> tuple[float, float, float, float] | None:
    """The padded lon/lat extent of the *key* feature ("states" or
    "countries") holding (*lon*, *lat*), or None when no feature does - the
    point is at sea, say."""
    from shapely.geometry import Point

    zoom = 3.5 if key == "countries" else None  # 10m, for small countries
    gdf = store.frame(key, zoom=zoom)
    point = Point(lon, lat)
    hits = gdf.sindex.query(point, predicate="intersects")
    if not len(hits):
        return None
    index = int(hits[0])
    geometry = gdf.geometry.iloc[index]
    parts = _parts(geometry)
    home = next((i for i, p in enumerate(parts) if p.intersects(point)), 0)
    # Per feature part, not per point: the inset asks again on every pan,
    # and a country with a few hundred islands takes a while to sort out.
    cache = store.__dict__.setdefault("_containing_extents", {})
    if (key, index, home) not in cache:
        whole = geometry.bounds[2] - geometry.bounds[0]
        cache[(key, index, home)] = _extent_near(
            parts, parts[home], key == "countries" or whole > _WIDE_STATE)
    return cache[(key, index, home)]


def _extent_near(parts, home, near_only: bool):
    """The padded extent of the feature's *parts*, or with *near_only* of
    *home* and the parts close to it."""
    if near_only:
        hx0, hy0, hx1, hy1 = home.bounds
        reach = max(max(hx1 - hx0, hy1 - hy0) * _NEARBY, _NEARBY_MIN)
        parts = [p for p in parts if p is home or p.distance(home) <= reach]
    bounds = [p.bounds for p in parts]
    return _pad((min(b[0] for b in bounds), max(b[2] for b in bounds),
                 min(b[1] for b in bounds), max(b[3] for b in bounds)))


def around_extent(view, factor: float) -> tuple[float, float, float, float]:
    """*view* (a lon/lat extent) grown *factor* times about its centre,
    kept on the globe."""
    lon0, lon1, lat0, lat1 = view
    factor = max(float(factor), 1.0)
    cx, cy = (lon0 + lon1) / 2.0, (lat0 + lat1) / 2.0
    half_w = min((lon1 - lon0) * factor / 2.0, 180.0)
    half_h = min((lat1 - lat0) * factor / 2.0, 90.0)
    lon0, lon1 = cx - half_w, cx + half_w
    if lon0 < -180.0:
        lon0, lon1 = -180.0, min(-180.0 + 2 * half_w, 180.0)
    elif lon1 > 180.0:
        lon0, lon1 = max(180.0 - 2 * half_w, -180.0), 180.0
    lat0, lat1 = cy - half_h, cy + half_h
    if lat0 < -90.0:
        lat0, lat1 = -90.0, min(-90.0 + 2 * half_h, 90.0)
    elif lat1 > 90.0:
        lat0, lat1 = max(90.0 - 2 * half_h, -90.0), 90.0
    return lon0, lon1, lat0, lat1


def inset_extent(store: LayerStore, options: InsetOptions, view,
                 centre) -> tuple[float, float, float, float]:
    """The lon/lat extent the inset shows.

    *view* is the main map's lon/lat extent and *centre* its centre point.
    A state or country that cannot be found (the map is centred on the sea)
    falls back to the area around the view, and a custom extent that is not
    complete yet to the whole world."""
    region = options.region
    if region in CONTINENT_EXTENTS:
        return CONTINENT_EXTENTS[region]
    if region == "custom":
        return options.custom_extent or CONTINENT_EXTENTS["World"]
    if region in ("state", "country"):
        lon, lat = centre
        if math.isfinite(lon) and math.isfinite(lat):
            key = "states" if region == "state" else "countries"
            found = containing_extent(store, key, lon, lat)
            if found is not None:
                return found
    return around_extent(view, options.zoom_out)
