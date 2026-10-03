"""Pure geometry for framing the map: the axes box for an orientation, the
x-limits that fit a view to it, the cropped size of an export, and the
degree labels on the graticule ticks. No renderer state, so each one is
tested on its own."""

from __future__ import annotations

import numpy as np


def oriented_axes_rect(margins: tuple[float, float, float, float],
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


def refit_xlim(box_ratio: float, xlim: tuple[float, float],
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


def clamp_zoom_factor(factor: float, width: float,
                      world_width: float) -> float:
    """*factor* limited so that a view *width* wide, zoomed by it, spans
    no more than one and a half *world_width* and no less than a millionth
    of it (>1 zooms in)."""
    factor = max(factor, width / (world_width * 1.5))
    return min(factor, width / (world_width * 1e-6))


# The printed area of a journal page: Zootaxa and Phytotaxa set figures
# within 17 x 25 cm. A map saved at a print width never runs taller.
PAGE_HEIGHT_CM = 25.0


def export_geometry(pos_bounds: tuple[float, float, float, float],
                    fig_w: float, fig_h: float,
                    margins: tuple[float, float, float, float],
                    width_in: float | None = None,
                    max_height_in: float | None = None
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
    full-canvas (landscape) map comes back at the figure size unchanged.

    With *width_in* the map box is scaled, keeping its shape, so the whole
    image is that wide - and no taller than *max_height_in*, which wins when
    both cannot hold. Text and symbols are sized in points, so they then
    print at their stated size whatever the window size was."""
    _x0, _y0, pw, ph = pos_bounds
    box_w, box_h = pw * fig_w, ph * fig_h
    left, bottom, right, top = margins
    left_gutter, right_gutter = left * fig_w, (1.0 - right) * fig_w
    bottom_gutter, top_gutter = bottom * fig_h, (1.0 - top) * fig_h
    if width_in is not None:
        scale = max(width_in - left_gutter - right_gutter, 1e-3) / box_w
        if max_height_in is not None:
            room = max(max_height_in - bottom_gutter - top_gutter, 1e-3)
            scale = min(scale, room / box_h)
        box_w, box_h = box_w * scale, box_h * scale
    exp_w = box_w + left_gutter + right_gutter
    exp_h = box_h + bottom_gutter + top_gutter
    rect = (left_gutter / exp_w, bottom_gutter / exp_h,
            box_w / exp_w, box_h / exp_h)
    return (exp_w, exp_h), rect


def lon_span(lons) -> tuple[float, float]:
    """The shortest run of longitude covering every value, as (west, east).

    Points on both sides of the antimeridian (Fiji at 178E, Samoa at 172W)
    span 178 to 188 - east given past 180 - rather than 172W to 178E, the
    whole world the other way round."""
    values = np.unique(np.asarray(lons, dtype=float))
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return float(values[0]), float(values[-1])
    gaps = np.diff(values)
    widest = int(np.argmax(gaps))
    if gaps[widest] <= 360.0 - (values[-1] - values[0]):
        return float(values[0]), float(values[-1])
    return float(values[widest + 1]), float(values[widest] + 360.0)


def _norm_lon(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def format_lon(value: float, _pos=None) -> str:
    value = _norm_lon(value)
    if value in (0, 180, -180):
        return f"{abs(value):g}\N{DEGREE SIGN}"
    return f"{abs(value):g}\N{DEGREE SIGN}{'W' if value < 0 else 'E'}"


def format_lat(value: float, _pos=None) -> str:
    if value == 0:
        return "0\N{DEGREE SIGN}"
    return f"{abs(value):g}\N{DEGREE SIGN}{'S' if value < 0 else 'N'}"
