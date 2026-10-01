"""The map's Tk canvas, which holds still while the window is resized.

Dragging a window edge makes Tk send a stream of <Configure> events.
matplotlib answers each one by resizing the figure, and the renderer
answers that by re-fitting the view, re-cropping the basemap and drawing
the whole map (about half a second), so the window lags far behind the
mouse. This canvas keeps the old picture centred while the size is still
changing and does the real resize once, 150 ms after the last event.
"""

from __future__ import annotations

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class DebouncedFigureCanvasTkAgg(FigureCanvasTkAgg):
    """A FigureCanvasTkAgg that resizes the figure once a drag settles."""

    RESIZE_DELAY_MS = 150

    def __init__(self, *args, **kwargs):
        # Set before the base class binds <Configure> to self.resize.
        self._resize_after_id = None
        self._has_sized = False
        super().__init__(*args, **kwargs)

    def resize(self, event):
        # These are matplotlib internals; if a release renames one, fall
        # back to its plain, immediate resize rather than breaking the map.
        if not (hasattr(self, "_resize_figure_for_canvas_size")
                and hasattr(self, "_tkcanvas_image_region")):
            super().resize(event)
            return

        width, height = event.width, event.height
        if not self._has_sized:
            # Startup and session restore size the map straight away.
            self._has_sized = True
            self._resize_figure_for_canvas_size(width, height)
            return

        # Keep the stale picture centred in the new window (on whole pixels,
        # as matplotlib centres it): cheap, and it stands in for the real
        # redraw until the drag settles.
        self._tkcanvas.coords(self._tkcanvas_image_region,
                              int(width / 2), int(height / 2))
        if self._resize_after_id is not None:
            self._tkcanvas.after_cancel(self._resize_after_id)
        self._resize_after_id = self._tkcanvas.after(
            self.RESIZE_DELAY_MS, self._apply_resize, width, height)

    def _apply_resize(self, width, height):
        self._resize_after_id = None
        if not self._tkcanvas.winfo_exists():
            return  # destroyed while the resize was waiting
        self._resize_figure_for_canvas_size(width, height)
