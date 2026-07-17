"""Natural Earth layer access: lazy loading, label points, continent extents.

Layers live in ``data/`` (populated by ``scripts/fetch_data.py``). In a
PyInstaller build the same tree is bundled next to the executable.

Three cross-cutting features live here:

* **Multiple resolutions** - core layers (countries, lakes, rivers, ocean,
  land) exist at 110m, 50m, and 10m. A ``LayerSpec`` lists its resolutions
  as (min zoom, directory) steps and ``directory_for_zoom`` picks the right
  one, so the renderer can swap detail in as the user zooms.
* **Derived layers** - continent outlines, dependencies, deserts, wadis,
  capitals, maritime/EEZ splits, and the stacked bathymetry are filtered or
  assembled views of the downloaded shapefiles, described in ``DERIVED``.
* **Disk cache** - parsing a big shapefile costs 1-2 s; a parsed frame is
  pickled (columns trimmed to what PyMappr uses) into ``data/cache/`` so
  every later load - including every later app start - is near-instant.
"""

from __future__ import annotations

import os
import pickle
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = ["LayerStore", "LAYER_SPECS", "OPTIONAL_LAYERS",
           "CONTINENT_EXTENTS", "default_data_dir"]

# Bump when the cached frame format changes; stale caches are rebuilt.
_CACHE_VERSION = 1

# Columns kept when caching a frame - everything PyMappr reads, nothing more.
# Trimming the rest (10m states ship ~120 columns) shrinks the cache and the
# in-memory frames considerably.
_KEEP_COLUMNS = {
    "geometry", "name", "featurecla", "scalerank", "min_zoom", "min_label",
    "type", "continent", "adm0cap", "pop_max", "zone", "time_zone",
    "unit_name", "unit_type", "natlscale", "labelrank", "depth",
}


@dataclass(frozen=True)
class LayerSpec:
    key: str
    directory: str  # directory of the default resolution
    geometry: str  # "polygon", "line" or "point"
    label_cap: int = 0  # max labels drawn at once; 0 = layer is never labelled
    shapefile: str | None = None  # member name for multi-shapefile archives
    # Resolution steps as (min zoom, directory), ascending by zoom. Empty =
    # single resolution. Zoom 0 shows the whole world; +1 per 2x magnification.
    resolutions: tuple[tuple[float, str], ...] = ()
    label_directory: str | None = None  # resolution used for label anchors
    label_column: str = "name"

    def directory_for_zoom(self, zoom: float | None) -> str:
        if zoom is None or not self.resolutions:
            return self.directory
        chosen = self.resolutions[0][1]
        for min_zoom, directory in self.resolutions:
            if zoom >= min_zoom:
                chosen = directory
        return chosen

    def directories(self) -> tuple[str, ...]:
        if self.resolutions:
            return tuple(directory for _z, directory in self.resolutions)
        return (self.directory,)


def _res(*steps) -> tuple[tuple[float, str], ...]:
    return tuple(steps)


# Zoom thresholds for the three Natural Earth resolutions: 110m while zoomed
# out, 50m for continent-level views, 10m once zoomed in to country level.
_Z50 = 1.0
_Z10 = 3.5

LAYER_SPECS = {
    # ------------------------------------------------------------ political
    "countries": LayerSpec(
        "countries", "ne_50m_admin_0_countries", "polygon", 400,
        resolutions=_res((0.0, "ne_110m_admin_0_countries"),
                         (_Z50, "ne_50m_admin_0_countries"),
                         (_Z10, "ne_10m_admin_0_countries"))),
    "states": LayerSpec("states", "ne_10m_admin_1_states_provinces",
                        "polygon", 600),
    "counties": LayerSpec("counties", "ne_10m_admin_2_counties",
                          "polygon", 1200),
    "sovereignty": LayerSpec("sovereignty", "ne_50m_admin_0_sovereignty",
                             "polygon"),
    "map_units": LayerSpec("map_units", "ne_50m_admin_0_map_units",
                           "polygon"),
    "subunits": LayerSpec("subunits", "ne_50m_admin_0_map_subunits",
                          "polygon"),
    "disputed": LayerSpec("disputed", "ne_10m_admin_0_disputed_areas",
                          "polygon", 80),
    "disputed_lines": LayerSpec(
        "disputed_lines", "ne_10m_admin_0_boundary_lines_disputed_areas",
        "line"),
    "maritime_all": LayerSpec(
        "maritime_all", "ne_10m_admin_0_boundary_lines_maritime_indicator",
        "line"),
    "timezones": LayerSpec("timezones", "ne_10m_time_zones", "polygon", 60,
                           label_column="time_zone"),
    # ------------------------------------------------------------- cultural
    "cities": LayerSpec("cities", "ne_10m_populated_places_simple",
                        "point", 250),
    "urban": LayerSpec("urban", "ne_10m_urban_areas", "polygon"),
    "airports": LayerSpec("airports", "ne_10m_airports", "point", 150),
    "ports": LayerSpec("ports", "ne_10m_ports", "point", 150),
    "parks": LayerSpec("parks", "ne_10m_parks_and_protected_lands",
                       "polygon", 60,
                       shapefile="ne_10m_parks_and_protected_lands_area"),
    "roads": LayerSpec("roads", "ne_10m_roads", "line"),
    # ---------------------------------------------------------------- water
    "lakes": LayerSpec(
        "lakes", "ne_50m_lakes", "polygon", 60,
        resolutions=_res((0.0, "ne_110m_lakes"),
                         (_Z50, "ne_50m_lakes"),
                         (_Z10, "ne_10m_lakes"))),
    "rivers": LayerSpec(
        "rivers", "ne_10m_rivers_lake_centerlines", "line", 60,
        resolutions=_res((0.0, "ne_110m_rivers_lake_centerlines"),
                         (_Z50, "ne_50m_rivers_lake_centerlines"),
                         (_Z10, "ne_10m_rivers_lake_centerlines"))),
    "ocean": LayerSpec(
        "ocean", "ne_50m_ocean", "polygon",
        resolutions=_res((0.0, "ne_110m_ocean"),
                         (_Z50, "ne_50m_ocean"),
                         (_Z10, "ne_10m_ocean"))),
    "land": LayerSpec(
        "land", "ne_50m_land", "polygon",
        resolutions=_res((0.0, "ne_110m_land"),
                         (_Z50, "ne_50m_land"),
                         (_Z10, "ne_10m_land"))),
    # ------------------------------------------------------------- physical
    "glaciers": LayerSpec("glaciers", "ne_10m_glaciated_areas", "polygon"),
    "ice_shelves": LayerSpec("ice_shelves",
                             "ne_50m_antarctic_ice_shelves_polys", "polygon"),
    "reefs": LayerSpec("reefs", "ne_10m_reefs", "line"),
    "playas": LayerSpec("playas", "ne_10m_playas", "polygon", 40),
    "regions": LayerSpec("regions", "ne_10m_geography_regions_polys",
                         "polygon", 150),
    # ------------------------------------------ biodiversity & ecoregions
    # Optional overlays from external open datasets (see scripts/fetch_data.py):
    # Conservation International biodiversity hotspots, RESOLVE terrestrial
    # ecoregions, and WWF/TNC marine ecoregions.
    "biodiversity": LayerSpec("biodiversity", "biodiversity_hotspots",
                              "polygon"),
    "ecoregions": LayerSpec("ecoregions", "ecoregions_2017", "polygon"),
    "marine_ecoregions": LayerSpec("marine_ecoregions", "marine_ecoregions",
                                   "polygon"),
}

# Layers whose data is fetched from external sources rather than Natural
# Earth; they are optional and absent until scripts/fetch_data.py downloads
# them, so the app checks availability before drawing them.
OPTIONAL_LAYERS = frozenset({"biodiversity", "ecoregions", "marine_ecoregions"})

# Derived layers: filtered or assembled views of the specs above.
# key -> (source key, filter). The filter receives the source frame.
_MARITIME_200NM = {"Marine Indicator 200 mi nl"}

DERIVED = {
    # Country polygons dissolved by continent: outlines without borders.
    "continents": ("countries", None),  # special-cased (dissolve)
    "dependencies": ("countries",
                     lambda df: df[df["type"].isin(["Dependency", "Lease"])]),
    "deserts": ("regions",
                lambda df: df[df["featurecla"].str.lower() == "desert"]),
    "wadis": ("rivers",
              lambda df: df[df["featurecla"] == "River (Intermittent)"]),
    "capitals": ("cities", lambda df: df[df["adm0cap"] == 1]),
    "maritime": ("maritime_all",
                 lambda df: df[~df["featurecla"].isin(_MARITIME_200NM)]),
    "eez": ("maritime_all",
            lambda df: df[df["featurecla"].isin(_MARITIME_200NM)]),
}

# Depth steps of the ne_10m_bathymetry_all archive, shallow to deep.
BATHYMETRY_STEPS = [
    ("L", 0), ("K", 200), ("J", 1000), ("I", 2000), ("H", 3000), ("G", 4000),
    ("F", 5000), ("E", 6000), ("D", 7000), ("C", 8000), ("B", 9000),
    ("A", 10000),
]

# Curated view extents: (lon_min, lon_max, lat_min, lat_max).
CONTINENT_EXTENTS = {
    "World": (-180.0, 180.0, -90.0, 90.0),
    "Africa": (-20.0, 55.0, -38.0, 40.0),
    "Antarctica": (-180.0, 180.0, -90.0, -60.0),
    "Asia": (25.0, 180.0, -12.0, 78.0),
    "Europe": (-25.0, 45.0, 34.0, 72.0),
    "North America": (-170.0, -50.0, 5.0, 84.0),
    "Oceania": (105.0, 180.0, -50.0, 10.0),
    "South America": (-85.0, -33.0, -58.0, 14.0),
}


def default_data_dir() -> Path:
    """Locate data/ both from a source checkout and a PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", "")) or Path(sys.executable).parent
        return base / "data"
    return Path(__file__).resolve().parent.parent / "data"


class LayerStore:
    """Loads and caches Natural Earth layers on first use.

    Frames are cached three ways: parsed shapefiles are pickled to
    ``data/cache/`` (fast app restarts), loaded frames are kept in memory
    per source directory (fast layer toggles), and reprojected frames are
    kept per (directory, CRS) (fast projection switches).
    """

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self._dir_frames: dict[str, "object"] = {}      # directory -> frame
        self._derived_frames: dict[str, "object"] = {}  # derived key -> frame
        self._projected: dict[tuple[str, str], "object"] = {}
        self._labels: dict[str, pd.DataFrame] = {}
        self._basemap: np.ndarray | None = None
        self._cache_root: Path | None | bool = False  # False = not probed yet

    def _cache_dir(self) -> Path | None:
        """Directory for pickled frames: data/cache/ in a source checkout,
        the per-user cache directory when the install is read-only (a
        PyInstaller bundle), or None if nothing is writable."""
        if self._cache_root is not False:
            return self._cache_root
        candidates = [self.data_dir / "cache"]
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA",
                                  Path.home() / "AppData" / "Local")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Caches"
        else:
            base = os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
        candidates.append(Path(base) / "pymappr")
        self._cache_root = None
        for root in candidates:
            try:
                root.mkdir(parents=True, exist_ok=True)
                probe = root / ".write-probe"
                probe.touch()
                probe.unlink()
            except OSError:
                continue
            self._cache_root = root
            break
        return self._cache_root

    def check_data(self) -> str | None:
        """Return an error message if the data directory is unusable."""
        probe = (self.data_dir / "shapes" / LAYER_SPECS["countries"].directory
                 / (LAYER_SPECS["countries"].directory + ".shp"))
        if not probe.exists():
            return (f"Map data not found in {self.data_dir}.\n"
                    "Run 'python scripts/fetch_data.py' first.")
        return None

    def has_layer_data(self, key: str) -> bool:
        """Whether the shapefile backing *key* is present on disk. Used to
        check the optional external layers before drawing them."""
        spec = LAYER_SPECS.get(key)
        if spec is None:
            return True  # derived/special layers ride on Natural Earth data
        for directory in spec.directories():
            if self._shapefile_path(directory, spec.shapefile).exists():
                return True
        return False

    # -------------------------------------------------------------- loading

    def _shapefile_path(self, directory: str,
                        shapefile: str | None = None) -> Path:
        name = shapefile or directory
        return self.data_dir / "shapes" / directory / f"{name}.shp"

    def _read_shapefile(self, path: Path):
        """Read + trim a shapefile, through the pickle cache in data/cache/.

        The cache is invalidated by version and source mtime and every
        failure falls back to reading the shapefile, so a stale, corrupt,
        or unwritable cache can never break the app.
        """
        cache_root = self._cache_dir()
        cache = (cache_root / f"{path.stem}.pkl") if cache_root else None
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        if cache is not None and cache.exists():
            try:
                with open(cache, "rb") as fh:
                    version, stamp, gdf = pickle.load(fh)
                if version == _CACHE_VERSION and stamp == mtime:
                    return gdf
            except Exception:  # noqa: BLE001 - any bad cache -> reread
                pass
        import geopandas as gpd

        gdf = gpd.read_file(path)
        gdf.columns = [c.lower() for c in gdf.columns]
        keep = [c for c in gdf.columns if c in _KEEP_COLUMNS]
        gdf = gdf[keep]
        if cache is not None:
            try:
                with open(cache, "wb") as fh:
                    pickle.dump((_CACHE_VERSION, mtime, gdf), fh,
                                protocol=pickle.HIGHEST_PROTOCOL)
            except Exception:  # noqa: BLE001 - cache is best-effort only
                pass
        return gdf

    def _frame_for_directory(self, directory: str,
                             shapefile: str | None = None):
        if directory not in self._dir_frames:
            self._dir_frames[directory] = self._read_shapefile(
                self._shapefile_path(directory, shapefile))
        return self._dir_frames[directory]

    def warm_cache(self, keys=None, zooms=(0.0, 2.0)) -> None:
        """Pre-parse (and disk-cache) the layers behind *keys* at the given
        zoom levels. Called from a background thread at startup so the first
        click on a layer toggle doesn't pay the shapefile-parsing cost."""
        for key in keys or ("countries", "states", "lakes", "rivers",
                            "ocean", "land", "cities"):
            try:
                for zoom in zooms:
                    self.frame(key, zoom=zoom)
            except Exception:  # noqa: BLE001 - warming must never crash
                pass

    # --------------------------------------------------------------- frames

    def frame(self, key: str, zoom: float | None = None):
        """GeoDataFrame for a layer key (columns lower-cased, cached).

        *zoom* selects the resolution for multi-resolution layers; None
        picks the default (50m for the core layers). Derived keys
        (continents, dependencies, deserts, wadis, capitals, maritime, eez,
        bathymetry) are filtered/assembled views of the downloaded layers.
        """
        if key == "bathymetry":
            return self._bathymetry_frame()
        if key in DERIVED:
            return self._derived_frame(key)
        spec = LAYER_SPECS[key]
        directory = spec.directory_for_zoom(zoom)
        return self._frame_for_directory(directory, spec.shapefile)

    def _derived_frame(self, key: str):
        if key not in self._derived_frames:
            source, filt = DERIVED[key]
            if key == "continents":
                countries = self.frame(source)
                gdf = (countries[["continent", "geometry"]]
                       .dissolve(by="continent").reset_index())
            else:
                # Filters need attribute detail: use the source's most
                # detailed resolution (10m rivers carry the intermittent
                # flag, 10m places the capital flag, ...).
                spec = LAYER_SPECS[source]
                directories = spec.directories()
                gdf = filt(self._frame_for_directory(directories[-1],
                                                     spec.shapefile))
                gdf = gdf.reset_index(drop=True)
            self._derived_frames[key] = gdf
        return self._derived_frames[key]

    def _bathymetry_frame(self):
        """All bathymetry depth polygons in one frame with a depth column."""
        if "bathymetry" not in self._derived_frames:
            frames = []
            for letter, depth in BATHYMETRY_STEPS:
                path = (self.data_dir / "shapes" / "ne_10m_bathymetry_all"
                        / f"ne_10m_bathymetry_{letter}_{depth}.shp")
                gdf = self._read_shapefile(path)
                gdf = gdf.assign(depth=depth)
                frames.append(gdf)
            import geopandas as gpd

            self._derived_frames["bathymetry"] = gpd.GeoDataFrame(
                pd.concat(frames, ignore_index=True),
                geometry="geometry", crs=frames[0].crs)
        return self._derived_frames["bathymetry"]

    def frame_projected(self, key: str, crs: str | None,
                        max_lat: float = 90.0, zoom: float | None = None,
                        clip_shape=None):
        """A layer reprojected to *crs* (None = untouched lon/lat), cached.

        The data is clipped before reprojection to keep coordinates the
        projection cannot represent out of the transform: *clip_shape* (a
        shapely geometry in lon/lat) is used when given - regional
        projections pass their latitude band, the Globe its visible
        hemisphere - otherwise *max_lat* clips a symmetric band, for world
        projections such as Mercator that blow up at the poles.
        """
        if crs is None:
            return self.frame(key, zoom=zoom)
        if key in LAYER_SPECS:
            cache_name = LAYER_SPECS[key].directory_for_zoom(zoom)
        else:
            cache_name = key
        cache_key = (cache_name, crs)
        if cache_key not in self._projected:
            from shapely.geometry import box

            gdf = self.frame(key, zoom=zoom)
            if clip_shape is not None:
                gdf = gdf.clip(clip_shape)
            elif max_lat < 90.0:
                gdf = gdf.clip(box(-180, -max_lat, 180, max_lat))
            self._projected[cache_key] = gdf.to_crs(crs)
        return self._projected[cache_key]

    # --------------------------------------------------------------- labels

    def label_points(self, key: str) -> pd.DataFrame:
        """Label anchors for a layer: columns x, y, text, min_label.

        ``min_label`` is Natural Earth's curated zoom level at which the
        label becomes appropriate (smaller = show earlier / more important).
        Point layers (cities, airports, ports) use their own point
        coordinates and their ``min_zoom``/``scalerank`` ordering.
        """
        if key not in self._labels:
            if key in DERIVED and key != "continents":
                source, _filt = DERIVED[key]
                spec = LAYER_SPECS[source]
            else:
                spec = LAYER_SPECS[key]
            # frame() without a zoom returns the default resolution, so
            # label anchors stay stable while the drawn resolution switches.
            gdf = self.frame(key)
            if spec.label_directory is not None:
                gdf = self._frame_for_directory(spec.label_directory,
                                                spec.shapefile)
            label_col = spec.label_column
            df = gdf[gdf[label_col].notna() & (gdf[label_col] != "")].copy()
            if key in ("cities", "capitals"):
                # Natural Earth's curated min_zoom: the zoom at which each
                # place becomes appropriate to show.
                df["min_label"] = pd.to_numeric(
                    df.get("min_zoom", 5.0), errors="coerce").fillna(5.0)
            elif "min_label" not in df.columns:
                if "min_zoom" in df.columns:
                    df["min_label"] = pd.to_numeric(df["min_zoom"],
                                                    errors="coerce")
                elif "scalerank" in df.columns:
                    df["min_label"] = pd.to_numeric(df["scalerank"],
                                                    errors="coerce")
                else:
                    df["min_label"] = 5.0
            with warnings.catch_warnings():
                # Length/interpolate in degrees is fine for label placement.
                warnings.simplefilter("ignore")
                if key in ("rivers", "wadis"):
                    # A river is split into many segments; label the longest.
                    df["_len"] = df.geometry.length
                    df = (df.sort_values("_len", ascending=False)
                            .drop_duplicates(subset=label_col))
                if spec.geometry == "point":
                    pts = df.geometry
                elif spec.geometry == "line":
                    pts = df.geometry.interpolate(0.5, normalized=True)
                else:
                    pts = df.geometry.representative_point()
            self._labels[key] = pd.DataFrame({
                "x": pts.x.to_numpy(),
                "y": pts.y.to_numpy(),
                "text": df[label_col].astype(str).to_numpy(),
                "min_label": pd.to_numeric(df["min_label"],
                                           errors="coerce").fillna(5.0).to_numpy(),
            })
        return self._labels[key]

    def point_features(self, key: str) -> pd.DataFrame:
        """Point-layer features: columns x, y, min_zoom (for zoom culling).

        Used for the city/airport/port markers; *key* may also be a derived
        point layer such as ``capitals``.
        """
        gdf = self.frame(key)
        if "min_zoom" in gdf.columns:
            min_zoom = pd.to_numeric(gdf["min_zoom"], errors="coerce")
        elif "scalerank" in gdf.columns:
            min_zoom = pd.to_numeric(gdf["scalerank"], errors="coerce")
        else:
            min_zoom = pd.Series(0.0, index=gdf.index)
        return pd.DataFrame({
            "x": gdf.geometry.x.to_numpy(),
            "y": gdf.geometry.y.to_numpy(),
            "min_zoom": min_zoom.fillna(5.0).to_numpy(),
        })

    # -------------------------------------------------------------- basemap

    def basemap_image(self) -> np.ndarray:
        """Full-color world basemap as an RGB array (extent is the globe)."""
        if self._basemap is None:
            from PIL import Image

            path = self.data_dir / "basemap" / "ne1_world.jpg"
            with Image.open(path) as img:
                self._basemap = np.asarray(img.convert("RGB"))
        return self._basemap

    def icon_path(self) -> Path | None:
        path = self.data_dir / "icon" / "pymappr.ico"
        return path if path.exists() else None
