from __future__ import annotations

import dataclasses
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
                                 combine_name_columns, guess_mapping,
                                 headers_look_like_data, list_sheets,
                                 read_table)
from pymappr.decorations import (CompassOptions,  # noqa: E402
                                 ScaleBarOptions)
from pymappr.layers import LayerStore  # noqa: E402
from pymappr.layout import (MapLayout, column_key,  # noqa: E402
                            editor_rows, layout_points, with_default_title)
from pymappr.legend import (ENTRY_ORDERS, PUBLICATION_LEGEND,  # noqa: E402
                            LegendOptions)
from pymappr.projects import PROJECT_EXTENSION, DatasetEntry  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styles import (BLACK_AND_WHITE_NAME,  # noqa: E402
                            DEFAULT_PALETTE_NAME, LEGIBLE_MARKER_LIMIT,
                            POINT_EDGE_COLOR, POINT_EDGE_WIDTH, PointStyle,
                            apply_override, marker_load, resolve_nesting,
                            row_key)
from pymappr.ui.column_mapper import ColumnMapperDialog  # noqa: E402
from pymappr.ui.combine_columns import CombineColumnsDialog  # noqa: E402
from pymappr.ui.control_panel import ControlPanel, name_for  # noqa: E402
from pymappr.ui.filter_bar import FilterBar  # noqa: E402
from pymappr.ui.legend_editor import LegendEditorDialog  # noqa: E402
from pymappr.ui.manual_entry import ManualEntryDialog  # noqa: E402
from pymappr.ui.projects_dialog import ProjectsDialog  # noqa: E402

MAX_SKIPPED_SHOWN = 12
UNTITLED = "Untitled"
# The point and export half of the "Publication style" preset (the legend
# half is pymappr.legend.PUBLICATION_LEGEND).
PUBLICATION_POINT_EDGE = ("#000000", 0.6)
PUBLICATION_DPI = "600"
PROJECT_FILETYPES = [("PyMappr project", "*" + PROJECT_EXTENSION),
                     ("All files", "*.*")]


def _pinned_style(style: PointStyle) -> dict:
    """A legend-row override pinning every part of *style*."""
    return {"color": style.color, "marker": style.marker, "size": style.size}


class PyMapprApp:
    def __init__(self, root: tk.Tk, store: LayerStore,
                 restore_session: bool = True):
        self.root = root
        self.store = store
        self.entries: list[DatasetEntry] = []
        # The corner the scale bar was last told to sit in, so a
        # drag is only discarded when the user picks a new corner.
        self._scale_bar_corner = "lower left"
        # A dragged scale bar position restored from a project.
        self._scale_bar_anchor: tuple[float, float] | None = None
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
        # The legend warning currently on show, so a rebuild can withdraw it
        # without clobbering a status message from somewhere else.
        self._legend_warning = ""

        self.filter_bar = FilterBar(map_frame, self.on_filter)
        self.filter_bar.pack(side="bottom", fill="x")

        # Defaults: simple basemap with country borders.
        self.renderer.set_layer("countries", True)
        # Spinning the globe re-centres the projection; keep the panel's
        # centre controls in step with the drag.
        self.renderer.set_globe_rotate_callback(self.on_globe_rotated)
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
                              command=self.on_open_kofi)
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

    def on_open_kofi(self) -> None:
        webbrowser.open(updates.KOFI_URL)

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
                "compass_options": p.compass_options().to_dict(),
                "scale_bar": p.scale_bar_options(
                    self.renderer.scale_bar_anchor()).to_dict(),
                "palette": p.palette_var.get(),
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
            # Dragging state is not a legend *option* - it is where the user
            # last put the thing - but it belongs in the same section so a
            # reopened project finds the legend where it was left.
            "legend": {
                **p.legend_options().to_dict(),
                "draggable": p.legend_drag_var.get(),
                "anchor": list(self.renderer.legend_anchor() or ()) or None,
            },
            "point_alpha": p.point_alpha_var.get(),
            "point_edge": dict(zip(("color", "width"), p.point_edge())),
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
        # "compass" is the original bare flag; the options dict arrived
        # later, so an older project has only the flag and defaults the rest.
        compass = CompassOptions.from_dict(m.get("compass_options"))
        compass.show = bool(m.get("compass", compass.show))
        p.set_compass_options(compass)
        bar = ScaleBarOptions.from_dict(m.get("scale_bar"))
        p.set_scale_bar_options(bar)
        self._scale_bar_corner = bar.position
        self._scale_bar_anchor = bar.anchor
        p.palette_var.set(m.get("palette", DEFAULT_PALETTE_NAME))
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
        p.set_legend_options(LegendOptions.from_dict(legend))
        p.legend_drag_var.set(bool(legend.get("draggable", False)))
        self.renderer.set_legend_dragging(p.legend_drag_var.get())
        anchor = legend.get("anchor")
        self.renderer.set_legend_anchor(
            tuple(anchor) if isinstance(anchor, (list, tuple))
            and len(anchor) == 2 else None)
        p.set_point_alpha(state.get("point_alpha", defaults["point_alpha"]))
        # Projects saved before the outline was settable used white.
        edge = dict(state.get("point_edge") or {})
        try:
            edge_width = float(edge.get("width", POINT_EDGE_WIDTH))
        except (TypeError, ValueError):
            edge_width = POINT_EDGE_WIDTH
        p.set_point_edge(str(edge.get("color") or POINT_EDGE_COLOR),
                         edge_width)

        self._busy(True)
        try:
            renderer = self.renderer
            lon0, lat0 = p.projection_origin()
            renderer.set_projection(p.projection_var.get(), lon0, lat0)
            renderer.set_basemap(p.basemap_var.get())
            renderer.set_orientation(p.orientation())
            renderer.set_extent(p.continent_var.get())
            for setter, vars_ in ((renderer.set_layer, p.layer_vars),
                                  (renderer.set_fill_layer, p.fill_vars),
                                  (renderer.set_point_layer, p.point_vars)):
                for key, var in vars_.items():
                    self._apply_layer(setter, key, var.get(), var)
            renderer.set_bathymetry(p.bathymetry_var.get())
            renderer.set_capitals_only(p.capitals_only_var.get())
            renderer.set_ocean(p.ocean_var.get())
            renderer.set_lake_fill(p.lake_fill_var.get())
            for key, var in p.label_vars.items():
                renderer.set_labels(key, var.get())
            renderer.set_compass(p.compass_options())
            renderer.set_scale_bar(p.scale_bar_options(
                self._scale_bar_anchor))
            renderer.set_graticule(
                p.graticule_interval(),
                show_labels=not p.hide_grid_labels_var.get())
            renderer.set_line_width_scale(p.line_width_var.get())
            renderer.set_point_alpha(p.point_alpha_var.get())
            renderer.set_point_edge(*p.point_edge())
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

    def _apply_layer(self, setter, key: str, visible: bool,
                     var: tk.BooleanVar):
        """Show or hide one layer, unticking *var* when it cannot be drawn.

        Optional external layers (biodiversity, ecoregions) may not be
        downloaded, and any layer's data could be missing or corrupt. Returns
        None when it worked, ``"missing"`` when the data is not downloaded,
        or the exception that stopped it - the caller decides whether to
        say so (a toggle does, a project restore stays quiet)."""
        if visible and not self.store.has_layer_data(key):
            var.set(False)
            return "missing"
        try:
            setter(key, visible)
        except Exception as exc:  # noqa: BLE001 - a bad layer must not crash
            var.set(False)
            try:
                setter(key, False)  # drop any half-built artists
            except Exception:  # noqa: BLE001
                pass
            return exc
        return None

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
        self.renderer.set_structured_legend(layout.sections)
        self.renderer.set_legend_row_order(layout.row_order)
        self.renderer.set_point_groups(
            [(label, style, rows["lon"].to_numpy(), rows["lat"].to_numpy())
             for label, style, rows in layout.groups])
        self._apply_legend(redraw=False)
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
        # Row customizations are keyed by value, so any that still name a
        # group that exists keep applying and the rest lie dormant.
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

    def on_publication_style(self) -> None:
        """Apply several settings at once for a journal figure: black and
        white points with black outlines and varied shapes, a plain boxed
        legend with italic names, and 600 DPI export. Rows the user styled
        by hand in the legend editor keep their styling."""
        p = self.panel
        p.palette_var.set(BLACK_AND_WHITE_NAME)
        p.set_point_edge(*PUBLICATION_POINT_EDGE)
        p.set_point_alpha(1.0)
        p.set_legend_options(dataclasses.replace(p.legend_options(),
                                                 **PUBLICATION_LEGEND))
        p.dpi_var.set(PUBLICATION_DPI)
        # Three shades alone cannot tell more than three groups apart.
        for entry in self.entries:
            entry.vary_symbols = True
        p.vary_symbols_var.set(True)
        self.renderer.set_point_alpha(1.0)
        self.renderer.set_point_edge(*p.point_edge())
        self._push_points()
        self.set_status("Applied the publication style. Export with "
                        "File \N{RIGHTWARDS ARROW} Save map as "
                        f"({PUBLICATION_DPI} DPI).")

    def on_legend_options(self) -> None:
        """A look-only change: restyle the legend that is already there."""
        self._apply_legend()

    def on_legend_content(self) -> None:
        """A change to the rows themselves - counts, order, nesting, the
        text of a label. Those are baked into the rows when the groups are
        built, so this has to rebuild rather than restyle."""
        self._push_points()

    def on_legend_position(self) -> None:
        # Choosing a preset position discards any manual (dragged) placement.
        self.renderer.clear_legend_anchor()
        self._apply_legend()

    def _legend_options(self) -> LegendOptions:
        """The panel's legend settings, with the title defaulted."""
        return with_default_title(self.entries, self.panel.legend_options())

    def _apply_legend(self, redraw: bool = True) -> None:
        self.renderer.set_legend(self._legend_options())
        if redraw:
            self.renderer.redraw()

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
        self.panel.legend_order_var.set(
            name_for(ENTRY_ORDERS, "manual"))
        self._push_points()

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
                      var: tk.BooleanVar) -> None:
        """A layer checkbox changed: draw it with a busy cursor, and explain
        (and untick) when it cannot be drawn."""
        if visible:
            self.set_status(f"Loading {key.replace('_', ' ')} layer"
                            f"\N{HORIZONTAL ELLIPSIS}")
            self._busy(True)
        try:
            problem = self._apply_layer(setter, key, visible, var)
        finally:
            if visible:
                self._busy(False)
                self.set_status("Ready.")
        if problem == "missing":
            self._optional_layer_missing(key)
        elif problem is not None:
            self._layer_load_error(key, problem)
        else:
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
        self.renderer.set_compass(self.panel.compass_options())
        self.renderer.redraw()

    def on_scale_bar(self) -> None:
        """Any scale bar setting changed. A dragged position survives unless
        the user picked a different corner, which is a request to move it."""
        self.panel.update_scale_length_state()
        anchor = self.renderer.scale_bar_anchor()
        if self.panel.scale_position_var.get() != self._scale_bar_corner:
            self._scale_bar_corner = self.panel.scale_position_var.get()
            anchor = None
        self.renderer.set_scale_bar(self.panel.scale_bar_options(anchor))
        self.renderer.redraw()
        note = self.renderer.scale_bar_note()
        if note:
            self.set_status(note)

    def on_reset_scale_bar(self) -> None:
        """Send a dragged scale bar back to its chosen corner."""
        self.renderer.set_scale_bar(self.panel.scale_bar_options(None))
        self.renderer.redraw()

    def _palette(self) -> list[str]:
        """The colour palette groups are styled from."""
        return self.panel.palette()

    def on_palette(self) -> None:
        """The colour palette changed: restyle every dataset's groups.
        Colours pinned per legend row live in ``legend_overrides`` and stay
        pinned."""
        # White points vanish inside a white outline, so a palette with
        # white in it brings a black outline along.
        color, width = self.panel.point_edge()
        if ("#ffffff" in self._palette()
                and color.lower() in ("#ffffff", "white")):
            self.panel.set_point_edge("#000000", width)
            self.renderer.set_point_edge(*self.panel.point_edge())
            self.set_status("Point outline set to black so white points "
                            "stay visible.")
        self._push_points()

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
