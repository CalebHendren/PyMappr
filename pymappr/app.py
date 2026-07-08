"""PyMappr main window: menu, matplotlib canvas, toolbar, control panel."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")

from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,  # noqa: E402
                                               NavigationToolbar2Tk)
from matplotlib.figure import Figure  # noqa: E402

from pymappr import __version__, updates  # noqa: E402
from pymappr.data_loader import (PointDataset, build_dataset,  # noqa: E402
                                guess_mapping, read_csv)
from pymappr.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styles import (NEUTRAL_MARKER_COLOR, PointStyle,  # noqa: E402
                            attribute_style_maps, default_styles,
                            group_points, style_by_attributes)
from pymappr.ui.column_mapper import ColumnMapperDialog  # noqa: E402
from pymappr.ui.control_panel import ControlPanel  # noqa: E402
from pymappr.ui.filter_bar import FilterBar  # noqa: E402
from pymappr.ui.legend_editor import LegendEditorDialog  # noqa: E402

MAX_SKIPPED_SHOWN = 12


class PyMapprApp:
    def __init__(self, root: tk.Tk, store: LayerStore):
        self.root = root
        self.store = store
        self.dataset: PointDataset | None = None
        self.styles: dict[str, PointStyle] = {}

        root.title("PyMappr")
        root.geometry("1280x800")
        root.minsize(980, 640)
        icon = store.icon_path()
        if icon is not None:
            try:
                root.iconbitmap(str(icon))
            except tk.TclError:
                pass  # non-Windows platforms

        self._build_menu()

        self.panel = ControlPanel(root, self)
        self.panel.pack(side="left", fill="y")

        map_frame = ttk.Frame(root)
        map_frame.pack(side="right", fill="both", expand=True)

        figure = Figure(figsize=(9, 6.5), dpi=100, facecolor="white")
        self.canvas = FigureCanvasTkAgg(figure, master=map_frame)
        self.renderer = MapRenderer(figure, store)

        self.toolbar = NavigationToolbar2Tk(self.canvas, map_frame,
                                            pack_toolbar=False)
        self.toolbar.update()
        self._add_zoom_buttons()
        self.toolbar.pack(side="top", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        # Scroll wheel zooms the map about the cursor.
        self.canvas.mpl_connect("scroll_event", self._on_scroll_zoom)

        self.status = ttk.Label(map_frame, text="Ready. Open a CSV to plot "
                                "points, or explore the map layers.",
                                anchor="w", padding=(6, 2))
        self.status.pack(side="bottom", fill="x")

        self.filter_bar = FilterBar(map_frame, self.on_filter)
        self.filter_bar.pack(side="bottom", fill="x")

        # Defaults: simple basemap with country borders.
        self.renderer.set_layer("countries", True)
        self.canvas.draw()

        # Once-a-day update check, off the UI thread and after startup.
        root.after(2000, self._auto_update_check)

    # ----------------------------------------------------------------- menu

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open CSV\N{HORIZONTAL ELLIPSIS}",
                              accelerator="Ctrl+O",
                              command=self.on_open_csv)
        file_menu.add_command(label="Save map as PNG\N{HORIZONTAL ELLIPSIS}",
                              accelerator="Ctrl+S",
                              command=self.on_save_png)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About PyMappr", command=self._about)
        help_menu.add_command(label="Check for updates"
                              "\N{HORIZONTAL ELLIPSIS}",
                              command=self.on_check_updates)
        help_menu.add_separator()
        help_menu.add_command(label="Support me on Patreon",
                              command=self._open_patreon)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)
        self.root.bind("<Control-o>", lambda _e: self.on_open_csv())
        self.root.bind("<Control-s>", lambda _e: self.on_save_png())
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.root.bind(seq, lambda _e: self.zoom_step(1.3))
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.root.bind(seq, lambda _e: self.zoom_step(1 / 1.3))

    # ----------------------------------------------------------------- zoom

    def _add_zoom_buttons(self) -> None:
        """Big, obvious zoom buttons next to the matplotlib toolbar."""
        ttk.Separator(self.toolbar, orient="vertical").pack(
            side="left", fill="y", padx=6, pady=2)
        ttk.Button(self.toolbar, text="\N{HEAVY MINUS SIGN} Zoom out",
                   command=lambda: self.zoom_step(1 / 1.5)).pack(side="left")
        ttk.Button(self.toolbar, text="\N{HEAVY PLUS SIGN} Zoom in",
                   command=lambda: self.zoom_step(1.5)).pack(side="left",
                                                             padx=(2, 0))

    def zoom_step(self, factor: float) -> None:
        """Zoom about the view center (buttons, Ctrl+= / Ctrl+-)."""
        self.renderer.zoom(factor)
        self.renderer.redraw()

    def _on_scroll_zoom(self, event) -> None:
        if event.inaxes is None or event.xdata is None:
            return
        factor = 1.25 if event.button == "up" else 1 / 1.25
        self.renderer.zoom(factor, (event.xdata, event.ydata))
        self.renderer.redraw()

    def _about(self) -> None:
        messagebox.showinfo(
            "About PyMappr",
            f"PyMappr {__version__}\n\n"
            "Simple mapping software: plot CSV point data on a world map.\n\n"
            "Map data \N{COPYRIGHT SIGN} Natural Earth (public domain),\n"
            "naturalearthdata.com",
            parent=self.root)

    def _open_patreon(self) -> None:
        from pymappr.ui.control_panel import PATREON_URL
        webbrowser.open(PATREON_URL)

    # -------------------------------------------------------------- updates

    def _auto_update_check(self) -> None:
        updates.check_daily_async(
            lambda version: self.root.after(0, self._offer_update, version))

    def on_check_updates(self) -> None:
        """Manual check from the Help menu: always reports a result."""
        self.set_status("Checking for updates\N{HORIZONTAL ELLIPSIS}")

        def worker() -> None:
            try:
                newer = updates.check_now()
            except Exception as exc:  # noqa: BLE001 - report any failure
                self.root.after(0, self._update_check_failed, str(exc))
                return
            self.root.after(0, self._update_check_done, newer)

        threading.Thread(target=worker, daemon=True).start()

    def _update_check_done(self, newer: str | None) -> None:
        self.set_status("Ready.")
        if newer:
            self._offer_update(newer)
        else:
            messagebox.showinfo(
                "Check for updates",
                f"PyMappr {__version__} is up to date.", parent=self.root)

    def _update_check_failed(self, error: str) -> None:
        self.set_status("Ready.")
        messagebox.showwarning(
            "Check for updates",
            f"Could not check for updates:\n{error}", parent=self.root)

    def _offer_update(self, version: str) -> None:
        if messagebox.askyesno(
                "Update available",
                f"PyMappr {version} is available (you have {__version__})."
                "\n\nOpen the releases page to download it?",
                parent=self.root):
            webbrowser.open(updates.RELEASES_URL)

    def set_status(self, text: str) -> None:
        self.status.config(text=text)

    def _busy(self, on: bool) -> None:
        self.root.config(cursor="watch" if on else "")
        self.root.update_idletasks()

    # ----------------------------------------------------------------- data

    def on_open_csv(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="Open CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            frame = read_csv(path)
            guess = guess_mapping(frame)
        except Exception as exc:  # noqa: BLE001 - show any read error
            messagebox.showerror("Could not read CSV", str(exc),
                                 parent=self.root)
            return

        dialog = ColumnMapperDialog(self.root, frame, guess)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return

        self._busy(True)
        try:
            dataset = build_dataset(frame, dialog.result, source_path=path)
        finally:
            self._busy(False)

        if len(dataset) == 0:
            messagebox.showerror(
                "No usable rows",
                "No rows had valid coordinates.\n\nFirst problems:\n"
                + "\n".join(dataset.skipped[:MAX_SKIPPED_SHOWN]),
                parent=self.root)
            return
        if dataset.skipped:
            shown = "\n".join(dataset.skipped[:MAX_SKIPPED_SHOWN])
            more = len(dataset.skipped) - MAX_SKIPPED_SHOWN
            if more > 0:
                shown += f"\n\N{HORIZONTAL ELLIPSIS} and {more} more"
            messagebox.showwarning(
                "Some rows skipped",
                f"Imported {len(dataset)} rows; skipped "
                f"{len(dataset.skipped)}:\n\n{shown}", parent=self.root)

        self.dataset = dataset
        short = path.replace("\\", "/").rsplit("/", 1)[-1]
        self.panel.set_file_info(f"{short}: {len(dataset)} points")
        self._update_group_choices()
        self.filter_bar.set_dataset(dataset.frame, dataset.name_labels,
                                    dataset.name_keys)
        self.styles = {}
        self._push_points()
        self._zoom_to_data()
        self.set_status(f"Loaded {len(dataset)} points from {short}.")

    def _update_group_choices(self) -> None:
        assert self.dataset is not None
        choices = ["None"] + list(self.dataset.name_labels)
        self._group_choice_keys = dict(zip(self.dataset.name_labels,
                                           self.dataset.name_keys))
        default = choices[1] if len(choices) > 1 else choices[0]
        self.panel.set_group_by_choices(choices, default)

    def _group_by_key(self) -> str | None:
        value = self.panel.group_by_var.get()
        return getattr(self, "_group_choice_keys", {}).get(value)

    def _color_by_key(self) -> str | None:
        value = self.panel.color_by_var.get()
        return getattr(self, "_group_choice_keys", {}).get(value)

    def _symbol_by_key(self) -> str | None:
        value = self.panel.symbol_by_var.get()
        return getattr(self, "_group_choice_keys", {}).get(value)

    def _label_for_key(self, key: str | None) -> str | None:
        if key is None or self.dataset is None:
            return None
        labels = dict(zip(self.dataset.name_keys, self.dataset.name_labels))
        return labels.get(key)

    def _push_points(self) -> None:
        if self.dataset is None:
            return
        if self._symbol_by_key() is not None:
            self._push_points_by_attributes()
            return
        # Styles come from the full, unfiltered grouping so each group's
        # color/symbol stays put while filter values are toggled.
        groups = group_points(self.dataset.frame, self._group_by_key())
        labels = [label for label, _ in groups]
        color_by = self._color_by_key()
        color_keys = None
        if color_by is not None and color_by in self.dataset.frame.columns:
            # One color-key per group: the group's value in the color-by
            # column (e.g. every cat group keyed "Felines").
            color_keys = [str(sub[color_by].iloc[0]) if len(sub) else ""
                          for _label, sub in groups]
        fresh = default_styles(labels, color_keys=color_keys,
                               vary_symbols=self.panel.vary_symbols_var.get())
        # Keep customized styles for groups that still exist.
        self.styles = {lb: self.styles.get(lb, fresh[lb]) for lb in labels}
        shown = group_points(self._filtered_frame(), self._group_by_key())
        self.renderer.set_structured_legend(None)
        self.renderer.set_point_groups([
            (label, self.styles.get(label, fresh.get(label, PointStyle())),
             sub["lon"].to_numpy(), sub["lat"].to_numpy())
            for label, sub in shown
        ])
        self._apply_legend(redraw=False)
        self.renderer.redraw()

    def _push_points_by_attributes(self) -> None:
        """Style points by a color column and a symbol column at once, with a
        compact color/symbol key legend (used when Symbol by is set)."""
        assert self.dataset is not None
        color_key = self._color_by_key()
        symbol_key = self._symbol_by_key()
        # Maps come from the full dataset so colors, symbols, and the legend
        # stay stable as the filter hides values.
        color_map, symbol_map = attribute_style_maps(
            self.dataset.frame, color_key, symbol_key)
        shown_frame = self._filtered_frame()
        groups = style_by_attributes(shown_frame, color_key,
                                     symbol_key, color_map, symbol_map)
        self.styles = {}
        self.renderer.set_point_groups([
            (label, style, sub["lon"].to_numpy(), sub["lat"].to_numpy())
            for label, style, sub in groups
        ])

        # Legend sections list only the values currently shown: anything
        # unticked in the filter bar disappears from the legend too (styles
        # still come from the full-dataset maps, so they stay stable).
        def shown_values(key):
            if key is None or key not in shown_frame.columns:
                return None
            return set(shown_frame[key].fillna(""))

        shown_colors = shown_values(color_key)
        shown_symbols = shown_values(symbol_key)
        sections = []
        if color_map:
            entries = [(value, PointStyle(color=color, marker="Circle"))
                       for value, color in color_map.items()
                       if shown_colors is None or value in shown_colors]
            if entries:
                sections.append((self._label_for_key(color_key) or "Color",
                                 entries))
        if symbol_map:
            entries = [(value, PointStyle(color=NEUTRAL_MARKER_COLOR,
                                          marker=marker))
                       for value, marker in symbol_map.items()
                       if shown_symbols is None or value in shown_symbols]
            if entries:
                sections.append((self._label_for_key(symbol_key) or "Symbol",
                                 entries))
        self.renderer.set_structured_legend(sections)
        self._apply_legend(redraw=False)
        self.renderer.redraw()

    def _filtered_frame(self):
        """The dataset frame with the filter bar's selection applied."""
        assert self.dataset is not None
        frame = self.dataset.frame
        selection = self.filter_bar.selection()
        if selection is None:
            return frame
        key, allowed = selection
        if key not in frame.columns:
            return frame
        return frame[frame[key].fillna("").isin(allowed)]

    def on_filter(self) -> None:
        if self.dataset is None:
            return
        self._push_points()
        shown = len(self._filtered_frame())
        total = len(self.dataset)
        if shown == total:
            self.set_status(f"Showing all {total} points.")
        else:
            self.set_status(f"Filter: showing {shown} of {total} points.")

    def _zoom_to_data(self) -> None:
        assert self.dataset is not None
        frame = self.dataset.frame
        x0, x1 = frame["lon"].min(), frame["lon"].max()
        y0, y1 = frame["lat"].min(), frame["lat"].max()
        pad_x = max((x1 - x0) * 0.15, 2.0)
        pad_y = max((y1 - y0) * 0.15, 2.0)
        self.renderer.set_extent((max(x0 - pad_x, -180), min(x1 + pad_x, 180),
                                  max(y0 - pad_y, -90), min(y1 + pad_y, 90)))
        self.toolbar.update()  # make this view the toolbar's Home
        self.renderer.redraw()

    # ------------------------------------------------------------- handlers

    def on_group_by(self) -> None:
        # New grouping: rebuild styles from scratch for the new groups.
        self.styles = {}
        self._push_points()

    def on_style_scheme(self) -> None:
        """Color-by column or symbol variation changed."""
        self.styles = {}
        self._push_points()

    def on_point_alpha(self) -> None:
        self.renderer.set_point_alpha(self.panel.point_alpha_var.get())
        self.renderer.redraw()

    def on_legend_options(self) -> None:
        self._apply_legend()

    def _apply_legend(self, redraw: bool = True) -> None:
        title = self.panel.legend_title_var.get().strip() or None
        # In two-attribute mode the legend's own sections name the columns,
        # so don't add a redundant group-by title on top.
        if (title is None and self.dataset is not None
                and self._symbol_by_key() is None):
            title = self._label_for_key(self._group_by_key())
        self.renderer.set_legend(
            self.panel.legend_show_var.get(), title,
            self.panel.legend_loc_var.get(),
            fontsize=self.panel.legend_fontsize(),
            columns=self.panel.legend_columns(),
            frame=self.panel.legend_frame_var.get())
        if redraw:
            self.renderer.redraw()

    def on_edit_styles(self) -> None:
        if self.dataset is None:
            messagebox.showinfo("No data", "Open a CSV first to customize "
                                "its legend.", parent=self.root)
            return
        if not self.styles:
            messagebox.showinfo(
                "Not available", "Per-group styles can't be edited while "
                "Symbol by is set (colors and symbols come from the chosen "
                "columns). Set Symbol by to None to customize groups.",
                parent=self.root)
            return
        LegendEditorDialog(self.root, self.styles, self._push_points)

    def on_basemap(self) -> None:
        self._busy(True)
        try:
            self.renderer.set_basemap(self.panel.basemap_var.get())
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_continent(self) -> None:
        self.renderer.set_extent(self.panel.continent_var.get())
        self.toolbar.update()
        self.renderer.redraw()

    def on_projection(self) -> None:
        self.set_status(f"Reprojecting to {self.panel.projection_var.get()}"
                        f"\N{HORIZONTAL ELLIPSIS}")
        self._busy(True)
        try:
            self.renderer.set_projection(self.panel.projection_var.get())
        finally:
            self._busy(False)
        self.toolbar.update()
        self.set_status("Ready.")
        self.renderer.redraw()

    def on_line_width(self) -> None:
        self.renderer.set_line_width_scale(self.panel.line_width_var.get())
        self.renderer.redraw()

    def on_layer(self, key: str) -> None:
        visible = self.panel.layer_vars[key].get()
        if visible:
            self.set_status(f"Loading {key.replace('_', ' ')} layer"
                            f"\N{HORIZONTAL ELLIPSIS}")
            self._busy(True)
        try:
            self.renderer.set_layer(key, visible)
        finally:
            if visible:
                self._busy(False)
                self.set_status("Ready.")
        self.renderer.redraw()

    def on_lake_fill(self) -> None:
        self._busy(True)
        try:
            self.renderer.set_lake_fill(self.panel.lake_fill_var.get())
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_ocean(self) -> None:
        self._busy(True)
        try:
            self.renderer.set_ocean(self.panel.ocean_var.get())
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_label(self, key: str) -> None:
        self._busy(True)
        try:
            self.renderer.set_labels(key, self.panel.label_vars[key].get())
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_graticule(self) -> None:
        interval = self.panel.graticule_interval()
        self.renderer.set_graticule(
            interval, show_labels=not self.panel.hide_grid_labels_var.get())
        self.renderer.redraw()

    def on_save_png(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save map as PNG",
            defaultextension=".png", initialfile="map.png",
            filetypes=[("PNG image", "*.png")])
        if not path:
            return
        self._busy(True)
        try:
            self.renderer.save_png(path, dpi=int(self.panel.dpi_var.get()))
        except Exception as exc:  # noqa: BLE001 - show any save error
            self._busy(False)
            messagebox.showerror("Could not save PNG", str(exc),
                                 parent=self.root)
            return
        self._busy(False)
        self.set_status(f"Saved map to {path}")


def main() -> int:
    store = LayerStore()
    error = store.check_data()
    root = tk.Tk()
    if error:
        root.withdraw()
        messagebox.showerror("PyMappr - missing map data", error)
        return 1
    PyMapprApp(root, store)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
