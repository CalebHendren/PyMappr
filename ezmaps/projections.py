"""Map projections for the renderer, built on pyproj.

Every projection maps geographic lon/lat (EPSG:4326) into a projected plane.
``Equirectangular`` is the identity (plain degrees) and is the default; the
others reproject all vector layers, points, labels, and the basemap raster.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

__all__ = ["PROJECTIONS", "Projection", "get_projection"]

# Display name -> (proj4 string or None for plain lon/lat, max usable latitude).
PROJECTION_DEFS = {
    "Equirectangular": (None, 90.0),
    "Mercator": ("+proj=merc +lon_0=0 +datum=WGS84 +units=m +no_defs", 85.05),
    "Robinson": ("+proj=robin +lon_0=0 +datum=WGS84 +units=m +no_defs", 90.0),
    "Mollweide": ("+proj=moll +lon_0=0 +datum=WGS84 +units=m +no_defs", 90.0),
    "Natural Earth": ("+proj=natearth +lon_0=0 +datum=WGS84 +units=m +no_defs", 90.0),
    "Winkel Tripel": ("+proj=wintri +lon_0=0 +datum=WGS84 +units=m +no_defs", 90.0),
}

PROJECTIONS = list(PROJECTION_DEFS)


@dataclass(frozen=True)
class Projection:
    name: str
    crs: str | None       # proj4 string, or None for plain lon/lat degrees
    max_lat: float        # data is clipped to +/- this latitude
    bounds: tuple[float, float, float, float]  # projected world x0,x1,y0,y1

    @property
    def is_geographic(self) -> bool:
        return self.crs is None

    @property
    def world_width(self) -> float:
        return self.bounds[1] - self.bounds[0]

    def forward(self, lons, lats) -> tuple[np.ndarray, np.ndarray]:
        """Project lon/lat arrays into map coordinates."""
        lons = np.asarray(lons, dtype=float)
        lats = np.asarray(lats, dtype=float)
        if self.crs is None:
            return lons, lats
        lats = np.clip(lats, -self.max_lat, self.max_lat)
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
        y0 = max(y0, -self.max_lat)
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
        return float(px.min()), float(px.max()), float(py.min()), float(py.max())


@lru_cache(maxsize=None)
def _transformer(crs: str):
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", crs, always_xy=True)


@lru_cache(maxsize=None)
def get_projection(name: str) -> Projection:
    crs, max_lat = PROJECTION_DEFS[name]
    if crs is None:
        bounds = (-180.0, 180.0, -90.0, 90.0)
    else:
        n = 60
        lons = np.concatenate([
            np.linspace(-180, 180, n), np.linspace(-180, 180, n),
            np.full(n, -180.0), np.full(n, 180.0)])
        lats = np.concatenate([
            np.full(n, -max_lat), np.full(n, max_lat),
            np.linspace(-max_lat, max_lat, n),
            np.linspace(-max_lat, max_lat, n)])
        xs, ys = _transformer(crs).transform(lons, lats)
        xs, ys = np.asarray(xs), np.asarray(ys)
        good = np.isfinite(xs) & np.isfinite(ys)
        bounds = (float(xs[good].min()), float(xs[good].max()),
                  float(ys[good].min()), float(ys[good].max()))
    return Projection(name=name, crs=crs, max_lat=max_lat, bounds=bounds)
