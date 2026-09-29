"""The north arrow and the scale bar: small annotations pinned to a
corner of the map. The options and the maths of a bar's length live in
pymappr.decorations; this draws them."""

from __future__ import annotations

import numpy as np
from matplotlib.patches import Polygon, Rectangle

from pymappr.decorations import (CompassOptions, ScaleBarOptions,
                                 corner_anchor, format_length,
                                 nice_length, unit_metres)
from pymappr.renderer.tables import LABEL_HALO, Z_COMPASS, Z_SCALE_BAR


class OverlaysMixin:
    """The north arrow and the scale bar."""

    def _init_overlays(self) -> None:
        self._compass = CompassOptions()
        self._scale_bar = ScaleBarOptions()
        self._scale_bar_note: str | None = None

    def set_compass(self, options: CompassOptions) -> None:
        """Set the north arrow's options."""
        self._compass = options
        self._apply_compass()

    def _apply_compass(self) -> None:
        for artist in self._artists.pop("compass", []):
            artist.remove()
        opts = self._compass
        if not opts.show:
            return
        x, y = corner_anchor(opts.position, pad=0.025)
        size = max(float(opts.size), 0.1)
        # The arrow runs downwards from the anchor when the compass sits at
        # the top, and upwards when it sits at the bottom, so it never points
        # out of the map.
        reach = 0.07 * size
        tail_y = y - reach if y > 0.5 else y + reach
        if opts.style == "triangle":
            artists = self._compass_triangle(x, y, tail_y, size, opts.color)
        else:
            artists = [self.ax.annotate(
                "N", xy=(x, y), xytext=(x, tail_y),
                xycoords="axes fraction", textcoords="axes fraction",
                ha="center", va="center", fontsize=11 * size,
                fontweight="bold", color=opts.color,
                path_effects=LABEL_HALO, zorder=Z_COMPASS,
                annotation_clip=False,
                arrowprops=dict(
                    arrowstyle="-|>,head_width=0.28,head_length=0.55",
                    color=opts.color, linewidth=1.4 * size,
                    shrinkA=6 * size, shrinkB=0))]
        self._artists["compass"] = artists

    def _compass_triangle(self, x, y, tail_y, size, color) -> list:
        """A filled triangle pointing north, with an "N" beside its base."""
        half = 0.016 * size
        up = y > tail_y
        tip = y
        base = tail_y + (0.02 * size if up else -0.02 * size)
        triangle = Polygon(
            [(x, tip), (x - half, base), (x + half, base)],
            closed=True, transform=self.ax.transAxes, facecolor=color,
            edgecolor="white", linewidth=0.8 * size, zorder=Z_COMPASS,
            clip_on=False)
        self.ax.add_patch(triangle)
        label = self.ax.text(
            x, tail_y, "N", transform=self.ax.transAxes,
            ha="center", va="center" if up else "center",
            fontsize=10 * size, fontweight="bold", color=color,
            path_effects=LABEL_HALO, zorder=Z_COMPASS, clip_on=False)
        return [triangle, label]

    def set_scale_bar(self, options: ScaleBarOptions) -> None:
        """Set the scale bar's options and redraw it."""
        self._scale_bar = options
        self._apply_scale_bar()

    def scale_bar_anchor(self) -> tuple[float, float] | None:
        return self._scale_bar.anchor

    def _axes_to_data(self, fx: float, fy: float) -> tuple[float, float]:
        """An axes-fraction point as map (data) coordinates."""
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        return x0 + (x1 - x0) * fx, y0 + (y1 - y0) * fy

    def _span_metres(self, fx0: float, fx1: float, fy: float) -> float:
        """Ground metres between two axes-fraction x positions on row *fy*.

        NaN where the row is off the map - outside a Robinson ellipse, or off
        the globe's disk - which callers treat as "not measurable here".
        """
        ax0, ay = self._axes_to_data(fx0, fy)
        ax1, _ = self._axes_to_data(fx1, fy)
        return self.proj.ground_distance(ax0, ay, ax1, ay)

    def _scale_reference_row(self, fy: float) -> float:
        """An axes row where the map scale can actually be measured.

        The bar's own row is used whenever it works, because a scale bar
        should describe the scale where it stands. On Robinson, Mollweide and
        the globe the corners of the axes lie outside the map altogether, so
        the search then steps towards the middle of the view until it finds a
        row that projects.
        """
        candidates = [fy] + [fy + (0.5 - fy) * step
                             for step in (0.25, 0.5, 0.75, 1.0)]
        for row in candidates:
            if np.isfinite(self._span_metres(0.45, 0.55, row)):
                return row
        return 0.5

    def _estimate_scale(self, fx: float, fy: float) -> float:
        """Ground metres spanned by one unit of axes x-fraction near *fx*.

        Only a first guess: map scale is not constant across a wide bar, so
        :meth:`_apply_scale_bar` refines the width against the bar's real
        endpoints afterwards.
        """
        left = float(np.clip(fx - 0.05, 0.0, 0.9))
        metres = self._span_metres(left, left + 0.1, fy)
        if not np.isfinite(metres) or metres <= 0:
            metres = self._span_metres(0.45, 0.55, fy)
        if not np.isfinite(metres) or metres <= 0:
            return float("nan")
        return metres / 0.1

    _BAR_HEIGHT = 0.011
    _BAR_GAP = 0.005
    _LABEL_GAP = 0.012
    # Vertical room one label row needs, so a stack of bars can be lifted
    # clear of the frame instead of running off it.
    _LABEL_ROOM = 0.030

    def scale_bar_note(self) -> str | None:
        """Why the scale bar is not on the map, or None when it is fine.

        The app shows this in the status line: a bar that silently fails to
        appear is worse than one that explains itself.
        """
        return self._scale_bar_note

    def _fit_bar_width(self, metres: float, x: float, row: float,
                       right_anchored: bool) -> float | None:
        """The axes-fraction width a bar of *metres* needs, or None when no
        honest bar of that length fits.

        The first guess comes from a short local sample, but a scale bar is
        long and the map scale varies across it, so the width is refined
        against the bar's own endpoints until the drawing really is the
        length its label claims.
        """
        per_fraction = self._estimate_scale(x, row)
        if not np.isfinite(per_fraction) or per_fraction <= 0:
            return None
        width = metres / per_fraction
        for _ in range(6):
            if not np.isfinite(width) or width <= 0 or width > 0.95:
                return None
            x0 = x - width if right_anchored else x
            actual = self._span_metres(x0, x0 + width, row)
            if not np.isfinite(actual) or actual <= 0:
                # The bar's own span is off the map - a corner of an
                # orthographic globe, or outside a Robinson ellipse. Refine
                # against the same width centred on the reference row, so the
                # bar still ends up the length its label claims for that row.
                actual = self._span_metres(0.5 - width / 2, 0.5 + width / 2,
                                           row)
            if not np.isfinite(actual) or actual <= 0:
                break  # nothing measurable: keep the estimate
            adjust = metres / actual
            if abs(adjust - 1.0) < 0.001:
                break
            width *= adjust
        if not np.isfinite(width) or width <= 0 or width > 0.95:
            return None
        return width

    def _apply_scale_bar(self) -> None:
        for artist in self._artists.pop("scale_bar", []):
            artist.remove()
        self._scale_bar_note = None
        opts = self._scale_bar
        if not opts.show:
            return
        units = opts.units_shown()
        dragged = opts.anchor is not None
        x, y = opts.anchor or corner_anchor(opts.position)
        right_anchored = x > 0.5 and not dragged
        top_anchored = y > 0.5 and not dragged

        height, gap = self._BAR_HEIGHT, self._BAR_GAP
        stack = len(units) * height + (len(units) - 1) * gap
        # A second unit is labelled underneath, so lift the stack clear of
        # the frame; anchored at the top, the stack hangs below the anchor.
        base_y = y - stack if top_anchored else y
        if len(units) > 1 and not top_anchored and not dragged:
            base_y += self._LABEL_ROOM
        # Each unit gets its own round length, so "3000 km" is not paired
        # with an unreadable "1864 mi" - two bars, each honest in its unit,
        # and each measured on the row it is actually drawn on.
        bars = []
        last = len(units) - 1
        for i, unit in enumerate(units):
            y0 = base_y + (last - i) * (height + gap)
            row = self._scale_reference_row(y0 + height / 2)
            if i == 0 and opts.length_mode == "fixed" and opts.fixed_length:
                metres = float(opts.fixed_length) * unit_metres(opts.units)
            else:
                estimate = self._estimate_scale(x, row)
                if not np.isfinite(estimate) or estimate <= 0:
                    self._scale_bar_note = (
                        "Scale bar: the map scale cannot be measured at "
                        "this view.")
                    return
                metres = nice_length(estimate * opts.width, unit)
            if metres <= 0:
                return
            width = self._fit_bar_width(metres, x, row, right_anchored)
            if width is None:
                self._scale_bar_note = (
                    "Scale bar: scale varies too much across this view to "
                    "draw an accurate bar - zoom in, or move the bar away "
                    "from the poles.")
                return
            bars.append((unit, metres, width))

        self._artists["scale_bar"] = self._draw_scale_bar(
            bars, x, base_y, right_anchored, opts)

    def _draw_scale_bar(self, bars, x, base_y, right_anchored, opts) -> list:
        """Draw the bar(s) and their labels in axes-fraction coordinates, so
        the decoration survives the export crop and every projection.

        Bars stack with the first unit on top; its label sits above the
        stack, and a second unit's label sits below it.
        """
        artists = []
        height, gap = self._BAR_HEIGHT, self._BAR_GAP
        last = len(bars) - 1
        for i, (unit, metres, width) in enumerate(bars):
            # The first unit draws on top of the stack.
            y0 = base_y + (last - i) * (height + gap)
            x0 = x - width if right_anchored else x
            segments = (max(int(opts.segments), 1)
                        if opts.style == "segmented" else 1)
            for seg in range(segments):
                patch = Rectangle(
                    (x0 + width * seg / segments, y0), width / segments,
                    height, transform=self.ax.transAxes,
                    facecolor=opts.color if seg % 2 == 0 else "white",
                    edgecolor=opts.color, linewidth=0.8,
                    zorder=Z_SCALE_BAR, clip_on=False)
                self.ax.add_patch(patch)
                artists.append(patch)
            above = i == 0
            artists.append(self.ax.text(
                x0 + width / 2,
                y0 + height + self._LABEL_GAP if above
                else y0 - self._LABEL_GAP,
                format_length(metres, unit),
                transform=self.ax.transAxes, ha="center",
                va="bottom" if above else "top",
                fontsize=opts.fontsize, color=opts.color,
                path_effects=LABEL_HALO, zorder=Z_SCALE_BAR, clip_on=False))
        return artists
