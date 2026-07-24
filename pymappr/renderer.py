from __future__ import annotations

from contextlib import contextmanager

import matplotlib.patheffects as patheffects
import matplotlib.transforms as mtransforms
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoLocator, FuncFormatter, MultipleLocator

from pymappr.layers import (BATHYMETRY_STEPS, CONTINENT_EXTENTS, LAYER_SPECS,
                            LayerStore)
from pymappr.projections import get_projection
from pymappr.styles import PointStyle

__all__ = ["MapRenderer"]

# Vector line layers:
# layer key -> (source layer, edge color, width, zorder, linestyle).
# "continents" is the countries layer dissolved by continent; it stands in
# for the countries layer when political borders are switched off.
LINE_LAYERS = {
    "countries": ("countries", "#000000", 0.8, 1.6, "solid"),
    "continents": ("continents", "#000000", 0.8, 1.55, "solid"),
    "sovereignty": ("sovereignty", "#5b2d8b", 0.9, 1.58, "solid"),
    "map_units": ("map_units", "#2d6b8b", 0.6, 1.57, "solid"),
    "subunits": ("subunits", "#8b6b2d", 0.5, 1.56, "solid"),
    "dependencies": ("dependencies", "#c2571a", 0.9, 1.62, "solid"),
    "disputed_lines": ("disputed_lines", "#c0392b", 0.9, 1.65, (0, (4, 2))),
    "maritime": ("maritime", "#3b7bbf", 0.7, 1.3, (0, (5, 3))),
    "eez": ("eez", "#1c5c99", 0.8, 1.31, (0, (1, 2))),
    "timezones": ("timezones", "#8a5fbf", 0.6, 1.35, (0, (6, 3))),
    "states": ("states", "#5a5a5a", 0.5, 1.5, "solid"),
    "counties": ("counties", "#8a8a8a", 0.35, 1.4, "solid"),
    "lakes_outline": ("lakes", "#2d5f8a", 0.6, 1.2, "solid"),
    "rivers": ("rivers", "#4a90c4", 0.5, 1.0, "solid"),
    "wadis": ("wadis", "#b3985c", 0.6, 1.0, (0, (3, 2))),
    "reefs": ("reefs", "#25a08c", 0.7, 1.15, "solid"),
    "regions": ("regions", "#a8763e", 0.5, 1.12, (0, (3, 3))),
    "roads": ("roads", "#b0693c", 0.35, 1.1, "solid"),
}

# Mode fills (lakes/ocean support "none"/"grey"/"blue").
FILL_COLORS = {
    ("lakes", "grey"): "#c9c9c9",
    ("lakes", "blue"): "#a6cae0",
    ("ocean", "grey"): "#dcdcdc",
    ("ocean", "blue"): "#d4e6f4",
}

# Simple on/off fill layers:
# layer key -> (source, facecolor, edgecolor, edge width, alpha, zorder).
FILL_LAYERS = {
    "land": ("land", "#f0ece1", "none", 0.0, 1.0, 0.35),
    "deserts": ("deserts", "#f3e6c0", "none", 0.0, 0.65, 0.52),
    "playas": ("playas", "#efe7c3", "#d8c98a", 0.3, 1.0, 0.55),
    "urban": ("urban", "#d95f4e", "none", 0.0, 0.55, 0.58),
    "parks": ("parks", "#bfe3b4", "#4e9a51", 0.4, 0.85, 0.6),
    "ice_shelves": ("ice_shelves", "#d8ecf7", "#a8cfe6", 0.3, 1.0, 0.61),
    "glaciers": ("glaciers", "#e6f3fb", "#b9d9ec", 0.3, 1.0, 0.62),
    "disputed": ("disputed", "#e8b4b8", "#b03a48", 0.5, 0.75, 0.66),
    # Optional biodiversity / ecoregion overlays (translucent thematic fills).
    "ecoregions": ("ecoregions", "#8fbf6f", "#4e7a3a", 0.25, 0.42, 0.44),
    "marine_ecoregions": ("marine_ecoregions", "#5fa8c4", "#2d6b8b",
                          0.25, 0.42, 0.43),
    "biodiversity": ("biodiversity", "#e0954a", "#a85f16", 0.5, 0.5, 0.53),
}

# Bathymetry: depth in meters -> fill color, shallow to deep. The polygons
# nest, so drawing shallow-to-deep stacks darker blues into the trenches.
BATHYMETRY_COLORS = {
    0: "#e3f2fa", 200: "#d2e9f5", 1000: "#c0dff0", 2000: "#a8d1e8",
    3000: "#8fc2e0", 4000: "#74b2d8", 5000: "#5a9fcd", 6000: "#4489bd",
    7000: "#3273aa", 8000: "#245e94", 9000: "#194a7d", 10000: "#103862",
}
Z_BATHYMETRY = 0.32

# Point-marker layers:
# key -> (source, marker, size, facecolor, edgecolor, zoom bias).
# A feature is shown once ``min_zoom <= zoom + bias`` (min_zoom falls back
# to scalerank for layers without one), so markers fade in while zooming.
POINT_LAYERS = {
    "cities": ("cities", "o", 11.0, "#333333", "white", 2.0),
    "capitals": ("capitals", "*", 60.0, "#b03a2e", "white", 99.0),
    "airports": ("airports", "^", 18.0, "#4757a8", "white", 4.0),
    "ports": ("ports", "v", 16.0, "#1f7a70", "white", 3.5),
}
Z_POINT_LAYERS = 2.45

# Label layers: key -> (source, font kwargs, min zoom, feature bias).
# Once the view is zoomed in at least to *min zoom* (zoom 0 = whole world,
# +1 per 2x magnification), features inside the view are labelled, up to
# the per-layer cap in LAYER_SPECS. Countries use min zoom 0 so every
# country in view is labelled even fully zoomed out. A non-None *feature
# bias* additionally culls per feature: a label is eligible only once its
# ``min_label`` (Natural Earth's curated zoom rank) is <= zoom + bias, so
# e.g. city labels appear gradually, biggest cities first.
LABEL_STYLES = {
    "countries": ("countries", dict(fontsize=9, color="#1a1a1a", fontweight="bold"), 0.0, None),
    "states": ("states", dict(fontsize=8, color="#3a3a3a"), 1.2, None),
    "counties": ("counties", dict(fontsize=6.5, color="#4a4a4a"), 3.6, None),
    "cities": ("cities", dict(fontsize=7.5, color="#222222"), 0.0, 2.0),
    "airports": ("airports", dict(fontsize=6.5, color="#3a4c8c"), 2.0, 3.0),
    "ports": ("ports", dict(fontsize=6.5, color="#14614f", fontstyle="italic"), 2.0, 3.0),
    "lakes": ("lakes", dict(fontsize=7.5, color="#14477a", fontstyle="italic"), 1.5, None),
    "rivers": ("rivers", dict(fontsize=7, color="#14477a", fontstyle="italic"), 1.5, None),
    "regions": ("regions", dict(fontsize=8, color="#7a5230", fontstyle="italic"), 0.5, 3.0),
    "timezones": ("timezones", dict(fontsize=8, color="#6a4a9c"), 0.0, None),
}

_LABEL_HALO = [patheffects.withStroke(linewidth=2.2, foreground="white", alpha=0.85)]

Z_SATELLITE = 0.1
Z_OCEAN = 0.3
Z_LAKE_FILL = 0.5
Z_GRID = 1.8
Z_POINTS = 2.6
Z_LABELS = 3.0
Z_COMPASS = 4.0

_MARGINS_WITH_TICKS = (0.055, 0.045, 0.99, 0.99)   # left, bottom, right, top
_MARGINS_PLAIN = (0.01, 0.012, 0.99, 0.988)

# Map orientation -> target width:height for the map axes box. "landscape"
# is None, meaning the map fills the whole canvas (the original behaviour);
# "portrait" constrains it to a tall box, centered with blank side margins,
# so tall regions (e.g. South America) fill the frame instead of floating in
# a band of ocean. The value is the inverse of the ~9:6.5 default figure so
# portrait reads as the page simply turned on its side.
_PORTRAIT_ASPECT = 6.5 / 9.0
ORIENTATION_ASPECT = {"landscape": None, "portrait": _PORTRAIT_ASPECT}

# Horizontal world copies drawn for wrap-around panning, in world-widths.
_WRAP_OFFSETS = (-1, 0, 1)

# Warped-basemap grid (columns x rows) for projected satellite rendering.
_WARP_GRID = (1600, 800)


def _oriented_axes_rect(margins: tuple[float, float, float, float],
                        fig_w: float, fig_h: float,
                        aspect: float | None
                        ) -> tuple[float, float, float, float]:
    """The axes position rectangle ``(left, bottom, width, height)`` in
    figure fractions for a target box *aspect* (width / height).

    *margins* is ``(left, bottom, right, top)``; the base box it describes
    is shrunk along whichever dimension is too long and re-centred so the
    axes ends up with the requested aspect. ``aspect=None`` keeps the full
    box (landscape / fill)."""
    left, bottom, right, top = margins
    width, height = right - left, top - bottom
    if aspect is None:
        return left, bottom, width, height
    avail_w = width * fig_w
    avail_h = height * fig_h
    if avail_w / max(avail_h, 1e-9) > aspect:  # too wide: narrow it
        new_w = aspect * avail_h / max(fig_w, 1e-9)
        left += (width - new_w) / 2
        width = new_w
    else:  # too tall: shorten it
        new_h = avail_w / aspect / max(fig_h, 1e-9)
        bottom += (height - new_h) / 2
        height = new_h
    return left, bottom, width, height


def _refit_xlim(box_ratio: float, xlim: tuple[float, float],
                ylim: tuple[float, float], world_width: float,
                clamp: bool) -> tuple[float, float]:
    """New x-limits that fit the current view to *box_ratio* (axes
    width / height) by keeping the centre and vertical span and adjusting
    the horizontal span - narrowing for portrait, widening for landscape.
    When *clamp*, the span never exceeds *world_width*."""
    x0, x1 = xlim
    y0, y1 = ylim
    cx = (x0 + x1) / 2.0
    new_w = abs(y1 - y0) * box_ratio
    if clamp:
        new_w = min(new_w, world_width)
    half = new_w / 2.0 if x1 >= x0 else -new_w / 2.0
    return cx - half, cx + half


def _export_geometry(pos_bounds: tuple[float, float, float, float],
                     fig_w: float, fig_h: float,
                     margins: tuple[float, float, float, float]
                     ) -> tuple[tuple[float, float],
                                tuple[float, float, float, float]]:
    """Figure size (inches) and axes rectangle for a saved image that crops
    a letterboxed map to its content, returned as ``((w, h), (left, bottom,
    width, height))``.

    *pos_bounds* is the axes' current fractional ``(x0, y0, w, h)`` and
    *margins* the ``(left, bottom, right, top)`` in effect. The map box is
    kept at its on-screen inches, and the tick-label / edge margins are kept
    at their on-screen inches too (so labels never crowd off a narrow
    portrait crop); only the blank orientation side bars are dropped. A
    full-canvas (landscape) map comes back at the figure size unchanged."""
    _x0, _y0, pw, ph = pos_bounds
    box_w, box_h = pw * fig_w, ph * fig_h
    left, bottom, right, top = margins
    left_gutter, right_gutter = left * fig_w, (1.0 - right) * fig_w
    bottom_gutter, top_gutter = bottom * fig_h, (1.0 - top) * fig_h
    exp_w = box_w + left_gutter + right_gutter
    exp_h = box_h + bottom_gutter + top_gutter
    rect = (left_gutter / exp_w, bottom_gutter / exp_h,
            box_w / exp_w, box_h / exp_h)
    return (exp_w, exp_h), rect


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
        self._fill_visible: set[str] = set()
        self._point_layers_visible: set[str] = set()
        self._bathymetry_visible = False
        self._capitals_only = False
        self._compass_visible = False
        self._lake_fill = "none"
        self._ocean_fill = "none"
        self._basemap = "simple"
        self._label_visible: set[str] = set()
        self._graticule: float | None = None
        self._graticule_labels = True
        self._line_scale = 1.0
        self._extent_request = "World"
        self._orientation = "landscape"
        # Base axes margins currently in effect (with or without room for
        # tick labels); the orientation narrows this into the axes box.
        self._axes_margins = _MARGINS_PLAIN
        # In portrait the map is a tall box centred on the figure; the blank
        # side bars are painted this "mat" colour (the app's background) so
        # the framing reads as a centred page instead of stray whitespace.
        # The map itself keeps a white background regardless.
        self._mat_color = "#e6e6e6"
        self.ax.set_facecolor("white")

        # (label, PointStyle, lons, lats) per group
        self._point_groups: list[tuple[str, PointStyle, np.ndarray, np.ndarray]] = []
        self._point_artists: list = []
        self._legend_visible = True
        self._legend_title: str | None = None
        self._legend_loc = "best"
        self._legend_fontsize = 8.0
        self._legend_title_fontsize = 9.0
        self._legend_columns = 1
        self._legend_frame = True
        self._legend_marker_scale = 1.0
        self._legend_label_spacing = 0.5
        # Structured legend: list of (section title, [(label, PointStyle)]).
        # When set, it replaces the one-row-per-group legend.
        self._legend_sections: list | None = None
        self._point_alpha = 1.0

        # Manual legend placement: dragging the legend (when enabled) anchors
        # its lower-left corner here, in axes fraction, with no limit; None
        # falls back to the automatic ``_legend_loc`` placement.
        self._legend_anchor: tuple[float, float] | None = None
        self._legend_drag: dict | None = None
        self._legend_dragging_enabled = False

        # Artists are keyed "<layer>@<source directory>" so multi-resolution
        # layers keep one artist set per resolution; _artist_res remembers
        # which resolution is currently shown for each visible layer.
        self._artists: dict[str, list] = {}
        self._artist_res: dict[str, str] = {}
        self._point_layer_artists: dict[str, list] = {}
        self._label_texts: dict[str, list] = {}
        self._label_xy_cache: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        self._point_xy_cache: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        self._warp_cache: dict[tuple, tuple[np.ndarray, tuple]] = {}
        self._in_wrap = False
        self._in_limits_refresh = False

        # Manual label placement: (layer key, label text) -> (dx, dy) offset
        # in map coordinates, set by dragging a label with the mouse.
        self._label_offsets: dict[tuple[str, str], tuple[float, float]] = {}
        self._label_drag: dict | None = None
        self._label_dragging_enabled = False

        # While the figure is temporarily resized for export, the resize
        # handler must not re-fit the on-screen view to the export size.
        self._suspend_resize = False

        self.set_extent("World")
        self._apply_graticule()
        self.ax.callbacks.connect("xlim_changed", self._on_limits_changed)
        self.ax.callbacks.connect("ylim_changed", self._on_limits_changed)
        if self.fig.canvas is not None:
            self.fig.canvas.mpl_connect("button_press_event",
                                        self._on_canvas_press)
            self.fig.canvas.mpl_connect("motion_notify_event",
                                        self._on_canvas_motion)
            self.fig.canvas.mpl_connect("button_release_event",
                                        self._on_canvas_release)
            self.fig.canvas.mpl_connect("resize_event", self._on_resize)

    # ------------------------------------------------------------------ view

    @contextmanager
    def _preserving_view(self):
        """Adding artists (gdf.plot / imshow) must never move the camera.

        Restoring the (unchanged) limits still fires the limits callback;
        suppress it, or a layer build triggered from that callback would
        re-enter itself and leak a duplicate, untoggleable artist set."""
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim()
        try:
            yield
        finally:
            was_refreshing = self._in_limits_refresh
            self._in_limits_refresh = True
            try:
                self.ax.set_xlim(xlim)
                self.ax.set_ylim(ylim)
            finally:
                self._in_limits_refresh = was_refreshing

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

        self._apply_axes_position()
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

    def set_orientation(self, name: str) -> None:
        """Switch the map between ``"landscape"`` (fill the canvas) and
        ``"portrait"`` (a tall box). The region on screen is kept: its
        vertical span stays put and the horizontal span is re-fit to the new
        box - cropping the sides for portrait, widening them for landscape -
        so a tall region loses its flanking ocean instead of the whole view
        jumping back to a preset."""
        name = name if name in ORIENTATION_ASPECT else "landscape"
        if name == self._orientation:
            return
        self._orientation = name
        self._apply_mat()
        self._refit_view_to_box()

    def set_mat_color(self, color: str) -> None:
        """Set the colour of the portrait side bars (the app's background),
        so the letterbox matches the surrounding UI. A no-op on the map
        itself, which always stays white."""
        self._mat_color = color or "#e6e6e6"
        self._apply_mat()

    def _apply_mat(self) -> None:
        portrait = ORIENTATION_ASPECT.get(self._orientation) is not None
        self.fig.set_facecolor(self._mat_color if portrait else "white")

    def _apply_axes_position(self) -> None:
        """Place the map axes for the current margins and orientation."""
        fig_w, fig_h = self.fig.get_size_inches()
        rect = _oriented_axes_rect(
            self._axes_margins, float(fig_w), float(fig_h),
            ORIENTATION_ASPECT.get(self._orientation))
        self.ax.set_position(list(rect))

    def _refit_view_to_box(self) -> None:
        """Re-fit the current view to the current orientation's axes box.

        The view centre and its vertical span are kept; the horizontal span
        is set to match the box aspect, so map units stay square. Landscape
        never widens past the world; portrait only ever narrows."""
        self._apply_axes_position()
        pos = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        box_ratio = max((pos.width * fig_w) / (pos.height * fig_h), 1e-6)
        x0, x1 = _refit_xlim(box_ratio, self.ax.get_xlim(),
                             self.ax.get_ylim(), self.proj.world_width,
                             clamp=not self.proj.hemisphere)
        self.ax.set_xlim(x0, x1)

    def _on_resize(self, _event) -> None:
        """Keep the map correctly shaped whenever the figure (window) resizes.

        The oriented axes box is a *figure fraction*, so a Tk resize - the
        window being maximised, or the first real layout after a restored
        session that was measured against the initial figure size - would
        leave a portrait box at a stale, no-longer-portrait aspect: the map
        turns into 'landscape but shrunk'. Re-deriving the box for the new
        size and re-fitting the view keeps portrait tall, landscape full, and
        map units square in either orientation."""
        if self._suspend_resize or self._in_limits_refresh:
            return
        self._refit_view_to_box()
        self.redraw()

    def get_view(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Current axis limits (map coordinates) for project persistence."""
        return tuple(self.ax.get_xlim()), tuple(self.ax.get_ylim())

    def set_view(self, xlim, ylim) -> None:
        """Restore axis limits saved by :meth:`get_view` (same projection)."""
        self.ax.set_xlim(tuple(xlim))
        self.ax.set_ylim(tuple(ylim))

    def zoom(self, factor: float, center: tuple[float, float] | None = None) -> None:
        """Zoom the view by *factor* (>1 zooms in), keeping *center* (map
        coordinates, e.g. the cursor position) fixed; without a center the
        view zooms about its middle."""
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        width = x1 - x0
        world_w = self.proj.world_width
        # Keep the zoom inside sane bounds: no further out than ~1.5
        # world-widths, no further in than a millionth of the world.
        factor = max(factor, width / (world_w * 1.5))
        factor = min(factor, width / (world_w * 1e-6))
        if abs(factor - 1.0) < 1e-9:
            return
        cx = center[0] if center is not None else (x0 + x1) / 2
        cy = center[1] if center is not None else (y0 + y1) / 2
        self.ax.set_xlim(cx - (cx - x0) / factor, cx + (x1 - cx) / factor)
        self.ax.set_ylim(cy - (cy - y0) / factor, cy + (y1 - cy) / factor)

    def _zoom_level(self) -> float:
        x0, x1 = self.ax.get_xlim()
        width = max(abs(x1 - x0), 1e-9)
        return float(np.log2(self.proj.world_width / width))

    def _on_limits_changed(self, _ax) -> None:
        # Refreshing adds artists, and adding artists restores the axis
        # limits, which re-fires this callback - don't recurse.
        if self._in_limits_refresh:
            return
        self._in_limits_refresh = True
        try:
            self._wrap_view()
            self._sync_resolutions()
            self._sync_wrap_copies()
            self._refresh_point_layers()
            self._refresh_labels()
        finally:
            self._in_limits_refresh = False

    def _wrap_view(self) -> None:
        """Loop the view around the globe: when a pan carries the view
        center past the antimeridian, shift it one world-width back. The
        neighbouring world copies keep the map seamless while crossing.

        The orthographic globe is a disk, not a repeating strip, so it does
        not wrap."""
        if self._in_wrap or self.proj.hemisphere:
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

    def set_projection(self, name: str, lon_0: float | None = None,
                       lat_0: float | None = None) -> None:
        """Switch projection and rebuild every artist in the new one.

        For Lambert presets and the Globe *lon_0*/*lat_0* set the point of
        natural origin; they are ignored for the fixed world projections."""
        proj = get_projection(name, lon_0, lat_0)
        if proj == self.proj:
            return
        self.proj = proj
        # Manual label offsets are in map coordinates, which just changed
        # scale/shape entirely - start fresh in the new projection.
        self._label_offsets.clear()
        self._clear_artists()
        self._rebuild_scene()

    def _clear_artists(self) -> None:
        for artists in self._artists.values():
            for artist in artists:
                artist.remove()
        self._artists = {}
        self._artist_res = {}
        for artists in self._point_layer_artists.values():
            for artist in artists:
                artist.remove()
        self._point_layer_artists = {}
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
        if self._basemap != "simple":
            self.set_basemap(self._basemap)
        for key in list(self._line_visible):
            self._show_line_layer(key)
        self._sync_continents()
        for key in list(self._fill_visible):
            self._show_fill_layer(key)
        if self._lake_fill != "none":
            self.set_lake_fill(self._lake_fill)
        if self._ocean_fill != "none":
            self.set_ocean(self._ocean_fill)
        if self._bathymetry_visible:
            self._show_bathymetry()
        self._apply_graticule()
        self._apply_horizon()
        self._apply_compass()
        self._rebuild_points()
        self._refresh_point_layers()
        self._refresh_labels()

    def _offsets(self) -> tuple[float, ...]:
        # The orthographic globe is a single disk: no wrap-around copies.
        if self.proj.hemisphere:
            return (0.0,)
        world_w = self.proj.world_width
        return tuple(k * world_w for k in _WRAP_OFFSETS)

    def _apply_horizon(self) -> None:
        """The globe's disk outline (the horizon circle). Other
        projections have no horizon and draw nothing."""
        for artist in self._artists.pop("horizon", []):
            artist.remove()
        if not self.proj.hemisphere:
            return
        xs, ys = self.proj.horizon_xy()
        with self._preserving_view():
            (line,) = self.ax.plot(xs, ys, color="#787878", linewidth=0.8,
                                   zorder=Z_GRID)
            line._pym_offset = 0.0
            self._artists["horizon"] = [line]

    # --------------------------------------------------------------- basemap

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
        cache_key = (self.proj.key, mode)
        if cache_key not in self._warp_cache:
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

    # ------------------------------------------------- multi-resolution core

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

    # ---------------------------------------------------------- line layers

    def _plot_gdf_copies(self, gdf, zorder: float, **plot_kwargs) -> list:
        """Plot a GeoDataFrame plus one wrapped copy either side.

        Only the primary copy pays the geometry-to-path conversion; the two
        wrap-around copies are collections sharing the same Path objects,
        shifted one world-width left/right, which makes switching big
        layers on (roads, urban areas, bathymetry) about 3x faster."""
        from matplotlib.collections import PathCollection

        artists = []
        with self._preserving_view():
            before = len(self.ax.collections)
            # aspect=None stops geopandas from forcing equal axes aspect,
            # which would letterbox the map inside the canvas.
            gdf.plot(ax=self.ax, zorder=zorder, aspect=None, **plot_kwargs)
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

    # ---------------------------------------------------------- fill layers

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

    # ------------------------------------------------------------ bathymetry

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

    # ----------------------------------------------------- point-marker layers

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
        features appear once their min_zoom/scalerank allows."""
        zoom = self._zoom_level()
        for artists in self._point_layer_artists.values():
            for artist in artists:
                artist.remove()
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
            px = np.concatenate([xs[show] + off for off in offsets])
            py = np.tile(ys[show], len(offsets))
            with self._preserving_view():
                artist = self.ax.scatter(
                    px, py, s=size, c=face, marker=marker,
                    edgecolors=edge, linewidths=0.5,
                    zorder=Z_POINT_LAYERS)
            self._point_layer_artists[key] = [artist]

    # -------------------------------------------------------------- compass

    def set_compass(self, visible: bool) -> None:
        """Toggle a north arrow in the top-right corner of the map."""
        self._compass_visible = visible
        self._apply_compass()

    def _apply_compass(self) -> None:
        for artist in self._artists.pop("compass", []):
            artist.remove()
        if not self._compass_visible:
            return
        annotation = self.ax.annotate(
            "N", xy=(0.975, 0.975), xytext=(0.975, 0.905),
            xycoords="axes fraction", textcoords="axes fraction",
            ha="center", va="center", fontsize=11, fontweight="bold",
            color="#1a1a1a", path_effects=_LABEL_HALO, zorder=Z_COMPASS,
            annotation_clip=False,
            arrowprops=dict(arrowstyle="-|>,head_width=0.28,head_length=0.55",
                            color="#1a1a1a", linewidth=1.4,
                            shrinkA=6, shrinkB=0))
        self._artists["compass"] = [annotation]

    # -------------------------------------------------------------- labels

    def set_labels(self, key: str, visible: bool) -> None:
        """Toggle labels: countries, states, counties, cities, airports,
        ports, lakes, rivers, regions, timezones."""
        if visible:
            self._label_visible.add(key)
        else:
            self._label_visible.discard(key)
        self._refresh_labels()

    def _label_xy(self, source: str) -> tuple[np.ndarray, np.ndarray]:
        cache_key = (source, self.proj.key)
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
        # Pixel-space rectangles of labels placed so far (all layers
        # together): a new label that would overlap one is skipped. Labels
        # the user has dragged are always drawn.
        placed_rects: list[tuple[float, float, float, float]] = []
        to_pixels = self.ax.transData
        px_per_pt = self.fig.dpi / 72.0
        for key in LABEL_STYLES:
            for text in self._label_texts.get(key, []):
                text.remove()
            self._label_texts[key] = []
            if key not in self._label_visible:
                continue
            source, font, min_zoom, feature_bias = LABEL_STYLES[key]
            if zoom < min_zoom:
                continue
            if key == "cities" and self._capitals_only:
                source = "capitals"
            points = self.store.label_points(source)
            xs, ys = self._label_xy(source)
            font = dict(font)
            font["fontsize"] = font["fontsize"] * font_scale
            cap = LAYER_SPECS["cities" if source == "capitals"
                              else source].label_cap
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

            eligible = pd.concat(candidates)
            if feature_bias is not None:
                # Per-feature zoom culling: a place is labelled only once
                # Natural Earth's curated min_label rank allows it, so e.g.
                # only the biggest cities are named when zoomed out.
                eligible = eligible[eligible["min_label"] <= zoom + feature_bias]
            eligible = eligible.nsmallest(cap, "min_label")
            if key in POINT_LAYERS:  # label sits above the marker dot
                font.setdefault("va", "bottom")
            for row in eligible.itertuples():
                offset = self._label_offsets.get((key, row.text))
                lx = row.px + (offset[0] if offset else 0.0)
                ly = row.py + (offset[1] if offset else 0.0)
                rect = self._estimate_rect(to_pixels, lx, ly, row.text,
                                           font["fontsize"] * px_per_pt)
                if offset is None and self._overlaps_any(rect, placed_rects):
                    continue
                placed_rects.append(rect)
                kwargs = dict(font)
                va = kwargs.pop("va", "center")
                text = self.ax.text(
                    lx, ly, row.text, ha="center", va=va,
                    zorder=Z_LABELS, clip_on=True,
                    path_effects=_LABEL_HALO, picker=True, **kwargs)
                text._pym_key = (key, row.text)
                text._pym_base = (row.px, row.py)
                texts.append(text)
            self._label_texts[key] = texts

    @staticmethod
    def _estimate_rect(to_pixels, x: float, y: float, text: str,
                       fontsize_px: float) -> tuple[float, float, float, float]:
        """Rough pixel bounding box of a centered label, cheap enough to run
        for every candidate without a canvas draw."""
        sx, sy = to_pixels.transform((x, y))
        half_w = (len(text) * 0.31 + 0.3) * fontsize_px
        half_h = 0.72 * fontsize_px
        return (sx - half_w, sy - half_h, sx + half_w, sy + half_h)

    @staticmethod
    def _overlaps_any(rect, rects) -> bool:
        ax0, ay0, ax1, ay1 = rect
        for bx0, by0, bx1, by1 in rects:
            if ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0:
                return True
        return False

    # Dragging a label with the left mouse button moves it and remembers the
    # offset (per layer + label text) across pans, zooms, and layer toggles;
    # a right-click on a label snaps it back to its computed position.

    def _toolbar_busy(self) -> bool:
        toolbar = getattr(self.fig.canvas, "toolbar", None)
        return bool(toolbar is not None and toolbar.mode)

    def _label_under(self, event):
        for texts in self._label_texts.values():
            for text in texts:
                contains, _info = text.contains(event)
                if contains:
                    return text
        return None

    def set_label_dragging(self, enabled: bool) -> None:
        self._label_dragging_enabled = enabled

    def _clamp_label_offset(self, bx: float, by: float,
                            dx: float, dy: float) -> tuple[float, float]:
        """Limit *dx, dy* so the label stays within 1% of the current
        view extent from its original position."""
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        max_dx = abs(x1 - x0) * 0.01
        max_dy = abs(y1 - y0) * 0.01
        dx = max(-max_dx, min(max_dx, dx))
        dy = max(-max_dy, min(max_dy, dy))
        return dx, dy

    # Dragging the legend (when enabled) is unbounded - unlike labels, which
    # are held near their computed spot - so it can be parked anywhere on or
    # off the map. A right-click on the legend restores automatic placement.

    def set_legend_dragging(self, enabled: bool) -> None:
        self._legend_dragging_enabled = enabled

    def _legend_lowerleft_axes(self, legend) -> tuple[float, float]:
        """The legend's lower-left corner in axes fraction (the coordinate an
        anchored legend is positioned by)."""
        bbox = legend.get_window_extent()
        x, y = self.ax.transAxes.inverted().transform((bbox.x0, bbox.y0))
        return float(x), float(y)

    def _legend_hit(self, event) -> bool:
        legend = self.ax.get_legend()
        if legend is None or event.x is None or event.y is None:
            return False
        return bool(legend.get_window_extent().contains(event.x, event.y))

    def _on_canvas_press(self, event) -> None:
        if event.inaxes is not self.ax or self._toolbar_busy():
            return
        if self._legend_press(event):
            return
        self._label_press(event)

    def _legend_press(self, event) -> bool:
        """Begin (or reset) a legend drag; returns True if it took the click."""
        if not self._legend_dragging_enabled or not self._legend_hit(event):
            return False
        if event.button == 3:  # right-click: back to automatic placement
            self._legend_anchor = None
            self._update_legend()
            self.redraw()
            return True
        if event.button == 1:
            legend = self.ax.get_legend()
            lx, ly = self._legend_lowerleft_axes(legend)
            cx, cy = self.ax.transAxes.inverted().transform((event.x, event.y))
            # If the legend was auto-placed, pin it to its current corner so
            # the drag has a stable anchor to move from.
            if self._legend_anchor is None:
                self._legend_anchor = (lx, ly)
                self._update_legend()
            self._legend_drag = {"grab": (lx - cx, ly - cy)}
        return True

    def _label_press(self, event) -> None:
        if not self._label_dragging_enabled:
            return
        text = self._label_under(event)
        if text is None:
            return
        if event.button == 3:  # right-click: reset to automatic position
            self._label_offsets.pop(text._pym_key, None)
            self._refresh_labels()
            self.redraw()
            return
        if event.button == 1:
            tx, ty = text.get_position()
            self._label_drag = {"text": text,
                                "grab": (tx - event.xdata, ty - event.ydata)}

    def _on_canvas_motion(self, event) -> None:
        if self._legend_drag is not None:
            self._drag_legend(event)
            return
        if self._label_drag is None or event.inaxes is not self.ax:
            return
        text = self._label_drag["text"]
        gx, gy = self._label_drag["grab"]
        bx, by = text._pym_base
        raw_dx = event.xdata + gx - bx
        raw_dy = event.ydata + gy - by
        dx, dy = self._clamp_label_offset(bx, by, raw_dx, raw_dy)
        text.set_position((bx + dx, by + dy))
        self.redraw()

    def _drag_legend(self, event) -> None:
        legend = self.ax.get_legend()
        if legend is None or event.x is None or event.y is None:
            return
        cx, cy = self.ax.transAxes.inverted().transform((event.x, event.y))
        gx, gy = self._legend_drag["grab"]
        self._legend_anchor = (cx + gx, cy + gy)
        legend.set_bbox_to_anchor(self._legend_anchor,
                                  transform=self.ax.transAxes)
        self.redraw()

    def _on_canvas_release(self, event) -> None:
        if self._legend_drag is not None:
            self._legend_drag = None
            return
        if self._label_drag is None:
            return
        text = self._label_drag["text"]
        self._label_drag = None
        tx, ty = text.get_position()
        bx, by = text._pym_base
        dx, dy = self._clamp_label_offset(bx, by, tx - bx, ty - by)
        self._label_offsets[text._pym_key] = (dx, dy)

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
        self._sync_wrap_copies()
        self.ax.tick_params(labelbottom=labels_on, labelleft=labels_on,
                            bottom=labels_on, left=labels_on)
        self._axes_margins = (_MARGINS_WITH_TICKS if labels_on
                              else _MARGINS_PLAIN)
        self._apply_axes_position()

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
                col._pym_offset = off
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
                   columns: int = 1, frame: bool = True,
                   title_fontsize: float | None = None,
                   marker_scale: float = 1.0,
                   label_spacing: float = 0.5) -> None:
        self._legend_visible = visible
        self._legend_title = title
        self._legend_loc = location
        self._legend_fontsize = fontsize
        self._legend_title_fontsize = (fontsize if title_fontsize is None
                                       else title_fontsize)
        self._legend_columns = max(int(columns), 1)
        self._legend_frame = frame
        self._legend_marker_scale = max(float(marker_scale), 0.1)
        self._legend_label_spacing = max(float(label_spacing), 0.0)
        self._update_legend()

    def set_structured_legend(self, sections: list | None) -> None:
        """Set (or clear with None) a sectioned color/symbol key legend."""
        self._legend_sections = sections
        self._update_legend()

    def clear_legend_anchor(self) -> None:
        """Drop any manual (dragged) legend position, returning to automatic
        placement at the chosen location."""
        self._legend_anchor = None

    def set_point_alpha(self, alpha: float) -> None:
        self._point_alpha = max(min(float(alpha), 1.0), 0.05)
        self._rebuild_points()

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
                    if style.is_open:  # outline-only marker
                        face, edge, lw = "none", style.color, 1.2
                    else:
                        face, edge, lw = style.color, "white", 0.5
                    self._point_artists.append(self.ax.scatter(
                        xs, ys, s=style.size, c=face,
                        marker=style.mpl_marker, zorder=Z_POINTS,
                        edgecolors=edge, linewidths=lw,
                        alpha=self._point_alpha, label=label))
        self._update_legend()

    def _legend_handle(self, style: PointStyle, size: float | None = None):
        area = style.size if size is None else size
        if style.is_open:
            face, edge, edge_w = "none", style.color, 1.2
        else:
            face, edge, edge_w = style.color, "white", 0.5
        return Line2D([], [], linestyle="", marker=style.mpl_marker,
                      markersize=max(np.sqrt(area), 2),
                      markerfacecolor=face, color=style.color,
                      markeredgecolor=edge, markeredgewidth=edge_w)

    def _legend_placement(self) -> dict:
        """Legend ``loc``/``bbox_to_anchor`` kwargs: the automatic location,
        or - once the legend has been dragged - its manual lower-left anchor
        in axes fraction (no bounds)."""
        if self._legend_anchor is not None:
            # borderaxespad=0 pins the lower-left corner exactly on the
            # anchor, so grabbing an auto-placed legend doesn't make it hop.
            return {"loc": "lower left", "bbox_to_anchor": self._legend_anchor,
                    "borderaxespad": 0.0}
        return {"loc": self._legend_loc}

    def _update_legend(self) -> None:
        legend = self.ax.get_legend()
        if legend is not None:
            legend.remove()
        if not (self._legend_visible and self._point_groups):
            return
        if self._legend_sections is not None:
            self._draw_structured_legend()
            return
        handles = [
            self._legend_handle(style)
            for _label, style, _, _ in self._point_groups
        ]
        for handle, (label, *_rest) in zip(handles, self._point_groups):
            handle.set_label(label)
        self.ax.legend(handles=handles,
                       title=self._legend_title,
                       fontsize=self._legend_fontsize,
                       title_fontsize=self._legend_title_fontsize,
                       ncols=self._legend_columns,
                       markerscale=self._legend_marker_scale,
                       labelspacing=self._legend_label_spacing,
                       frameon=self._legend_frame, framealpha=0.85,
                       **self._legend_placement())

    def _draw_structured_legend(self) -> None:
        """A compact legend split into titled sections (a color key and a
        symbol key), so encoding two columns needs only ``colors + symbols``
        rows instead of one row per combination."""
        handles: list = []
        labels: list[str] = []
        header_rows: list[int] = []

        def blank():
            return Line2D([], [], linestyle="", marker="")

        for title, entries in self._legend_sections:
            if handles:  # spacer between sections
                header_rows.append(len(labels))
                handles.append(blank())
                labels.append(" ")
            header_rows.append(len(labels))
            handles.append(blank())
            labels.append(title)
            for label, style in entries:
                handles.append(self._legend_handle(style, size=45))
                labels.append("   " + label)
        leg = self.ax.legend(handles, labels,
                             title=self._legend_title,
                             fontsize=self._legend_fontsize,
                             title_fontsize=self._legend_title_fontsize,
                             ncols=self._legend_columns,
                             markerscale=self._legend_marker_scale,
                             frameon=self._legend_frame, framealpha=0.85,
                             handletextpad=0.4,
                             labelspacing=self._legend_label_spacing,
                             **self._legend_placement())
        texts = leg.get_texts()
        for row in header_rows:
            if row < len(texts):
                texts[row].set_fontweight("bold")

    # --------------------------------------------------------------- output

    def redraw(self) -> None:
        self.fig.canvas.draw_idle()

    def export_size_inches(self) -> tuple[float, float]:
        """The saved image's size in inches at the current geometry.

        For a portrait (letterboxed) map this is the cropped map, not the
        on-screen figure with its blank side bars; for a landscape map it
        equals the figure size. Used to report the output resolution and to
        drive the exported-code figure size."""
        fig_w, fig_h = self.fig.get_size_inches()
        (size, _rect) = _export_geometry(self.ax.get_position().bounds,
                                         float(fig_w), float(fig_h),
                                         self._axes_margins)
        return size

    def save_image(self, path: str, fmt: str = "png", dpi: int = 200) -> None:
        """Write the map to *path* in the given format.

        ``fmt`` is a short key: ``png``, ``jpg``/``jpeg``, ``tiff``/``tif``,
        ``pdf``, ``svg`` or ``webp``. TIFF is written through Pillow so the
        DPI metadata tags are correct; everything else goes straight through
        matplotlib (which uses Pillow for the raster formats it does not
        write natively).

        A portrait map is letterboxed on screen; before writing, the figure
        is temporarily resized so the file is cropped to the map (no blank
        side bars) and then restored.
        """
        fmt = fmt.lower()
        with self._cropped_for_export():
            if fmt in ("tif", "tiff"):
                self._save_tiff(path, dpi)
                return
            if fmt in ("jpg", "jpeg"):
                fmt = "jpeg"  # JPEG has no alpha; the white facecolor fills it
            self.fig.savefig(path, format=fmt, dpi=dpi, facecolor="white")

    @contextmanager
    def _cropped_for_export(self):
        """Temporarily resize the figure so a saved image is cropped to the
        map axes (dropping any orientation letterbox bars), restoring the
        on-screen geometry afterwards. A no-op for a full-canvas map."""
        old_size = tuple(self.fig.get_size_inches())
        old_bounds = self.ax.get_position().bounds
        (new_w, new_h), rect = _export_geometry(
            old_bounds, float(old_size[0]), float(old_size[1]),
            self._axes_margins)
        if (abs(new_w - old_size[0]) < 1e-3
                and abs(new_h - old_size[1]) < 1e-3):
            yield  # landscape / already full-canvas: nothing to crop
            return
        was_suspended = self._suspend_resize
        self._suspend_resize = True
        try:
            self.fig.set_size_inches(new_w, new_h, forward=False)
            self.ax.set_position(list(rect))
            yield
        finally:
            self.fig.set_size_inches(*old_size, forward=False)
            self.ax.set_position(list(old_bounds))
            self._suspend_resize = was_suspended
            self.redraw()

    def _save_tiff(self, path: str, dpi: int) -> None:
        # Render to PNG in memory first; matplotlib's Agg backend does not
        # embed DPI metadata in TIFF files, so we hand off to Pillow which
        # writes the correct XResolution/YResolution TIFF tags.
        import io

        from PIL import Image

        buf = io.BytesIO()
        self.fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
        buf.seek(0)
        img = Image.open(buf)
        img.save(path, format="TIFF", dpi=(dpi, dpi))
