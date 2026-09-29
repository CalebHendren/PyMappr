"""Screenshot the running app for the README.

Needs a display. On Linux, run it under Xvfb with a screen bigger than the
app's 1280x800 window:

    xvfb-run -a -s "-screen 0 1600x1000x24" python scripts/make_app_screenshot.py

Use a Python whose Tk draws text through Xft (distribution and python.org
builds do); without it, symbols such as the heart come out as ``\\u2665``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import tkinter as tk  # noqa: E402

import sv_ttk  # noqa: E402

from pymappr.app import PyMapprApp  # noqa: E402
from pymappr.data_loader import load_csv  # noqa: E402
from pymappr.layers import LayerStore  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "images"


def new_root(geometry: str) -> tk.Tk:
    """A Tk root in the app's light theme, as ``pymappr.app.main`` sets up."""
    root = tk.Tk()
    root.geometry(geometry)
    sv_ttk.set_theme("light")
    return root


def load_sample(app: PyMapprApp, name: str, group_by: str | None = None) -> None:
    """Load a bundled CSV exactly as the Add data file flow would."""
    from pymappr.projects import DatasetEntry

    dataset = load_csv(str(REPO_ROOT / "sample_data" / name))
    labels = dataset.name_labels
    app._add_entry(DatasetEntry(
        dataset=dataset, name=name,
        group_by=group_by or (labels[0] if labels else "")))


def select_tab(panel, title: str) -> None:
    """Show a control-panel tab by name, so adding a tab cannot silently
    shift these screenshots onto the wrong one."""
    for index in range(panel.notebook.index("end")):
        if panel.notebook.tab(index, "text") == title:
            panel.notebook.select(index)
            return
    raise SystemExit(f"no {title!r} tab in the control panel")


def grab_window(root: tk.Tk, path: Path) -> None:
    """Screenshot the app window (crops a full-screen X grab)."""
    from PIL import ImageGrab

    root.update_idletasks()
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(path)
    print("wrote", path.relative_to(REPO_ROOT))


def grab_widget(widget, path: Path) -> None:
    """Screenshot a single Toplevel/widget (e.g. a dialog)."""
    from PIL import ImageGrab

    widget.update_idletasks()
    widget.update()
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    w, h = widget.winfo_width(), widget.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(path)
    print("wrote", path.relative_to(REPO_ROOT))


def shot_main_and_layers(store: LayerStore) -> None:
    root = new_root("1500x950+0+0")
    app = PyMapprApp(root, store, restore_session=False)
    root.update()

    # 1. Grouped points with a legend, states + blue water (Data tab).
    load_sample(app, "south_america_beetles.csv", group_by="Genus")
    app.panel.continent_var.set("South America")
    app.on_continent()
    app.panel.basemap_var.set("blue_marble")
    app.on_basemap()
    app.panel.layer_vars["states"].set(True)
    app.on_layer("states")
    app.canvas.draw()
    grab_window(root, OUT_DIR / "app_points.png")

    # 2. The same beetles, but in the new Portrait orientation - the map is
    #    reframed as a tall page instead of a wide band of ocean.
    app.panel.orientation_var.set("Portrait")
    app.on_orientation()
    app.canvas.draw()
    grab_window(root, OUT_DIR / "app_portrait.png")

    # 3. The Layers tab with the physical layers on a world view.
    app.panel.orientation_var.set("Landscape")
    app.on_orientation()
    select_tab(app.panel, "Layers")
    app.panel.continent_var.set("World")
    app.on_continent()
    app.panel.basemap_var.set("simple")
    app.on_basemap()
    app.panel.layer_vars["states"].set(False)
    app.on_layer("states")
    app.panel.legend_vars["show"].set(False)
    app.on_legend_options()
    app.panel.bathymetry_var.set(True)
    app.on_bathymetry()
    for key in ("land", "glaciers", "ice_shelves", "deserts"):
        app.panel.fill_vars[key].set(True)
        app.on_fill_layer(key)
    app.panel.compass_var.set(True)
    app.on_compass()
    app.canvas.draw()
    grab_window(root, OUT_DIR / "app_layers.png")

    root.destroy()


def shot_publication(store: LayerStore) -> None:
    """Genus and Species joined into one legend line, in the publication
    style: the Combine columns dialog, then the map it gives."""
    root = new_root("1500x950+0+0")
    app = PyMapprApp(root, store, restore_session=False)
    root.update()

    load_sample(app, "south_america_beetles.csv", group_by="Genus")
    app.panel.continent_var.set("South America")
    app.on_continent()
    app.panel.orientation_var.set("Portrait")
    app.on_orientation()
    app.panel.basemap_var.set("relief")
    app.on_basemap()

    def grab_and_accept() -> None:
        dialog = next(w for w in root.winfo_children()
                      if isinstance(w, tk.Toplevel))
        grab_widget(dialog, OUT_DIR / "combine_columns.png")
        dialog._accept()

    # The real Data-tab handler: it waits on the dialog, which is grabbed
    # and accepted with its defaults (the last two columns, space-joined).
    root.after(500, grab_and_accept)
    app.on_combine_columns()
    app.on_publication_style()
    select_tab(app.panel, "Data")
    app.canvas.draw()
    grab_window(root, OUT_DIR / "app_publication.png")
    root.destroy()


def shot_column_mapper() -> None:
    """The column-mapping dialog shown on every import."""
    from pymappr.data_loader import guess_mapping, read_table
    from pymappr.ui.column_mapper import ColumnMapperDialog

    csv = str(REPO_ROOT / "sample_data" / "south_america_beetles.csv")
    root = new_root("900x650+0+0")
    root.update()
    frame = read_table(csv, headers=True)
    dialog = ColumnMapperDialog(
        root, frame, guess_mapping(frame),
        reread=lambda h, s: read_table(csv, headers=h, sheet=s),
        headers=True, sheets=[])
    dialog.update_idletasks()
    dialog.update()
    grab_widget(dialog, OUT_DIR / "column_mapper.png")
    root.destroy()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    store = LayerStore()
    if (err := store.check_data()):
        print(err)
        return 1
    shot_main_and_layers(store)
    shot_publication(store)
    shot_column_mapper()
    return 0


if __name__ == "__main__":
    sys.exit(main())
