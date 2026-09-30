"""Mouse handling: panning and spinning the globe, and dragging the
legend, labels and scale bar."""

from __future__ import annotations

import time

import numpy as np

from pymappr.decorations import corner_anchor
from pymappr.projections import GLOBE

# The globe re-projects at most this often (seconds) while being dragged;
# the last position is always applied when the drag ends.
_SPIN_INTERVAL = 0.05

# A pan re-renders for real at most this often (seconds). Every motion event
# in between only shifts the cached bitmap, which costs ~0.1 ms against ~1 s
# for a full re-render of a raster basemap with several vector layers. The
# real render is what fills in the strip the shift cannot cover, and the
# release always ends on one.
_PAN_INTERVAL = 0.18


class MouseMixin:
    """Press, drag and release on the map."""

    def _init_mouse(self) -> None:
        self._scale_bar_drag: dict | None = None
        self._legend_drag: dict | None = None
        self._legend_dragging_enabled = False
        self._label_drag: dict | None = None
        self._label_dragging_enabled = False
        # Globe spin: a left-drag on the orthographic globe rotates it by
        # re-centring the projection. ``_on_globe_rotate`` lets the app keep
        # its centre-lon/lat controls in sync with the drag.
        self._globe_drag: dict | None = None
        self._on_globe_rotate = None
        # Map pan: a left-drag with the toolbar's pan tool active, shown by
        # shifting the cached bitmap rather than re-rendering (see
        # ``_pan_press``).
        self._pan_drag: dict | None = None

    # Dragging a label with the left mouse button moves it and remembers the
    # offset (per layer + label text) across pans, zooms, and layer toggles;
    # a right-click on a label snaps it back to its computed position.

    def _toolbar_busy(self) -> bool:
        toolbar = getattr(self.fig.canvas, "toolbar", None)
        return bool(toolbar is not None and toolbar.mode)

    def _toolbar_panning(self) -> bool:
        """Whether the toolbar's pan/zoom tool is the active one."""
        toolbar = getattr(self.fig.canvas, "toolbar", None)
        mode = getattr(toolbar, "mode", "")
        return str(mode) == "pan/zoom"

    def _label_under(self, event):
        for texts in self._label_texts.values():
            for text in texts:
                contains, _info = text.contains(event)
                if contains:
                    return text
        return None

    def set_label_dragging(self, enabled: bool) -> None:
        self._label_dragging_enabled = enabled

    def _clamp_label_offset(self, dx: float,
                            dy: float) -> tuple[float, float]:
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

    def _sync_navigation(self) -> None:
        """Hand pan drags to our own handlers rather than matplotlib's.

        Matplotlib's axes pan re-renders the whole scene on every motion event.
        Switching it off for the map axes leaves the gesture to us in every
        projection: the globe spins (``_globe_press``) and every other
        projection blits (``_pan_press``). The rubber-band zoom is switched off
        only on the globe, whose disk stays centred. The scroll wheel and the
        zoom buttons still zoom - they don't route through this."""
        self.ax.can_pan = lambda *_a, **_k: False
        if self.proj.hemisphere:
            self.ax.can_zoom = lambda *_a, **_k: False
        else:
            self.ax.__dict__.pop("can_zoom", None)

    def set_globe_rotate_callback(self, callback) -> None:
        """Register *callback(lon0, lat0)*, invoked as the globe is spun so
        the app can mirror the new centre in its controls."""
        self._on_globe_rotate = callback

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
        if event.inaxes is not self.ax:
            return
        # The globe spin takes the press even while a matplotlib toolbar tool
        # (pan/zoom) is active: matplotlib's own axes pan and rubber-band zoom
        # are switched off for the map axes on the globe (see _sync_navigation),
        # so the gestures never fight. Panning the globe therefore spins it
        # instead of sliding the disk around.
        #
        # Legend and label dragging (when enabled) still win over a globe spin,
        # so annotations stay draggable on the globe. They yield to an active
        # toolbar tool, exactly as before.
        if not self._toolbar_busy():
            if self._scale_bar_press(event):
                return
            if self._legend_press(event):
                return
            self._label_press(event)
            if self._label_drag is not None:
                return
        if event.button != 1:
            return
        if self.proj.hemisphere:
            self._globe_press(event)
        elif self._toolbar_panning():
            self._pan_press(event)

    def _globe_disk_px(self) -> float:
        """The globe disk's diameter on screen, in pixels."""
        ext = self.ax.get_window_extent()
        diameter = 2.0 * self._globe_disk()[2]
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        px = min(diameter / max(abs(x1 - x0), 1e-9) * ext.width,
                 diameter / max(abs(y1 - y0), 1e-9) * ext.height)
        return max(px, 1.0)

    def _globe_press(self, event) -> None:
        self._globe_drag = {"x": event.x, "y": event.y,
                            "lon0": self.proj.lon_0, "lat0": self.proj.lat_0,
                            "pending": None, "applied_at": None}

    def _spin_globe(self, event) -> None:
        if self._globe_drag is None or event.x is None or event.y is None:
            return
        drag = self._globe_drag
        # ~180 degrees span the visible disk; scale the pixel drag to that so
        # grabbing and dragging turns the globe about that much. The disk is
        # measured on screen, not assumed to fill the box, so the gesture keeps
        # tracking the surface under the cursor at any zoom.
        scale = 180.0 / self._globe_disk_px()
        lon0 = drag["lon0"] - (event.x - drag["x"]) * scale
        lat0 = drag["lat0"] - (event.y - drag["y"]) * scale
        lat0 = max(-90.0, min(90.0, lat0))
        lon0 = ((lon0 + 180.0) % 360.0) - 180.0
        drag["pending"] = (lon0, lat0)
        last = drag["applied_at"]
        if last is None or time.monotonic() - last >= _SPIN_INTERVAL:
            self._apply_spin()

    def _apply_spin(self) -> None:
        """Re-centre the globe on the drag's latest position."""
        drag = self._globe_drag
        lon0, lat0 = drag["pending"]
        drag["pending"] = None
        self.set_projection(GLOBE, lon0, lat0)
        # Timed from the end of the rebuild: the interval is breathing room
        # between rebuilds, not a deadline they compete with.
        drag["applied_at"] = time.monotonic()
        if self._on_globe_rotate is not None:
            self._on_globe_rotate(lon0, lat0)
        self.redraw()

    # ------------------------------------------------------------------- pan
    #
    # Panning a flat projection only translates the map, so the drag shifts the
    # pixels already rendered - ~0.1 ms a frame - and re-renders for real only
    # every _PAN_INTERVAL. Matplotlib's own axes pan re-rendered the whole
    # scene on every motion event instead: about a second a frame with a raster
    # basemap and a few vector layers.
    #
    # The shift is geometrically exact: measured against a re-render of the
    # shifted view it is bit-identical wherever the content is drawn at 1:1
    # scale. Where the content is resampled - a downscaled basemap, an
    # anti-aliased stroke - a re-render samples the source at a different
    # sub-pixel phase, so a shifted frame is the same content in the same
    # place but not the same bytes. That, and the strip newly exposed at the
    # leading edge, is what the throttled render settles; the release always
    # ends on one, so what the user stops on is a full render either way.

    def _pinned_overlays(self) -> list:
        """The artists anchored to the axes rather than to the map.

        The scale bar, compass and legend sit at a corner in axes coordinates,
        so they must not slide with a shifted bitmap. They are held out of the
        cached background and re-drawn over each shift instead."""
        overlays = [*self._artists.get("scale_bar", []),
                    *self._artists.get("compass", [])]
        legend = self.ax.get_legend()
        if legend is not None:
            overlays.append(legend)
        return overlays

    def _pan_press(self, event) -> None:
        canvas = self.fig.canvas
        if not hasattr(canvas, "copy_from_bbox"):
            return  # a canvas that cannot cache pixels: no blitting to do
        overlays = self._pinned_overlays()
        for artist in overlays:
            artist.set_animated(True)
        # Drawn once with the overlays held out, so the cached bitmap is the
        # map alone.
        canvas.draw()
        self._pan_drag = {"x": event.x, "y": event.y,
                          "last": (event.x, event.y), "overlays": overlays,
                          "background": canvas.copy_from_bbox(self.ax.bbox),
                          "pending": None, "applied_at": None}

    def _drag_map(self, event) -> None:
        drag = self._pan_drag
        if event.x is None or event.y is None:
            return
        dx, dy = event.x - drag["x"], event.y - drag["y"]
        self._blit_pan(dx, dy)
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        bbox = self.ax.bbox
        # The map follows the cursor, so the view moves the opposite way.
        drag["pending"] = (-(x1 - x0) / bbox.width * dx,
                           -(y1 - y0) / bbox.height * dy)
        drag["last"] = (event.x, event.y)
        last = drag["applied_at"]
        if last is None or time.monotonic() - last >= _PAN_INTERVAL:
            self._apply_pan()

    def _blit_pan(self, dx: float, dy: float) -> None:
        """Shift the cached map bitmap by *dx, dy* pixels and put the pinned
        overlays back on top.

        *dy* arrives in event coordinates, which count upwards, while the
        region's rows count down from the top; hence the negated y.
        """
        drag = self._pan_drag
        canvas = self.fig.canvas
        bbox = self.ax.bbox
        canvas.restore_region(drag["background"], bbox=bbox,
                              xy=(bbox.x0 + dx, bbox.y0 - dy))
        for artist in drag["overlays"]:
            self.ax.draw_artist(artist)
        canvas.blit(bbox)

    def _apply_pan(self) -> None:
        """Move the view to the drag's latest position and render for real.

        Re-caches the bitmap, so the shifts that follow move the new pixels,
        and re-bases the drag on the position just applied."""
        drag = self._pan_drag
        if drag["pending"] is None:
            return
        dx, dy = drag["pending"]
        drag["pending"] = None
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        with self._one_view_change():
            self.ax.set_xlim(x0 + dx, x1 + dx)
            self.ax.set_ylim(y0 + dy, y1 + dy)
        canvas = self.fig.canvas
        # Drawn now rather than deferred: the fresh pixels are needed
        # immediately, as the next motion event will shift them.
        canvas.draw()
        drag["background"] = canvas.copy_from_bbox(self.ax.bbox)
        drag["x"], drag["y"] = drag["last"]
        # Timed from the end of the render, so the interval is breathing room
        # between renders rather than a deadline they compete with.
        drag["applied_at"] = time.monotonic()

    def _pan_release(self) -> None:
        drag = self._pan_drag
        self._apply_pan()
        self._pan_drag = None
        for artist in drag["overlays"]:
            artist.set_animated(False)
        self.redraw()

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

    def _scale_bar_hit(self, event) -> bool:
        """Whether the press landed on the scale bar's artists."""
        if event.x is None or event.y is None:
            return False
        for artist in self._artists.get("scale_bar", []):
            try:
                if artist.get_window_extent().contains(event.x, event.y):
                    return True
            except Exception:  # noqa: BLE001 - a hit test must never crash
                continue
        return False

    def _scale_bar_press(self, event) -> bool:
        """Start dragging the scale bar, or right-click it back to its corner.

        Returns True when the press was consumed, so the caller stops looking
        for something else under the cursor.
        """
        if not self._scale_bar.draggable or not self._scale_bar_hit(event):
            return False
        if event.button == 3:  # right-click: back to the chosen corner
            self._scale_bar.anchor_x = None
            self._scale_bar.anchor_y = None
            self._apply_scale_bar()
            self.redraw()
            return True
        if event.button == 1:
            x, y = (self._scale_bar.anchor
                    or corner_anchor(self._scale_bar.position))
            cx, cy = self.ax.transAxes.inverted().transform((event.x, event.y))
            self._scale_bar_drag = {"grab": (x - cx, y - cy)}
        return True

    def _drag_scale_bar(self, event) -> None:
        if event.x is None or event.y is None:
            return
        cx, cy = self.ax.transAxes.inverted().transform((event.x, event.y))
        gx, gy = self._scale_bar_drag["grab"]
        # Keep the bar on the map; its own width is added inwards from here.
        self._scale_bar.anchor_x = float(np.clip(cx + gx, 0.01, 0.99))
        self._scale_bar.anchor_y = float(np.clip(cy + gy, 0.01, 0.97))
        self._apply_scale_bar()
        self.redraw()

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
        if self._globe_drag is not None:
            self._spin_globe(event)
            return
        if self._pan_drag is not None:
            self._drag_map(event)
            return
        if self._scale_bar_drag is not None:
            self._drag_scale_bar(event)
            return
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
        dx, dy = self._clamp_label_offset(raw_dx, raw_dy)
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
        if self._globe_drag is not None:
            if self._globe_drag["pending"] is not None:
                self._apply_spin()
            dragged = self._globe_drag["applied_at"] is not None
            self._globe_drag = None
            if dragged and self._basemap != "simple":
                # The drag drew a coarse preview; finish at full resolution.
                for artist in self._artists.pop(f"raster_{self._basemap}",
                                                []):
                    artist.remove()
                self.set_basemap(self._basemap)
                self.redraw()
            return
        if self._pan_drag is not None:
            self._pan_release()
            return
        if self._scale_bar_drag is not None:
            self._scale_bar_drag = None
            return
        if self._legend_drag is not None:
            self._legend_drag = None
            return
        if self._label_drag is None:
            return
        text = self._label_drag["text"]
        self._label_drag = None
        tx, ty = text.get_position()
        bx, by = text._pym_base
        dx, dy = self._clamp_label_offset(tx - bx, ty - by)
        self._label_offsets[text._pym_key] = (dx, dy)
