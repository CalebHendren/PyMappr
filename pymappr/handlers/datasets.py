"""The datasets: adding, editing and removing them, the filter, grouping,
open symbols and point styling, and laying the points out for the map."""

from __future__ import annotations

from tkinter import filedialog, messagebox

import numpy as np
import pandas as pd

from pymappr.files.data_loader import (
    OPEN_FILETYPES, PointDataset, build_dataset, build_manual_dataset,
    combine_name_columns, far_points, guess_mapping, headers_look_like_data,
    list_sheets, read_table)
from pymappr.files.projects import DatasetEntry
from pymappr.renderer.geometry import lon_span
from pymappr.styling.layout import (
    MapLayout, column_key, column_values, layout_points)
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import (
    LEGIBLE_MARKER_LIMIT, PointStyle, apply_override, marker_load,
    resolve_nesting, row_key)
from pymappr.ui.column_mapper import ColumnMapperDialog
from pymappr.ui.combine_columns import CombineColumnsDialog
from pymappr.ui.manual_entry import ManualEntryDialog

MAX_SKIPPED_SHOWN = 12


def _pinned_style(style: PointStyle) -> dict:
    """A legend-row override pinning every part of *style*."""
    return {"color": style.color, "marker": style.marker, "size": style.size}


class DatasetsMixin:
    """The datasets and their points."""

    def _active_entry(self) -> DatasetEntry | None:
        if self.active is None or not (0 <= self.active < len(self.entries)):
            return None
        return self.entries[self.active]

    def _report_skipped(self, dataset: PointDataset) -> bool:
        """Show row-skipping problems; False when nothing was imported."""
        if len(dataset) == 0:
            problems = "\n".join(dataset.skipped[:MAX_SKIPPED_SHOWN])
            messagebox.showerror(
                "No usable rows",
                "No rows had valid coordinates."
                + (f"\n\nFirst problems:\n{problems}" if problems else ""),
                parent=self.root)
            return False
        if dataset.skipped:
            shown = "\n".join(dataset.skipped[:MAX_SKIPPED_SHOWN])
            more = len(dataset.skipped) - MAX_SKIPPED_SHOWN
            if more > 0:
                shown += f"\n\N{HORIZONTAL ELLIPSIS} and {more} more"
            messagebox.showwarning(
                "Some rows skipped",
                f"Imported {len(dataset)} rows; skipped "
                f"{len(dataset.skipped)}:\n\n{shown}", parent=self.root)
        return True

    def _report_far_points(self, dataset: PointDataset) -> None:
        """Point out stray points - usually a missing minus sign or
        hemisphere letter - which otherwise only show as a map zoomed out
        to the whole world. They stay on the map; the file is the place
        to fix them."""
        notes = far_points(dataset)
        if not notes:
            return
        shown = "\n".join(notes[:MAX_SKIPPED_SHOWN])
        more = len(notes) - MAX_SKIPPED_SHOWN
        if more > 0:
            shown += f"\n\N{HORIZONTAL ELLIPSIS} and {more} more"
        messagebox.showwarning(
            "Points far from the rest",
            f"{shown}\n\nA point this far from the others is often a "
            "coordinate missing its minus sign or hemisphere letter. "
            "Check these rows in the file.", parent=self.root)

    def _add_entry(self, entry: DatasetEntry) -> None:
        self.entries.append(entry)
        self.active = len(self.entries) - 1
        self._sync_dataset_ui()
        self._push_points()
        self._zoom_to_data()

    def on_add_file(self) -> None:
        """Import a CSV/TSV/text file or an Excel/OpenDocument workbook."""
        path = filedialog.askopenfilename(
            parent=self.root, title="Add data file",
            filetypes=OPEN_FILETYPES)
        if not path:
            return
        try:
            sheets = list_sheets(path)
            first_sheet = sheets[0] if sheets else None
            frame = read_table(path, headers=True, sheet=first_sheet)
            # Don't assume the first row is headers: if it looks like data
            # (e.g. coordinates), start with it treated as data. The user
            # can flip the choice in the dialog either way.
            headers = not headers_look_like_data(frame)
            if not headers:
                frame = read_table(path, headers=False, sheet=first_sheet)
            guess = guess_mapping(frame)
        except Exception as exc:  # noqa: BLE001 - show any read error
            messagebox.showerror("Could not read file", str(exc),
                                 parent=self.root)
            return

        dialog = ColumnMapperDialog(
            self.root, frame, guess,
            reread=lambda h, s: read_table(path, headers=h, sheet=s),
            headers=headers, sheets=sheets)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return

        self._busy(True)
        try:
            dataset = build_dataset(dialog.frame, dialog.result,
                                    source_path=path)
        finally:
            self._busy(False)
        if not self._report_skipped(dataset):
            return

        short = path.replace("\\", "/").rsplit("/", 1)[-1]
        labels = dataset.name_labels
        self._add_entry(DatasetEntry(dataset=dataset, name=short,
                                     group_by=labels[0] if labels else ""))
        self.set_status(f"Loaded {len(dataset)} points from {short}.")
        self._report_far_points(dataset)

    def on_manual_entry(self) -> None:
        """Type or paste points by hand (legend name + coordinate lines)."""
        dialog = ManualEntryDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        r = dialog.result
        dataset = build_manual_dataset(r["legend"], r["text"], r["order"])
        if not self._report_skipped(dataset):
            return
        self._add_entry(DatasetEntry(
            dataset=dataset, name=r["legend"], group_by="Legend",
            legend_overrides={row_key("group", r["legend"]):
                              _pinned_style(r["style"])},
            manual={"text": r["text"], "order": r["order"]}))
        self.set_status(f"Added {len(dataset)} manually entered points.")

    def on_edit_dataset(self) -> None:
        entry = self._active_entry()
        if entry is None:
            return
        if entry.manual is None:
            messagebox.showinfo(
                "Not editable",
                "Only manually entered datasets can be edited here. "
                "To change a file-based dataset, edit the file and add "
                "it again.", parent=self.root)
            return
        style = apply_override(PointStyle(), entry.legend_overrides.get(
            row_key("group", entry.name)))
        dialog = ManualEntryDialog(
            self.root, legend=entry.name, text=entry.manual.get("text", ""),
            order=entry.manual.get("order", "lat,lon"), style=style)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        r = dialog.result
        dataset = build_manual_dataset(r["legend"], r["text"], r["order"])
        if not self._report_skipped(dataset):
            return
        # The legend name is the group's value, so a rename moves the row.
        old = entry.legend_overrides.pop(row_key("group", entry.name), {})
        entry.legend_overrides[row_key("group", r["legend"])] = {
            **old, **_pinned_style(r["style"])}
        entry.dataset = dataset
        entry.name = r["legend"]
        entry.manual = {"text": r["text"], "order": r["order"]}
        self._sync_dataset_ui()
        self._push_points()
        self.set_status(f"Updated {entry.name}: {len(dataset)} points.")

    def on_globe_rotated(self, lon0: float, lat0: float) -> None:
        """Mirror a globe spin in the centre-lon/lat controls (the renderer
        has already re-centred the projection)."""
        self.panel.proj_lon0_var.set(f"{lon0:g}")
        self.panel.proj_lat0_var.set(f"{lat0:g}")

    def on_remove_dataset(self) -> None:
        entry = self._active_entry()
        if entry is None:
            return
        if not messagebox.askyesno(
                "Remove dataset",
                f"Remove \N{LEFT DOUBLE QUOTATION MARK}{entry.name}"
                f"\N{RIGHT DOUBLE QUOTATION MARK} from the project?",
                parent=self.root):
            return
        self.entries.remove(entry)
        if not self.entries:
            self.active = None
        elif self.active is not None and self.active >= len(self.entries):
            self.active = len(self.entries) - 1
        self._sync_dataset_ui()
        self._push_points()
        self.set_status(f"Removed {entry.name}.")

    def on_select_dataset(self, index: int | None) -> None:
        if index is None or index == self.active:
            return
        self.active = index
        self._sync_active_controls()
        # The filter bar now points at the newly selected dataset, so any
        # previous filter no longer applies.
        self._push_points()

    def on_dataset_visible(self) -> None:
        entry = self._active_entry()
        if entry is None:
            return
        entry.visible = self.panel.dataset_visible_var.get()
        self.panel.set_dataset_list(
            [(e.name, e.visible) for e in self.entries], self.active)
        self._push_points()

    def _sync_dataset_ui(self) -> None:
        """Refresh the dataset list, info line, and per-dataset controls."""
        self.panel.set_dataset_list(
            [(e.name, e.visible) for e in self.entries], self.active)
        if not self.entries:
            self.panel.set_file_info("No data loaded")
        else:
            total = sum(len(e.dataset) for e in self.entries)
            count = len(self.entries)
            plural = "s" if count != 1 else ""
            self.panel.set_file_info(
                f"{count} dataset{plural}, {total} points")
        self._sync_active_controls()

    def _sync_active_controls(self) -> None:
        entry = self._active_entry()
        if entry is None:
            self.panel.set_dataset_controls(["None"], "None", "None",
                                            "None", False)
            self.panel.dataset_visible_var.set(True)
            self.filter_bar.set_dataset(pd.DataFrame(), [], [])
            return
        choices = ["None"] + list(entry.dataset.name_labels)
        self.panel.set_dataset_controls(
            choices, entry.group_by or "None", entry.color_by or "None",
            entry.symbol_by or "None", entry.vary_symbols)
        self._sync_open_controls(entry, choices)
        self.panel.dataset_visible_var.set(entry.visible)
        self.filter_bar.set_dataset(entry.dataset.frame,
                                    entry.dataset.name_labels,
                                    entry.dataset.name_keys)

    # ------------------------------------------------------------ rendering

    def _filtered_frame(self, entry: DatasetEntry):
        """The entry's frame with the filter bar applied (active entry
        only - the filter bar always points at the selected dataset)."""
        frame = entry.dataset.frame
        if entry is not self._active_entry():
            return frame
        selection = self.filter_bar.selection()
        if selection is None:
            return frame
        key, allowed = selection
        if key not in frame.columns:
            return frame
        return frame[frame[key].fillna("").isin(allowed)]

    def _layout(self) -> MapLayout:
        """What every visible dataset draws, with the filter applied."""
        return layout_points(self.entries, self._legend_options(),
                             self._palette(), self._filtered_frame)

    def _push_points(self) -> None:
        """Rebuild the plotted points and legend from every visible
        dataset."""
        options = self._legend_options()
        layout = layout_points(self.entries, options, self._palette(),
                               self._filtered_frame)
        self.renderer.set_points(
            [(label, style, rows["lon"].to_numpy(), rows["lat"].to_numpy())
             for label, style, rows in layout.groups],
            layout.sections, layout.row_order, options,
            [layout.open_note] if layout.open_note else None)
        self.renderer.redraw()
        self._warn_marker_load([d.entry for d in layout.datasets], options)

    def _warn_marker_load(self, visible: list[DatasetEntry],
                          options: LegendOptions) -> None:
        """Say so when a symbol column asks for more shapes than stay
        tellable apart, or when forced nesting is quietly hiding rows,
        rather than drawing a map the legend does not describe."""
        if self._warn_forced_nesting(visible, options):
            return
        worst, worst_entry = 0, None
        for entry in visible:
            symbol_key = column_key(entry, entry.symbol_by)
            if symbol_key is None:
                continue
            load = marker_load(entry.dataset.frame,
                               column_key(entry, entry.color_by),
                               symbol_key, options.hierarchy)
            if load > worst:
                worst, worst_entry = load, entry
        if worst > LEGIBLE_MARKER_LIMIT and worst_entry is not None:
            self._set_legend_warning(
                f"{worst_entry.name}: \N{LEFT DOUBLE QUOTATION MARK}"
                f"{worst_entry.symbol_by}\N{RIGHT DOUBLE QUOTATION MARK} "
                f"needs {worst} shapes, more than the {LEGIBLE_MARKER_LIMIT} "
                "that stay easy to tell apart. Consider a Color by column "
                "that groups them, or filtering to fewer values.")
        else:
            # Switching Hierarchy changes how many shapes are needed, so a
            # warning that no longer applies has to come down with it.
            self._clear_legend_warning()

    def _set_legend_warning(self, text: str) -> None:
        """Show a legend warning and remember it, so the next rebuild can
        take it back down again once it stops being true."""
        self._legend_warning = text
        self.set_status(text)

    def _clear_legend_warning(self) -> None:
        """Drop a legend warning we raised earlier - but never a status
        message something else put there since."""
        if not self._legend_warning:
            return
        if self.status.cget("text") == self._legend_warning:
            self.set_status("Ready.")
        self._legend_warning = ""

    def _warn_forced_nesting(self, visible: list[DatasetEntry],
                             options: LegendOptions) -> bool:
        """Warn when "Always nest" is applied to columns that genuinely
        cross. Each symbol value then appears under several colours on the
        map but only once in the legend, so the key stops describing the
        map. Returns True when a warning was shown."""
        if options.hierarchy != "always":
            return False
        for entry in visible:
            color_key = column_key(entry, entry.color_by)
            symbol_key = column_key(entry, entry.symbol_by)
            if symbol_key is None or color_key is None:
                continue
            frame = entry.dataset.frame
            if resolve_nesting(frame, color_key, symbol_key, "auto"):
                continue
            self._set_legend_warning(
                f"{entry.name}: \N{LEFT DOUBLE QUOTATION MARK}"
                f"{entry.symbol_by}\N{RIGHT DOUBLE QUOTATION MARK} does not "
                f"nest inside \N{LEFT DOUBLE QUOTATION MARK}"
                f"{entry.color_by}\N{RIGHT DOUBLE QUOTATION MARK}, so each "
                "shape is listed under the first colour it appears in. Set "
                "Hierarchy to Auto for two independent keys.")
            return True
        return False

    def on_filter(self) -> None:
        entry = self._active_entry()
        if entry is None:
            return
        self._push_points()
        shown = len(self._filtered_frame(entry))
        total = len(entry.dataset)
        if shown == total:
            self.set_status(f"Showing all {total} points of {entry.name}.")
        else:
            self.set_status(f"Filter: showing {shown} of {total} points "
                            f"of {entry.name}.")

    def _zoom_to_data(self) -> None:
        frames = [e.dataset.frame for e in self.entries
                  if e.visible and len(e.dataset)]
        if not frames:
            return
        # The shortest span, so points either side of the antimeridian
        # (Fiji and Samoa) frame the Pacific, not the whole world.
        x0, x1 = lon_span(np.concatenate([frame["lon"].to_numpy()
                                          for frame in frames]))
        y0 = min(frame["lat"].min() for frame in frames)
        y1 = max(frame["lat"].max() for frame in frames)
        pad_x = max((x1 - x0) * 0.15, 2.0)
        pad_y = max((y1 - y0) * 0.15, 2.0)
        if x1 > 180:  # across the antimeridian: no 180 edge to stop at
            west, east = x0 - pad_x, x1 + pad_x
        else:
            west, east = max(x0 - pad_x, -180), min(x1 + pad_x, 180)
        self.renderer.set_extent((west, east,
                                  max(y0 - pad_y, -90), min(y1 + pad_y, 90)))
        self.toolbar.update()  # make this view the toolbar's Home
        self.renderer.redraw()

    # ------------------------------------------------------------- handlers

    def on_group_by(self) -> None:
        entry = self._active_entry()
        if entry is None:
            return
        value = self.panel.group_by_var.get()
        entry.group_by = "" if value == "None" else value
        # Row customizations are keyed by value, so any that still name a
        # group that exists keep applying and the rest lie dormant.
        self._push_points()

    def _sync_open_controls(self, entry: DatasetEntry,
                            choices: list[str]) -> None:
        values = column_values(entry, entry.open_by) if entry.open_by else []
        chosen = entry.open_values[0] if entry.open_values else ""
        self.panel.set_open_controls(choices, entry.open_by or "None",
                                     values, chosen)

    def on_open_by(self) -> None:
        """The open-symbol column changed: offer its values, starting on
        "Holotype" when there is one."""
        entry = self._active_entry()
        if entry is None:
            return
        column = self.panel.open_by_var.get()
        entry.open_by = "" if column == "None" else column
        values = column_values(entry, entry.open_by) if entry.open_by else []
        chosen = next((v for v in values if v.lower() == "holotype"),
                      values[0] if values else "")
        entry.open_values = [chosen] if chosen else []
        self._sync_open_controls(entry, ["None"]
                                 + list(entry.dataset.name_labels))
        self._push_points()

    def on_open_symbols(self) -> None:
        """The value drawn with open symbols changed."""
        entry = self._active_entry()
        if entry is None:
            return
        value = self.panel.open_value_var.get()
        entry.open_values = [value] if entry.open_by and value else []
        self._push_points()

    def on_style_scheme(self) -> None:
        """Color-by / symbol-by column or symbol variation changed."""
        entry = self._active_entry()
        if entry is None:
            return
        color = self.panel.color_by_var.get()
        symbol = self.panel.symbol_by_var.get()
        entry.color_by = "" if color == "None" else color
        entry.symbol_by = "" if symbol == "None" else symbol
        entry.vary_symbols = self.panel.vary_symbols_var.get()
        self._push_points()

    def on_point_alpha(self) -> None:
        self.renderer.set_point_alpha(self.panel.point_alpha_var.get())
        self.renderer.redraw()

    def on_point_edge(self) -> None:
        self.renderer.set_point_edge(*self.panel.point_edge())
        self.renderer.redraw()

    def on_combine_columns(self) -> None:
        """Join name columns (Genus + Species) into a new column and group
        by it, so each legend row carries the full name."""
        entry = self._active_entry()
        labels = entry.dataset.name_labels if entry else []
        if len(labels) < 2:
            messagebox.showinfo(
                "Combine columns",
                "Select a dataset with at least two name columns first.",
                parent=self.root)
            return

        first_row = PointDataset(frame=entry.dataset.frame.head(1),
                                 source_path="")

        def preview(chosen, separator):
            sample, _label = combine_name_columns(first_row, chosen,
                                                  separator)
            values = sample.frame[sample.name_keys[-1]]
            return str(values.iloc[0]) if len(values) else ""

        dialog = CombineColumnsDialog(self.root, labels, preview)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        chosen, separator = dialog.result
        entry.dataset, label = combine_name_columns(entry.dataset, chosen,
                                                    separator)
        # Group by the new column; Symbol by would switch the legend to the
        # two-column key and hide the full names again.
        entry.group_by = label
        entry.symbol_by = ""
        self._sync_dataset_ui()
        self._push_points()
        self.set_status(f"Added the column \N{LEFT DOUBLE QUOTATION MARK}"
                        f"{label}\N{RIGHT DOUBLE QUOTATION MARK} and grouped "
                        "by it.")
