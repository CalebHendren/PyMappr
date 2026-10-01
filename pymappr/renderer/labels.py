"""Place names: which labels fit the view, most important first,
without overlapping each other."""

from __future__ import annotations

import numpy as np

from pymappr.geo.layers import LAYER_SPECS, BoundedCache
from pymappr.renderer.tables import (LABEL_HALO, LABEL_STYLES, POINT_LAYERS,
                                     Z_LABELS)


class LabelsMixin:
    """Place-name labels."""

    def _init_labels(self) -> None:
        self._label_visible: set[str] = set()
        self._label_texts: dict[str, list] = {}
        self._label_xy_cache = BoundedCache(maxsize=32)
        # Manual label placement: (layer key, label text) -> (dx, dy) offset
        # in map coordinates, set by dragging a label with the mouse.
        self._label_offsets: dict[tuple[str, str], tuple[float, float]] = {}

    def set_labels(self, key: str, visible: bool) -> None:
        """Toggle labels: countries, states, counties, cities, airports,
        ports, lakes, rivers, regions, timezones."""
        if visible:
            self._label_visible.add(key)
        else:
            self._label_visible.discard(key)
        self._refresh_labels()

    def _label_xy(self, source: str) -> tuple[np.ndarray, np.ndarray]:
        cache_key = (source, self.proj.key)
        if cache_key not in self._label_xy_cache:
            points = self.store.label_points(source)
            xs, ys = self.proj.forward(points["x"].to_numpy(),
                                       points["y"].to_numpy())
            self._label_xy_cache[cache_key] = (np.asarray(xs, float),
                                               np.asarray(ys, float))
        return self._label_xy_cache[cache_key]

    def _refresh_labels(self) -> None:
        """Place the labels for the current view.

        This runs on every pan and zoom step, so a label that stays in view
        keeps its Text artist (moved and resized); only labels coming into
        view are created, and only those leaving it are removed.
        """
        zoom = self._zoom_level()
        x0, x1 = sorted(self.ax.get_xlim())
        y0, y1 = sorted(self.ax.get_ylim())
        # Slightly smaller fonts when zoomed far out, so a fully labelled
        # world map stays readable.
        font_scale = float(np.clip(0.78 + 0.06 * zoom, 0.78, 1.15))
        # Pixel-space rectangles of labels placed so far (all layers
        # together): a new label that would overlap one is skipped. Labels
        # the user has dragged are always drawn.
        placed_rects: list[tuple[float, float, float, float]] = []
        to_pixels = self.ax.transData
        px_per_pt = self.fig.dpi / 72.0
        for key in LABEL_STYLES:
            previous = {text._pym_id: text
                        for text in self._label_texts.get(key, [])}
            texts = self._label_texts[key] = []
            source, font, min_zoom, feature_bias = LABEL_STYLES[key]
            if key in self._label_visible and zoom >= min_zoom:
                if key == "cities" and self._capitals_only:
                    source = "capitals"
                font = dict(font)
                font["fontsize"] = font["fontsize"] * font_scale
                va = font.pop("va", "bottom" if key in POINT_LAYERS
                              else "center")  # above a marker dot
                for ident, name, px, py in self._label_candidates(
                        key, source, feature_bias, zoom, (x0, x1, y0, y1)):
                    offset = self._label_offsets.get((key, name))
                    lx = px + (offset[0] if offset else 0.0)
                    ly = py + (offset[1] if offset else 0.0)
                    rect = self._estimate_rect(to_pixels, lx, ly, name,
                                               font["fontsize"] * px_per_pt)
                    if (offset is None
                            and self._overlaps_any(rect, placed_rects)):
                        continue
                    placed_rects.append(rect)
                    text = previous.pop(ident, None)
                    if text is None:
                        text = self.ax.text(
                            lx, ly, name, ha="center", va=va,
                            zorder=Z_LABELS, clip_on=True,
                            path_effects=LABEL_HALO, picker=True, **font)
                        text._pym_id = ident
                        text._pym_key = (key, name)
                    else:
                        text.set_position((lx, ly))
                        text.set_fontsize(font["fontsize"])
                    text._pym_base = (px, py)
                    texts.append(text)
            for text in previous.values():
                text.remove()

    def _label_candidates(self, key, source, feature_bias, zoom, view):
        """(identity, text, x, y) for the labels of *source* in view, most
        important first and at most the layer's cap. The wrapped world
        copies count, so labels follow the view across the antimeridian."""
        x0, x1, y0, y1 = view
        points = self.store.label_points(source)
        xs, ys = self._label_xy(source)
        ranks = points["min_label"].to_numpy()
        names = points["text"].to_numpy()
        finite = np.isfinite(xs) & np.isfinite(ys)
        rows, shifts = [], []
        for off in self._offsets():
            inside = (finite & (xs + off >= x0) & (xs + off <= x1)
                      & (ys >= y0) & (ys <= y1))
            if feature_bias is not None:
                # Per-feature zoom culling: a place is labelled only once
                # Natural Earth's curated min_label rank allows it, so e.g.
                # only the biggest cities are named when zoomed out.
                inside &= ranks <= zoom + feature_bias
            found = np.nonzero(inside)[0]
            rows.append(found)
            shifts.append(np.full(len(found), off))
        rows, shifts = np.concatenate(rows), np.concatenate(shifts)
        cap = LAYER_SPECS["cities" if source == "capitals"
                          else source].label_cap
        # Stable, so equal ranks keep their order - as nsmallest did.
        for i in np.argsort(ranks[rows], kind="stable")[:cap]:
            row, off = int(rows[i]), float(shifts[i])
            yield ((source, row, off), str(names[row]),
                   float(xs[row] + off), float(ys[row]))

    @staticmethod
    def _estimate_rect(to_pixels, x: float, y: float, text: str,
                       fontsize_px: float) -> tuple[float, float, float, float]:
        """Rough pixel bounding box of a centered label, cheap enough to run
        for every candidate without a canvas draw."""
        sx, sy = to_pixels.transform((x, y))
        half_w = (len(text) * 0.31 + 0.3) * fontsize_px
        half_h = 0.72 * fontsize_px
        return (sx - half_w, sy - half_h, sx + half_w, sy + half_h)

    @staticmethod
    def _overlaps_any(rect, rects) -> bool:
        ax0, ay0, ax1, ay1 = rect
        for bx0, by0, bx1, by1 in rects:
            if ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0:
                return True
        return False
