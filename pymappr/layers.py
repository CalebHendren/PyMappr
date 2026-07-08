"""Natural Earth layer access: lazy loading, label points, continent extents.

Layers live in ``data/`` (populated by ``scripts/fetch_data.py``). In a
PyInstaller build the same tree is bundled next to the executable.
"""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = ["LayerStore", "LAYER_SPECS", "CONTINENT_EXTENTS", "default_data_dir"]


@dataclass(frozen=True)
class LayerSpec:
    key: str
    directory: str
    geometry: str  # "polygon" or "line"
    label_cap: int = 0  # max labels drawn at once; 0 = layer is never labelled


LAYER_SPECS = {
    "countries": LayerSpec("countries", "ne_50m_admin_0_countries", "polygon", 400),
    "states": LayerSpec("states", "ne_10m_admin_1_states_provinces", "polygon", 600),
    "counties": LayerSpec("counties", "ne_10m_admin_2_counties", "polygon", 1200),
    "lakes": LayerSpec("lakes", "ne_50m_lakes", "polygon", 60),
    "rivers": LayerSpec("rivers", "ne_10m_rivers_lake_centerlines", "line", 60),
    "ocean": LayerSpec("ocean", "ne_50m_ocean", "polygon"),
    "roads": LayerSpec("roads", "ne_10m_roads", "line"),
}

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
    """Loads and caches Natural Earth layers on first use."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self._frames: dict[str, "object"] = {}
        self._projected: dict[tuple[str, str], "object"] = {}
        self._labels: dict[str, pd.DataFrame] = {}
        self._basemap: np.ndarray | None = None

    def check_data(self) -> str | None:
        """Return an error message if the data directory is unusable."""
        probe = (self.data_dir / "shapes" / LAYER_SPECS["countries"].directory
                 / (LAYER_SPECS["countries"].directory + ".shp"))
        if not probe.exists():
            return (f"Map data not found in {self.data_dir}.\n"
                    "Run 'python scripts/fetch_data.py' first.")
        return None

    def frame(self, key: str):
        """GeoDataFrame for a layer, columns lower-cased, cached.

        ``"continents"`` is a derived layer: the country polygons dissolved
        by continent, giving continent outlines without political borders.
        """
        if key not in self._frames:
            if key == "continents":
                countries = self.frame("countries")
                gdf = (countries[["continent", "geometry"]]
                       .dissolve(by="continent").reset_index())
            else:
                import geopandas as gpd

                spec = LAYER_SPECS[key]
                path = (self.data_dir / "shapes" / spec.directory
                        / f"{spec.directory}.shp")
                gdf = gpd.read_file(path)
                gdf.columns = [c.lower() for c in gdf.columns]
            self._frames[key] = gdf
        return self._frames[key]

    def frame_projected(self, key: str, crs: str | None, max_lat: float = 90.0):
        """A layer reprojected to *crs* (None = untouched lon/lat), cached.

        *max_lat* clips the data first, for projections such as Mercator
        that blow up at the poles.
        """
        if crs is None:
            return self.frame(key)
        cache_key = (key, crs)
        if cache_key not in self._projected:
            from shapely.geometry import box

            gdf = self.frame(key)
            if max_lat < 90.0:
                gdf = gdf.clip(box(-180, -max_lat, 180, max_lat))
            self._projected[cache_key] = gdf.to_crs(crs)
        return self._projected[cache_key]

    def label_points(self, key: str) -> pd.DataFrame:
        """Label anchors for a layer: columns x, y, text, min_label.

        ``min_label`` is Natural Earth's curated zoom level at which the
        label becomes appropriate (smaller = show earlier / more important).
        """
        if key not in self._labels:
            gdf = self.frame(key)
            spec = LAYER_SPECS[key]
            df = gdf[gdf["name"].notna() & (gdf["name"] != "")].copy()
            if "min_label" not in df.columns:
                df["min_label"] = 5.0
            with warnings.catch_warnings():
                # Length/interpolate in degrees is fine for label placement.
                warnings.simplefilter("ignore")
                if key == "rivers":
                    # A river is split into many segments; label the longest.
                    df["_len"] = df.geometry.length
                    df = (df.sort_values("_len", ascending=False)
                            .drop_duplicates(subset="name"))
                if spec.geometry == "line":
                    pts = df.geometry.interpolate(0.5, normalized=True)
                else:
                    pts = df.geometry.representative_point()
            self._labels[key] = pd.DataFrame({
                "x": pts.x.to_numpy(),
                "y": pts.y.to_numpy(),
                "text": df["name"].to_numpy(),
                "min_label": pd.to_numeric(df["min_label"],
                                           errors="coerce").fillna(5.0).to_numpy(),
            })
        return self._labels[key]

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
