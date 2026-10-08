"""ControlPanel: the mixins put together, plus the footer and the
theme refresh."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pymappr.ui.control_panel.data_tab import DataTabMixin
from pymappr.ui.control_panel.layers_tab import LayersTabMixin
from pymappr.ui.control_panel.map_tab import MapTabMixin
from pymappr.ui.control_panel.tables import PANEL_WIDTH
from pymappr.ui.control_panel.values import ValuesMixin
from pymappr.ui.control_panel.widgets import WidgetsMixin


class ControlPanel(ttk.Frame, WidgetsMixin, DataTabMixin, MapTabMixin,
                   LayersTabMixin, ValuesMixin):
    """The tabbed side panel. It owns the Tk variables and forwards
    changes to the app's handler methods; the app owns the renderer and
    the data."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.layer_vars: dict[str, tk.BooleanVar] = {}
        self.fill_vars: dict[str, tk.BooleanVar] = {}
        self.point_vars: dict[str, tk.BooleanVar] = {}
        self.label_vars: dict[str, tk.BooleanVar] = {}
        # Colour swatch buttons, keyed by the Tk name of the var they set
        # (StringVar itself is unhashable), so restoring a project can
        # repaint them to match the values it loaded.
        self._color_buttons: dict[str, tk.Button] = {}

        self.notebook = ttk.Notebook(self, width=PANEL_WIDTH)
        # The footer packs to the bottom edge first so the notebook fills
        # whatever height remains above it.
        self._build_footer()
        self.notebook.pack(fill="both", expand=True)

        data_tab = self._scroll_tab("Data")
        # The legend carries enough settings now to want its own tab rather
        # than a very long scroll under the data controls.
        legend_tab = self._scroll_tab("Legend")
        map_tab = self._scroll_tab("Map")
        layers_tab = self._scroll_tab("Layers")
        labels_tab = self._scroll_tab("Labels")

        self._build_presets_section(data_tab)
        self._build_data_section(data_tab)
        self._build_legend_section(legend_tab)

        self._build_view_section(map_tab)
        self._build_decorations_section(map_tab)
        self._build_inset_section(map_tab)
        self._build_graticule_section(map_tab)
        self._build_export_section(map_tab)

        self._build_layers_tab(layers_tab)
        self._build_labels_tab(labels_tab)

    # -------------------------------------------------------------- footer

    def _build_footer(self) -> None:
        """Persistent bar pinned to the bottom edge of the panel (below the
        notebook, so it shows on every tab): support and update actions."""
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=6, pady=(2, 4))
        ttk.Button(bar, text="\N{BLACK HEART SUIT} Support on Ko-fi",
                   command=self.app.on_open_kofi).pack(fill="x", pady=(2, 0))
        ttk.Button(bar, text="Check for updates\N{HORIZONTAL ELLIPSIS}",
                   command=self.app.on_check_updates).pack(fill="x",
                                                           pady=(2, 0))

    # --------------------------------------------------------------- theme

    def update_theme(self) -> None:
        """Refresh non-ttk widgets after a theme switch."""
        style = ttk.Style()
        bg = style.lookup("TFrame", "background") or "white"
        fg = style.lookup("TLabel", "foreground") or "black"
        sel = style.lookup("TButton", "background", ["active"]) or "#005fb8"
        # Canvas backgrounds in every scrollable tab.
        for tab_id in self.notebook.tabs():
            outer = self.nametowidget(tab_id)
            for child in outer.winfo_children():
                if isinstance(child, tk.Canvas):
                    child.configure(background=bg)
        # Dataset listbox.
        self.dataset_list.configure(
            background=bg, foreground=fg,
            selectbackground=sel, selectforeground="white")
