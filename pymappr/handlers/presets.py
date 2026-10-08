"""Presets and the legend: the built-in Standard preset, user-saved
presets, the legend options and the legend editor."""

from __future__ import annotations

import dataclasses
from tkinter import messagebox, simpledialog

from pymappr.files import presets
from pymappr.styling.layout import (
    column_values, editor_rows, holotype_marking,
    organise_publication_legend, with_default_title)
from pymappr.styling.legend import (
    ENTRY_ORDERS, PUBLICATION_LEGEND, LegendOptions)
from pymappr.styling.styles import (
    BLACK_AND_WHITE_NAME, PUBLICATION_POINT_EDGE)
from pymappr.ui.control_panel import name_for
from pymappr.ui.legend_editor import LegendEditorDialog
from pymappr.ui.save_image import JOURNAL_PAGE_WIDTH

# The export DPI and print width of the built-in "Standard" preset, a
# Zootaxa / Phytotaxa figure: 600 dpi, 17 cm wide (the point and legend
# halves are pymappr.styling.styles.PUBLICATION_POINT_EDGE and
# pymappr.styling.legend.PUBLICATION_LEGEND).
PUBLICATION_DPI = "600"
PUBLICATION_WIDTH = JOURNAL_PAGE_WIDTH
# The built-in preset, listed first; it runs on_publication_style rather
# than restoring saved values, so it adapts to the data it is applied to.
# The user may delete it, which hides it for good.
BUILT_IN_PRESET = "Standard"


class PresetsMixin:
    """Presets and the legend."""

    def on_publication_style(self) -> None:
        """Apply several settings at once for a journal figure: black and
        white points with black outlines and varied shapes, a plain boxed
        legend with italic names sorted A-Z and shaded by genus, and 600 DPI
        export. Rows the user styled by hand in the legend editor keep their
        styling, and so do a manual legend order and a chosen Color by."""
        p = self.panel
        p.palette_var.set(BLACK_AND_WHITE_NAME)
        p.set_point_edge(*PUBLICATION_POINT_EDGE)
        p.set_point_alpha(1.0)
        legend = dataclasses.replace(p.legend_options(), **PUBLICATION_LEGEND)
        if not (legend.title or "").strip():
            # No heading for a journal legend: the caption says what the
            # symbols are, and a column name ("Genus Species") reads oddly.
            # A title the user typed is kept.
            legend = dataclasses.replace(legend, show_title=False)
        p.set_legend_options(organise_publication_legend(self.entries,
                                                         legend))
        p.dpi_var.set(PUBLICATION_DPI)
        p.export_width_var.set(PUBLICATION_WIDTH)
        # Three shades alone cannot tell more than three groups apart.
        for entry in self.entries:
            entry.vary_symbols = True
            # Holotypes as open symbols, when a Type status column names
            # them and the user has not chosen open symbols already.
            marking = None if entry.open_by else holotype_marking(entry)
            if marking:
                entry.open_by, value = marking
                entry.open_values = [value]
        p.vary_symbols_var.set(True)
        active = self._active_entry()
        if active is not None:
            p.color_by_var.set(active.color_by or "None")
            p.set_open_controls(
                ["None"] + list(active.dataset.name_labels),
                active.open_by or "None",
                column_values(active, active.open_by)
                if active.open_by else [],
                active.open_values[0] if active.open_values else "")
        self.renderer.set_point_alpha(1.0)
        self.renderer.set_point_edge(*p.point_edge())
        self._push_points()
        self.set_status(f"Applied the {BUILT_IN_PRESET} preset. Export with "
                        "File \N{RIGHTWARDS ARROW} Save map as "
                        f"({PUBLICATION_DPI} DPI, 17 cm wide).")

    # -------------------------------------------------------------- presets

    def _refresh_presets(self, selected: str | None = None) -> None:
        self._presets = dict(presets.list_presets())
        self._built_in = not presets.built_in_deleted()
        self.panel.set_preset_names(
            [BUILT_IN_PRESET] * self._built_in + list(self._presets),
            selected)

    def _framing(self) -> tuple:
        """What decides where the map's coordinates lie: a view saved under
        one of these is meaningless under another."""
        p = self.panel
        return (p.projection_var.get(), p.proj_lon0_var.get(),
                p.proj_lat0_var.get(), p.orientation_var.get())

    def on_apply_preset(self) -> None:
        name = self.panel.preset_var.get()
        if not name:
            return
        if name == BUILT_IN_PRESET and self._built_in:
            self.on_publication_style()
            return
        path = self._presets.get(name)
        try:
            if path is None:
                raise OSError(f"No preset named {name!r}.")
            _name, settings = presets.load_preset(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Apply preset", str(exc), parent=self.root)
            self._refresh_presets()
            return
        skipped = []
        for entry in self.entries:
            skipped += [f"{what} is not a column in {entry.name}"
                        for what in presets.apply_dataset_style(
                            entry, dict(settings.get("dataset") or {}))]
        framing, view = self._framing(), self.renderer.get_view()
        self._apply_settings(settings)
        # The zoom belongs to the project, so it stays on this project's
        # data - unless the preset reprojected the map, which moves it.
        if self._framing() == framing:
            self.renderer.set_view(*view)
            self.toolbar.update()
        else:
            self._zoom_to_data()
        self._sync_dataset_ui()
        self._push_points()
        status = (f"Applied the preset \N{LEFT DOUBLE QUOTATION MARK}{name}"
                  "\N{RIGHT DOUBLE QUOTATION MARK}.")
        if skipped:
            status += " Not applied: " + "; ".join(skipped) + "."
        self.set_status(status)

    def on_save_preset(self) -> None:
        current = self.panel.preset_var.get()
        name = simpledialog.askstring(
            "Save preset", "Preset name:",
            initialvalue=("" if current == BUILT_IN_PRESET and self._built_in
                          else current),
            parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if name == BUILT_IN_PRESET and self._built_in:
            messagebox.showinfo(
                "Save preset", "That name belongs to the built-in "
                f"{BUILT_IN_PRESET} preset. Choose another.", parent=self.root)
            return
        path = presets.preset_path(name)
        if path.exists() and not messagebox.askyesno(
                "Save preset",
                f"A preset named \N{LEFT DOUBLE QUOTATION MARK}{name}"
                f"\N{RIGHT DOUBLE QUOTATION MARK} already exists. "
                "Overwrite it?", parent=self.root):
            return
        try:
            presets.save_preset(path, name, presets.settings_from_state(
                self._collect_state(), self._active_entry()))
        except OSError as exc:
            messagebox.showerror("Save preset", str(exc), parent=self.root)
            return
        self._refresh_presets(name)
        self.set_status(f"Saved the preset \N{LEFT DOUBLE QUOTATION MARK}"
                        f"{name}\N{RIGHT DOUBLE QUOTATION MARK}. Apply it "
                        "in any project from the Data tab.")

    def on_delete_preset(self) -> None:
        name = self.panel.preset_var.get()
        built_in = name == BUILT_IN_PRESET and self._built_in
        path = self._presets.get(name)
        if not built_in and path is None:
            return
        if not messagebox.askyesno(
                "Delete preset",
                f"Delete the preset \N{LEFT DOUBLE QUOTATION MARK}{name}"
                "\N{RIGHT DOUBLE QUOTATION MARK}?", parent=self.root):
            return
        try:
            if built_in:
                presets.delete_built_in()
            else:
                presets.delete_preset(path)
        except OSError as exc:
            messagebox.showerror("Delete preset", str(exc), parent=self.root)
        self._refresh_presets()

    def on_legend_options(self) -> None:
        """Any legend setting changed. Rebuilding is one legend build, so
        there is no separate restyle-only path to keep in step with it."""
        self._push_points()

    def on_legend_position(self) -> None:
        # Choosing a preset position discards any manual (dragged) placement.
        self.renderer.clear_legend_anchor()
        self._push_points()

    def _legend_options(self) -> LegendOptions:
        """The panel's legend settings, with the title defaulted."""
        return with_default_title(self.entries, self.panel.legend_options())

    def on_edit_styles(self) -> None:
        entry = self._active_entry()
        if entry is None:
            messagebox.showinfo("No data", "Add a dataset first to "
                                "customize its legend.", parent=self.root)
            return
        # The editor shows each row in the colour the map gives it, which in
        # group-by mode depends on the datasets drawn before this one.
        drawn = next((d for d in self._layout().datasets if d.entry is entry),
                     None)
        rows = editor_rows(entry, self._legend_options(), self._palette(),
                           drawn.palette_offset if drawn else 0)
        if not rows:
            messagebox.showinfo(
                "Nothing to customize",
                "This dataset has no legend rows yet. Choose a Group by, "
                "Color by or Symbol by column first.", parent=self.root)
            return
        LegendEditorDialog(self.root, rows, entry.legend_overrides,
                           self._push_points, self._order_manually)

    def _order_manually(self) -> None:
        """Switch the legend to manual ordering and redraw.

        Moving a row does nothing while the legend is sorting itself, so
        the reorder buttons flip the Order setting rather than leaving the
        user to work out why nothing moved.
        """
        self.panel.legend_vars["order"].set(name_for(ENTRY_ORDERS, "manual"))
        self._push_points()
