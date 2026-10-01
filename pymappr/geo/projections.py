from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

__all__ = [
    "CAP_CLIP_RADIUS", "GLOBE", "PROJECTIONS", "LAMBERT_PROJECTIONS",
    "Projection", "default_origin", "get_projection", "has_custom_origin",
    "is_globe", "is_lambert", "proj4_string",
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

# The globe: orthographic, one hemisphere on a disk, customizable centre.
GLOBE = "Globe (Orthographic)"

# Vector layers are clipped to a spherical cap slightly inside the 90 deg
# visible hemisphere, so no clipped coordinate sits close enough to the
# horizon for the transform to blow up. Public: the code export bakes the
# same radius into the script it writes.
CAP_CLIP_RADIUS = 88.0
# The drawn globe outline (and the projected bounds) sit just inside the
# exact horizon, where the forward transform is still finite everywhere.
_HORIZON_RADIUS = 89.9

PROJECTIONS = list(PROJECTION_DEFS) + [GLOBE] + list(LAMBERT_DEFS)
LAMBERT_PROJECTIONS = list(LAMBERT_DEFS)


def is_lambert(name: str) -> bool:
    """True if *name* is a Lambert preset with a customizable origin."""
    return name in LAMBERT_DEFS


def is_globe(name: str) -> bool:
    """True if *name* is the orthographic globe."""
    return name == GLOBE


def has_custom_origin(name: str) -> bool:
    """True if *name* exposes a customizable centre / point of natural
    origin (the Lambert presets and the Globe)."""
    return is_lambert(name) or is_globe(name)


def default_origin(name: str) -> tuple[float, float]:
    """The default (lon_0, lat_0) centre for any origin-customizable
    projection (Lambert presets and the Globe)."""
    if is_globe(name):
        return 0.0, 0.0
    d = LAMBERT_DEFS[name]
    return d.lon_0, d.lat_0


def proj4_string(name: str, lon_0: float | None = None,
                 lat_0: float | None = None) -> str | None:
    """The proj4 CRS string for a projection name (None = plain lon/lat).

    For Lambert presets and the Globe, *lon_0*/*lat_0* override the
    default point of natural origin, exactly as in :func:`get_projection`.
    """
    if name == GLOBE:
        lon0 = 0.0 if lon_0 is None else float(lon_0)
        lat0 = 0.0 if lat_0 is None else float(lat_0)
        return (f"+proj=ortho +lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 "
                "+datum=WGS84 +units=m +no_defs")
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
    lat_0: float = 0.0        # latitude of the centre (globe tilt)
    hemisphere: bool = False  # only the near hemisphere exists (the Globe)

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

    def clip_shape(self):
        """Lon/lat geometry vector layers are clipped to before
        reprojection (a shapely geometry), or None to leave them whole.

        The Globe clips to its visible spherical cap - the far hemisphere
        projects to infinity - and regional (Lambert) projections to their
        latitude band, so the singular pole never reaches the reprojected
        geometry."""
        if self.hemisphere:
            return _cap_clip(self.lon_0, self.lat_0)
        if self.is_regional:
            from shapely.geometry import box

            return box(-180.0, self.min_lat, 180.0, self.max_lat)
        return None

    def label_region(self):
        """The lon/lat area a regional (Lambert) map shows - its latitude
        band and its longitude span around lon_0 - as a shapely geometry,
        or None for every other projection.

        Polygon and line labels are anchored on the part of a feature
        inside it, so a country only partly on the map (Russia on
        Lambert: Europe) is labelled where it is drawn instead of at an
        anchor off the map. The Globe is left out: every spin step is a
        new projection, and clipping the larger label layers (states)
        each time is too slow."""
        if self.hemisphere or not self.is_regional:
            return None
        return _region_clip(self.lon_0, self.lon_halfspan,
                            self.min_lat, self.max_lat)

    def horizon_xy(self) -> tuple[np.ndarray, np.ndarray]:
        """The globe's horizon circle in projected coordinates (the disk
        outline the renderer draws). Only meaningful for the Globe."""
        lons, lats = _cap_ring(self.lon_0, self.lat_0, _HORIZON_RADIUS)
        return self.forward(lons, lats)

    def _clip(self, lons: np.ndarray, lats: np.ndarray, clamp: bool):
        """Bring lon/lat into the projected region. Longitudes are first
        wrapped to within 180 degrees of a regional centre (175E is 185W
        on a map of North America). Then *clamp* moves anything outside
        the region onto its edge; otherwise those points become NaN."""
        regional_lon = self.lon_halfspan < 180.0
        if regional_lon:
            lons = self.lon_0 + ((lons - self.lon_0 + 180.0) % 360.0) - 180.0
        if not clamp:
            outside = (lats < self.min_lat) | (lats > self.max_lat)
            if regional_lon:
                outside |= np.abs(lons - self.lon_0) > self.lon_halfspan
            return (np.where(outside, np.nan, lons),
                    np.where(outside, np.nan, lats))
        lats = np.clip(lats, self.min_lat, self.max_lat)
        if regional_lon:
            lons = np.clip(lons, self.lon_0 - self.lon_halfspan,
                           self.lon_0 + self.lon_halfspan)
        return lons, lats

    def forward(self, lons, lats,
                clamp: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """Project lon/lat arrays into map coordinates. Coordinates the
        projection cannot represent (the globe's far hemisphere) come back
        as NaN, which matplotlib drops from paths and scatters cleanly.

        On a regional (Lambert) projection, points outside the region are
        clamped onto its edge, so none of the user's data goes missing;
        with *clamp* False they come back as NaN instead, for Natural
        Earth labels and markers that would otherwise pile up there."""
        lons = np.asarray(lons, dtype=float)
        lats = np.asarray(lats, dtype=float)
        if self.crs is None:
            return lons, lats
        lons, lats = self._clip(lons, lats, clamp)
        xs, ys = _transformer(self.crs).transform(lons, lats)
        if self.hemisphere:
            xs = np.asarray(xs, dtype=float)
            ys = np.asarray(ys, dtype=float)
            bad = ~(np.isfinite(xs) & np.isfinite(ys))
            if bad.any():
                xs = np.where(bad, np.nan, xs)
                ys = np.where(bad, np.nan, ys)
        return xs, ys

    def inverse(self, xs, ys) -> tuple[np.ndarray, np.ndarray]:
        """Map coordinates back to lon/lat (non-finite where undefined)."""
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        if self.crs is None:
            return xs, ys
        with np.errstate(all="ignore"):
            return _transformer(self.crs).transform(
                xs, ys, direction="INVERSE")

    def ground_distance(self, x0: float, y0: float,
                        x1: float, y1: float) -> float:
        """Distance on the ground, in metres, between two points given in map
        (axis) coordinates.

        Axis units differ per projection - degrees for Equirectangular, metres
        for every projected CRS - and on a projected CRS the axis metre is not
        the ground metre anyway (a Mercator map stretches enormously towards
        the poles). So this goes back to lon/lat and measures on the WGS84
        ellipsoid, which is right for every projection the app offers.

        Returns NaN when either endpoint has no lon/lat - off the globe's
        visible disk, say - which callers must treat as "cannot measure here".
        """
        lons, lats = self.inverse(np.array([x0, x1]), np.array([y0, y1]))
        lons = np.asarray(lons, dtype=float)
        lats = np.asarray(lats, dtype=float)
        if not np.isfinite(lons).all() or not np.isfinite(lats).all():
            return float("nan")
        _, _, metres = _geod().inv(lons[0], lats[0], lons[1], lats[1])
        return abs(float(metres))

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
        if self.hemisphere:
            # The box edges may lie entirely on the far hemisphere (a
            # world extent's do) while the interior is visible: sample a
            # grid instead of just the edges.
            glons, glats = np.meshgrid(np.linspace(x0, x1, n),
                                       np.linspace(y0, y1, n))
            px, py = self.forward(glons.ravel(), glats.ravel())
            good = np.isfinite(px) & np.isfinite(py)
            if not good.any():  # extent fully on the far side: whole disk
                return self.bounds
            px, py = px[good], py[good]
            return (float(px.min()), float(px.max()),
                    float(py.min()), float(py.max()))
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
def _geod():
    """The WGS84 ellipsoid used for ground distances. Cached, and imported
    lazily for the same reason as :func:`_transformer`."""
    from pyproj import Geod

    return Geod(ellps="WGS84")


@lru_cache(maxsize=64)
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


def _cap_ring(lon_0: float, lat_0: float, radius_deg: float,
              n: int = 361) -> tuple[np.ndarray, np.ndarray]:
    """The lon/lat ring of points *radius_deg* great-circle degrees away
    from (lon_0, lat_0), traced by azimuth. Longitudes come back centred
    on lon_0 (within +/-180 of it), not wrapped into [-180, 180]."""
    az = np.linspace(0.0, 2.0 * np.pi, n)
    phi0 = np.radians(lat_0)
    r = np.radians(radius_deg)
    lat = np.arcsin(np.sin(phi0) * np.cos(r)
                    + np.cos(phi0) * np.sin(r) * np.cos(az))
    dlon = np.arctan2(np.sin(az) * np.sin(r) * np.cos(phi0),
                      np.cos(r) - np.sin(phi0) * np.sin(lat))
    return lon_0 + np.degrees(dlon), np.degrees(lat)


@lru_cache(maxsize=16)
def _cap_clip(lon_0: float, lat_0: float):
    """The visible spherical cap around (lon_0, lat_0) as lon/lat geometry
    for clipping vector layers, with +/-360 degree copies so caps crossing
    the antimeridian still cover data stored in [-180, 180]."""
    from shapely import affinity
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    lons, lats = _cap_ring(lon_0, lat_0, CAP_CLIP_RADIUS)
    if lat_0 + CAP_CLIP_RADIUS >= 90.0:  # cap encloses the north pole
        order = np.argsort(lons)
        shell = list(zip(lons[order], lats[order]))
        shell += [(lon_0 + 180.0, 90.0), (lon_0 - 180.0, 90.0)]
    elif lat_0 - CAP_CLIP_RADIUS <= -90.0:  # ... the south pole
        order = np.argsort(lons)
        shell = list(zip(lons[order], lats[order]))
        shell += [(lon_0 + 180.0, -90.0), (lon_0 - 180.0, -90.0)]
    else:  # a closed ring away from both poles
        shell = list(zip(lons, lats))
    cap = Polygon(shell).buffer(0)  # heal numerical self-touches
    return unary_union([affinity.translate(cap, xoff=off)
                        for off in (-360.0, 0.0, 360.0)])


@lru_cache(maxsize=16)
def _region_clip(lon_0: float, lon_halfspan: float, min_lat: float,
                 max_lat: float):
    """A regional map's lon/lat area for anchoring labels, with +/-360
    degree copies so a region crossing the antimeridian still covers data
    stored in [-180, 180]."""
    from shapely import affinity
    from shapely.geometry import box
    from shapely.ops import unary_union

    lon0 = (lon_0 + 180.0) % 360.0 - 180.0
    region = box(lon0 - lon_halfspan, min_lat, lon0 + lon_halfspan, max_lat)
    copies = unary_union([affinity.translate(region, xoff=off)
                          for off in (-360.0, 0.0, 360.0)])
    return copies.intersection(box(-180.0, min_lat, 180.0, max_lat))


def normalize_origin(lon_0: float, lat_0: float) -> tuple[float, float]:
    """*lon_0* wrapped into [-180, 180] and *lat_0* clamped to [-90, 90]:
    the range PROJ accepts, so a typed or previously saved out-of-range
    centre still builds."""
    lon = float(lon_0)
    if not -180.0 <= lon <= 180.0:
        lon = (lon + 180.0) % 360.0 - 180.0
    return lon, max(-90.0, min(90.0, float(lat_0)))


def _build_globe(lon_0: float | None, lat_0: float | None) -> Projection:
    lon0, lat0 = normalize_origin(0.0 if lon_0 is None else lon_0,
                                  0.0 if lat_0 is None else lat_0)
    crs = proj4_string(GLOBE, lon0, lat0)
    lons, lats = _cap_ring(lon0, lat0, _HORIZON_RADIUS)
    xs, ys = _transformer(crs).transform(lons, lats)
    xs, ys = np.asarray(xs), np.asarray(ys)
    good = np.isfinite(xs) & np.isfinite(ys)
    bounds = (float(xs[good].min()), float(xs[good].max()),
              float(ys[good].min()), float(ys[good].max()))
    return Projection(name=GLOBE, crs=crs, max_lat=90.0, min_lat=-90.0,
                      bounds=bounds, lon_0=lon0, lon_halfspan=180.0,
                      lat_0=lat0, hemisphere=True)


def _build_lambert(name: str, lon_0: float | None,
                   lat_0: float | None) -> Projection:
    d = LAMBERT_DEFS[name]
    lon0, lat0 = normalize_origin(d.lon_0 if lon_0 is None else lon_0,
                                  d.lat_0 if lat_0 is None else lat_0)
    crs = proj4_string(name, lon0, lat0)
    bounds = _bounds_from_grid(crs, lon0 - d.lon_halfspan,
                               lon0 + d.lon_halfspan, d.lat_min, d.lat_max)
    return Projection(name=name, crs=crs, max_lat=d.lat_max, min_lat=d.lat_min,
                      bounds=bounds, lon_0=lon0, lon_halfspan=d.lon_halfspan)


# Bounded: every globe spin step and Lambert origin edit is a new projection.
@lru_cache(maxsize=64)
def get_projection(name: str, lon_0: float | None = None,
                   lat_0: float | None = None) -> Projection:
    """Build a :class:`Projection` by name.

    For Lambert presets and the Globe, *lon_0*/*lat_0* override the default
    point of natural origin; they are ignored for the fixed world
    projections.
    """
    if name == GLOBE:
        return _build_globe(lon_0, lat_0)
    if name in LAMBERT_DEFS:
        return _build_lambert(name, lon_0, lat_0)
    crs, max_lat = PROJECTION_DEFS[name]
    if crs is None:
        bounds = (-180.0, 180.0, -90.0, 90.0)
    else:
        bounds = _bounds_from_grid(crs, -180.0, 180.0, -max_lat, max_lat)
    return Projection(name=name, crs=crs, max_lat=max_lat, min_lat=-max_lat,
                      bounds=bounds, lon_0=0.0, lon_halfspan=180.0)
