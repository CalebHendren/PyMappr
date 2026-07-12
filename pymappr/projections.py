"""Map projections for the renderer, built on pyproj.

Every projection maps geographic lon/lat (EPSG:4326) into a projected plane.
``Equirectangular`` is the identity (plain degrees) and is the default; the
others reproject all vector layers, points, labels, and the basemap raster.

Two families live here:

* **World projections** (Mercator, Robinson, ...) cover the whole globe and
  are keyed by name alone.
* **Lambert projections** (Lambert Conformal Conic and Lambert Azimuthal
  Equal Area) are regional. Each preset centres on a region but exposes a
  **customizable point of natural origin** (central meridian ``lon_0`` and
  latitude of origin ``lat_0``); ``get_projection`` rebuilds the CRS when the
  origin changes. Regional projections clip data to a latitude band and a
  longitude span around the origin so the far side of the globe (where a
  conic projection fans out to infinity) never distorts the map.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

__all__ = [
    "PROJECTIONS", "LAMBERT_PROJECTIONS", "Projection", "get_projection",
    "is_lambert", "lambert_default_origin", "proj4_string",
]

# Display name -> (proj4 string or None for plain lon/lat, max usable latitude).
PROJECTION_DEFS = {
    "Equirectangular": (None, 90.0),
    "Mercator": ("+proj=merc +lon_0=0 +datum=WGS84 +units=m +no_defs", 85.05),
    "Robinson": ("+proj=robin +lon_0=0 +datum=WGS84 +units=m +no_defs", 90.0),
    "Mollweide": ("+proj=moll +lon_0=0 +datum=WGS84 +units=m +no_defs", 90.0),
    "Natural Earth": ("+proj=natearth +lon_0=0 +datum=WGS84 +units=m +no_defs", 90.0),
    "Winkel Tripel": ("+proj=wintri +lon_0=0 +datum=WGS84 +units=m +no_defs", 90.0),
}


@dataclass(frozen=True)
class LambertDef:
    """A regional Lambert preset with a default point of natural origin.

    ``proj`` is ``"lcc"`` (Conformal Conic, with two standard parallels) or
    ``"laea"`` (Azimuthal Equal Area). ``lon_0``/``lat_0`` are the default
    origin the UI seeds and the user can override. ``lon_halfspan`` and
    ``lat_min``/``lat_max`` bound the region that is actually projected.
    """

    proj: str            # "lcc" or "laea"
    lon_0: float         # default central meridian (point of natural origin)
    lat_0: float         # default latitude of origin
    lat_1: float | None  # standard parallels (lcc only)
    lat_2: float | None
    lon_halfspan: float  # +/- degrees around lon_0 kept in view
    lat_min: float
    lat_max: float


# Regional Lambert presets. The point of natural origin (lon_0/lat_0) is
# customizable per the map controls; the standard parallels and the region
# bounds stay tied to the preset.
LAMBERT_DEFS = {
    "Lambert: N. America": LambertDef("lcc", -96.0, 40.0, 20.0, 60.0,
                                      90.0, 7.0, 84.0),
    "Lambert: Europe": LambertDef("lcc", 10.0, 52.0, 35.0, 65.0,
                                  55.0, 30.0, 72.0),
    "Lambert: Asia": LambertDef("lcc", 95.0, 30.0, 15.0, 65.0,
                                90.0, -12.0, 78.0),
    "Lambert: S. America": LambertDef("lcc", -60.0, -32.0, -5.0, -42.0,
                                      55.0, -58.0, 14.0),
    "Lambert: Africa": LambertDef("laea", 20.0, 5.0, None, None,
                                  60.0, -38.0, 40.0),
    "Lambert Azimuthal (custom)": LambertDef("laea", 0.0, 0.0, None, None,
                                             120.0, -88.0, 88.0),
}

PROJECTIONS = list(PROJECTION_DEFS) + list(LAMBERT_DEFS)
LAMBERT_PROJECTIONS = list(LAMBERT_DEFS)


def is_lambert(name: str) -> bool:
    """True if *name* is a Lambert preset with a customizable origin."""
    return name in LAMBERT_DEFS


def lambert_default_origin(name: str) -> tuple[float, float]:
    """The preset's default (lon_0, lat_0) point of natural origin."""
    d = LAMBERT_DEFS[name]
    return d.lon_0, d.lat_0


def proj4_string(name: str, lon_0: float | None = None,
                 lat_0: float | None = None) -> str | None:
    """The proj4 CRS string for a projection name (None = plain lon/lat).

    For Lambert presets, *lon_0*/*lat_0* override the default point of
    natural origin, exactly as in :func:`get_projection` - but no
    transformer or bounds are built, so callers that only need the CRS
    text (the code export) stay cheap.
    """
    if name in LAMBERT_DEFS:
        d = LAMBERT_DEFS[name]
        lon0 = d.lon_0 if lon_0 is None else float(lon_0)
        lat0 = d.lat_0 if lat_0 is None else float(lat_0)
        if d.proj == "lcc":
            return (f"+proj=lcc +lat_1={d.lat_1} +lat_2={d.lat_2} "
                    f"+lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 "
                    "+datum=WGS84 +units=m +no_defs")
        return (f"+proj=laea +lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 "
                "+datum=WGS84 +units=m +no_defs")
    crs, _max_lat = PROJECTION_DEFS[name]
    return crs


@dataclass(frozen=True)
class Projection:
    name: str
    crs: str | None       # proj4 string, or None for plain lon/lat degrees
    max_lat: float        # data is clipped to this upper latitude
    min_lat: float        # ... and this lower latitude
    bounds: tuple[float, float, float, float]  # projected world x0,x1,y0,y1
    lon_0: float = 0.0        # central meridian (region centre)
    lon_halfspan: float = 180.0  # +/- degrees around lon_0 kept (<180 = regional)

    @property
    def is_geographic(self) -> bool:
        return self.crs is None

    @property
    def is_regional(self) -> bool:
        """Regional projections (Lambert) clip to a region instead of the
        whole globe."""
        return self.lon_halfspan < 180.0 or self.min_lat != -self.max_lat

    @property
    def key(self) -> str:
        """Cache key that distinguishes custom origins sharing a name."""
        return self.crs or self.name

    @property
    def world_width(self) -> float:
        return self.bounds[1] - self.bounds[0]

    def clip_box(self) -> tuple[float, float, float, float] | None:
        """Lon/lat box vector layers are clipped to before reprojection, or
        None to leave them whole. Regional projections clip to their latitude
        band so the singular pole never reaches the reprojected geometry."""
        if self.is_regional:
            return (-180.0, 180.0, self.min_lat, self.max_lat)
        return None

    def _clip(self, lons: np.ndarray, lats: np.ndarray):
        lats = np.clip(lats, self.min_lat, self.max_lat)
        if self.lon_halfspan < 180.0:
            lons = np.clip(lons, self.lon_0 - self.lon_halfspan,
                           self.lon_0 + self.lon_halfspan)
        return lons, lats

    def forward(self, lons, lats) -> tuple[np.ndarray, np.ndarray]:
        """Project lon/lat arrays into map coordinates."""
        lons = np.asarray(lons, dtype=float)
        lats = np.asarray(lats, dtype=float)
        if self.crs is None:
            return lons, lats
        lons, lats = self._clip(lons, lats)
        return _transformer(self.crs).transform(lons, lats)

    def inverse(self, xs, ys) -> tuple[np.ndarray, np.ndarray]:
        """Map coordinates back to lon/lat (non-finite where undefined)."""
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        if self.crs is None:
            return xs, ys
        with np.errstate(all="ignore"):
            return _transformer(self.crs).transform(
                xs, ys, direction="INVERSE")

    def project_extent(self, extent) -> tuple[float, float, float, float]:
        """Project a (lon0, lon1, lat0, lat1) box to a projected bbox.

        The box edges are densified so curved projected edges are bounded
        correctly.
        """
        x0, x1, y0, y1 = (float(v) for v in extent)
        if self.crs is None:
            return x0, x1, y0, y1
        y0 = max(y0, self.min_lat)
        y1 = min(y1, self.max_lat)
        n = 40
        lons = np.concatenate([
            np.linspace(x0, x1, n), np.linspace(x0, x1, n),
            np.full(n, x0), np.full(n, x1)])
        lats = np.concatenate([
            np.full(n, y0), np.full(n, y1),
            np.linspace(y0, y1, n), np.linspace(y0, y1, n)])
        px, py = self.forward(lons, lats)
        good = np.isfinite(px) & np.isfinite(py)
        px, py = px[good], py[good]
        if not len(px):  # extent outside the region: fall back to full bounds
            return self.bounds
        return float(px.min()), float(px.max()), float(py.min()), float(py.max())


@lru_cache(maxsize=None)
def _transformer(crs: str):
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", crs, always_xy=True)


def _bounds_from_grid(crs: str, lon0: float, lon1: float,
                      lat0: float, lat1: float) -> tuple[float, float, float, float]:
    """Projected bounding box of a lon/lat region, densified along the edges."""
    n = 60
    lons = np.concatenate([
        np.linspace(lon0, lon1, n), np.linspace(lon0, lon1, n),
        np.full(n, lon0), np.full(n, lon1)])
    lats = np.concatenate([
        np.full(n, lat0), np.full(n, lat1),
        np.linspace(lat0, lat1, n), np.linspace(lat0, lat1, n)])
    xs, ys = _transformer(crs).transform(lons, lats)
    xs, ys = np.asarray(xs), np.asarray(ys)
    good = np.isfinite(xs) & np.isfinite(ys)
    return (float(xs[good].min()), float(xs[good].max()),
            float(ys[good].min()), float(ys[good].max()))


def _build_lambert(name: str, lon_0: float | None,
                   lat_0: float | None) -> Projection:
    d = LAMBERT_DEFS[name]
    lon0 = d.lon_0 if lon_0 is None else float(lon_0)
    lat0 = d.lat_0 if lat_0 is None else float(lat_0)
    crs = proj4_string(name, lon0, lat0)
    bounds = _bounds_from_grid(crs, lon0 - d.lon_halfspan,
                               lon0 + d.lon_halfspan, d.lat_min, d.lat_max)
    return Projection(name=name, crs=crs, max_lat=d.lat_max, min_lat=d.lat_min,
                      bounds=bounds, lon_0=lon0, lon_halfspan=d.lon_halfspan)


@lru_cache(maxsize=None)
def get_projection(name: str, lon_0: float | None = None,
                   lat_0: float | None = None) -> Projection:
    """Build a :class:`Projection` by name.

    For Lambert presets, *lon_0*/*lat_0* override the default point of natural
    origin; they are ignored for the fixed world projections.
    """
    if name in LAMBERT_DEFS:
        return _build_lambert(name, lon_0, lat_0)
    crs, max_lat = PROJECTION_DEFS[name]
    if crs is None:
        bounds = (-180.0, 180.0, -90.0, 90.0)
    else:
        bounds = _bounds_from_grid(crs, -180.0, 180.0, -max_lat, max_lat)
    return Projection(name=name, crs=crs, max_lat=max_lat, min_lat=-max_lat,
                      bounds=bounds, lon_0=0.0, lon_halfspan=180.0)
