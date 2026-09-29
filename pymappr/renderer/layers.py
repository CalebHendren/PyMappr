"""The base map: raster basemaps, the Natural Earth line and fill
layers (drawn from whichever resolution the zoom calls for), bathymetry, and
the city / airport / port markers."""

from __future__ import annotations

import matplotlib.transforms as mtransforms
import numpy as np

from pymappr.layers import BATHYMETRY_STEPS, LAYER_SPECS, BoundedCache
from pymappr.renderer.tables import (BATHYMETRY_COLORS, FILL_COLORS,
                                     FILL_LAYERS, LINE_LAYERS, POINT_LAYERS,
                                     Z_BATHYMETRY, Z_LAKE_FILL, Z_OCEAN,
                                     Z_POINT_LAYERS, Z_SATELLITE)

# Warped-basemap grid (columns x rows) for projected satellite rendering,
# and the coarser one used while the globe is being dragged: a full warp is
# most of the cost of a spin step, and the drag only needs a preview.
_WARP_GRID = (1600, 800)
_DRAG_WARP_GRID = (400, 200)


class LayersMixin:
    """Basemaps and every Natural Earth layer."""

    def _init_layers(self) -> None:
        # Desired state, kept independently of the artists so the whole
        # scene can be rebuilt when the projection changes.
        self._line_visible: set[str] = set()
        self._fill_visible: set[str] = set()
        self._point_layers_visible: set[str] = set()
        self._bathymetry_visible = False
        self._capitals_only = False
        self._lake_fill = "none"
        self._ocean_fill = "none"
        self._basemap = "simple"
        self._line_scale = 1.0
        # Which resolution is currently shown for each visible layer.
        self._artist_res: dict[str, str] = {}
        self._point_layer_artists: dict[str, list] = {}
        # Keyed by projection, so bounded: a globe spin is a new projection
        # at every step.
        self._point_xy_cache = BoundedCache(maxsize=32)
        self._warp_cache = BoundedCache(maxsize=3)

    _RASTER_MODES = {"relief", "relief_alt", "relief_grey", "blue_marble"}

    def set_basemap(self, mode: str) -> None:
        """``"simple"`` or a raster mode (``"relief"``, ``"relief_alt"``,
        ``"relief_grey"``, ``"blue_marble"``)."""
        self._basemap = mode
        is_raster = mode in self._RASTER_MODES
        artist_key = f"raster_{mode}"
        if is_raster and artist_key not in self._artists:
            with self._preserving_view():
                img, extent = self._warped_basemap(mode)
                artists = []
                for off in self._offsets():
                    x0, x1, y0, y1 = extent
                    # aspect="auto" keeps the axes from locking to equal
                    # (imshow's default), which would letterbox any non-2:1
                    # extent - breaking portrait framing and re-fit sizing.
                    artist = self.ax.imshow(
                        img, extent=(x0 + off, x1 + off, y0, y1),
                        origin="upper", interpolation="bilinear",
                        aspect="auto", zorder=Z_SATELLITE)
                    artist._pym_offset = off
                    artists.append(artist)
                self._artists[artist_key] = artists
        # Show only the active raster; hide all others.
        for rmode in self._RASTER_MODES:
            rkey = f"raster_{rmode}"
            for artist in self._artists.get(rkey, []):
                artist.set_visible(rmode == mode)
        self._sync_wrap_copies()

    def _warped_basemap(self, mode: str) -> tuple[np.ndarray, tuple]:
        """The basemap image in the current projection, plus its extent."""
        img = self.store.basemap_image(mode)
        if self.proj.is_geographic:
            return img, (-180, 180, -90, 90)
        grid = _DRAG_WARP_GRID if self._globe_drag else _WARP_GRID
        cache_key = (self.proj.key, mode, grid)
        if cache_key not in self._warp_cache:
            wx0, wx1, wy0, wy1 = self.proj.bounds
            nx, ny = grid
            xs = np.linspace(wx0, wx1, nx)
            ys = np.linspace(wy1, wy0, ny)  # top row first (origin="upper")
            gx, gy = np.meshgrid(xs, ys)
            lons, lats = self.proj.inverse(gx.ravel(), gy.ravel())
            lons, lats = lons.reshape(gy.shape), lats.reshape(gy.shape)
            valid = (np.isfinite(lons) & np.isfinite(lats)
                     & (np.abs(lons) <= 180.001) & (np.abs(lats) <= 90.001))
            h, w = img.shape[:2]
            lons = np.clip(np.nan_to_num(lons, nan=0.0, posinf=0.0,
                                         neginf=0.0), -360.0, 360.0)
            lats = np.clip(np.nan_to_num(lats, nan=0.0, posinf=0.0,
                                         neginf=0.0), -90.0, 90.0)
            cols = np.clip(((lons + 180) / 360 * w).astype(int), 0, w - 1)
            rows = np.clip(((90 - lats) / 180 * h).astype(int), 0, h - 1)
            warped = np.zeros((ny, nx, 4), dtype=np.uint8)
            warped[..., :3] = img[rows, cols]
            warped[..., 3] = np.where(valid, 255, 0)
            self._warp_cache[cache_key] = (warped, (wx0, wx1, wy0, wy1))
        return self._warp_cache[cache_key]

    def _source_directory(self, source: str) -> str:
        """The Natural Earth directory the *source* layer should currently
        be drawn from (multi-resolution layers follow the zoom level)."""
        spec = LAYER_SPECS.get(source)
        if spec is None:  # derived layers have one fixed resolution
            return source
        return spec.directory_for_zoom(self._zoom_level())

    def _projected_frame(self, source: str):
        return self.store.frame_projected(source, self.proj.crs,
                                          self.proj.max_lat,
                                          zoom=self._zoom_level(),
                                          clip_shape=self.proj.clip_shape())

    def _sync_resolutions(self) -> None:
        """Swap multi-resolution layers to the resolution matching the new
        zoom. Building a resolution is a one-time cost; afterwards crossing
        a threshold only flips artist visibility."""
        for key in tuple(self._line_visible):
            if self._artist_res.get(key) != self._source_directory(
                    LINE_LAYERS[key][0]):
                self._show_line_layer(key)
        for key in tuple(self._fill_visible):
            if self._artist_res.get(key) != self._source_directory(
                    FILL_LAYERS[key][0]):
                self._show_fill_layer(key)
        for source, mode in (("lakes", self._lake_fill),
                             ("ocean", self._ocean_fill)):
            if (mode != "none" and self._artist_res.get(source + "_fill")
                    != self._source_directory(source)):
                self._show_mode_fill(source, mode)
        if ("continents" in self._artist_res
                and "countries" not in self._line_visible
                and self._artist_res.get("continents")
                != self._source_directory("continents")):
            self._sync_continents()

    def _show_variant(self, key: str, source: str, plot) -> None:
        """Show *key* drawn from the current resolution of *source*, hiding
        any other resolution's artists; *plot* builds the artists lazily."""
        directory = self._source_directory(source)
        artist_key = f"{key}@{directory}"
        if artist_key not in self._artists:
            self._artists[artist_key] = plot(directory)
        for name, artists in self._artists.items():
            if name.startswith(key + "@"):
                visible = name == artist_key
                for artist in artists:
                    artist.set_visible(visible)
        self._artist_res[key] = directory
        self._sync_wrap_copies()

    def _sync_wrap_copies(self) -> None:
        """Hide the wrap-around world copies while the view stays inside
        the primary world. Rendering skips them entirely then, which makes
        panning/zooming with heavy 10m layers visible ~3x faster; the
        copies reappear the moment the view crosses a world edge."""
        x0, x1 = sorted(self.ax.get_xlim())
        wx0, wx1 = self.proj.bounds[0], self.proj.bounds[1]
        need = {-1.0: x0 < wx0, 1.0: x1 > wx1}
        for artists in self._artists.values():
            base_visible = None
            for artist in artists:
                if not getattr(artist, "_pym_offset", 0.0):
                    base_visible = artist.get_visible()
                    break
            if base_visible is None:
                continue
            for artist in artists:
                offset = getattr(artist, "_pym_offset", 0.0)
                if offset:
                    artist.set_visible(base_visible
                                       and need[float(np.sign(offset))])

    def _hide_layer(self, key: str) -> None:
        for name, artists in self._artists.items():
            if name.startswith(key + "@"):
                for artist in artists:
                    artist.set_visible(False)
        self._artist_res.pop(key, None)

    def _plot_gdf_copies(self, gdf, zorder: float, **plot_kwargs) -> list:
        """Plot a GeoDataFrame plus one wrapped copy either side.

        Only the primary copy pays the geometry-to-path conversion; the two
        wrap-around copies are collections sharing the same Path objects,
        shifted one world-width left/right, which makes switching big
        layers on (roads, urban areas, bathymetry) about 3x faster."""
        from matplotlib.collections import PathCollection

        artists = []
        # A layer can clip to nothing in the current projection (e.g. a
        # regional layer on the far side of the globe): geopandas then adds no
        # collection, so there is nothing to copy - bail out with no artists.
        if gdf is None or len(gdf) == 0:
            return artists
        with self._preserving_view():
            before = len(self.ax.collections)
            # aspect=None stops geopandas from forcing equal axes aspect,
            # which would letterbox the map inside the canvas.
            gdf.plot(ax=self.ax, zorder=zorder, aspect=None, **plot_kwargs)
            # geopandas 1.2+ names the axes after the CRS ("Geodetic
            # latitude [degree]"), which would crop into every export.
            self.ax.set_xlabel("")
            self.ax.set_ylabel("")
            if len(self.ax.collections) == before:
                return artists
            base = self.ax.collections[before]
            base._pym_offset = 0.0
            artists.append(base)
            for off in self._offsets():
                if not off:
                    continue
                copy = PathCollection(base.get_paths())
                copy.update_from(base)
                copy.set_zorder(zorder)
                copy.set_transform(mtransforms.Affine2D().translate(
                    off, 0) + self.ax.transData)
                copy._pym_offset = off
                self.ax.add_collection(copy, autolim=False)
                artists.append(copy)
        return artists

    def _show_line_layer(self, key: str) -> None:
        source, color, width, zorder, linestyle = LINE_LAYERS[key]

        def plot(_directory: str) -> list:
            gdf = self._projected_frame(source)
            return self._plot_gdf_copies(
                gdf, zorder, facecolor="none", edgecolor=color,
                linewidth=width * self._line_scale, linestyle=linestyle)

        self._show_variant(key, source, plot)

    def set_layer(self, key: str, visible: bool) -> None:
        """Toggle a line layer (countries, states, disputed_lines, reefs,
        ...). Switching countries off swaps in the continent outlines so
        coastlines/continent borders stay visible."""
        if visible:
            self._line_visible.add(key)
            self._show_line_layer(key)
        else:
            self._line_visible.discard(key)
            self._hide_layer(key)
        if key == "countries":
            self._sync_continents()

    def _sync_continents(self) -> None:
        show = "countries" not in self._line_visible
        if show:
            self._show_line_layer("continents")
        else:
            self._hide_layer("continents")

    def set_line_width_scale(self, scale: float) -> None:
        """Scale the line width of every vector line layer (0.25 - 3)."""
        self._line_scale = max(float(scale), 0.05)
        for artist_key, artists in self._artists.items():
            key = artist_key.split("@", 1)[0]
            if key in LINE_LAYERS:
                width = LINE_LAYERS[key][2]
                for artist in artists:
                    artist.set_linewidth(width * self._line_scale)

    def set_lake_fill(self, mode: str) -> None:
        """``"none"``, ``"grey"`` or ``"blue"``."""
        self._lake_fill = mode
        if mode == "none":
            self._hide_layer("lakes_fill")
        else:
            self._show_mode_fill("lakes", mode)

    def set_ocean(self, mode: str) -> None:
        """``"none"``, ``"grey"`` or ``"blue"``."""
        self._ocean_fill = mode
        if mode == "none":
            self._hide_layer("ocean_fill")
        else:
            self._show_mode_fill("ocean", mode)

    def _show_mode_fill(self, source: str, mode: str) -> None:
        zorder = Z_LAKE_FILL if source == "lakes" else Z_OCEAN

        def plot(_directory: str) -> list:
            gdf = self._projected_frame(source)
            return self._plot_gdf_copies(gdf, zorder, edgecolor="none")

        key = source + "_fill"
        self._show_variant(key, source, plot)
        directory = self._artist_res[key]
        for artist in self._artists[f"{key}@{directory}"]:
            artist.set_facecolor(FILL_COLORS[(source, mode)])

    def set_fill_layer(self, key: str, visible: bool) -> None:
        """Toggle an on/off fill layer: land, glaciers, ice_shelves, urban,
        parks, playas, deserts, disputed."""
        if visible:
            self._fill_visible.add(key)
            self._show_fill_layer(key)
        else:
            self._fill_visible.discard(key)
            self._hide_layer(key)

    def _show_fill_layer(self, key: str) -> None:
        source, face, edge, edge_w, alpha, zorder = FILL_LAYERS[key]

        def plot(_directory: str) -> list:
            gdf = self._projected_frame(source)
            return self._plot_gdf_copies(
                gdf, zorder, facecolor=face, edgecolor=edge,
                linewidth=edge_w, alpha=alpha)

        self._show_variant(key, source, plot)

    def set_bathymetry(self, visible: bool) -> None:
        """Toggle the stacked ocean-depth polygons (10m bathymetry)."""
        self._bathymetry_visible = visible
        if visible:
            self._show_bathymetry()
        else:
            self._hide_layer("bathymetry")

    def _show_bathymetry(self) -> None:
        def plot(_directory: str) -> list:
            gdf = self.store.frame_projected("bathymetry", self.proj.crs,
                                             self.proj.max_lat,
                                             clip_shape=self.proj.clip_shape())
            artists = []
            for _letter, depth in BATHYMETRY_STEPS:
                sub = gdf[gdf["depth"] == depth]
                if not len(sub):
                    continue
                artists.extend(self._plot_gdf_copies(
                    sub, Z_BATHYMETRY + depth * 1e-6, edgecolor="none",
                    facecolor=BATHYMETRY_COLORS[depth]))
            return artists

        self._show_variant("bathymetry", "bathymetry", plot)

    def set_point_layer(self, key: str, visible: bool) -> None:
        """Toggle a point-marker layer: cities, airports, ports. City
        markers respect :meth:`set_capitals_only`."""
        if visible:
            self._point_layers_visible.add(key)
        else:
            self._point_layers_visible.discard(key)
        self._refresh_point_layers()

    def set_capitals_only(self, capitals_only: bool) -> None:
        """Restrict the cities layer (markers and labels) to national
        capitals."""
        self._capitals_only = bool(capitals_only)
        self._refresh_point_layers()
        self._refresh_labels()

    def _point_xy(self, source: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cache_key = (source, self.proj.key)
        if cache_key not in self._point_xy_cache:
            features = self.store.point_features(source)
            xs, ys = self.proj.forward(features["x"].to_numpy(),
                                       features["y"].to_numpy())
            self._point_xy_cache[cache_key] = (
                np.asarray(xs, float), np.asarray(ys, float),
                features["min_zoom"].to_numpy())
        return self._point_xy_cache[cache_key]

    def _refresh_point_layers(self) -> None:
        """(Re)draw the visible point-marker layers for the current zoom;
        features appear once their min_zoom/scalerank allows. Runs on every
        pan and zoom step, so an existing layer's markers are moved rather
        than rebuilt."""
        zoom = self._zoom_level()
        previous = self._point_layer_artists
        self._point_layer_artists = {}
        for key in self._point_layers_visible:
            layer = key
            if key == "cities" and self._capitals_only:
                layer = "capitals"
            source, marker, size, face, edge, bias = POINT_LAYERS[layer]
            xs, ys, min_zoom = self._point_xy(source)
            show = min_zoom <= zoom + bias
            if not show.any():
                continue
            offsets = self._offsets()
            xy = np.column_stack(
                [np.concatenate([xs[show] + off for off in offsets]),
                 np.tile(ys[show], len(offsets))])
            (artist,) = previous.pop(key, [None])
            if artist is not None and artist._pym_layer == layer:
                artist.set_offsets(xy)
            else:
                if artist is not None:
                    artist.remove()
                with self._preserving_view():
                    artist = self.ax.scatter(
                        xy[:, 0], xy[:, 1], s=size, c=face, marker=marker,
                        edgecolors=edge, linewidths=0.5,
                        zorder=Z_POINT_LAYERS)
                artist._pym_layer = layer
            self._point_layer_artists[key] = [artist]
        for artists in previous.values():
            for artist in artists:
                artist.remove()
