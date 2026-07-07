"""Matplotlib map rendering for EzMaps.

The renderer owns one Figure/Axes pair. Every map layer becomes a single
matplotlib artist, created lazily the first time it is switched on and then
toggled with ``set_visible`` - this keeps interaction real-time instead of
re-plotting shapefiles on every change.
"""

from __future__ import annotations

from contextlib import contextmanager

import matplotlib.patheffects as patheffects
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator

from ezmaps.heatmap import compute_heatmap
from ezmaps.layers import CONTINENT_EXTENTS, LAYER_SPECS, LayerStore
from ezmaps.styles import PointStyle

__all__ = ["MapRenderer"]

# Vector line layers: layer key -> (source layer, edge color, width, zorder).
LINE_LAYERS = {
    "countries": ("countries", "#000000", 0.8, 1.6),
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

# Label layers: key -> (source layer, font kwargs, zoom bias).
# A label is eligible when its Natural Earth min_label <= zoom + bias, where
# zoom = log2(360 / view width); the per-layer cap then keeps the densest
# views readable.
LABEL_STYLES = {
    "countries": ("countries", dict(fontsize=9, color="#1a1a1a", fontweight="bold"), 4.0),
    "states": ("states", dict(fontsize=8, color="#3a3a3a"), 4.5),
    "counties": ("counties", dict(fontsize=6.5, color="#4a4a4a"), 4.5),
    "lakes": ("lakes", dict(fontsize=7.5, color="#14477a", fontstyle="italic"), 4.5),
    "rivers": ("rivers", dict(fontsize=7, color="#14477a", fontstyle="italic"), 4.5),
}

_LABEL_HALO = [patheffects.withStroke(linewidth=2.2, foreground="white", alpha=0.85)]

Z_SATELLITE = 0.1
Z_OCEAN = 0.3
Z_LAKE_FILL = 0.5
Z_GRID = 1.8
Z_HEATMAP = 2.2
Z_POINTS = 2.6
Z_LABELS = 3.0

_MARGINS_WITH_TICKS = (0.055, 0.045, 0.99, 0.99)   # left, bottom, right, top
_MARGINS_PLAIN = (0.01, 0.012, 0.99, 0.988)


def _format_lon(value: float, _pos=None) -> str:
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

        self._artists: dict[str, object] = {}
        self._lake_fill = "none"
        self._ocean_fill = "none"
        self._basemap = "simple"

        self._label_visible: set[str] = set()
        self._label_texts: dict[str, list] = {}

        self._graticule: float | None = None
        self._graticule_labels = True

        # (label, PointStyle, lons, lats) per group
        self._point_groups: list[tuple[str, PointStyle, np.ndarray, np.ndarray]] = []
        self._point_artists: list = []
        self._legend_visible = True
        self._legend_title: str | None = None
        self._legend_loc = "best"

        self._heatmap_on = False
        self._heatmap_radius = 10.0
        self._heatmap_blur = 0.0
        self._heatmap_intensity = 1.0
        self._heatmap_threshold = 0.0
        self._heatmap_levels = 0
        self._heatmap_bloom = False
        self._heatmap_cmap = "hot"
        self._heatmap_opacity = 0.7
        self._heatmap_points = False
        self._heatmap_artist = None
        self._heatmap_bloom_artist = None

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
        """*extent* is a continent name or a (x0, x1, y0, y1) tuple.

        The extent is padded to the canvas aspect ratio so degrees stay
        square, but never beyond the world bounds; extents too wide to fit
        (World, Antarctica) simply fill the canvas.
        """
        if isinstance(extent, str):
            extent = CONTINENT_EXTENTS[extent]
        x0, x1, y0, y1 = (float(v) for v in extent)

        pos = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        box_ratio = max((pos.width * fig_w) / (pos.height * fig_h), 1e-6)
        width, height = x1 - x0, y1 - y0

        if width / height < box_ratio:  # widen to fill the canvas
            new_w = height * box_ratio
            if new_w <= 360:
                cx = min(max((x0 + x1) / 2, -180 + new_w / 2), 180 - new_w / 2)
                x0, x1 = cx - new_w / 2, cx + new_w / 2
        else:  # grow vertically to fill the canvas
            new_h = width / box_ratio
            if new_h <= 180:
                cy = min(max((y0 + y1) / 2, -90 + new_h / 2), 90 - new_h / 2)
                y0, y1 = cy - new_h / 2, cy + new_h / 2

        self.ax.set_xlim(x0, x1)
        self.ax.set_ylim(y0, y1)

    def _zoom_level(self) -> float:
        x0, x1 = self.ax.get_xlim()
        width = max(abs(x1 - x0), 1e-6)
        return float(np.log2(360.0 / width))

    def _on_limits_changed(self, _ax) -> None:
        self._refresh_labels()

    # --------------------------------------------------------------- basemap

    def set_basemap(self, mode: str) -> None:
        """``"simple"`` (white, line work) or ``"satellite"`` (color raster)."""
        self._basemap = mode
        if mode == "satellite" and "satellite" not in self._artists:
            with self._preserving_view():
                img = self.store.basemap_image()
                self._artists["satellite"] = self.ax.imshow(
                    img, extent=(-180, 180, -90, 90), origin="upper",
                    interpolation="bilinear", zorder=Z_SATELLITE)
        if "satellite" in self._artists:
            self._artists["satellite"].set_visible(mode == "satellite")

    # ---------------------------------------------------------- line layers

    def _ensure_line_layer(self, key: str) -> None:
        if key in self._artists:
            return
        source, color, width, zorder = LINE_LAYERS[key]
        gdf = self.store.frame(source)
        with self._preserving_view():
            before = len(self.ax.collections)
            # aspect=None stops geopandas from forcing equal axes aspect,
            # which would letterbox the map inside the canvas.
            gdf.plot(ax=self.ax, facecolor="none", edgecolor=color,
                     linewidth=width, zorder=zorder, aspect=None)
            self._artists[key] = self.ax.collections[before]

    def set_layer(self, key: str, visible: bool) -> None:
        """Toggle a line layer: countries, states, counties, lakes_outline,
        rivers, roads."""
        if visible:
            self._ensure_line_layer(key)
        if key in self._artists:
            self._artists[key].set_visible(visible)

    def layer_visible(self, key: str) -> bool:
        artist = self._artists.get(key)
        return bool(artist and artist.get_visible())

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
                gdf = self.store.frame(source)
                with self._preserving_view():
                    before = len(self.ax.collections)
                    gdf.plot(ax=self.ax, edgecolor="none", zorder=zorder,
                             aspect=None)
                    self._artists[artist_key] = self.ax.collections[before]
            self._artists[artist_key].set_facecolor(FILL_COLORS[(source, mode)])
        if artist_key in self._artists:
            self._artists[artist_key].set_visible(mode != "none")

    # -------------------------------------------------------------- labels

    def set_labels(self, key: str, visible: bool) -> None:
        """Toggle labels: countries, states, counties, lakes, rivers."""
        if visible:
            self._label_visible.add(key)
        else:
            self._label_visible.discard(key)
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        zoom = self._zoom_level()
        x0, x1 = sorted(self.ax.get_xlim())
        y0, y1 = sorted(self.ax.get_ylim())
        for key in LABEL_STYLES:
            for text in self._label_texts.get(key, []):
                text.remove()
            self._label_texts[key] = []
            if key not in self._label_visible:
                continue
            source, font, bias = LABEL_STYLES[key]
            points = self.store.label_points(source)
            eligible = points[
                (points["x"] >= x0) & (points["x"] <= x1)
                & (points["y"] >= y0) & (points["y"] <= y1)
                & (points["min_label"] <= zoom + bias)
            ]
            cap = LAYER_SPECS[source].label_cap
            eligible = eligible.nsmallest(cap, "min_label")
            texts = []
            for row in eligible.itertuples():
                texts.append(self.ax.text(
                    row.x, row.y, row.text, ha="center", va="center",
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
        on = self._graticule is not None
        labels_on = on and self._graticule_labels
        if on:
            self.ax.xaxis.set_major_locator(MultipleLocator(self._graticule))
            self.ax.yaxis.set_major_locator(MultipleLocator(self._graticule))
            self.ax.grid(True, color="#787878", linewidth=0.4, alpha=0.7)
            for line in (*self.ax.get_xgridlines(), *self.ax.get_ygridlines()):
                line.set_zorder(Z_GRID)
        else:
            self.ax.grid(False)
        self.ax.tick_params(labelbottom=labels_on, labelleft=labels_on,
                            bottom=labels_on, left=labels_on)
        left, bottom, right, top = (
            _MARGINS_WITH_TICKS if labels_on else _MARGINS_PLAIN)
        self.ax.set_position([left, bottom, right - left, top - bottom])

    # --------------------------------------------------------------- points

    def set_point_groups(self, groups) -> None:
        """*groups* is a list of (label, PointStyle, lons, lats)."""
        self._point_groups = [
            (label, style, np.asarray(lons, float), np.asarray(lats, float))
            for label, style, lons, lats in groups
        ]
        self._rebuild_points()

    def set_legend(self, visible: bool, title: str | None = None,
                   location: str = "best") -> None:
        self._legend_visible = visible
        self._legend_title = title
        self._legend_loc = location
        self._update_legend()

    def set_heatmap(self, enabled: bool, radius: float = 10.0,
                    cmap: str = "hot", opacity: float = 0.7,
                    show_points: bool = False, blur: float = 0.0,
                    intensity: float = 1.0, threshold: float = 0.0,
                    levels: int = 0, bloom: bool = False) -> None:
        """Configure the heatmap overlay.

        *radius* is the bandwidth / area of influence, *blur* adds extra
        smoothing, *intensity* is the weight (gamma) curve, *threshold*
        clips faint densities, *levels* > 1 classifies the density into
        discrete bands, and *bloom* draws a soft glow under the heatmap.
        """
        self._heatmap_on = enabled
        self._heatmap_radius = radius
        self._heatmap_blur = blur
        self._heatmap_intensity = intensity
        self._heatmap_threshold = threshold
        self._heatmap_levels = levels
        self._heatmap_bloom = bloom
        self._heatmap_cmap = cmap
        self._heatmap_opacity = opacity
        self._heatmap_points = show_points
        self._rebuild_points()

    def _all_points(self) -> tuple[np.ndarray, np.ndarray]:
        if not self._point_groups:
            return np.array([]), np.array([])
        lons = np.concatenate([g[2] for g in self._point_groups])
        lats = np.concatenate([g[3] for g in self._point_groups])
        return lons, lats

    def _rebuild_points(self) -> None:
        for artist in self._point_artists:
            artist.remove()
        self._point_artists = []
        if self._heatmap_artist is not None:
            self._heatmap_artist.remove()
            self._heatmap_artist = None
        if self._heatmap_bloom_artist is not None:
            self._heatmap_bloom_artist.remove()
            self._heatmap_bloom_artist = None

        points_visible = self._point_groups and (
            not self._heatmap_on or self._heatmap_points)
        if points_visible:
            with self._preserving_view():
                for label, style, lons, lats in self._point_groups:
                    self._point_artists.append(self.ax.scatter(
                        lons, lats, s=style.size, c=style.color,
                        marker=style.mpl_marker, zorder=Z_POINTS,
                        edgecolors="white", linewidths=0.5, label=label))

        lons, lats = self._all_points()
        if self._heatmap_on and lons.size:
            import matplotlib.pyplot as plt

            density, extent = compute_heatmap(
                lons, lats, radius=self._heatmap_radius,
                blur=self._heatmap_blur, intensity=self._heatmap_intensity,
                threshold=self._heatmap_threshold,
                levels=self._heatmap_levels)
            cmap = plt.get_cmap(self._heatmap_cmap)
            rgba = cmap(density)
            rgba[..., 3] = self._heatmap_opacity * np.minimum(
                density / 0.10, 1.0)
            with self._preserving_view():
                if self._heatmap_bloom:
                    from scipy.ndimage import gaussian_filter

                    glow = gaussian_filter(density, sigma=8.0)
                    peak = glow.max()
                    if peak > 0:
                        glow /= peak
                    glow_rgba = cmap(glow)
                    glow_rgba[..., 3] = (0.55 * self._heatmap_opacity
                                         * np.minimum(glow / 0.05, 1.0))
                    self._heatmap_bloom_artist = self.ax.imshow(
                        glow_rgba, extent=extent, origin="lower",
                        interpolation="bilinear", zorder=Z_HEATMAP - 0.05)
                # Keep class boundaries crisp when the density is quantised.
                interp = ("nearest" if self._heatmap_levels > 1
                          else "bilinear")
                self._heatmap_artist = self.ax.imshow(
                    rgba, extent=extent, origin="lower",
                    interpolation=interp, zorder=Z_HEATMAP)
        self._update_legend()

    def _update_legend(self) -> None:
        legend = self.ax.get_legend()
        if legend is not None:
            legend.remove()
        show_points = self._point_groups and (
            not self._heatmap_on or self._heatmap_points)
        if not (self._legend_visible and show_points):
            return
        handles = [
            Line2D([], [], linestyle="", marker=style.mpl_marker,
                   markersize=max(np.sqrt(style.size), 2), color=style.color,
                   markeredgecolor="white", markeredgewidth=0.5, label=label)
            for label, style, _, _ in self._point_groups
        ]
        self.ax.legend(handles=handles, loc=self._legend_loc,
                       title=self._legend_title, fontsize=8,
                       title_fontsize=8, framealpha=0.85)

    # --------------------------------------------------------------- output

    def redraw(self) -> None:
        self.fig.canvas.draw_idle()

    def save_png(self, path: str, dpi: int = 200) -> None:
        self.fig.savefig(path, dpi=dpi, facecolor="white")
