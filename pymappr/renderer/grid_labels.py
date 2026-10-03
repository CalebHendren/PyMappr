"""Degree labels on the graticule.

On the plain lon/lat map the grid lines are the axis ticks. On a projected
map (Lambert, Robinson, Mercator) they are curves, so the ticks go where
each meridian meets the bottom of the frame and each parallel the left.
Either way, labels that would run into their neighbours are thinned to
every second, third, ... line. Both are worked out at draw time, so they
follow zooming, panning and the size a map is saved at.
"""

from __future__ import annotations

import math

import numpy as np
from matplotlib.ticker import Formatter, Locator

from pymappr.renderer.geometry import format_lat, format_lon

# Every n-th grid line keeps its label, n from this list: with 5-degree
# lines that is 5, 10, 15, 20, 30, 45 ... degrees, all round numbers.
_STRIDES = (1, 2, 3, 4, 6, 9, 12, 18, 36)
# A label's footprint along its axis, in ems of the tick-label font: up to
# five characters ("175°W") across, one line up the side, plus a gap.
_WIDTH_EMS = 5 * 0.62 + 1.0
_HEIGHT_EMS = 1.2 + 0.6


def edge_crossings(xs: np.ndarray, ys: np.ndarray, edge: float,
                   along: str) -> list[float]:
    """Where a projected polyline crosses a frame edge.

    *along* "x" finds crossings of the horizontal line y = *edge* and
    returns their x; "y" finds crossings of x = *edge* and returns their y.
    Gaps (NaN) in the line are never bridged."""
    cut, other = (ys, xs) if along == "x" else (xs, ys)
    found = []
    d = cut - edge
    for i in range(len(d) - 1):
        a, b = d[i], d[i + 1]
        if not (np.isfinite(a) and np.isfinite(b)) or a * b > 0 or a == b:
            continue
        if not (np.isfinite(other[i]) and np.isfinite(other[i + 1])):
            continue
        t = a / (a - b)
        found.append(float(other[i] + t * (other[i + 1] - other[i])))
    return found


def edge_ticks(xs: np.ndarray, ys: np.ndarray, view, along: str
               ) -> list[float]:
    """Where a grid line meets the bottom (*along* "x") or left ("y") edge
    of *view* ``((x0, x1), (y0, y1))``, as tick positions on that axis.

    A line that stops short of the edge - a parallel ending at the rim of
    a Robinson world, a meridian at the southern limit of a Lambert region
    - is continued straight on from its end, and ticked where that meets
    the edge. A curved line (a conic parallel) heads off steeply and misses
    the edge or meets it far away; it goes unlabelled rather than labelled
    somewhere it is not."""
    (x0, x1), (y0, y1) = view
    if along == "x":
        ticks = [x for x in edge_crossings(xs, ys, y0, "x") if x0 <= x <= x1]
    else:
        ticks = [y for y in edge_crossings(xs, ys, x0, "y") if y0 <= y <= y1]
    if ticks:
        return ticks
    good = np.isfinite(xs) & np.isfinite(ys)
    if good.sum() < 4:
        return []
    xs, ys = xs[good], ys[good]
    end = int(np.argmin(ys if along == "x" else xs))
    if 0 < end < len(xs) - 1:
        return []  # the line turns back before the edge: no end to extend
    inner = 3 if end == 0 else len(xs) - 4
    x, y = float(xs[end]), float(ys[end])
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return []
    dx, dy = x - float(xs[inner]), y - float(ys[inner])
    if along == "x":
        if dy >= 0:
            return []
        t = (y0 - y) / dy
        tick, reach = x + t * dx, (x1 - x0)
        ok = x0 <= tick <= x1
    else:
        if dx >= 0:
            return []
        t = (x0 - x) / dx
        tick, reach = y + t * dy, (y1 - y0)
        ok = y0 <= tick <= y1
    # Off by more than a few percent of the frame: too far from the line
    # to read as its label.
    drift = abs(t * (dx if along == "x" else dy))
    return [tick] if ok and drift <= 0.03 * reach else []


def label_stride(spacing_pts: float, label_pts: float) -> int:
    """How many grid lines apart labels must be so that labels
    *label_pts* long, on lines *spacing_pts* apart, do not touch."""
    if spacing_pts <= 0:
        return _STRIDES[-1]
    need = label_pts / spacing_pts
    return next((s for s in _STRIDES if s >= need), _STRIDES[-1])


class GridLocator(Locator):
    """Ticks where the projected graticule meets the frame: meridians on
    the x axis (bottom edge), parallels on the y axis (left edge)."""

    def __init__(self, renderer, which: str):
        self.renderer = renderer
        self.which = which
        self.degrees: dict[float, float] = {}

    def __call__(self):
        r = self.renderer
        step = r._graticule
        proj = r.proj
        if not step:
            return []
        view = (tuple(sorted(r.ax.get_xlim())),
                tuple(sorted(r.ax.get_ylim())))
        found: dict[float, float] = {}
        if self.which == "x":
            lats = np.linspace(proj.min_lat, proj.max_lat, 361)
            for lon in np.arange(-180.0, 180.0, step):
                xs, ys = proj.forward(np.full_like(lats, lon), lats,
                                      clamp=False)
                for off in r._offsets():
                    for x in edge_ticks(xs + off, ys, view, "x"):
                        found[x] = float(lon)
        else:
            span = proj.lon_halfspan
            lons = proj.lon_0 + np.linspace(-span, span, 721)
            first = math.ceil(proj.min_lat / step) * step
            for lat in np.arange(first, proj.max_lat + step / 2, step):
                if abs(lat) > 90:
                    continue
                xs, ys = proj.forward(lons, np.full_like(lons, lat),
                                      clamp=False)
                for off in r._offsets():
                    for y in edge_ticks(xs + off, ys, view, "y"):
                        found[y] = float(lat)
        self.degrees = found
        return sorted(found)


class GridLabelFormatter(Formatter):
    """Degree labels, thinned so neighbours never run together. On the
    plain lon/lat map a tick's value is its degree; on a projected map the
    :class:`GridLocator` that placed it says which degree it is."""

    def __init__(self, renderer, which: str, locator: GridLocator | None):
        self.renderer = renderer
        self.which = which
        self.locator = locator

    def _degree(self, value: float) -> float:
        if self.locator is None:
            return float(value)
        return self.locator.degrees.get(value, float("nan"))

    def _text(self, degree: float) -> str:
        if not np.isfinite(degree):
            return ""
        return format_lon(degree) if self.which == "x" else format_lat(degree)

    def __call__(self, value, pos=None):
        return self._text(self._degree(value))

    def format_ticks(self, values):
        values = list(values)
        degrees = [self._degree(v) for v in values]
        step = self.renderer._graticule
        stride = self._stride(values)
        labels = []
        for degree in degrees:
            keep = (step and np.isfinite(degree)
                    and round(degree / step) % stride == 0)
            labels.append(self._text(degree) if keep else "")
        return labels

    def _stride(self, values: list[float]) -> int:
        """Labels a whole number of grid lines apart, enough that the
        closest pair on screen (or in the saved file) does not touch."""
        if len(values) < 2:
            return 1
        ax = self.renderer.ax
        if self.which == "x":
            px = ax.transData.transform(
                np.column_stack([values, np.zeros(len(values))]))[:, 0]
        else:
            px = ax.transData.transform(
                np.column_stack([np.zeros(len(values)), values]))[:, 1]
        gaps = np.diff(np.sort(px))
        gaps = gaps[gaps > 0]
        if not len(gaps):
            return 1
        points_per_px = 72.0 / ax.figure.dpi
        ticks = (ax.xaxis if self.which == "x" else ax.yaxis).get_major_ticks()
        size = ticks[0].label1.get_fontsize() if ticks else 7.0
        ems = _WIDTH_EMS if self.which == "x" else _HEIGHT_EMS
        return label_stride(float(gaps.min()) * points_per_px, ems * size)
