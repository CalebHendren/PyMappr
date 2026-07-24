from __future__ import annotations

import json
import shutil
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import sv_ttk
import matplotlib

matplotlib.use("TkAgg")

import pandas as pd  # noqa: E402

from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,  # noqa: E402
                                               NavigationToolbar2Tk)
from matplotlib.figure import Figure  # noqa: E402

from pymappr import __version__, projects, updates  # noqa: E402
from pymappr.data_loader import (OPEN_FILETYPES, PointDataset,  # noqa: E402
                                 build_dataset, build_manual_dataset,
                                 guess_mapping, headers_look_like_data,
                                 list_sheets, read_table)
from pymappr.layers import LayerStore  # noqa: E402
from pymappr.projects import PROJECT_EXTENSION, DatasetEntry  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styles import (NEUTRAL_MARKER_COLOR, PointStyle,  # noqa: E402
                            attribute_style_maps, default_styles,
                            group_points, style_by_attributes)
from pymappr.ui.column_mapper import ColumnMapperDialog  # noqa: E402
from pymappr.ui.control_panel import ControlPanel  # noqa: E402
from pymappr.ui.filter_bar import FilterBar  # noqa: E402
from pymappr.ui.legend_editor import LegendEditorDialog  # noqa: E402
from pymappr.ui.manual_entry import ManualEntryDialog  # noqa: E402
from pymappr.ui.projects_dialog import ProjectsDialog  # noqa: E402

MAX_SKIPPED_SHOWN = 12
UNTITLED = "Untitled"
PROJECT_FILETYPES = [("PyMappr project", "*" + PROJECT_EXTENSION),
                     ("All files", "*.*")]


class PyMapprApp:
    def __init__(self, root: tk.Tk, store: LayerStore,
                 restore_session: bool = True):
        self.root = root
        self.store = store
        self.entries: list[DatasetEntry] = []
        self.active: int | None = None
        self.project_path: Path | None = None
        self.project_name: str = UNTITLED

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

        toolbar_row = ttk.Frame(map_frame)
        toolbar_row.pack(side="top", fill="x")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_row,
                                            pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side="left", fill="x", expand=True)
        self._add_zoom_buttons(toolbar_row)
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        # Scroll wheel zooms the map about the cursor.
        self.canvas.mpl_connect("scroll_event", self._on_scroll_zoom)

        self.status = ttk.Label(map_frame, text="Ready. Add a data file or "
                                "enter points manually to plot them, or "
                                "explore the map layers.",
                                anchor="w", padding=(6, 2))
        self.status.pack(side="bottom", fill="x")

        self.filter_bar = FilterBar(map_frame, self.on_filter)
        self.filter_bar.pack(side="bottom", fill="x")

        # Defaults: simple basemap with country borders.
        self.renderer.set_layer("countries", True)
        self._style_toolbar()
        self.canvas.draw()

        # Everything a project stores, in its pristine state: New project
        # restores this, and unsaved-changes checks compare against it.
        self._default_state = self._collect_state()
        self._clean_snapshot = self._snapshot()
        self._set_title()

        # Closing the window autosaves the session for the next launch.
        root.protocol("WM_DELETE_WINDOW", self.on_exit)
        if restore_session:
            self._restore_session()

        # Pre-parse the most-used layers (and prime the on-disk cache) in
        # the background so the first layer toggles feel instant.
        threading.Thread(target=store.warm_cache, daemon=True).start()

        # Once-a-day update check, off the UI thread and after startup.
        root.after(2000, self._auto_update_check)

    # ----------------------------------------------------------------- menu

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New project", accelerator="Ctrl+N",
                              command=self.on_new_project)
        file_menu.add_command(label="Projects\N{HORIZONTAL ELLIPSIS}",
                              accelerator="Ctrl+P",
                              command=self.on_projects)
        file_menu.add_separator()
        file_menu.add_command(label="Save project", accelerator="Ctrl+S",
                              command=self.on_save_project)
        file_menu.add_command(label="Save project as"
                              "\N{HORIZONTAL ELLIPSIS}",
                              command=self.on_save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Import project"
                              "\N{HORIZONTAL ELLIPSIS}",
                              command=self.on_import_project)
        file_menu.add_command(label="Export project"
                              "\N{HORIZONTAL ELLIPSIS}",
                              command=self.on_export_project)
        file_menu.add_command(label="Set projects folder"
                              "\N{HORIZONTAL ELLIPSIS}",
                              command=self.on_set_projects_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Add data file\N{HORIZONTAL ELLIPSIS}",
                              accelerator="Ctrl+O",
                              command=self.on_add_file)
        file_menu.add_command(label="Manual entry\N{HORIZONTAL ELLIPSIS}",
                              accelerator="Ctrl+M",
                              command=self.on_manual_entry)
        file_menu.add_separator()
        file_menu.add_command(label="Save map as\N{HORIZONTAL ELLIPSIS}",
                              accelerator="Ctrl+E",
                              command=self.on_save_image)
        file_menu.add_command(label="Export map as code (Python/R)"
                              "\N{HORIZONTAL ELLIPSIS}",
                              command=self.on_export_code)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        self._theme_var = tk.StringVar(value=sv_ttk.get_theme())
        view_menu.add_radiobutton(label="Light theme",
                                  variable=self._theme_var, value="light",
                                  command=self._apply_theme)
        view_menu.add_radiobutton(label="Dark theme",
                                  variable=self._theme_var, value="dark",
                                  command=self._apply_theme)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About PyMappr", command=self._about)
        help_menu.add_command(label="Check for updates"
                              "\N{HORIZONTAL ELLIPSIS}",
                              command=self.on_check_updates)
        help_menu.add_separator()
        help_menu.add_command(label="Support me on Ko-fi",
                              command=self._open_kofi)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)
        self.root.bind("<Control-n>", lambda _e: self.on_new_project())
        self.root.bind("<Control-p>", lambda _e: self.on_projects())
        self.root.bind("<Control-s>", lambda _e: self.on_save_project())
        self.root.bind("<Control-o>", lambda _e: self.on_add_file())
        self.root.bind("<Control-m>", lambda _e: self.on_manual_entry())
        self.root.bind("<Control-e>", lambda _e: self.on_save_image())
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.root.bind(seq, lambda _e: self.zoom_step(1.3))
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.root.bind(seq, lambda _e: self.zoom_step(1 / 1.3))

    def _set_title(self) -> None:
        self.root.title(f"PyMappr \N{EN DASH} {self.project_name}")

    # ----------------------------------------------------------------- zoom

    def _add_zoom_buttons(self, parent) -> None:
        """Big, obvious zoom buttons next to the matplotlib toolbar."""
        ttk.Separator(parent, orient="vertical").pack(
            side="left", fill="y", padx=6, pady=2)
        ttk.Button(parent, text="\N{HEAVY MINUS SIGN} Zoom out",
                   command=lambda: self.zoom_step(1 / 1.5)).pack(side="left")
        ttk.Button(parent, text="\N{HEAVY PLUS SIGN} Zoom in",
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

    def _apply_theme(self) -> None:
        theme = self._theme_var.get()
        sv_ttk.set_theme(theme)
        settings = projects.load_settings()
        settings["theme"] = theme
        projects.save_settings(settings)
        # Update non-ttk widgets that don't respond to theme changes.
        self.panel.update_theme()
        self._style_toolbar()

    def _style_toolbar(self) -> None:
        """Re-colour the matplotlib toolbar and canvas to match the theme."""
        style = ttk.Style()
        bg = style.lookup("TFrame", "background") or "white"
        fg = style.lookup("TLabel", "foreground") or "black"
        # Portrait side bars use the UI background so the map sits on a mat.
        self.renderer.set_mat_color(bg)
        self.toolbar.configure(background=bg)
        for child in self.toolbar.winfo_children():
            try:
                child.configure(background=bg, foreground=fg)
            except tk.TclError:
                try:
                    child.configure(background=bg)
                except tk.TclError:
                    pass
        # Re-render toolbar icons so matplotlib picks up the new
        # background colour and recolours icons for contrast.
        self.toolbar._rescale()
        self.canvas.get_tk_widget().configure(background=bg)

    def _about(self) -> None:
        messagebox.showinfo(
            "About PyMappr",
            f"PyMappr {__version__}\n\n"
            "Simple mapping software: plot point data on a world map.\n\n"
            "Map data \N{COPYRIGHT SIGN} Natural Earth (public domain),\n"
            "naturalearthdata.com",
            parent=self.root)

    def _open_kofi(self) -> None:
        from pymappr.ui.control_panel import KOFI_URL
        webbrowser.open(KOFI_URL)

    # -------------------------------------------------------------- updates

    def _auto_update_check(self) -> None:
        updates.check_daily_async(
            lambda version: self.root.after(0, self._offer_update, version))

    def on_check_updates(self) -> None:
        """Manual check (Help menu / panel button): always reports a result."""
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

    # ------------------------------------------------------------- projects

    def _snapshot(self) -> str:
        return json.dumps(self._collect_state(), sort_keys=True, default=str)

    def _mark_clean(self) -> None:
        self._clean_snapshot = self._snapshot()

    def _confirm_discard(self) -> bool:
        """Offer to save unsaved changes; False means the user cancelled."""
        if self._snapshot() == self._clean_snapshot:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save changes to \N{LEFT DOUBLE QUOTATION MARK}"
            f"{self.project_name}\N{RIGHT DOUBLE QUOTATION MARK} first?",
            parent=self.root)
        if answer is None:
            return False
        if answer:
            return self.on_save_project()
        return True

    def on_new_project(self) -> None:
        if not self._confirm_discard():
            return
        self._apply_state(json.loads(json.dumps(self._default_state)))
        self.project_path = None
        self.project_name = UNTITLED
        self._mark_clean()
        self._set_title()
        self.set_status("Started a new project.")

    def on_projects(self) -> None:
        """Open the project manager (open / rename / delete)."""
        dialog = ProjectsDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.open_path is not None:
            self._open_project_path(dialog.open_path)

    def _open_project_path(self, path: Path | str) -> None:
        if not self._confirm_discard():
            return
        try:
            _name, state = projects.load_project(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open project", str(exc), parent=self.root)
            return
        try:
            self._apply_state(state)
        except Exception as exc:  # noqa: BLE001 - corrupt/edited file
            messagebox.showerror(
                "Open project",
                f"Could not open the project:\n{exc}", parent=self.root)
            return
        self.project_path = Path(path)
        self.project_name = self.project_path.stem
        self._mark_clean()
        self._set_title()
        self.set_status(f"Opened project {self.project_name}.")

    def on_save_project(self) -> bool:
        if self.project_path is None:
            return self.on_save_project_as()
        try:
            projects.save_project(self.project_path, self.project_name,
                                  self._collect_state())
        except OSError as exc:
            messagebox.showerror("Save project", str(exc), parent=self.root)
            return False
        self._mark_clean()
        self.set_status(f"Saved project to {self.project_path}.")
        return True

    def on_save_project_as(self) -> bool:
        name = simpledialog.askstring(
            "Save project", "Project name:",
            initialvalue="" if self.project_name == UNTITLED
            else self.project_name, parent=self.root)
        if not name or not name.strip():
            return False
        name = name.strip()
        path = (projects.projects_dir()
                / (projects.safe_filename(name) + PROJECT_EXTENSION))
        if path.exists() and path != self.project_path:
            if not messagebox.askyesno(
                    "Save project",
                    f"A project named \N{LEFT DOUBLE QUOTATION MARK}{name}"
                    f"\N{RIGHT DOUBLE QUOTATION MARK} already exists. "
                    "Overwrite it?", parent=self.root):
                return False
        self.project_path = path
        self.project_name = name
        self._set_title()
        return self.on_save_project()

    def on_import_project(self) -> None:
        """Copy a shared project file into the projects folder and open it."""
        source = filedialog.askopenfilename(
            parent=self.root, title="Import project",
            filetypes=PROJECT_FILETYPES)
        if not source:
            return
        try:
            projects.load_project(source)  # validate before copying
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import project", str(exc),
                                 parent=self.root)
            return
        folder = projects.projects_dir()
        base = projects.safe_filename(Path(source).stem)
        target = folder / (base + PROJECT_EXTENSION)
        counter = 2
        while target.exists():
            target = folder / f"{base} ({counter}){PROJECT_EXTENSION}"
            counter += 1
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            messagebox.showerror("Import project", str(exc),
                                 parent=self.root)
            return
        self._open_project_path(target)

    def on_export_project(self) -> None:
        """Save the current project anywhere, for sharing."""
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export project",
            defaultextension=PROJECT_EXTENSION,
            initialfile=(projects.safe_filename(self.project_name)
                         + PROJECT_EXTENSION),
            filetypes=PROJECT_FILETYPES)
        if not path:
            return
        try:
            projects.save_project(path, self.project_name,
                                  self._collect_state())
        except OSError as exc:
            messagebox.showerror("Export project", str(exc),
                                 parent=self.root)
            return
        self.set_status(f"Exported project to {path}")

    def on_set_projects_folder(self) -> None:
        folder = filedialog.askdirectory(
            parent=self.root, title="Choose the folder to save projects in",
            initialdir=str(projects.projects_dir()))
        if not folder:
            return
        projects.set_projects_dir(folder)
        self.set_status(f"Projects are now saved in {folder}")

    def on_exit(self) -> None:
        self._save_session()
        self.root.destroy()

    # -------------------------------------------------------------- session

    def _save_session(self) -> None:
        """Autosave everything so the next launch resumes where we left off."""
        try:
            state = self._collect_state()
            state["project_path"] = (str(self.project_path)
                                     if self.project_path else "")
            state["project_name"] = self.project_name
            state["geometry"] = self.root.geometry()
            projects.save_project(projects.session_path(),
                                  self.project_name, state)
        except Exception:  # noqa: BLE001 - never block closing the app
            pass

    def _restore_session(self) -> None:
        path = projects.session_path()
        if not path.exists():
            return
        try:
            _name, state = projects.load_project(path)
            geometry = state.get("geometry")
            if geometry:
                self.root.geometry(str(geometry))
            self._apply_state(state)
            stored = str(state.get("project_path") or "")
            self.project_path = (Path(stored)
                                 if stored and Path(stored).exists()
                                 else None)
            self.project_name = (str(state.get("project_name") or "")
                                 or UNTITLED)
            self._mark_clean()
            self._set_title()
            if self.entries:
                self.set_status("Restored your previous session.")
        except Exception:  # noqa: BLE001 - a bad session must not block startup
            pass

    # ---------------------------------------------------------------- state

    def _collect_state(self) -> dict:
        """Everything a project stores, as a JSON-safe dict."""
        p = self.panel
        xlim, ylim = self.renderer.get_view()
        return {
            "datasets": [projects.entry_to_dict(e) for e in self.entries],
            "active": self.active,
            "map": {
                "projection": p.projection_var.get(),
                "proj_lon0": p.proj_lon0_var.get(),
                "proj_lat0": p.proj_lat0_var.get(),
                "basemap": p.basemap_var.get(),
                "continent": p.continent_var.get(),
                "orientation": p.orientation_var.get(),
                "compass": p.compass_var.get(),
                "graticule": p.graticule_var.get(),
                "hide_grid_labels": p.hide_grid_labels_var.get(),
                "line_width": p.line_width_var.get(),
                "dpi": p.dpi_var.get(),
                "ocean": p.ocean_var.get(),
                "lake_fill": p.lake_fill_var.get(),
                "bathymetry": p.bathymetry_var.get(),
                "capitals_only": p.capitals_only_var.get(),
                "lines": {k: v.get() for k, v in p.layer_vars.items()},
                "fills": {k: v.get() for k, v in p.fill_vars.items()},
                "points": {k: v.get() for k, v in p.point_vars.items()},
                "labels": {k: v.get() for k, v in p.label_vars.items()},
            },
            "legend": {
                "show": p.legend_show_var.get(),
                "frame": p.legend_frame_var.get(),
                "location": p.legend_loc_var.get(),
                "fontsize": p.legend_fontsize_var.get(),
                "title_fontsize": p.legend_title_fontsize_var.get(),
                "columns": p.legend_columns_var.get(),
                "marker_scale": p.legend_marker_scale_var.get(),
                "label_spacing": p.legend_label_spacing_var.get(),
                "title": p.legend_title_var.get(),
            },
            "point_alpha": p.point_alpha_var.get(),
            "view": {"xlim": list(xlim), "ylim": list(ylim)},
        }

    def _apply_state(self, state: dict) -> None:
        """Restore a collected state: datasets, map settings, and view."""
        p = self.panel
        defaults = self._default_state

        self.entries = [projects.entry_from_dict(d)
                        for d in state.get("datasets", [])]
        active = state.get("active")
        if not (isinstance(active, int) and 0 <= active < len(self.entries)):
            active = 0 if self.entries else None
        self.active = active

        m = {**defaults["map"], **dict(state.get("map", {}))}
        legend = {**defaults["legend"], **dict(state.get("legend", {}))}

        p.projection_var.set(m["projection"])
        p.proj_lon0_var.set(m.get("proj_lon0", ""))
        p.proj_lat0_var.set(m.get("proj_lat0", ""))
        p.update_projection_origin(m["projection"])
        basemap = m["basemap"]
        if basemap == "satellite":
            basemap = "relief"  # migrate legacy value
        p.basemap_var.set(basemap)
        p.continent_var.set(m["continent"])
        p.orientation_var.set(m.get("orientation", "Landscape"))
        p.compass_var.set(m["compass"])
        p.graticule_var.set(m["graticule"])
        p.hide_grid_labels_var.set(m["hide_grid_labels"])
        p.line_width_var.set(m["line_width"])
        p.dpi_var.set(m["dpi"])
        p.ocean_var.set(m["ocean"])
        p.lake_fill_var.set(m["lake_fill"])
        p.bathymetry_var.set(m["bathymetry"])
        p.capitals_only_var.set(m["capitals_only"])
        for section, vars_ in (("lines", p.layer_vars),
                               ("fills", p.fill_vars),
                               ("points", p.point_vars),
                               ("labels", p.label_vars)):
            stored = {**defaults["map"][section], **dict(m.get(section, {}))}
            for key, var in vars_.items():
                var.set(bool(stored.get(key, False)))
        p.legend_show_var.set(legend["show"])
        p.legend_frame_var.set(legend["frame"])
        p.legend_loc_var.set(legend["location"])
        p.legend_fontsize_var.set(legend["fontsize"])
        p.legend_title_fontsize_var.set(legend["title_fontsize"])
        p.legend_columns_var.set(legend["columns"])
        p.legend_marker_scale_var.set(legend["marker_scale"])
        p.legend_label_spacing_var.set(legend["label_spacing"])
        p.legend_title_var.set(legend["title"])
        p.point_alpha_var.set(state.get("point_alpha",
                                        defaults["point_alpha"]))

        self._busy(True)
        try:
            renderer = self.renderer
            lon0, lat0 = p.projection_origin()
            renderer.set_projection(p.projection_var.get(), lon0, lat0)
            renderer.set_basemap(p.basemap_var.get())
            renderer.set_orientation(p.orientation())
            renderer.set_extent(p.continent_var.get())
            for key, var in p.layer_vars.items():
                self._restore_layer(renderer.set_layer, key, var)
            for key, var in p.fill_vars.items():
                self._restore_layer(renderer.set_fill_layer, key, var)
            for key, var in p.point_vars.items():
                self._restore_layer(renderer.set_point_layer, key, var)
            renderer.set_bathymetry(p.bathymetry_var.get())
            renderer.set_capitals_only(p.capitals_only_var.get())
            renderer.set_ocean(p.ocean_var.get())
            renderer.set_lake_fill(p.lake_fill_var.get())
            for key, var in p.label_vars.items():
                renderer.set_labels(key, var.get())
            renderer.set_compass(p.compass_var.get())
            renderer.set_graticule(
                p.graticule_interval(),
                show_labels=not p.hide_grid_labels_var.get())
            renderer.set_line_width_scale(p.line_width_var.get())
            renderer.set_point_alpha(p.point_alpha_var.get())
        finally:
            self._busy(False)

        view = dict(state.get("view", {}))
        xlim, ylim = view.get("xlim"), view.get("ylim")
        if (isinstance(xlim, (list, tuple)) and len(xlim) == 2
                and isinstance(ylim, (list, tuple)) and len(ylim) == 2):
            self.renderer.set_view(xlim, ylim)
        self.toolbar.update()

        self._sync_dataset_ui()
        self._push_points()

    # ----------------------------------------------------------------- data

    def _restore_layer(self, setter, key: str,
                       var: tk.BooleanVar) -> None:
        """Apply one layer toggle while restoring state, tolerating optional
        layers whose data was never downloaded (untick them silently instead
        of aborting the whole restore)."""
        want = var.get()
        if want and not self.store.has_layer_data(key):
            var.set(False)
            return
        try:
            setter(key, want)
        except Exception:  # noqa: BLE001 - a bad layer must not block restore
            var.set(False)
            try:
                setter(key, False)
            except Exception:  # noqa: BLE001
                pass

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
            styles={r["legend"]: r["style"]},
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
        style = entry.styles.get(entry.name) or PointStyle()
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
        entry.dataset = dataset
        entry.name = r["legend"]
        entry.styles = {r["legend"]: r["style"]}
        entry.manual = {"text": r["text"], "order": r["order"]}
        self._sync_dataset_ui()
        self._push_points()
        self.set_status(f"Updated {entry.name}: {len(dataset)} points.")

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
        self.panel.dataset_visible_var.set(entry.visible)
        self.filter_bar.set_dataset(entry.dataset.frame,
                                    entry.dataset.name_labels,
                                    entry.dataset.name_keys)

    # ------------------------------------------------------------ rendering

    @staticmethod
    def _entry_key(entry: DatasetEntry, label: str) -> str | None:
        """Frame column key for a name-column display label ("" = None)."""
        if not label or label == "None":
            return None
        mapping = dict(zip(entry.dataset.name_labels,
                           entry.dataset.name_keys))
        return mapping.get(label)

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

    def _push_points(self) -> None:
        """Rebuild the plotted points and legend from every visible
        dataset."""
        visible = [e for e in self.entries if e.visible and len(e.dataset)]
        multi = len(visible) > 1
        any_attr = any(self._entry_key(e, e.symbol_by) is not None
                       for e in visible)
        render_groups: list = []
        sections: list = []
        palette_offset = 0
        used_labels: set[str] = set()
        for entry in visible:
            if self._entry_key(entry, entry.symbol_by) is not None:
                groups, entry_sections = self._attribute_groups(entry, multi)
                render_groups += groups
                sections += entry_sections
            else:
                groups, legend_entries, palette_offset = self._plain_groups(
                    entry, palette_offset, multi, used_labels)
                render_groups += groups
                if any_attr and legend_entries:
                    sections.append((entry.name, legend_entries))
        self.renderer.set_structured_legend(sections if any_attr else None)
        self.renderer.set_point_groups(render_groups)
        self._apply_legend(redraw=False)
        self.renderer.redraw()

    def _plain_groups(self, entry: DatasetEntry, palette_offset: int,
                      multi: bool, used_labels: set[str]):
        """Render groups for a dataset in group-by mode. Styles come from
        the full, unfiltered grouping so each group's color/symbol stays
        put while filter values are toggled."""
        frame = entry.dataset.frame
        group_key = self._entry_key(entry, entry.group_by)
        groups = group_points(frame, group_key)
        labels = [label for label, _ in groups]
        color_key = self._entry_key(entry, entry.color_by)
        color_keys = None
        if color_key is not None and color_key in frame.columns:
            # One color-key per group: the group's value in the color-by
            # column (e.g. every cat group keyed "Felines").
            color_keys = [str(sub[color_key].iloc[0]) if len(sub) else ""
                          for _label, sub in groups]
        fresh = default_styles(labels, color_keys=color_keys,
                               vary_symbols=entry.vary_symbols,
                               palette_offset=palette_offset)
        # Keep customized styles for groups that still exist.
        entry.styles = {lb: entry.styles.get(lb, fresh[lb]) for lb in labels}
        shown = group_points(self._filtered_frame(entry), group_key)
        render = []
        legend_entries = []
        for label, sub in shown:
            style = entry.styles.get(label, PointStyle())
            display = label
            # With several datasets on the map, disambiguate legend rows:
            # a lone "All points" group takes the dataset's name, and a
            # label already used by another dataset gets it appended.
            if multi and label == "All points":
                display = entry.name
            elif multi and label in used_labels:
                display = f"{label} ({entry.name})"
            used_labels.add(display)
            render.append((display, style, sub["lon"].to_numpy(),
                           sub["lat"].to_numpy()))
            legend_entries.append((display, style))
        return render, legend_entries, palette_offset + len(labels)

    def _attribute_groups(self, entry: DatasetEntry, multi: bool):
        """Render groups + legend sections for a dataset styled by a color
        column and a symbol column at once (Symbol by set). Style maps come
        from the full dataset so colors, symbols, and the legend stay
        stable as the filter hides values."""
        frame = entry.dataset.frame
        color_key = self._entry_key(entry, entry.color_by)
        symbol_key = self._entry_key(entry, entry.symbol_by)
        color_map, symbol_map = attribute_style_maps(frame, color_key,
                                                     symbol_key)
        shown_frame = self._filtered_frame(entry)
        groups = style_by_attributes(shown_frame, color_key, symbol_key,
                                     color_map, symbol_map)
        entry.styles = {}
        render = [
            (label, style, sub["lon"].to_numpy(), sub["lat"].to_numpy())
            for label, style, sub in groups
        ]

        # Legend sections list only the values currently shown: anything
        # unticked in the filter bar disappears from the legend too.
        def shown_values(key):
            if key is None or key not in shown_frame.columns:
                return None
            return set(shown_frame[key].fillna(""))

        prefix = f"{entry.name}: " if multi else ""
        shown_colors = shown_values(color_key)
        shown_symbols = shown_values(symbol_key)
        sections = []
        if color_map:
            entries = [(value, PointStyle(color=color, marker="Circle"))
                       for value, color in color_map.items()
                       if shown_colors is None or value in shown_colors]
            if entries:
                sections.append((prefix + (entry.color_by or "Color"),
                                 entries))
        if symbol_map:
            entries = [(value, PointStyle(color=NEUTRAL_MARKER_COLOR,
                                          marker=marker))
                       for value, marker in symbol_map.items()
                       if shown_symbols is None or value in shown_symbols]
            if entries:
                sections.append((prefix + (entry.symbol_by or "Symbol"),
                                 entries))
        return render, sections

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
        x0 = min(frame["lon"].min() for frame in frames)
        x1 = max(frame["lon"].max() for frame in frames)
        y0 = min(frame["lat"].min() for frame in frames)
        y1 = max(frame["lat"].max() for frame in frames)
        pad_x = max((x1 - x0) * 0.15, 2.0)
        pad_y = max((y1 - y0) * 0.15, 2.0)
        self.renderer.set_extent((max(x0 - pad_x, -180), min(x1 + pad_x, 180),
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
        # New grouping: rebuild styles from scratch for the new groups.
        entry.styles = {}
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
        entry.styles = {}
        self._push_points()

    def on_point_alpha(self) -> None:
        self.renderer.set_point_alpha(self.panel.point_alpha_var.get())
        self.renderer.redraw()

    def on_legend_options(self) -> None:
        self._apply_legend()

    def on_legend_position(self) -> None:
        # Choosing a preset position discards any manual (dragged) placement.
        self.renderer.clear_legend_anchor()
        self._apply_legend()

    def _apply_legend(self, redraw: bool = True) -> None:
        title = self.panel.legend_title_var.get().strip() or None
        # With a single dataset in plain mode, default the title to its
        # group-by column; in two-attribute mode the legend's own sections
        # name the columns, and with several datasets no one column fits.
        visible = [e for e in self.entries if e.visible and len(e.dataset)]
        if (title is None and len(visible) == 1
                and self._entry_key(visible[0], visible[0].symbol_by)
                is None):
            title = visible[0].group_by or None
        self.renderer.set_legend(
            self.panel.legend_show_var.get(), title,
            self.panel.legend_loc_var.get(),
            fontsize=self.panel.legend_fontsize(),
            columns=self.panel.legend_columns(),
            frame=self.panel.legend_frame_var.get(),
            title_fontsize=self.panel.legend_title_fontsize(),
            marker_scale=self.panel.legend_marker_scale(),
            label_spacing=self.panel.legend_label_spacing())
        if redraw:
            self.renderer.redraw()

    def on_edit_styles(self) -> None:
        entry = self._active_entry()
        if entry is None:
            messagebox.showinfo("No data", "Add a dataset first to "
                                "customize its legend.", parent=self.root)
            return
        if not entry.styles:
            messagebox.showinfo(
                "Not available", "Per-group styles can't be edited while "
                "Symbol by is set (colors and symbols come from the chosen "
                "columns). Set Symbol by to None to customize groups.",
                parent=self.root)
            return
        LegendEditorDialog(self.root, entry.styles, self._push_points)

    def on_basemap(self) -> None:
        mode = self.panel.basemap_var.get()
        if mode != "simple" and not self.store.has_basemap(mode):
            self.panel.basemap_var.set("simple")
            messagebox.showinfo(
                "Basemap not downloaded",
                f"The {mode.replace('_', ' ')} raster is not available.\n\n"
                "Run 'python scripts/fetch_data.py' to download additional "
                "basemap rasters, then select it again.",
                parent=self.root)
            return
        self._busy(True)
        try:
            self.renderer.set_basemap(mode)
        finally:
            self._busy(False)
        self.renderer.redraw()

    def on_continent(self) -> None:
        self.renderer.set_extent(self.panel.continent_var.get())
        self.toolbar.update()
        self.renderer.redraw()

    def on_orientation(self) -> None:
        self.renderer.set_orientation(self.panel.orientation())
        self.toolbar.update()  # re-frame becomes the toolbar's Home
        self.renderer.redraw()

    def on_projection(self) -> None:
        name = self.panel.projection_var.get()
        # A newly chosen Lambert projection seeds its preset origin; other
        # projections disable the origin controls.
        self.panel.update_projection_origin(name, reset=True)
        lon0, lat0 = self.panel.projection_origin()
        self.set_status(f"Reprojecting to {name}\N{HORIZONTAL ELLIPSIS}")
        self._busy(True)
        try:
            self.renderer.set_projection(name, lon0, lat0)
        finally:
            self._busy(False)
        self.toolbar.update()
        self.set_status("Ready.")
        self.renderer.redraw()

    def on_projection_origin(self) -> None:
        """Re-centre a Lambert projection on an edited point of natural
        origin (central meridian / latitude of origin). A no-op for the
        world projections, whose origin controls are disabled."""
        name = self.panel.projection_var.get()
        lon0, lat0 = self.panel.projection_origin()
        self._busy(True)
        try:
            self.renderer.set_projection(name, lon0, lat0)
        finally:
            self._busy(False)
        self.toolbar.update()
        self.renderer.redraw()

    def on_line_width(self) -> None:
        self.renderer.set_line_width_scale(self.panel.line_width_var.get())
        self.renderer.redraw()

    def _toggle_layer(self, key: str, visible: bool, setter,
                      var: tk.BooleanVar | None = None) -> None:
        """Shared busy-cursor plumbing for every kind of layer toggle.

        Optional external layers (biodiversity, ecoregions) may not be
        downloaded, and any layer's data could be missing or corrupt; rather
        than crash, revert the checkbox and explain."""
        if visible and not self.store.has_layer_data(key):
            if var is not None:
                var.set(False)
            self._optional_layer_missing(key)
            return
        if visible:
            self.set_status(f"Loading {key.replace('_', ' ')} layer"
                            f"\N{HORIZONTAL ELLIPSIS}")
            self._busy(True)
        try:
            setter(key, visible)
        except Exception as exc:  # noqa: BLE001 - a bad layer must not crash
            if visible:
                self._busy(False)
                self.set_status("Ready.")
                if var is not None:
                    var.set(False)
                try:
                    setter(key, False)  # drop any half-built artists
                except Exception:  # noqa: BLE001
                    pass
            self._layer_load_error(key, exc)
            return
        if visible:
            self._busy(False)
            self.set_status("Ready.")
        self.renderer.redraw()

    def _optional_layer_missing(self, key: str) -> None:
        label = key.replace("_", " ")
        messagebox.showinfo(
            "Layer not downloaded",
            f"The {label} layer is an optional dataset that has not been "
            "downloaded yet.\n\nRun 'python scripts/fetch_data.py' to fetch "
            "the biodiversity and ecoregion layers, then tick the box again.",
            parent=self.root)
        self.set_status(f"{label.capitalize()} layer not available.")

    def _layer_load_error(self, key: str, exc: Exception) -> None:
        messagebox.showwarning(
            "Could not load layer",
            f"The {key.replace('_', ' ')} layer could not be loaded:\n\n{exc}",
            parent=self.root)
        self.set_status("Ready.")

    def on_layer(self, key: str) -> None:
        self._toggle_layer(key, self.panel.layer_vars[key].get(),
                           self.renderer.set_layer,
                           self.panel.layer_vars[key])

    def on_fill_layer(self, key: str) -> None:
        self._toggle_layer(key, self.panel.fill_vars[key].get(),
                           self.renderer.set_fill_layer,
                           self.panel.fill_vars[key])

    def on_point_layer(self, key: str) -> None:
        self._toggle_layer(key, self.panel.point_vars[key].get(),
                           self.renderer.set_point_layer,
                           self.panel.point_vars[key])

    def on_bathymetry(self) -> None:
        self._toggle_layer(
            "bathymetry", self.panel.bathymetry_var.get(),
            lambda _key, visible: self.renderer.set_bathymetry(visible),
            self.panel.bathymetry_var)

    def on_capitals_only(self) -> None:
        self.renderer.set_capitals_only(self.panel.capitals_only_var.get())
        self.renderer.redraw()

    def on_compass(self) -> None:
        self.renderer.set_compass(self.panel.compass_var.get())
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

    def on_label_drag_toggle(self) -> None:
        self.renderer.set_label_dragging(
            self.panel.label_drag_var.get())

    def on_legend_drag_toggle(self) -> None:
        self.renderer.set_legend_dragging(
            self.panel.legend_drag_var.get())

    def on_graticule(self) -> None:
        interval = self.panel.graticule_interval()
        self.renderer.set_graticule(
            interval, show_labels=not self.panel.hide_grid_labels_var.get())
        self.renderer.redraw()

    def on_save_image(self) -> None:
        """Open the "Save map as..." dialog (format, resolution and DPI)."""
        from pymappr.ui.save_image import SaveImageDialog

        SaveImageDialog(self.root, self)

    def on_export_code(self) -> None:
        """Show the map as ready-to-run Python or R code (assembled from
        pre-made function templates, not an AI model)."""
        from pymappr.ui.code_export import CodeExportDialog

        CodeExportDialog(self.root, self)


def main() -> int:
    store = LayerStore()
    error = store.check_data()
    root = tk.Tk()
    theme = projects.load_settings().get("theme", "light")
    if theme not in ("light", "dark"):
        theme = "light"
    sv_ttk.set_theme(theme)
    if error:
        root.withdraw()
        messagebox.showerror("PyMappr - missing map data", error)
        return 1
    PyMapprApp(root, store)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
