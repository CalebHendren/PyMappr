"""The user's points and the legend that describes them."""

from __future__ import annotations

import matplotlib.transforms as mtransforms
import numpy as np
from matplotlib.lines import Line2D

from pymappr.renderer.tables import Z_POINTS
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import (POINT_EDGE_COLOR, POINT_EDGE_WIDTH,
                                    PointStyle)


class PointsMixin:
    """Point groups and the legend."""

    def _init_points(self) -> None:
        # (label, PointStyle, lons, lats) per group
        self._point_groups: list[tuple[str, PointStyle, np.ndarray,
                                       np.ndarray]] = []
        self._point_artists: list = []
        # Every legend setting lives in one options object; see
        # pymappr.styling.legend.LegendOptions. Weight/style are derived from
        # its bold/italic flags at draw time, and underline is stroked on each
        # draw (matplotlib text has no underline property).
        self._legend = LegendOptions()
        # Legend Text artists that need an underline stroke on each draw.
        self._legend_underline_texts: list = []
        # Structured legend: list of (section title, [(label, PointStyle)]).
        # When set, it replaces the one-row-per-group legend.
        self._legend_sections: list | None = None
        # Legend row order for the plain (one-row-per-group) legend, by
        # label. The app works it out because ordering by count needs the
        # data; None keeps the order the point groups were added in.
        self._legend_row_order: list[str] | None = None
        self._point_alpha = 1.0
        # Outline (colour, width) around filled markers, map and legend alike.
        self._point_edge = (POINT_EDGE_COLOR, POINT_EDGE_WIDTH)
        # Manual legend placement: dragging the legend (when enabled) anchors
        # its lower-left corner here, in axes fraction, with no limit; None
        # falls back to the automatic ``LegendOptions.location`` placement.
        self._legend_anchor: tuple[float, float] | None = None

    def set_point_groups(self, groups) -> None:
        """*groups* is a list of (label, PointStyle, lons, lats)."""
        self._point_groups = self._as_groups(groups)
        self._rebuild_points()

    def set_points(self, groups, sections: list | None,
                   row_order: list[str] | None,
                   options: LegendOptions) -> None:
        """Install the point groups and everything about the legend that
        describes them at once, so the legend is built once rather than once
        per setter. When the points themselves are unchanged - a legend
        setting changed - they are left as drawn."""
        groups = self._as_groups(groups)
        unchanged = (len(groups) == len(self._point_groups) and all(
            style == old_style and np.array_equal(lons, old_lons)
            and np.array_equal(lats, old_lats)
            for (_l, style, lons, lats), (_o, old_style, old_lons, old_lats)
            in zip(groups, self._point_groups)))
        self._point_groups = groups
        self._legend_sections = sections
        self._legend_row_order = (list(row_order) if row_order is not None
                                  else None)
        self._legend = options
        if unchanged:
            self._update_legend()
        else:
            self._rebuild_points()

    @staticmethod
    def _as_groups(groups) -> list:
        return [(label, style, np.asarray(lons, float),
                 np.asarray(lats, float))
                for label, style, lons, lats in groups]

    def set_legend(self, options: LegendOptions) -> None:
        """Install the full set of legend settings and redraw the legend."""
        self._legend = options
        self._update_legend()

    def set_structured_legend(self, sections: list | None) -> None:
        """Set (or clear with None) a sectioned color/symbol key legend."""
        self._legend_sections = sections
        self._update_legend()

    def set_legend_row_order(self, labels: list[str] | None) -> None:
        """The plain legend's rows, in order. None keeps every point group
        in insertion order; otherwise this is the whole legend - a group
        left out of the list keeps its points but loses its row.

        The app decides, because ordering by count and hiding rows both
        need the data.
        """
        self._legend_row_order = list(labels) if labels is not None else None
        self._update_legend()

    def set_legend_anchor(self, anchor) -> None:
        """Restore a previously dragged legend position (axes fraction)."""
        if anchor is None:
            self._legend_anchor = None
        else:
            x, y = anchor
            self._legend_anchor = (float(x), float(y))

    def legend_anchor(self) -> tuple[float, float] | None:
        """The manual legend position, so it can be saved with the project."""
        return self._legend_anchor

    def clear_legend_anchor(self) -> None:
        """Drop any manual (dragged) legend position, returning to automatic
        placement at the chosen location."""
        self._legend_anchor = None

    def set_point_alpha(self, alpha: float) -> None:
        self._point_alpha = max(min(float(alpha), 1.0), 0.05)
        self._rebuild_points()

    def set_point_edge(self, color: str, width: float) -> None:
        """Outline filled markers in *color* at *width* points (0 = none)."""
        self._point_edge = (color or POINT_EDGE_COLOR,
                            max(float(width), 0.0))
        self._rebuild_points()

    def _marker_paint(self, style: PointStyle) -> tuple[str, str, float]:
        """(face, edge, edge width) for a marker: open markers draw only an
        outline in their own colour, filled ones take the point outline."""
        if style.is_open:
            return "none", style.color, 1.2
        return (style.color, *self._point_edge)

    def _rebuild_points(self) -> None:
        for artist in self._point_artists:
            artist.remove()
        self._point_artists = []
        if self._point_groups:
            offsets = self._offsets()
            with self._preserving_view():
                for label, style, lons, lats in self._point_groups:
                    xs, ys = self.proj.forward(lons, lats)
                    xs = np.concatenate([xs + off for off in offsets])
                    ys = np.tile(ys, len(offsets))
                    face, edge, lw = self._marker_paint(style)
                    self._point_artists.append(self.ax.scatter(
                        xs, ys, s=style.size, c=face,
                        marker=style.mpl_marker, zorder=Z_POINTS,
                        edgecolors=edge, linewidths=lw,
                        alpha=self._point_alpha, label=label))
        self._update_legend()

    def _legend_handle(self, style: PointStyle | None,
                       size: float | None = None):
        # A None style is a row that takes no swatch, e.g. a nested key's
        # group row when the user has turned its marker off.
        if style is None:
            return Line2D([], [], linestyle="", marker="")
        area = style.size if size is None else size
        face, edge, edge_w = self._marker_paint(style)
        return Line2D([], [], linestyle="", marker=style.mpl_marker,
                      markersize=max(np.sqrt(area), 2),
                      markerfacecolor=face, color=style.color,
                      markeredgecolor=edge, markeredgewidth=edge_w)

    def _legend_kwargs(self, sectioned: bool) -> dict:
        """The matplotlib legend keywords shared by both draw paths."""
        opts = self._legend
        return {
            "title": opts.title,
            "fontsize": opts.fontsize,
            "title_fontsize": opts.title_fontsize,
            "ncols": max(int(opts.columns), 1),
            "markerscale": max(float(opts.marker_scale), 0.1),
            "labelspacing": max(float(opts.label_spacing), 0.0),
            "columnspacing": max(float(opts.column_spacing), 0.0),
            "handletextpad": max(opts.pad_for(sectioned), 0.0),
            "handlelength": max(float(opts.handle_length), 0.0),
            "borderpad": max(float(opts.border_pad), 0.0),
            "frameon": opts.frame,
            "framealpha": opts.frame_alpha,
            "facecolor": opts.frame_color,
            "edgecolor": opts.frame_edge_color,
            "fancybox": opts.rounded,
            "shadow": opts.shadow,
            "alignment": opts.title_align,
            **self._legend_placement(),
        }

    def _finish_legend(self, leg) -> None:
        """Apply the settings matplotlib takes no keyword for."""
        frame = leg.get_frame()
        if frame is not None:
            frame.set_linewidth(max(float(self._legend.frame_width), 0.0))

    def _legend_placement(self) -> dict:
        """Legend ``loc``/``bbox_to_anchor`` kwargs: the automatic location,
        or - once the legend has been dragged - its manual lower-left anchor
        in axes fraction (no bounds).

        A legend in the scale bar's corner sits beyond the bar instead of
        on it: its frame is opaque and would hide the bar completely."""
        if self._legend_anchor is not None:
            # borderaxespad=0 pins the lower-left corner exactly on the
            # anchor, so grabbing an auto-placed legend doesn't make it hop.
            return {"loc": "lower left", "bbox_to_anchor": self._legend_anchor,
                    "borderaxespad": 0.0}
        clear = getattr(self, "_scale_bar_clear", None)
        if clear is not None and clear[0] == self._legend.location:
            corner, frac, points = clear
            x = 0.0 if corner.endswith("left") else 1.0
            lift = mtransforms.ScaledTranslation(0.0, points / 72.0,
                                                 self.fig.dpi_scale_trans)
            return {"loc": corner, "bbox_to_anchor": (x, frac),
                    "bbox_transform": self.ax.transAxes + lift}
        return {"loc": self._legend.location}

    def _update_legend(self) -> None:
        legend = self.ax.get_legend()
        if legend is not None:
            legend.remove()
        # Rebuilt below for whatever legend (if any) is created this pass.
        self._legend_underline_texts = []
        if not (self._legend.show and self._point_groups):
            return
        if self._legend_sections is not None:
            self._draw_structured_legend()
            return
        groups = self._ordered_point_groups()
        handles = [self._legend_handle(style) for _label, style, _, _ in groups]
        for handle, (label, *_rest) in zip(handles, groups):
            handle.set_label(label)
        leg = self.ax.legend(handles=handles, **self._legend_kwargs(False))
        self._finish_legend(leg)
        self._apply_legend_text_format(leg, leg.get_texts())

    def _ordered_point_groups(self) -> list:
        """The point groups that get a legend row, in order.

        Sorting or hiding a legend row must not disturb what is drawn, so
        this filters and reorders a copy for the legend only.
        """
        if self._legend_row_order is None:
            return list(self._point_groups)
        rank = {label: i for i, label in enumerate(self._legend_row_order)}
        return sorted((g for g in self._point_groups if g[0] in rank),
                      key=lambda g: rank[g[0]])

    def _draw_structured_legend(self) -> None:
        """A compact legend split into titled sections, so encoding two
        columns needs only ``colors + symbols`` rows instead of one row per
        combination.

        Entries are ``(label, style)`` or ``(label, style, depth)``; *depth*
        indents a row under the one above it, which is how a nested key lists
        each symbol value beneath the color group it belongs to.
        """
        opts = self._legend
        handles: list = []
        labels: list[str] = []
        header_rows: list[int] = []

        def blank():
            return Line2D([], [], linestyle="", marker="")

        def spacer():
            header_rows.append(len(labels))
            handles.append(blank())
            labels.append(" ")

        for title, entries in self._legend_sections:
            if handles:  # spacer between sections
                spacer()
            if title:  # section titles can be turned off entirely
                header_rows.append(len(labels))
                handles.append(blank())
                labels.append(title)
            # In a nested key the depth-0 rows head a block of children, so
            # they take the header formatting (bold by default) on top of
            # their swatch - indentation alone reads too weakly when every
            # swatch sits in the same column.
            nested = any(len(entry) > 2 and entry[2] for entry in entries)
            for index, entry in enumerate(entries):
                label, style, *rest = entry
                depth = rest[0] if rest else 0
                if nested and depth == 0:
                    if index and opts.group_spacer:
                        spacer()  # separate this block from the one before
                    if opts.bold_groups:
                        header_rows.append(len(labels))
                handles.append(self._legend_handle(style, size=45))
                labels.append(opts.indent_for(depth) + label)
        leg = self.ax.legend(handles, labels, **self._legend_kwargs(True))
        self._finish_legend(leg)
        texts = leg.get_texts()
        header_set = set(header_rows)
        entry_texts = [t for i, t in enumerate(texts) if i not in header_set]
        self._apply_legend_text_format(leg, entry_texts)
        # Section headers read as sub-titles: give them the title formatting
        # (kept bold by default) rather than the entry-label formatting.
        for row in header_rows:
            if row < len(texts):
                self._format_text(texts[row], title_role=True)

    def _format_text(self, text, title_role: bool) -> None:
        """Apply the label or title text settings to a Text, and register it
        for underlining. Section headers take the title settings, which is
        what keeps them reading as sub-titles."""
        opts = self._legend
        bold = opts.title_bold if title_role else opts.label_bold
        italic = opts.title_italic if title_role else opts.label_italic
        underline = (opts.title_underline if title_role
                     else opts.label_underline)
        text.set_fontweight("bold" if bold else "normal")
        text.set_fontstyle("italic" if italic else "normal")
        text.set_color(opts.title_color if title_role else opts.label_color)
        if opts.font_family:
            text.set_fontfamily(opts.font_family)
        if underline and text.get_text().strip():
            self._legend_underline_texts.append(text)

    def _apply_legend_text_format(self, leg, entry_texts) -> None:
        """Style the legend title and entry labels, and collect the texts
        that need an underline stroke drawn on the next draw."""
        self._legend_underline_texts = [
            t for t in self._legend_underline_texts
            if t not in set(entry_texts) and t is not leg.get_title()]
        title = leg.get_title()
        if title is not None and title.get_text():
            self._format_text(title, title_role=True)
        for text in entry_texts:
            self._format_text(text, title_role=False)

    def _on_draw(self, event) -> None:
        self._draw_legend_underlines(getattr(event, "renderer", None))

    def _draw_legend_underlines(self, renderer) -> None:
        """Stroke an underline beneath each flagged legend Text in display
        coordinates. Runs during every draw (screen and file export), so the
        underline tracks the text's true position at any size or DPI."""
        if renderer is None or not self._legend_underline_texts:
            return
        for text in self._legend_underline_texts:
            if not text.get_visible() or not text.get_text().strip():
                continue
            try:
                bbox = text.get_window_extent(renderer)
            except Exception:  # noqa: BLE001 - never let a draw crash the app
                continue
            y = bbox.y0 - max(bbox.height * 0.1, 1.0)
            line = Line2D([bbox.x0, bbox.x1], [y, y],
                          transform=mtransforms.IdentityTransform(),
                          color=text.get_color(),
                          linewidth=max(text.get_fontsize() / 11.0, 0.6),
                          solid_capstyle="butt")
            line.set_figure(self.fig)
            line.draw(renderer)
