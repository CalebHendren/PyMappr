"""Blitting: showing the map from pixels already rendered, rather than
re-rendering it, while it moves under the cursor.

A full render with a raster basemap and a few vector layers takes about half a
second, so a gesture that moves the map works from a bitmap of it and renders
for real only when the gesture pauses or ends.

The bitmap comes free with every screen render. An artist that draws nothing
sits in the axes' draw order between the map content and the overlays pinned
to the axes (scale bar, compass, legend), and copies the pixels drawn so far
when its turn comes. So the snapshot is the map alone - the overlays are never
in it, and no extra render with them held out is needed to get it.
"""

from __future__ import annotations

import math
import weakref

import numpy as np
from matplotlib.artist import Artist
from PIL import Image

from pymappr.renderer.tables import Z_SNAPSHOT


class _SnapshotArtist(Artist):
    """Copies the axes' pixels as drawn so far; draws nothing itself."""

    def __init__(self):
        super().__init__()
        self.set_zorder(Z_SNAPSHOT)
        # No extent of its own, so it never widens a tight bounding box.
        self.set_in_layout(False)
        self.region = None
        self.bounds = None
        self._source = None

    def draw(self, renderer) -> None:
        copy_from_bbox = getattr(renderer, "copy_from_bbox", None)
        if copy_from_bbox is None:
            # PDF, SVG and PS renderers have no pixels to copy, so an export
            # through them is untouched.
            return
        bbox = self.axes.bbox
        self.region = copy_from_bbox(bbox)
        self.bounds = bbox.bounds
        # Held weakly: a renderer thrown away and replaced can be given the
        # same id(), which would pass a stale snapshot off as current.
        self._source = weakref.ref(renderer)
        self.stale = False

    def source(self):
        """The renderer the snapshot was copied from, if it still exists."""
        return self._source() if self._source is not None else None


class BlitMixin:
    """The map snapshot, and compositing the pinned overlays over it."""

    def _init_blit(self) -> None:
        self._snapshot = _SnapshotArtist()
        self.ax.add_artist(self._snapshot)

    def _map_background(self):
        """The map as last rendered on screen, without the pinned overlays,
        or None when there is no such snapshot to work from.

        Every render leaves a snapshot behind, including a raster export at
        another dpi, whose snapshot is the wrong size for the screen. Only one
        taken by the canvas's own renderer, with the axes where they are now,
        is the screen's. On None the caller renders once to take a fresh one.
        """
        snap = self._snapshot
        if snap.region is None:
            return None
        get_renderer = getattr(self.fig.canvas, "get_renderer", None)
        if get_renderer is None or snap.source() is not get_renderer():
            return None
        if snap.bounds != self.ax.bbox.bounds:
            return None
        return snap.region

    def _frame_inset(self) -> int:
        """Pixels at the edge of the snapshot covered by the axes frame.

        The frame line straddles the axes edge, so it is in the snapshot. A
        snapshot moved or scaled would carry a copy of it into the map; this
        much of each edge is left out, and the frame redrawn in place."""
        widths = [spine.get_linewidth() for spine in self.ax.spines.values()
                  if spine.get_visible()]
        if not widths:
            return 0
        # Half the line lies inside the box, plus a pixel of anti-aliasing.
        return math.ceil(max(widths) * self.fig.dpi / 72.0 / 2.0) + 1

    def _pinned_overlays(self) -> list:
        """The artists anchored to the axes rather than to the map.

        The scale bar, compass and legend sit at a corner in axes coordinates,
        so they must not move with the map. Collected afresh on every call:
        a view change replaces the scale bar's artists (its length follows the
        view)."""
        overlays = [*self._artists.get("scale_bar", []),
                    *self._artists.get("compass", [])]
        legend = self.ax.get_legend()
        if legend is not None:
            overlays.append(legend)
        return overlays

    def _composite(self, bbox) -> None:
        """Draw what the snapshot leaves out over the map restored on the
        canvas - the axes frame, the pinned overlays and the legend
        underlines - and put *bbox* on screen."""
        canvas = self.fig.canvas
        # In the order a full render draws them: frame, overlays, then the
        # underlines, which a render adds from its draw_event afterwards.
        for spine in self.ax.spines.values():
            self.ax.draw_artist(spine)
        for artist in self._pinned_overlays():
            self.ax.draw_artist(artist)
        self._draw_legend_underlines(canvas.get_renderer())
        canvas.blit(bbox)

    def _blit_scaled(self, background, scale: float,
                     shift: tuple[float, float]) -> None:
        """Show the map snapshot scaled by *scale* and moved by *shift*, so
        that the display point x lands on ``scale * x + shift``, with the
        pinned overlays at their corners on top.

        Display coordinates count upwards; the region's are the canvas
        buffer's, whose rows count down from the top, and the image handed
        to the renderer is drawn bottom row first."""
        renderer = self.fig.canvas.get_renderer()
        left, top, right, bottom = background.get_extents()
        height = renderer.height
        inset = self._frame_inset()
        # The snapshot less the frame line at its edges, in display
        # coordinates; _composite redraws the frame in place.
        sx0, sx1 = left + inset, right - inset
        sy0, sy1 = height - bottom + inset, height - top - inset
        tx, ty = shift
        # Where it lands, cut to that same box: zoomed in, the part of the
        # snapshot still in view fills it; zoomed out, the shrunken snapshot
        # sits inside it.
        x0 = max(round(scale * sx0 + tx), sx0)
        x1 = min(round(scale * sx1 + tx), sx1)
        y0 = max(round(scale * sy0 + ty), sy0)
        y1 = min(round(scale * sy1 + ty), sy1)
        # What a zoom out uncovers shows the axes background.
        self.ax.draw_artist(self.ax.patch)
        if x0 < x1 and y0 < y1:
            image = Image.fromarray(np.asarray(background))
            # The part of the snapshot that lands there, in its own pixels
            # (rows down from its top edge). Pillow resamples a fractional
            # box exactly, so the preview does not jitter between notches.
            box = ((x0 - tx) / scale - left,
                   (height - top) - (y1 - ty) / scale,
                   (x1 - tx) / scale - left,
                   (height - top) - (y0 - ty) / scale)
            box = tuple(min(max(v, 0.0), limit) for v, limit in
                        zip(box, (image.width, image.height) * 2))
            scaled = image.resize((x1 - x0, y1 - y0), Image.BILINEAR, box=box)
            gc = renderer.new_gc()
            renderer.draw_image(gc, x0, y0, np.asarray(scaled)[::-1])
            gc.restore()
        self._composite(self.ax.bbox)

    def _single_shot_timer(self, interval_ms: int, callback):
        """A GUI timer that runs *callback* once, *interval_ms* after it is
        (re)started, or None on a canvas without timers.

        On Agg the timer never fires; the release still renders, so nothing
        is left unfinished without it."""
        new_timer = getattr(self.fig.canvas, "new_timer", None)
        if new_timer is None:
            return None
        timer = new_timer(interval=interval_ms)
        timer.single_shot = True
        timer.add_callback(callback)
        return timer
