"""The inset map: a small second map in a corner of the main one.

It is a child axes of the map (``Axes.inset_axes``), so it sits in the map's
own axes fraction and follows it through a resize, an orientation switch and
the export crop without any bookkeeping. Its layers come straight from the
LayerStore in its own projection; nothing here touches the main map's
artists except the box a zoomed inset draws on it.

The inset is rebuilt only when what it shows changes - its region, its
projection, its resolution, the points. Panning the main map otherwise only
moves the box that marks the view, so a pan stays as fast as without an
inset.
"""

from __future__ import annotations

import math

import matplotlib.transforms as mtransforms
import numpy as np
from matplotlib.patches import Polygon

from pymappr.geo.layers import LAYER_SPECS
from pymappr.geo.projections import GLOBE, get_projection
from pymappr.geo.regions import inset_extent
from pymappr.renderer.tables import (FILL_COLORS, INSET_BOX_WIDTH,
                                     INSET_FRAME_WIDTH, INSET_LAND,
                                     INSET_LINE_SCALE, INSET_POINT_SCALE,
                                     LINE_LAYERS, Z_INSET, Z_INSET_BOX)
from pymappr.styling.decorations import (InsetOptions, corner_anchor,
                                         inset_box_target)

# Gap between the inset and the map frame, in axes fraction.
_PAD = 0.02
# Gap between the inset and the scale bar or legend it steps around.
_GAP = 0.015
# The inset's width is kept within these fractions of the map box, and its
# height under _MAX_HEIGHT: a tall region is widened to fit rather than
# letting the inset cover half the map.
_SIZE_RANGE = (0.1, 0.6)
_MAX_HEIGHT = 0.6
# Room left around a globe's disk inside its inset.
_GLOBE_MARGIN = 1.04
# Points along each edge of a box, so it bends with the projection.
_EDGE_POINTS = 50


class _InsetLocator:
    """Places the inset axes at the renderer's current rect, in the map's
    axes fraction - read at every draw, so moving the inset is one
    attribute change."""

    def __init__(self, renderer):
        self._renderer = renderer

    def __call__(self, ax, _renderer):
        bbox = mtransforms.Bbox.from_bounds(*self._renderer._inset_rect)
        return mtransforms.TransformedBbox(
            bbox, self._renderer.ax.transAxes - ax.figure.transSubfigure)


class InsetMixin:
    """One inset map per figure."""

    def _init_inset(self) -> None:
        self._inset = InsetOptions()
        self._inset_ax = None
        # x, y, width, height in the map's axes fraction.
        self._inset_rect = (0.0, 0.0, 0.3, 0.3)
        # What the inset was last built from; a refresh with the same key
        # only moves the box.
        self._inset_key = None
        self._inset_proj = None
        self._inset_region = None   # its lon/lat extent
        self._inset_limits = None   # its x0, x1, y0, y1 in its projection
        self._inset_box_artists: list = []
        self._inset_main_artists: list = []
        # (corner, axes-fraction y) a legend in the inset's corner has to
        # keep beyond; None when it can sit anywhere.
        self._inset_clear: tuple[str, float] | None = None
        self._inset_drag: dict | None = None
        # Bumped whenever the points are redrawn, so the inset redraws its.
        self._points_version = 0

    # ------------------------------------------------------------ settings

    def set_inset(self, options: InsetOptions) -> None:
        """Set the inset's options and redraw it."""
        self._inset = options
        self._inset_key = None
        self._refresh_inset()

    def inset_options(self) -> InsetOptions:
        """The options in effect, including a dragged position."""
        return self._inset

    def inset_anchor(self) -> tuple[float, float] | None:
        return self._inset.anchor

    def view_lonlat(self) -> tuple[tuple[float, float, float, float],
                                   tuple[float, float]]:
        """The main map's view as a lon/lat extent, and its centre.

        Sampled over a grid, as on a curved projection the corners of the
        view may be off the map entirely, and the widest lon/lat is
        anywhere along its edges."""
        x0, x1 = sorted(self.ax.get_xlim())
        y0, y1 = sorted(self.ax.get_ylim())
        gx, gy = np.meshgrid(np.linspace(x0, x1, 25), np.linspace(y0, y1, 25))
        lons, lats = self.proj.inverse(gx.ravel(), gy.ravel())
        lons, lats = np.asarray(lons, float), np.asarray(lats, float)
        good = (np.isfinite(lons) & np.isfinite(lats)
                & (np.abs(lons) < 1e6) & (np.abs(lats) <= 90.0))
        if not good.any():
            return (-180.0, 180.0, -90.0, 90.0), (0.0, 0.0)
        lons, lats = lons[good], lats[good]
        extent = (float(lons.min()), float(lons.max()),
                  float(lats.min()), float(lats.max()))
        if extent[1] - extent[0] > 300.0:
            extent = (-180.0, 180.0, extent[2], extent[3])
        clon, clat = self.proj.inverse(np.array([(x0 + x1) / 2.0]),
                                       np.array([(y0 + y1) / 2.0]))
        clon, clat = float(np.asarray(clon)[0]), float(np.asarray(clat)[0])
        if not (math.isfinite(clon) and math.isfinite(clat)):
            clon, clat = float(lons.mean()), float(lats.mean())
        return extent, ((clon + 180.0) % 360.0 - 180.0, clat)

    # ------------------------------------------------------------- framing

    def _inset_projection(self, region, centre):
        opts = self._inset
        if opts.projection == "Globe":
            # Whole degrees: the globe follows the map's centre, and a new
            # projection for every pixel of a pan would rebuild it each time.
            return get_projection(GLOBE, float(round(centre[0])),
                                  float(round(centre[1])))
        if opts.projection in ("Equirectangular", "Robinson"):
            return get_projection(opts.projection)
        main = self.proj
        if main.hemisphere:
            return get_projection("Equirectangular")
        if main.is_regional:
            lon0, lon1, lat0, lat1 = region
            inside = (lat0 >= main.min_lat and lat1 <= main.max_lat
                      and lon0 >= main.lon_0 - main.lon_halfspan
                      and lon1 <= main.lon_0 + main.lon_halfspan)
            if not inside:
                return get_projection("Equirectangular")
        return main

    def _inset_frame(self, proj, region) -> tuple[float, float, float, float]:
        """The inset's limits in its projection, before fitting its box."""
        if proj.hemisphere:
            cx = (proj.bounds[0] + proj.bounds[1]) / 2.0
            cy = (proj.bounds[2] + proj.bounds[3]) / 2.0
            half = max(proj.bounds[1] - proj.bounds[0],
                       proj.bounds[3] - proj.bounds[2]) / 2.0 * _GLOBE_MARGIN
            return cx - half, cx + half, cy - half, cy + half
        return proj.project_extent(region)

    def _map_box_aspect(self) -> float:
        """Width over height of the map box, in display units."""
        bbox = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        return max(bbox.width * fig_w, 1e-6) / max(bbox.height * fig_h, 1e-6)

    def _fit_inset(self, limits):
        """The inset's (rect, limits): sized to its region's shape, no
        taller than _MAX_HEIGHT, with the limits widened to the box so map
        units stay square."""
        x0, x1, y0, y1 = limits
        width = min(max(float(self._inset.size), _SIZE_RANGE[0]),
                    _SIZE_RANGE[1])
        span_x, span_y = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        box_aspect = self._map_box_aspect()
        height = width * box_aspect * span_y / span_x
        if height > _MAX_HEIGHT:
            height = _MAX_HEIGHT
            new_x = span_y * width * box_aspect / height
            cx = (x0 + x1) / 2.0
            x0, x1 = cx - new_x / 2.0, cx + new_x / 2.0
        return (width, height), (x0, x1, y0, y1)

    def _place_inset(self, size) -> None:
        """Put the inset in its corner, or where it was dragged, stepping
        above (or below) a scale bar in the same corner."""
        width, height = size
        opts = self._inset
        if opts.anchor is not None:
            x = float(np.clip(opts.anchor_x, 0.0, 1.0 - width))
            y = float(np.clip(opts.anchor_y, 0.0, 1.0 - height))
            self._inset_rect = (x, y, width, height)
            self._inset_clear = None
            return
        cx, cy = corner_anchor(opts.position, pad=_PAD)
        right, top = cx > 0.5, cy > 0.5
        x = cx - width if right else cx
        y = cy - height if top else cy
        bar = getattr(self, "_scale_bar_clear", None)
        if bar is not None and bar[0] == opts.position:
            _corner, frac, points = bar
            lift = points / 72.0 * self.fig.dpi / max(self.ax.bbox.height, 1.0)
            if top:
                y = min(y, frac + lift - _GAP - height)
            else:
                y = max(y, frac + lift + _GAP)
        self._inset_rect = (x, y, width, height)
        self._inset_clear = (opts.position,
                             y - _GAP if top else y + height + _GAP)

    # ------------------------------------------------------------- refresh

    def _inset_zoom(self, proj, limits) -> float:
        """The zoom level whose resolution suits the inset: its own span,
        at the fraction of the map it takes up."""
        span = max(abs(limits[1] - limits[0]), 1e-9)
        zoom = math.log2(proj.world_width / span)
        zoom += math.log2(max(self._inset_rect[2], 0.05))
        return max(zoom, 0.0) + getattr(self, "_detail_boost", 0.0)

    def _refresh_inset(self) -> None:
        """Bring the inset in line with the options and the map's view:
        rebuild it when what it shows changed, otherwise just move it and
        its box."""
        opts = self._inset
        before = self._inset_clear
        if not opts.show:
            self._remove_inset()
        else:
            view, centre = self.view_lonlat()
            region = inset_extent(self.store, opts, view, centre)
            proj = self._inset_projection(region, centre)
            size, limits = self._fit_inset(self._inset_frame(proj, region))
            self._place_inset(size)
            zoom = self._inset_zoom(proj, limits)
            directories = tuple(LAYER_SPECS[key].directory_for_zoom(zoom)
                                for key in ("countries", "land", "ocean"))
            key = (repr(opts.to_dict() | {"anchor_x": None,
                                          "anchor_y": None}),
                   proj.key, tuple(round(v, 6) for v in limits),
                   directories, self._points_version, self._point_alpha,
                   self._point_edge)
            if key != self._inset_key or self._inset_ax is None:
                self._inset_proj, self._inset_region = proj, region
                self._inset_limits = limits
                self._build_inset(zoom)
                self._inset_key = key
            self._draw_inset_box(view)
        if self._inset_clear != before:
            # A legend in the inset's corner moves to keep it in view.
            self._update_legend()

    def _remove_inset(self) -> None:
        if self._inset_ax is not None:
            self._inset_ax.remove()
        self._inset_ax = None
        self._inset_key = None
        self._inset_clear = None
        self._inset_box_artists = []
        for artist in self._inset_main_artists:
            artist.remove()
        self._inset_main_artists = []

    def _build_inset(self, zoom: float) -> None:
        if self._inset_ax is not None:
            self._inset_ax.remove()
        self._inset_box_artists = []
        proj, opts = self._inset_proj, self._inset
        ax = self.ax.inset_axes(self._inset_rect, zorder=Z_INSET)
        ax.set_axes_locator(_InsetLocator(self))
        self._inset_ax = ax
        ax.set_navigate(False)
        ax.set_autoscale_on(False)
        ax.set_xticks([])
        ax.set_yticks([])
        x0, x1, y0, y1 = self._inset_limits
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        if proj.hemisphere:
            # A globe reads as a disk: no square frame around it, and white
            # only inside its horizon.
            ax.set_facecolor("none")
            for spine in ax.spines.values():
                spine.set_visible(False)
            hx, hy = proj.horizon_xy()
            ax.add_patch(Polygon(np.column_stack([hx, hy]), closed=True,
                                 facecolor="white", edgecolor="none",
                                 zorder=0.05))
        else:
            ax.set_facecolor("white")
            for spine in ax.spines.values():
                spine.set_linewidth(INSET_FRAME_WIDTH)
                spine.set_edgecolor("#000000")
        for source, kwargs in self._inset_layers(opts):
            gdf = self._inset_frame_data(source, zoom)
            if gdf is not None and len(gdf):
                gdf.plot(ax=ax, aspect=None, **kwargs)
        ax.set_xlabel("")
        ax.set_ylabel("")
        if proj.hemisphere:
            hx, hy = proj.horizon_xy()
            ax.plot(hx, hy, color="#000000", linewidth=INSET_FRAME_WIDTH,
                    zorder=1.9)
        if opts.points:
            self._draw_inset_points(ax, proj)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)

    @staticmethod
    def _inset_layers(opts: InsetOptions) -> list[tuple[str, dict]]:
        """(source layer, plot keywords) for what the inset draws, bottom
        up."""
        layers = []
        if opts.ocean in ("grey", "blue"):
            layers.append(("ocean", dict(
                facecolor=FILL_COLORS[("ocean", opts.ocean)],
                edgecolor="none", zorder=0.3)))
        if opts.land:
            layers.append(("land", dict(facecolor=INSET_LAND,
                                        edgecolor="none", zorder=0.35)))
        # Without country borders the coast is still drawn, as on the map.
        for key, on in (("counties", opts.counties), ("states", opts.states),
                        ("countries" if opts.countries else "continents",
                         True)):
            if not on:
                continue
            source, color, width, zorder, linestyle = LINE_LAYERS[key]
            layers.append((source, dict(
                facecolor="none", edgecolor=color, linestyle=linestyle,
                linewidth=max(width * INSET_LINE_SCALE, 0.2),
                zorder=zorder)))
        return layers

    def _inset_frame_data(self, source: str, zoom: float):
        """*source* in the inset's projection, cut to the part in view so a
        detailed layer (counties) does not draw the whole world."""
        proj = self._inset_proj
        gdf = self.store.frame_projected(source, proj.crs, proj.max_lat,
                                         zoom=zoom,
                                         clip_shape=proj.clip_shape())
        if proj.hemisphere or gdf is None or not len(gdf):
            return gdf
        x0, x1, y0, y1 = self._inset_limits
        mx, my = (x1 - x0) * 0.05, (y1 - y0) * 0.05
        return gdf.cx[x0 - mx:x1 + mx, y0 - my:y1 + my]

    def _draw_inset_points(self, ax, proj) -> None:
        for _label, style, lons, lats in self._point_groups:
            xs, ys = proj.forward(lons, lats, clamp=False)
            face, edge, width = self._marker_paint(style)
            ax.scatter(xs, ys, s=max(style.size * INSET_POINT_SCALE, 3.0),
                       c=face, marker=style.mpl_marker, edgecolors=edge,
                       linewidths=width * 0.6, alpha=self._point_alpha,
                       zorder=2.6)

    # ----------------------------------------------------------------- box

    @staticmethod
    def _box_ring(x0, x1, y0, y1) -> tuple[np.ndarray, np.ndarray]:
        """A rectangle's outline, densified so it can be reprojected."""
        t = np.linspace(0.0, 1.0, _EDGE_POINTS)
        xs = np.concatenate([x0 + (x1 - x0) * t, np.full_like(t, x1),
                             x1 - (x1 - x0) * t, np.full_like(t, x0)])
        ys = np.concatenate([np.full_like(t, y0), y0 + (y1 - y0) * t,
                             np.full_like(t, y1), y1 - (y1 - y0) * t])
        return xs, ys

    def _inset_box_target(self, view) -> str | None:
        if not self._inset.box:
            return None
        if self._inset_proj.hemisphere:
            return "inset"
        return inset_box_target(self._inset_region, view)

    def inset_box_xy(self, view=None):
        """(target, xs, ys) of the box linking the two maps - on the inset
        in its projection, or on the map in the map's - or None."""
        if self._inset_ax is None:
            return None
        if view is None:
            view, _centre = self.view_lonlat()
        target = self._inset_box_target(view)
        if target == "inset":
            x0, x1 = sorted(self.ax.get_xlim())
            y0, y1 = sorted(self.ax.get_ylim())
            lons, lats = self.proj.inverse(*self._box_ring(x0, x1, y0, y1))
            xs, ys = self._inset_proj.forward(lons, lats, clamp=False)
        elif target == "main":
            xs, ys = self.proj.forward(*self._box_ring(*self._inset_region),
                                       clamp=False)
        else:
            return None
        return target, np.asarray(xs, float), np.asarray(ys, float)

    def _draw_inset_box(self, view) -> None:
        for artist in self._inset_box_artists + self._inset_main_artists:
            artist.remove()
        self._inset_box_artists, self._inset_main_artists = [], []
        box = self.inset_box_xy(view)
        if box is None:
            return
        target, xs, ys = box
        color = self._inset.box_color or "#d62728"
        if target == "inset":
            (line,) = self._inset_ax.plot(xs, ys, color=color,
                                          linewidth=INSET_BOX_WIDTH,
                                          zorder=3.0)
            self._inset_box_artists = [line]
            return
        with self._preserving_view():
            (line,) = self.ax.plot(xs, ys, color=color,
                                   linewidth=INSET_BOX_WIDTH,
                                   zorder=Z_INSET_BOX)
        self._inset_main_artists = [line]

    # -------------------------------------------------------------- export

    def inset_export(self) -> dict | None:
        """Everything the code export needs to redraw the inset as it is on
        screen, as plain JSON-able values, or None without an inset.

        The region, projection and box are resolved here rather than in the
        exported script, so the script needs no state or country lookup.
        """
        if self._inset_ax is None:
            return None
        proj, opts = self._inset_proj, self._inset
        box = self.inset_box_xy()

        def numbers(values) -> list:
            return [None if not math.isfinite(v) else round(float(v), 6)
                    for v in values]

        return {
            "rect": [round(float(v), 6) for v in self._inset_rect],
            "projection": proj.name,
            "crs": proj.crs,
            "hemisphere": proj.hemisphere,
            "lon_0": proj.lon_0, "lat_0": proj.lat_0,
            "min_lat": proj.min_lat, "max_lat": proj.max_lat,
            "lon_halfspan": proj.lon_halfspan,
            "region": [float(v) for v in self._inset_region],
            "limits": [float(v) for v in self._inset_limits],
            # Without any export detail boost: the script picks its own.
            "zoom": self._inset_zoom(proj, self._inset_limits)
            - getattr(self, "_detail_boost", 0.0),
            "layers": [[source, kwargs]
                       for source, kwargs in self._inset_layers(opts)],
            "points": bool(opts.points),
            "point_scale": INSET_POINT_SCALE,
            "frame_width": INSET_FRAME_WIDTH,
            "horizon": ([numbers(v) for v in proj.horizon_xy()]
                        if proj.hemisphere else None),
            "box": None if box is None else {
                "target": box[0], "x": numbers(box[1]), "y": numbers(box[2]),
                "color": opts.box_color or "#d62728",
                "width": INSET_BOX_WIDTH},
        }

    # ---------------------------------------------------------------- drag

    def _inset_hit(self, event) -> bool:
        if (self._inset_ax is None or event.x is None or event.y is None):
            return False
        return bool(self._inset_ax.bbox.contains(event.x, event.y))

    def _inset_press(self, event) -> bool:
        """Start dragging the inset, or right-click it back to its corner.
        Returns True when the press was consumed."""
        if not self._inset.draggable or not self._inset_hit(event):
            return False
        if event.button == 3:
            self._inset.anchor_x = None
            self._inset.anchor_y = None
            self._refresh_inset()
            self.redraw()
            return True
        if event.button == 1:
            x, y, _w, _h = self._inset_rect
            cx, cy = self.ax.transAxes.inverted().transform((event.x, event.y))
            self._inset_drag = {"grab": (x - cx, y - cy)}
        return True

    def _drag_inset(self, event) -> None:
        if event.x is None or event.y is None:
            return
        cx, cy = self.ax.transAxes.inverted().transform((event.x, event.y))
        gx, gy = self._inset_drag["grab"]
        _x, _y, width, height = self._inset_rect
        self._inset.anchor_x = float(np.clip(cx + gx, 0.0, 1.0 - width))
        self._inset.anchor_y = float(np.clip(cy + gy, 0.0, 1.0 - height))
        self._place_inset((width, height))
        self._update_legend()
        self.redraw()
