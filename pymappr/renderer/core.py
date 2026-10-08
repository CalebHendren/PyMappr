"""MapRenderer: the mixins put together, plus the start-up wiring."""

from __future__ import annotations

from pymappr.geo.layers import LayerStore
from pymappr.renderer.blit import BlitMixin
from pymappr.renderer.inset import InsetMixin
from pymappr.renderer.labels import LabelsMixin
from pymappr.renderer.layers import LayersMixin
from pymappr.renderer.mouse import MouseMixin
from pymappr.renderer.overlays import OverlaysMixin
from pymappr.renderer.points import PointsMixin
from pymappr.renderer.view import ViewMixin


class MapRenderer(ViewMixin, LayersMixin, OverlaysMixin, LabelsMixin,
                  PointsMixin, InsetMixin, MouseMixin, BlitMixin):
    """Draws the map onto a matplotlib figure and keeps it in step with the
    app's settings.

    Every mixin keeps its own state, set up by its ``_init_*`` method. They
    share the figure and axes (``fig``, ``ax``), the layer data (``store``),
    the current projection (``proj``), and ``_artists``, which holds every
    drawn piece of the scene by name so a projection change can rebuild it.
    """

    def __init__(self, figure, store: LayerStore):
        self._init_view(figure, store)
        self._init_layers()
        self._init_overlays()
        self._init_labels()
        self._init_points()
        self._init_inset()
        self._init_mouse()
        self._init_blit()

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
            # Underlining legend text is done at draw time: matplotlib Text
            # has no underline property, so a stroke is drawn under each
            # flagged label using the live renderer (fires on save too).
            self.fig.canvas.mpl_connect("draw_event", self._on_draw)
        self._sync_navigation()
