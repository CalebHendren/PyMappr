"""Matplotlib map rendering for EzMaps.

The renderer owns one Figure/Axes pair. Every map layer becomes a small set
of matplotlib artists, created lazily the first time it is switched on and
then toggled with ``set_visible`` - this keeps interaction real-time instead
of re-plotting shapefiles on every change.

Two cross-cutting features shape the implementation:

* **Wrap-around panning** - every layer is drawn three times, at horizontal
  offsets of one world-width left and right of the primary copy, and the
  view is re-centered whenever a pan crosses the antimeridian. Panning east
  or west therefore loops around the globe seamlessly.
* **Projections** - all drawing goes through a `Projection` (see
  ``ezmaps.projections``). The default Equirectangular projection is the
  identity; the others reproject vectors, points, labels, and the basemap.
"""

from __future__ import annotations

from contextlib import contextmanager

import matplotlib.patheffects as patheffects
import matplotlib.transforms as mtransforms
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoLocator, FuncFormatter, MultipleLocator

from ezmaps.layers import CONTINENT_EXTENTS, LAYER_SPECS, LayerStore
from ezmaps.projections import get_projection
from ezmaps.styles import PointStyle

__all__ = ["MapRenderer"]

# Vector line layers: layer key -> (source layer, edge color, width, zorder).
# "continents" is the countries layer dissolved by continent; it stands in
# for the countries layer when political borders are switched off.
LINE_LAYERS = {
    "countries": ("countries", "#000000", 0.8, 1.6),
    "continents": ("continents", "#000000", 0.8, 1.55),
    "states": ("states", "#5a5a5a", 0.5, 1.5),
    "counties": ("counties", "#8a8a8a", 0.35, 1.4),
    "lakes_outline": ("lakes", "#2d5f8a", 0.6, 1.2),
    "rivers": ("rivers", "#4a90c4", 0.5, 1.0),
    "roads": ("roads", "#b0693c", 0.35, 1.1),
}

FILL_COLORS = {
    ("lakes", "grey"): "#c9c9c9",
    ("lakes", "blue"): "#a6cae0",
    ("ocean", "grey"): "#dcdcdc",
    ("ocean", "blue"): "#d4e6f4",
}

# Label layers: key -> (source layer, font kwargs, min zoom).
# Once the view is zoomed in at least to *min zoom* (zoom 0 = whole world,
# +1 per 2x magnification), every feature inside the view is labelled, up to
# the per-layer cap in LAYER_SPECS. Countries use min zoom 0 so every
# country in view is labelled even fully zoomed out.
LABEL_STYLES = {
    "countries": ("countries", dict(fontsize=9, color="#1a1a1a", fontweight="bold"), 0.0),
    "states": ("states", dict(fontsize=8, color="#3a3a3a"), 1.2),
    "counties": ("counties", dict(fontsize=6.5, color="#4a4a4a"), 3.6),
    "lakes": ("lakes", dict(fontsize=7.5, color="#14477a", fontstyle="italic"), 1.5),
    "rivers": ("rivers", dict(fontsize=7, color="#14477a", fontstyle="italic"), 1.5),
}

_LABEL_HALO = [patheffects.withStroke(linewidth=2.2, foreground="white", alpha=0.85)]

Z_SATELLITE = 0.1
Z_OCEAN = 0.3
Z_LAKE_FILL = 0.5
Z_GRID = 1.8
Z_POINTS = 2.6
Z_LABELS = 3.0

_MARGINS_WITH_TICKS = (0.055, 0.045, 0.99, 0.99)   # left, bottom, right, top
_MARGINS_PLAIN = (0.01, 0.012, 0.99, 0.988)

# Horizontal world copies drawn for wrap-around panning, in world-widths.
_WRAP_OFFSETS = (-1, 0, 1)

# Warped-basemap grid (columns x rows) for projected satellite rendering.
_WARP_GRID = (1600, 800)


def _norm_lon(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _format_lon(value: float, _pos=None) -> str:
    value = _norm_lon(value)
    if value in (0, 180, -180):
        return f"{abs(value):g}\N{DEGREE SIGN}"
    return f"{abs(value):g}\N{DEGREE SIGN}{'W' if value < 0 else 'E'}"


def _format_lat(value: float, _pos=None) -> str:
    if value == 0:
        return "0\N{DEGREE SIGN}"
    return f"{abs(value):g}\N{DEGREE SIGN}{'S' if value < 0 else 'N'}"


class MapRenderer:
    def __init__(self, figure, store: LayerStore):
        self.fig = figure
        self.store = store
        self.ax = figure.add_axes([0.055, 0.045, 0.935, 0.945])
        self.ax.set_autoscale_on(False)
        self.ax.xaxis.set_major_formatter(FuncFormatter(_format_lon))
        self.ax.yaxis.set_major_formatter(FuncFormatter(_format_lat))
        self.ax.tick_params(labelsize=7, length=2.5, direction="out")

        self.proj = get_projection("Equirectangular")

        # Desired state, kept independently of the artists so the whole
        # scene can be rebuilt when the projection changes.
        self._line_visible: set[str] = set()
        self._lake_fill = "none"
        self._ocean_fill = "none"
        self._basemap = "simple"
        self._label_visible: set[str] = set()
        self._graticule: float | None = None
        self._graticule_labels = True
        self._line_scale = 1.0
        self._extent_request = "World"

        # (label, PointStyle, lons, lats) per group
        self._point_groups: list[tuple[str, PointStyle, np.ndarray, np.ndarray]] = []
        self._point_artists: list = []
        self._legend_visible = True
        self._legend_title: str | None = None
        self._legend_loc = "best"
        self._legend_fontsize = 8.0
        self._legend_columns = 1
        self._legend_frame = True

        self._artists: dict[str, list] = {}
        self._label_texts: dict[str, list] = {}
        self._label_xy_cache: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        self._warp_cache: dict[str, tuple[np.ndarray, tuple]] = {}
        self._in_wrap = False

        self.set_extent("World")
        self._apply_graticule()
        self.ax.callbacks.connect("xlim_changed", self._on_limits_changed)
        self.ax.callbacks.connect("ylim_changed", self._on_limits_changed)

    # ------------------------------------------------------------------ view

    @contextmanager
    def _preserving_view(self):
        """Adding artists (gdf.plot / imshow) must never move the camera."""
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim()
        try:
            yield
        finally:
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

    def set_extent(self, extent) -> None:
        """*extent* is a continent name or a (lon0, lon1, lat0, lat1) tuple
        in degrees; it is projected into map coordinates here.

        The extent is padded to the canvas aspect ratio so map units stay
        square, but never beyond the world bounds; extents too wide to fit
        (World, Antarctica) simply fill the canvas.
        """
        self._extent_request = extent
        if isinstance(extent, str):
            extent = CONTINENT_EXTENTS[extent]
        x0, x1, y0, y1 = self.proj.project_extent(extent)
        wx0, wx1, wy0, wy1 = self.proj.bounds
        world_w, world_h = wx1 - wx0, wy1 - wy0

        pos = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        box_ratio = max((pos.width * fig_w) / (pos.height * fig_h), 1e-6)
        width, height = x1 - x0, y1 - y0

        if width / height < box_ratio:  # widen to fill the canvas
            new_w = height * box_ratio
            if new_w <= world_w:
                cx = min(max((x0 + x1) / 2, wx0 + new_w / 2), wx1 - new_w / 2)
                x0, x1 = cx - new_w / 2, cx + new_w / 2
        else:  # grow vertically to fill the canvas
            new_h = width / box_ratio
            if new_h <= world_h:
                cy = min(max((y0 + y1) / 2, wy0 + new_h / 2), wy1 - new_h / 2)
                y0, y1 = cy - new_h / 2, cy + new_h / 2

        self.ax.set_xlim(x0, x1)
        self.ax.set_ylim(y0, y1)

    def _zoom_level(self) -> float:
        x0, x1 = self.ax.get_xlim()
        width = max(abs(x1 - x0), 1e-9)
        return float(np.log2(self.proj.world_width / width))

    def _on_limits_changed(self, _ax) -> None:
        self._wrap_view()
        self._refresh_labels()

    def _wrap_view(self) -> None:
        """Loop the view around the globe: when a pan carries the view
        center past the antimeridian, shift it one world-width back. The
        neighbouring world copies keep the map seamless while crossing."""
        if self._in_wrap:
            return
        wx0, wx1 = self.proj.bounds[0], self.proj.bounds[1]
        world_w = wx1 - wx0
        x0, x1 = self.ax.get_xlim()
        cx = (x0 + x1) / 2
        shift = 0.0
        while cx + shift > wx1:
            shift -= world_w
        while cx + shift < wx0:
            shift += world_w
        if shift:
            self._in_wrap = True
            try:
                self.ax.set_xlim(x0 + shift, x1 + shift)
            finally:
                self._in_wrap = False

    # ----------------------------------------------------------- projection

    def set_projection(self, name: str) -> None:
        """Switch projection and rebuild every artist in the new one."""
        if name == self.proj.name:
            return
        self.proj = get_projection(name)
        self._clear_artists()
        self._rebuild_scene()

    def _clear_artists(self) -> None:
        for artists in self._artists.values():
            for artist in artists:
                artist.remove()
        self._artists = {}
        for texts in self._label_texts.values():
            for text in texts:
                text.remove()
        self._label_texts = {}
        for artist in self._point_artists:
            artist.remove()
        self._point_artists = []
        legend = self.ax.get_legend()
        if legend is not None:
            legend.remove()

    def _rebuild_scene(self) -> None:
        # Move the camera into the new projection's coordinates first:
        # everything downstream (graticule locators, label culling) reads
        # the axis limits.
        self.set_extent(self._extent_request)
        if self._basemap == "satellite":
            self.set_basemap("satellite")
        for key in self._line_visible:
            self._ensure_line_layer(key)
        self._sync_continents()
        if self._lake_fill != "none":
            self.set_lake_fill(self._lake_fill)
        if self._ocean_fill != "none":
            self.set_ocean(self._ocean_fill)
        self._apply_graticule()
        self._rebuild_points()
        self._refresh_labels()

    def _offsets(self) -> tuple[float, ...]:
        world_w = self.proj.world_width
        return tuple(k * world_w for k in _WRAP_OFFSETS)

    # --------------------------------------------------------------- basemap

    def set_basemap(self, mode: str) -> None:
        """``"simple"`` (white, line work) or ``"satellite"`` (color raster)."""
        self._basemap = mode
        if mode == "satellite" and "satellite" not in self._artists:
            with self._preserving_view():
                img, extent = self._warped_basemap()
                artists = []
                for off in self._offsets():
                    x0, x1, y0, y1 = extent
                    artists.append(self.ax.imshow(
                        img, extent=(x0 + off, x1 + off, y0, y1),
                        origin="upper", interpolation="bilinear",
                        zorder=Z_SATELLITE))
                self._artists["satellite"] = artists
        for artist in self._artists.get("satellite", []):
            artist.set_visible(mode == "satellite")

    def _warped_basemap(self) -> tuple[np.ndarray, tuple]:
        """The basemap image in the current projection, plus its extent."""
        img = self.store.basemap_image()
        if self.proj.is_geographic:
            return img, (-180, 180, -90, 90)
        if self.proj.name not in self._warp_cache:
            wx0, wx1, wy0, wy1 = self.proj.bounds
            nx, ny = _WARP_GRID
            xs = np.linspace(wx0, wx1, nx)
            ys = np.linspace(wy1, wy0, ny)  # top row first (origin="upper")
            gx, gy = np.meshgrid(xs, ys)
            lons, lats = self.proj.inverse(gx.ravel(), gy.ravel())
            lons, lats = lons.reshape(gy.shape), lats.reshape(gy.shape)
            valid = (np.isfinite(lons) & np.isfinite(lats)
                     & (np.abs(lons) <= 180.001) & (np.abs(lats) <= 90.001))
            h, w = img.shape[:2]
            # Out-of-globe grid cells invert to NaN/inf or wild values;
            # neutralise them (they are masked via *valid* below).
            lons = np.clip(np.nan_to_num(lons, nan=0.0, posinf=0.0,
                                         neginf=0.0), -360.0, 360.0)
            lats = np.clip(np.nan_to_num(lats, nan=0.0, posinf=0.0,
                                         neginf=0.0), -90.0, 90.0)
            cols = np.clip(((lons + 180) / 360 * w).astype(int), 0, w - 1)
            rows = np.clip(((90 - lats) / 180 * h).astype(int), 0, h - 1)
            warped = np.zeros((ny, nx, 4), dtype=np.uint8)
            warped[..., :3] = img[rows, cols]
            warped[..., 3] = np.where(valid, 255, 0)
            self._warp_cache[self.proj.name] = (warped, (wx0, wx1, wy0, wy1))
        return self._warp_cache[self.proj.name]

    # ---------------------------------------------------------- line layers

    def _plot_gdf_copies(self, gdf, zorder: float, **plot_kwargs) -> list:
        """Plot a GeoDataFrame plus one wrapped copy either side."""
        artists = []
        with self._preserving_view():
            for off in self._offsets():
                before = len(self.ax.collections)
                # aspect=None stops geopandas from forcing equal axes aspect,
                # which would letterbox the map inside the canvas.
                gdf.plot(ax=self.ax, zorder=zorder, aspect=None, **plot_kwargs)
                artist = self.ax.collections[before]
                if off:
                    artist.set_transform(mtransforms.Affine2D().translate(
                        off, 0) + self.ax.transData)
                artists.append(artist)
        return artists

    def _ensure_line_layer(self, key: str) -> None:
        if key in self._artists:
            return
        source, color, width, zorder = LINE_LAYERS[key]
        gdf = self.store.frame_projected(source, self.proj.crs,
                                         self.proj.max_lat)
        self._artists[key] = self._plot_gdf_copies(
            gdf, zorder, facecolor="none", edgecolor=color,
            linewidth=width * self._line_scale)

    def set_layer(self, key: str, visible: bool) -> None:
        """Toggle a line layer: countries, states, counties, lakes_outline,
        rivers, roads. Switching countries off swaps in the continent
        outlines so coastlines/continent borders stay visible."""
        if visible:
            self._line_visible.add(key)
            self._ensure_line_layer(key)
        else:
            self._line_visible.discard(key)
        for artist in self._artists.get(key, []):
            artist.set_visible(visible)
        if key == "countries":
            self._sync_continents()

    def _sync_continents(self) -> None:
        show = "countries" not in self._line_visible
        if show:
            self._ensure_line_layer("continents")
        for artist in self._artists.get("continents", []):
            artist.set_visible(show)

    def layer_visible(self, key: str) -> bool:
        return key in self._line_visible

    def set_line_width_scale(self, scale: float) -> None:
        """Scale the line width of every vector line layer (0.25 - 3)."""
        self._line_scale = max(float(scale), 0.05)
        for key, (_source, _color, width, _z) in LINE_LAYERS.items():
            for artist in self._artists.get(key, []):
                artist.set_linewidth(width * self._line_scale)

    # ---------------------------------------------------------- fill layers

    def set_lake_fill(self, mode: str) -> None:
        """``"none"``, ``"grey"`` or ``"blue"``."""
        self._lake_fill = mode
        self._set_fill("lakes", Z_LAKE_FILL, mode)

    def set_ocean(self, mode: str) -> None:
        """``"none"``, ``"grey"`` or ``"blue"``."""
        self._ocean_fill = mode
        self._set_fill("ocean", Z_OCEAN, mode)

    def _set_fill(self, source: str, zorder: float, mode: str) -> None:
        artist_key = source + "_fill"
        if mode != "none":
            if artist_key not in self._artists:
                gdf = self.store.frame_projected(source, self.proj.crs,
                                                 self.proj.max_lat)
                self._artists[artist_key] = self._plot_gdf_copies(
                    gdf, zorder, edgecolor="none")
            for artist in self._artists[artist_key]:
                artist.set_facecolor(FILL_COLORS[(source, mode)])
        for artist in self._artists.get(artist_key, []):
            artist.set_visible(mode != "none")

    # -------------------------------------------------------------- labels

    def set_labels(self, key: str, visible: bool) -> None:
        """Toggle labels: countries, states, counties, lakes, rivers."""
        if visible:
            self._label_visible.add(key)
        else:
            self._label_visible.discard(key)
        self._refresh_labels()

    def _label_xy(self, source: str) -> tuple[np.ndarray, np.ndarray]:
        cache_key = (source, self.proj.name)
        if cache_key not in self._label_xy_cache:
            points = self.store.label_points(source)
            xs, ys = self.proj.forward(points["x"].to_numpy(),
                                       points["y"].to_numpy())
            self._label_xy_cache[cache_key] = (np.asarray(xs, float),
                                               np.asarray(ys, float))
        return self._label_xy_cache[cache_key]

    def _refresh_labels(self) -> None:
        zoom = self._zoom_level()
        x0, x1 = sorted(self.ax.get_xlim())
        y0, y1 = sorted(self.ax.get_ylim())
        # Slightly smaller fonts when zoomed far out, so a fully labelled
        # world map stays readable.
        font_scale = float(np.clip(0.78 + 0.06 * zoom, 0.78, 1.15))
        for key in LABEL_STYLES:
            for text in self._label_texts.get(key, []):
                text.remove()
            self._label_texts[key] = []
            if key not in self._label_visible:
                continue
            source, font, min_zoom = LABEL_STYLES[key]
            if zoom < min_zoom:
                continue
            points = self.store.label_points(source)
            xs, ys = self._label_xy(source)
            font = dict(font)
            font["fontsize"] = font["fontsize"] * font_scale
            cap = LAYER_SPECS[source].label_cap
            texts = []
            # Consider the wrapped world copies so labels follow the view
            # across the antimeridian.
            candidates = []
            for off in self._offsets():
                in_view = ((xs + off >= x0) & (xs + off <= x1)
                           & (ys >= y0) & (ys <= y1)
                           & np.isfinite(xs) & np.isfinite(ys))
                sub = points[in_view].copy()
                sub["px"] = xs[in_view] + off
                sub["py"] = ys[in_view]
                candidates.append(sub)
            import pandas as pd

            eligible = pd.concat(candidates).nsmallest(cap, "min_label")
            for row in eligible.itertuples():
                texts.append(self.ax.text(
                    row.px, row.py, row.text, ha="center", va="center",
                    zorder=Z_LABELS, clip_on=True,
                    path_effects=_LABEL_HALO, **font))
            self._label_texts[key] = texts

    # ------------------------------------------------------------ graticule

    def set_graticule(self, interval: float | None, show_labels: bool = True) -> None:
        """*interval* in degrees (1, 5, 10) or None for off."""
        self._graticule = interval
        self._graticule_labels = show_labels
        self._apply_graticule()

    def _apply_graticule(self) -> None:
        for artist in self._artists.pop("graticule", []):
            artist.remove()
        on = self._graticule is not None
        # Axis ticks and their labels only make sense on the rectangular
        # default projection; curved projections draw the grid manually.
        labels_on = on and self._graticule_labels and self.proj.is_geographic
        if on and self.proj.is_geographic:
            self.ax.xaxis.set_major_locator(MultipleLocator(self._graticule))
            self.ax.yaxis.set_major_locator(MultipleLocator(self._graticule))
            self.ax.grid(True, color="#787878", linewidth=0.4, alpha=0.7)
            for line in (*self.ax.get_xgridlines(), *self.ax.get_ygridlines()):
                line.set_zorder(Z_GRID)
        else:
            # Drop any degree-spaced locator: on projected axes (meters)
            # it would try to generate millions of ticks.
            self.ax.xaxis.set_major_locator(AutoLocator())
            self.ax.yaxis.set_major_locator(AutoLocator())
            self.ax.grid(False)
            if on:
                self._artists["graticule"] = self._projected_graticule()
        self.ax.tick_params(labelbottom=labels_on, labelleft=labels_on,
                            bottom=labels_on, left=labels_on)
        left, bottom, right, top = (
            _MARGINS_WITH_TICKS if labels_on else _MARGINS_PLAIN)
        self.ax.set_position([left, bottom, right - left, top - bottom])

    def _projected_graticule(self) -> list:
        """Graticule drawn as projected polylines (curved projections)."""
        step = self._graticule
        max_lat = self.proj.max_lat
        segments = []
        for lon in np.arange(-180, 180 + step / 2, step):
            lats = np.linspace(-max_lat, max_lat, 91)
            xs, ys = self.proj.forward(np.full_like(lats, lon), lats)
            segments.append(np.column_stack([xs, ys]))
        for lat in np.arange(-90, 90 + step / 2, step):
            if abs(lat) > max_lat:
                continue
            lons = np.linspace(-180, 180, 181)
            xs, ys = self.proj.forward(lons, np.full_like(lons, lat))
            segments.append(np.column_stack([xs, ys]))
        artists = []
        with self._preserving_view():
            for off in self._offsets():
                col = LineCollection(segments, colors="#787878",
                                     linewidths=0.4, alpha=0.7, zorder=Z_GRID)
                if off:
                    col.set_transform(mtransforms.Affine2D().translate(
                        off, 0) + self.ax.transData)
                self.ax.add_collection(col)
                artists.append(col)
        return artists

    # --------------------------------------------------------------- points

    def set_point_groups(self, groups) -> None:
        """*groups* is a list of (label, PointStyle, lons, lats)."""
        self._point_groups = [
            (label, style, np.asarray(lons, float), np.asarray(lats, float))
            for label, style, lons, lats in groups
        ]
        self._rebuild_points()

    def set_legend(self, visible: bool, title: str | None = None,
                   location: str = "best", fontsize: float = 8.0,
                   columns: int = 1, frame: bool = True) -> None:
        self._legend_visible = visible
        self._legend_title = title
        self._legend_loc = location
        self._legend_fontsize = fontsize
        self._legend_columns = max(int(columns), 1)
        self._legend_frame = frame
        self._update_legend()

    def _rebuild_points(self) -> None:
        for artist in self._point_artists:
            artist.remove()
        self._point_artists = []
        if self._point_groups:
            offsets = self._offsets()
            with self._preserving_view():
                for label, style, lons, lats in self._point_groups:
                    xs, ys = self.proj.forward(lons, lats)
                    xs = np.concatenate([xs + off for off in offsets])
                    ys = np.tile(ys, len(offsets))
                    self._point_artists.append(self.ax.scatter(
                        xs, ys, s=style.size, c=style.color,
                        marker=style.mpl_marker, zorder=Z_POINTS,
                        edgecolors="white", linewidths=0.5, label=label))
        self._update_legend()

    def _update_legend(self) -> None:
        legend = self.ax.get_legend()
        if legend is not None:
            legend.remove()
        if not (self._legend_visible and self._point_groups):
            return
        handles = [
            Line2D([], [], linestyle="", marker=style.mpl_marker,
                   markersize=max(np.sqrt(style.size), 2), color=style.color,
                   markeredgecolor="white", markeredgewidth=0.5, label=label)
            for label, style, _, _ in self._point_groups
        ]
        self.ax.legend(handles=handles, loc=self._legend_loc,
                       title=self._legend_title,
                       fontsize=self._legend_fontsize,
                       title_fontsize=self._legend_fontsize,
                       ncols=self._legend_columns,
                       frameon=self._legend_frame, framealpha=0.85)

    # --------------------------------------------------------------- output

    def redraw(self) -> None:
        self.fig.canvas.draw_idle()

    def save_png(self, path: str, dpi: int = 200) -> None:
        self.fig.savefig(path, dpi=dpi, facecolor="white")
