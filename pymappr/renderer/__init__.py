"""The matplotlib map: everything PyMappr draws, and the mouse handling on it.

``MapRenderer`` is put together from one mixin per concern:

- ``view``: extent, orientation, zoom, projection, graticule and export
- ``layers``: basemaps and the Natural Earth layers
- ``overlays``: the north arrow and the scale bar
- ``labels``: place-name labels
- ``points``: the user's points and the legend
- ``mouse``: spinning the globe and dragging the legend, labels and scale bar

``tables`` holds the layer styles and draw order (shared with the code
export), and ``geometry`` the pure framing maths.
"""

from pymappr.renderer.core import MapRenderer

__all__ = ["MapRenderer"]
