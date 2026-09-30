"""The base map: raster basemaps, the Natural Earth line and fill
layers (drawn from whichever resolution the zoom calls for), bathymetry, and
the city / airport / port markers."""

from __future__ import annotations

from dataclasses import dataclass

import matplotlib.transforms as mtransforms
import numpy as np

from pymappr.layers import BATHYMETRY_STEPS, LAYER_SPECS, BoundedCache
from pymappr.renderer.tables import (BATHYMETRY_COLORS, FILL_COLORS,
                                     FILL_LAYERS, LINE_LAYERS, POINT_LAYERS,
                                     Z_BATHYMETRY, Z_LAKE_FILL, Z_OCEAN,
                                     Z_POINT_LAYERS, Z_SATELLITE)

# Source basemap pixels per screen pixel. Handing imshow the whole 5400x2700
# world made matplotlib convert and resample all 14.6M pixels on every draw,
# whatever was on screen - ~1000 ms a frame, which is what made panning a
# colorized basemap lag. Drawing from the pyramid level and crop the view
# actually needs costs ~70 ms instead, and the pixels come out the same.
# A little over 1 keeps bilinear sampling honest without paying for detail
# nobody can see.
_OVERSAMPLE = 1.3
# While the globe is mid-spin a coarse preview will do; the release rebuilds
# at full detail (see MouseMixin._on_canvas_release).
_DRAG_OVERSAMPLE = 0.35
# The crop is grown by this much of the view span on each side, so a small pan
# or zoom reuses it instead of re-cropping.
_CROP_MARGIN = 0.15
# A crop is reused while it spans no more than this much of what the view
# needs. Slack enough to pan and zoom a little without re-cropping, tight
# enough that a zoom never leaves imshow resampling mostly-offscreen pixels.
_CROP_REUSE = 2.0
# A warp grid never exceeds this, however large the window: the inverse
# transform is per-point, so this bounds the cost of one settle pass.
_MAX_WARP_PX = 2400


@dataclass
class _Crop:
    """A basemap image prepared for one region of one view.

    Kept on the artist so a view change can tell whether the crop already
    loaded still serves: re-cropping is only needed when the detail level
    changes or the view moves outside *region*.
    """

    image: np.ndarray
    extent: tuple[float, float, float, float]
    level: int
    region: tuple[float, float, float, float]
    px: tuple[int, int] = (0, 0)
    oversample: float = 0.0
    proj_key: object = None

    def matches(self, px: tuple[int, int], oversample: float,
                proj_key: object) -> bool:
        return (self.px == px and self.oversample == oversample
                and self.proj_key == proj_key)

    def covers(self, region: tuple[float, float, float, float]) -> bool:
        x0, x1, y0, y1 = region
        rx0, rx1, ry0, ry1 = self.region
        return rx0 <= x0 and rx1 >= x1 and ry0 <= y0 and ry1 >= y1

    def oversized(self, region: tuple[float, float, float, float],
                  factor: float) -> bool:
        """Whether this crop spans more than *factor* times *region*.

        Covering the view is not enough to justify reuse: zoom in far enough
        and a crop still covers everything while most of its pixels have gone
        off screen, which is the cost this whole mechanism exists to avoid.
        The factor is the slack that stops a small zoom from re-cropping."""
        x0, x1, y0, y1 = region
        rx0, rx1, ry0, ry1 = self.region
        return ((rx1 - rx0) > (x1 - x0) * factor
                or (ry1 - ry0) > (y1 - y0) * factor)


def _require_key(key: str, table: dict, what: str) -> None:
    """Reject an unknown layer key before any state records it.

    The toggles below note the key in their "visible" set and only then look
    it up, so without this an unknown key would leave that set holding a name
    nothing can draw - and every later ``_sync_resolutions`` would raise on
    it, turning a typo here into a crash on the next pan."""
    if key not in table:
        raise KeyError(f"unknown {what}: {key!r}")


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
        # Keyed by projection, mode and crop, so a pan that leaves the current
        # crop behind can find the neighbouring one again.
        self._warp_cache = BoundedCache(maxsize=12)

    _RASTER_MODES = {"relief", "relief_alt", "relief_grey", "blue_marble"}

    def set_basemap(self, mode: str) -> None:
        """``"simple"`` or a raster mode (``"relief"``, ``"relief_alt"``,
        ``"relief_grey"``, ``"blue_marble"``)."""
        self._basemap = mode
        is_raster = mode in self._RASTER_MODES
        artist_key = f"raster_{mode}"
        if is_raster and artist_key not in self._artists:
            crop = self._basemap_crop(mode)
            with self._preserving_view():
                artists = []
                for off in self._offsets():
                    # aspect="auto" keeps the axes from locking to equal
                    # (imshow's default), which would letterbox any non-2:1
                    # extent - breaking portrait framing and re-fit sizing.
                    x0, x1, y0, y1 = crop.extent
                    artist = self.ax.imshow(
                        crop.image, extent=(x0 + off, x1 + off, y0, y1),
                        origin="upper", interpolation="bilinear",
                        aspect="auto", zorder=Z_SATELLITE)
                    artist._pym_offset = off
                    # Left unstamped, so the refresh below gives each copy the
                    # crop its own slice of the world needs.
                    artist._pym_crop = None
                    artists.append(artist)
                self._artists[artist_key] = artists
        # Show only the active raster; hide all others.
        for rmode in self._RASTER_MODES:
            rkey = f"raster_{rmode}"
            for artist in self._artists.get(rkey, []):
                artist.set_visible(rmode == mode)
        self._sync_wrap_copies()
        # Each wrap copy covers a different slice of the world, so let the
        # view-driven refresh give every visible one its own crop.
        self._refresh_basemap()

    # ------------------------------------------------------- basemap detail

    def _axes_px(self, dpi: float | None = None) -> tuple[int, int]:
        """The map axes' size in pixels, at *dpi* (the figure's own if None).

        Exports render at their own dpi without touching ``fig.dpi``, so the
        dpi has to be passed in or a 200-dpi save would be handed the crop
        sized for a 100-dpi screen."""
        pos = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        scale = self.fig.dpi if dpi is None else dpi
        return (max(int(pos.width * float(fig_w) * scale), 1),
                max(int(pos.height * float(fig_h) * scale), 1))

    def _basemap_oversample(self) -> float:
        return _DRAG_OVERSAMPLE if self._globe_drag else _OVERSAMPLE

    def _view_region(self, margin: float = 0.0) -> tuple[float, ...]:
        """The view in map coordinates, optionally grown by *margin* of its
        own span on each side."""
        x0, x1 = sorted(self.ax.get_xlim())
        y0, y1 = sorted(self.ax.get_ylim())
        mx, my = (x1 - x0) * margin, (y1 - y0) * margin
        return x0 - mx, x1 + mx, y0 - my, y1 + my

    def _clip_to_world(self, region: tuple[float, ...]) -> tuple | None:
        """*region* intersected with the projection's bounds, or None when it
        falls entirely outside (a wrap copy that is off screen)."""
        x0, x1, y0, y1 = region
        wx0, wx1, wy0, wy1 = self.proj.bounds
        x0, x1 = max(x0, wx0), min(x1, wx1)
        y0, y1 = max(y0, wy0), min(y1, wy1)
        if x1 <= x0 or y1 <= y0:
            return None
        return x0, x1, y0, y1

    def _pyramid_level(self, mode: str, span: float, px: int) -> int:
        """Index of the coarsest mipmap level still carrying enough detail for
        a view *span* map-units wide drawn *px* pixels wide."""
        levels = self.store.basemap_pyramid(mode)
        fraction = max(span / self.proj.world_width, 1e-9)
        want = self._basemap_oversample() * px
        index = 0
        for i, level in enumerate(levels):
            if level.shape[1] * fraction >= want:
                index = i
            else:
                break
        return index

    def _basemap_crop(self, mode: str, region: tuple | None = None,
                      dpi: float | None = None,
                      level: int | None = None) -> _Crop:
        """The basemap covering *region* (the padded view by default), at the
        detail the current view and dpi call for."""
        if region is None:
            region = self._clip_to_world(self._view_region(_CROP_MARGIN))
            if region is None:  # a degenerate view; fall back to the world
                region = self.proj.bounds
        px = self._axes_px(dpi)
        if level is None:
            level = self._pyramid_level(mode, region[1] - region[0], px[0])
        if self.proj.is_geographic:
            crop = self._crop_geographic(mode, region, level)
        else:
            crop = self._warp_projected(mode, region, px[0], px[1], level)
        crop.px = px
        crop.oversample = self._basemap_oversample()
        crop.proj_key = self.proj.key
        return crop

    def _crop_geographic(self, mode: str, region: tuple,
                         level: int) -> _Crop:
        """A slice of the mipmap for an unprojected (lon/lat) view.

        The slice is a numpy view, so this costs nothing beyond picking the
        level - the saving is entirely in what imshow is then asked to
        resample."""
        lon0, lon1, lat0, lat1 = region
        img = self.store.basemap_pyramid(mode)[level]
        h, w = img.shape[:2]
        c0 = max(int(np.floor((lon0 + 180.0) / 360.0 * w)), 0)
        c1 = min(int(np.ceil((lon1 + 180.0) / 360.0 * w)) + 1, w)
        r0 = max(int(np.floor((90.0 - lat1) / 180.0 * h)), 0)
        r1 = min(int(np.ceil((90.0 - lat0) / 180.0 * h)) + 1, h)
        c1, r1 = max(c1, c0 + 1), max(r1, r0 + 1)
        extent = (c0 / w * 360.0 - 180.0, c1 / w * 360.0 - 180.0,
                  90.0 - r1 / h * 180.0, 90.0 - r0 / h * 180.0)
        return _Crop(img[r0:r1, c0:c1], extent, level, region)

    def _warp_projected(self, mode: str, region: tuple, px_w: int,
                        px_h: int, level: int) -> _Crop:
        """Inverse-warp the basemap into a projected view.

        The grid covers the visible region at screen resolution rather than
        the whole projection at a fixed 1600x800: a zoomed-in projected map
        used to be resampled up from a world-wide grid, so this is sharper as
        well as cheaper."""
        x0, x1, y0, y1 = region
        over = self._basemap_oversample()
        nx = int(min(max(px_w * over, 2), _MAX_WARP_PX))
        ny = int(min(max(px_h * over, 2), _MAX_WARP_PX))
        img = self.store.basemap_pyramid(mode)[level]
        cache_key = (self.proj.key, mode, level, nx, ny,
                     round(x0, 6), round(x1, 6), round(y0, 6), round(y1, 6))
        if cache_key not in self._warp_cache:
            xs = np.linspace(x0, x1, nx)
            ys = np.linspace(y1, y0, ny)  # top row first (origin="upper")
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
            self._warp_cache[cache_key] = warped
        return _Crop(self._warp_cache[cache_key], (x0, x1, y0, y1), level,
                     region)

    def _refresh_basemap(self, dpi: float | None = None) -> None:
        """Point each visible raster artist at the crop its part of the view
        needs. Runs on every view change, but only re-crops when the detail
        level changed or the view left the crop already loaded."""
        mode = self._basemap
        if mode not in self._RASTER_MODES:
            return
        artists = self._artists.get(f"raster_{mode}")
        if not artists:
            return
        px = self._axes_px(dpi)
        over = self._basemap_oversample()
        vx0, vx1, vy0, vy1 = self._view_region()
        # One level for every copy, taken from the whole view rather than each
        # copy's slice: a wrap copy showing a thin sliver would otherwise pick
        # a finer level than the primary and the seam would change sharpness
        # mid-pan.
        level = self._pyramid_level(mode, vx1 - vx0, px[0])
        for artist in artists:
            if not artist.get_visible():
                continue
            # A wrap copy is drawn one world-width over, so it shows the slice
            # of the world the view covers once shifted back.
            off = float(getattr(artist, "_pym_offset", 0.0))
            raw = (vx0 - off, vx1 - off, vy0, vy1)
            needed = self._clip_to_world(raw)
            if needed is None:
                continue
            # The margin is grown on the *unclipped* view, then clipped. Grown
            # on the clipped sliver instead, a copy at the world's edge would
            # get a margin a fraction of a sliver wide and leave its crop again
            # on the very next frame.
            padded = self._clip_to_world(self._pad(raw, _CROP_MARGIN)) or needed
            current = getattr(artist, "_pym_crop", None)
            if (current is not None and current.matches(px, over, self.proj.key)
                    and current.level == level and current.covers(needed)
                    and not current.oversized(padded, _CROP_REUSE)):
                continue
            crop = self._basemap_crop(mode, padded, dpi, level=level)
            x0, x1, y0, y1 = crop.extent
            with self._preserving_view():
                artist.set_data(crop.image)
                artist.set_extent((x0 + off, x1 + off, y0, y1))
            artist._pym_crop = crop

    @staticmethod
    def _pad(region: tuple, margin: float) -> tuple:
        x0, x1, y0, y1 = region
        mx, my = (x1 - x0) * margin, (y1 - y0) * margin
        return x0 - mx, x1 + mx, y0 - my, y1 + my

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
        _require_key(key, LINE_LAYERS, "line layer")
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
        _require_key(key, FILL_LAYERS, "fill layer")
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
        _require_key(key, POINT_LAYERS, "point layer")
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
