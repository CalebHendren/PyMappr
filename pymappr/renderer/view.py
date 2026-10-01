"""What part of the map is on screen, and in which projection: the
extent, orientation and zoom, the refresh every view change triggers, the
projection switch that rebuilds the scene, the graticule, and saving the
map to a file."""

from __future__ import annotations

from contextlib import contextmanager

import matplotlib.transforms as mtransforms
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.ticker import AutoLocator, FuncFormatter, MultipleLocator

from pymappr.geo.layers import CONTINENT_EXTENTS, LayerStore
from pymappr.geo.projections import get_projection
from pymappr.renderer.geometry import (clamp_zoom_factor, export_geometry,
                                       format_lat, format_lon,
                                       oriented_axes_rect, refit_xlim)
from pymappr.renderer.tables import (MARGINS_PLAIN, MARGINS_WITH_TICKS,
                                     ORIENTATION_ASPECT, Z_GRID)

# Horizontal world copies drawn for wrap-around panning, in world-widths.
_WRAP_OFFSETS = (-1, 0, 1)

# Fraction of the shorter side of the map box the globe's disk spans, so it
# sits centred with a margin instead of running the full length of the canvas.
_GLOBE_FILL = 0.88

# A scroll-wheel or zoom-button zoom renders for real once no notch has come
# for this long (milliseconds). Until then each notch only rescales the map
# snapshot, which costs a few milliseconds against ~0.5 s for a render of a
# raster basemap with several vector layers.
_ZOOM_PAUSE_MS = 150


class ViewMixin:
    """The camera: extent, orientation, zoom, projection, graticule and export."""

    def _init_view(self, figure, store: LayerStore) -> None:
        self.fig = figure
        self.store = store
        self.ax = figure.add_axes([0.055, 0.045, 0.935, 0.945])
        self.ax.set_autoscale_on(False)
        self.ax.xaxis.set_major_formatter(FuncFormatter(format_lon))
        self.ax.yaxis.set_major_formatter(FuncFormatter(format_lat))
        self.ax.tick_params(labelsize=7, length=2.5, direction="out")

        self.proj = get_projection("Equirectangular")
        self._extent_request = "World"
        self._orientation = "landscape"
        self._graticule: float | None = None
        self._graticule_labels = True
        # Base axes margins currently in effect (with or without room for
        # tick labels); the orientation narrows this into the axes box.
        self._axes_margins = MARGINS_PLAIN
        # In portrait the map is a tall box centred on the figure; the blank
        # side bars are painted this "mat" colour (the app's background) so
        # the framing reads as a centred page instead of stray whitespace.
        # The map itself keeps a white background regardless.
        self._mat_color = "#e6e6e6"
        self.ax.set_facecolor("white")

        # Every drawn artist that belongs to the scene, by name. Layers are
        # keyed "<layer>@<source directory>" so multi-resolution layers keep
        # one artist set per resolution; the graticule, horizon, compass and
        # scale bar have a key each.
        self._artists: dict[str, list] = {}
        self._in_wrap = False
        self._in_limits_refresh = False
        # While the figure is temporarily resized for export, the resize
        # handler must not re-fit the on-screen view to the export size.
        self._suspend_resize = False
        # The scroll-wheel zoom waiting on its timer (see zoom_interactive).
        self._zoom_gesture: dict | None = None

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

    @contextmanager
    def _one_view_change(self):
        """Change both axis limits with one view refresh rather than one per
        axis - each refresh rebuilds the labels and point layers."""
        if self._in_limits_refresh:
            yield
            return
        self._in_limits_refresh = True
        try:
            yield
        finally:
            self._in_limits_refresh = False
        self._on_limits_changed(self.ax)

    def set_extent(self, extent) -> None:
        """*extent* is a continent name or a (lon0, lon1, lat0, lat1) tuple
        in degrees; it is projected into map coordinates here.

        The extent is padded to the canvas aspect ratio so map units stay
        square, but never beyond the world bounds; extents too wide to fit
        (World, Antarctica) simply fill the canvas.

        The globe ignores the extent and always frames its whole disk - see
        :meth:`_frame_globe`.
        """
        self._extent_request = extent
        if self.proj.hemisphere:
            self._frame_globe()
            return
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

        with self._one_view_change():
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
        rect = oriented_axes_rect(
            self._axes_margins, float(fig_w), float(fig_h),
            ORIENTATION_ASPECT.get(self._orientation))
        self.ax.set_position(list(rect))

    def _globe_disk(self) -> tuple[float, float, float]:
        """The globe's disk as ``(centre x, centre y, radius)`` in map
        coordinates.

        On the WGS84 ellipsoid the orthographic disk is very slightly off
        centre and non-circular, and both drift with the origin, so the disk
        is measured from the projection's own bounds rather than assumed to
        be a circle about (0, 0)."""
        wx0, wx1, wy0, wy1 = self.proj.bounds
        return ((wx0 + wx1) / 2.0, (wy0 + wy1) / 2.0,
                max(wx1 - wx0, wy1 - wy0) / 2.0)

    def _frame_globe(self, keep_zoom: bool = False) -> None:
        """Centre the globe's disk in the map box, with a margin around it.

        The view follows the disk itself, never the requested extent: a
        lon/lat extent's projected bounding box lurches sideways and changes
        width as parts of it swing behind the horizon, which is what made a
        spin jump left and right. The disk, by contrast, stays put whatever
        the origin, so re-deriving the view on every spin is a no-op.

        With *keep_zoom* the current zoom level is preserved and only the
        aspect is re-fitted (a window resize or an orientation switch)."""
        self._apply_axes_position()
        pos = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        box_ratio = max((pos.width * fig_w) / (pos.height * fig_h), 1e-6)
        cx, cy, radius = self._globe_disk()
        short = radius / _GLOBE_FILL  # half-span across the box's short side
        if keep_zoom:
            x0, x1 = self.ax.get_xlim()
            y0, y1 = self.ax.get_ylim()
            zoomed = min(abs(x1 - x0), abs(y1 - y0)) / 2.0
            if zoomed > 0:
                short = zoomed
        half_h = short if box_ratio >= 1.0 else short / box_ratio
        half_w = half_h * box_ratio
        with self._one_view_change():
            self.ax.set_xlim(cx - half_w, cx + half_w)
            self.ax.set_ylim(cy - half_h, cy + half_h)

    def _refit_view_to_box(self) -> None:
        """Re-fit the current view to the current orientation's axes box.

        The view centre and its vertical span are kept; the horizontal span
        is set to match the box aspect, so map units stay square. Landscape
        never widens past the world; portrait only ever narrows."""
        if self.proj.hemisphere:
            # Keeping the vertical span would crop the disk when a wide box
            # turns tall; re-centre it in the new box instead.
            self._frame_globe(keep_zoom=True)
            return
        self._apply_axes_position()
        pos = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        box_ratio = max((pos.width * fig_w) / (pos.height * fig_h), 1e-6)
        x0, x1 = refit_xlim(box_ratio, self.ax.get_xlim(),
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
        with self._one_view_change():
            self.ax.set_xlim(tuple(xlim))
            self.ax.set_ylim(tuple(ylim))

    def zoom(self, factor: float, center: tuple[float, float] | None = None) -> None:
        """Zoom the view by *factor* (>1 zooms in), keeping *center* (map
        coordinates, e.g. the cursor position) fixed; without a center the
        view zooms about its middle."""
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        factor = clamp_zoom_factor(factor, x1 - x0, self.proj.world_width)
        if abs(factor - 1.0) < 1e-9:
            return
        if self.proj.hemisphere:
            # The globe is pinned to the middle of the map box; zooming about
            # the cursor would slide the disk off centre, and a spin would
            # then snap it back.
            center = None
        cx = center[0] if center is not None else (x0 + x1) / 2
        cy = center[1] if center is not None else (y0 + y1) / 2
        with self._one_view_change():
            self.ax.set_xlim(cx - (cx - x0) / factor,
                             cx + (x1 - cx) / factor)
            self.ax.set_ylim(cy - (cy - y0) / factor,
                             cy + (y1 - cy) / factor)

    # A scroll-wheel notch or a zoom button zooms through zoom_interactive.
    # A render with a raster basemap and a few layers takes most of a second,
    # so rendering every notch would stall a quick spin of the wheel for
    # seconds. Instead each notch scales the map snapshot the last render
    # left behind (blit.py), and the view changes, with one render, once the
    # wheel has rested for _ZOOM_PAUSE_MS.
    #
    # The notches are kept as one scaling of the display, x -> scale * x +
    # shift, with each notch scaling about its own cursor position. Every
    # preview resamples the original snapshot by that, never the previous
    # preview, so a burst blurs no more than a single notch does. Nothing
    # renders in between, so the snapshot stays the original.

    def zoom_interactive(self, factor: float,
                         center_px: tuple[float, float] | None = None) -> None:
        """Zoom by *factor* (>1 zooms in) about the display point
        *center_px* - the cursor - showing a scaled snapshot of the map now
        and rendering the zoom once no further call has come for
        _ZOOM_PAUSE_MS. Without a centre, and always on the globe, the zoom
        is about the middle of the map box, as with :meth:`zoom`."""
        if self._pan_drag is not None or self._globe_drag is not None:
            # The drag owns the view until it is released.
            return
        if self._map_background() is None:
            # No snapshot of the screen as it is - nothing rendered since
            # start-up, or the map box has changed size. Finishing a zoom in
            # progress renders one, as does a plain render otherwise.
            if self._zoom_gesture is not None:
                self._finish_zoom()
            else:
                self.fig.canvas.draw()
        background = self._map_background()
        bbox = self.ax.bbox
        if center_px is None or self.proj.hemisphere:
            center_px = ((bbox.x0 + bbox.x1) / 2.0, (bbox.y0 + bbox.y1) / 2.0)
        if background is None:
            # A canvas that cannot cache pixels: no preview to show.
            self.zoom(factor,
                      tuple(self.ax.transData.inverted().transform(center_px)))
            self.redraw()
            return
        gesture = self._zoom_gesture
        if gesture is None:
            gesture = self._zoom_gesture = {
                "scale": 1.0, "shift": (0.0, 0.0),
                "timer": self._single_shot_timer(_ZOOM_PAUSE_MS,
                                                 self._finish_zoom)}
        # Clamped as a whole, as zoom() will clamp it, so the preview never
        # shows a zoom the render then refuses.
        x0, x1 = self.ax.get_xlim()
        scale = clamp_zoom_factor(gesture["scale"] * factor, x1 - x0,
                                  self.proj.world_width)
        step = scale / gesture["scale"]
        (tx, ty), (px, py) = gesture["shift"], center_px
        gesture["scale"] = scale
        gesture["shift"] = (step * tx + (1.0 - step) * px,
                            step * ty + (1.0 - step) * py)
        self._blit_scaled(background, scale, gesture["shift"])
        timer = gesture["timer"]
        if timer is not None:
            # Re-armed on every notch, so it fires only once the wheel rests.
            timer.stop()
            timer.start()

    def _finish_zoom(self) -> None:
        """Apply the zoom the notches so far add up to, and render it."""
        gesture = self._zoom_gesture
        if gesture is None:
            return
        self._zoom_gesture = None
        if gesture["timer"] is not None:
            gesture["timer"].stop()
        scale = gesture["scale"]
        tx, ty = gesture["shift"]
        if abs(scale - 1.0) >= 1e-9:
            # Zoomed about the one display point the scaling leaves where
            # it was.
            fixed = (tx / (1.0 - scale), ty / (1.0 - scale))
            self.zoom(scale, tuple(self.ax.transData.inverted().transform(
                fixed)))
        else:
            # In at one point and out at another: the scales cancel, and
            # what is left moves the map by *shift* pixels, as a pan would.
            x0, x1 = self.ax.get_xlim()
            y0, y1 = self.ax.get_ylim()
            bbox = self.ax.bbox
            dx = -(x1 - x0) / bbox.width * tx
            dy = -(y1 - y0) / bbox.height * ty
            with self._one_view_change():
                self.ax.set_xlim(x0 + dx, x1 + dx)
                self.ax.set_ylim(y0 + dy, y1 + dy)
        # Drawn now rather than deferred: the next notch or drag scales the
        # snapshot this render leaves.
        self.fig.canvas.draw()

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
            # After the wrap copies settle, so only the copies actually on
            # screen pay for a crop.
            self._refresh_basemap()
            self._refresh_point_layers()
            self._refresh_labels()
            # Unlike the compass, the bar's length is a function of the view.
            self._apply_scale_bar()
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

    def set_projection(self, name: str, lon_0: float | None = None,
                       lat_0: float | None = None) -> None:
        """Switch projection and rebuild every artist in the new one.

        For Lambert presets and the Globe *lon_0*/*lat_0* set the point of
        natural origin; they are ignored for the fixed world projections."""
        proj = get_projection(name, lon_0, lat_0)
        if proj == self.proj:
            return
        # Spinning the globe only moves its origin: the disk keeps the same
        # size in map coordinates, so the view is re-centred on it at the
        # current zoom rather than rebuilt from the extent request. That keeps
        # the spin perfectly steady and preserves however far the user has
        # zoomed in.
        respin = self.proj.hemisphere and proj.hemisphere
        self.proj = proj
        # Manual label offsets are in map coordinates, which just changed
        # scale/shape entirely - start fresh in the new projection.
        self._label_offsets.clear()
        self._clear_artists()
        self._rebuild_scene(respin=respin)
        # The globe takes over pan/zoom drags to spin; other projections hand
        # them back to matplotlib.
        self._sync_navigation()

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

    def _rebuild_scene(self, respin: bool = False) -> None:
        # Move the camera into the new projection's coordinates first:
        # everything downstream (graticule locators, label culling) reads
        # the axis limits. A *respin* only re-centred the globe, so the view
        # is re-fitted to the disk at the zoom it already has.
        if respin:
            self._frame_globe(keep_zoom=True)
        else:
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
        self._apply_scale_bar()
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
        self._axes_margins = (MARGINS_WITH_TICKS if labels_on
                              else MARGINS_PLAIN)
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

    def redraw(self) -> None:
        self.fig.canvas.draw_idle()

    def export_size_inches(self) -> tuple[float, float]:
        """The saved image's size in inches at the current geometry.

        For a portrait (letterboxed) map this is the cropped map, not the
        on-screen figure with its blank side bars; for a landscape map it
        equals the figure size. Used to report the output resolution and to
        drive the exported-code figure size."""
        fig_w, fig_h = self.fig.get_size_inches()
        (size, _rect) = export_geometry(self.ax.get_position().bounds,
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
        with self._cropped_for_export(), self.basemap_detail_for(dpi):
            if fmt in ("tif", "tiff"):
                self._save_tiff(path, dpi)
                return
            if fmt in ("jpg", "jpeg"):
                fmt = "jpeg"  # JPEG has no alpha; the white facecolor fills it
            self.fig.savefig(path, format=fmt, dpi=dpi, facecolor="white")

    @contextmanager
    def basemap_detail_for(self, dpi: float):
        """Raise the raster basemap's detail to suit a render at *dpi*.

        ``savefig`` renders at its own dpi without changing ``fig.dpi``, so
        without this a 200- or 600-dpi export would be written from the crop
        cut for a 100-dpi screen - visibly softer than before the basemap
        became view-scoped. Anything that saves the figure directly rather
        than through :meth:`save_image` wants this too."""
        try:
            self._refresh_basemap(dpi=dpi)
            yield
        finally:
            self._refresh_basemap()

    @contextmanager
    def _cropped_for_export(self):
        """Temporarily resize the figure so a saved image is cropped to the
        map axes (dropping any orientation letterbox bars), restoring the
        on-screen geometry afterwards. A no-op for a full-canvas map."""
        old_size = tuple(self.fig.get_size_inches())
        old_bounds = self.ax.get_position().bounds
        (new_w, new_h), rect = export_geometry(
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
