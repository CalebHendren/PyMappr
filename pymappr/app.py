from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import sv_ttk
import matplotlib

matplotlib.use("TkAgg")

from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pymappr import __version__, updates  # noqa: E402
from pymappr.files import projects  # noqa: E402
from pymappr.files.projects import DatasetEntry  # noqa: E402
from pymappr.geo.layers import LayerStore  # noqa: E402
from pymappr.handlers import (  # noqa: E402
    DatasetsMixin, MapSettingsMixin, PresetsMixin, ProjectFilesMixin,
    StateMixin)
from pymappr.handlers.presets import BUILT_IN_PRESET  # noqa: E402
from pymappr.handlers.project_files import UNTITLED  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styling.decorations import InsetOptions  # noqa: E402
from pymappr.ui.control_panel import ControlPanel  # noqa: E402
from pymappr.ui.filter_bar import FilterBar  # noqa: E402
from pymappr.ui.map_canvas import DebouncedFigureCanvasTkAgg  # noqa: E402

# Still reachable from here: the tests stub pymappr.app.messagebox and
# pymappr.app.simpledialog, and scripts import the two constants.
__all__ = ["BUILT_IN_PRESET", "UNTITLED", "PyMapprApp", "filedialog", "main",
           "messagebox", "simpledialog"]


class PyMapprApp(ProjectFilesMixin, StateMixin, DatasetsMixin, PresetsMixin,
                 MapSettingsMixin):
    """The main window: the menus, the control panel and the map.

    The panel's handlers live in the mixins of pymappr.handlers, one per
    concern; they share the attributes set up in ``__init__``.
    """

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
        # The same two for the inset map.
        self._inset_corner = InsetOptions().position
        self._inset_anchor: tuple[float, float] | None = None
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
        self.canvas = DebouncedFigureCanvasTkAgg(figure, master=map_frame)
        self.renderer = MapRenderer(figure, store)

        toolbar_row = ttk.Frame(map_frame)
        toolbar_row.pack(side="top", fill="x")
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_row,
                                            pack_toolbar=False)
        self.toolbar.update()
        # The zoom buttons are packed first so they keep their room; the
        # toolbar, which stretches, gets whatever width is left.
        self._add_zoom_buttons(toolbar_row)
        self.toolbar.pack(side="left", fill="x", expand=True)

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
        # The map is packed last, so it takes the room between the toolbar
        # and the bars below it rather than squeezing them.
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        # Scroll wheel zooms the map about the cursor.
        self.canvas.mpl_connect("scroll_event", self._on_scroll_zoom)

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
        self._presets: dict[str, Path] = {}
        self._built_in = True
        self._refresh_presets()

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
        """Big, obvious zoom buttons at the right end of the toolbar row.

        Packed from the right, so the rightmost widget comes first."""
        ttk.Button(parent, text="\N{HEAVY PLUS SIGN} Zoom in",
                   command=lambda: self.zoom_step(1.5)).pack(side="right",
                                                             padx=(2, 4))
        ttk.Button(parent, text="\N{HEAVY MINUS SIGN} Zoom out",
                   command=lambda: self.zoom_step(1 / 1.5)).pack(side="right")
        ttk.Separator(parent, orient="vertical").pack(
            side="right", fill="y", padx=6, pady=2)

    def zoom_step(self, factor: float) -> None:
        """Zoom about the view center (buttons, Ctrl+= / Ctrl+-)."""
        self.renderer.zoom_interactive(factor)

    def _on_scroll_zoom(self, event) -> None:
        if event.inaxes is None or event.x is None:
            return
        factor = 1.25 if event.button == "up" else 1 / 1.25
        self.renderer.zoom_interactive(factor, (event.x, event.y))

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
