from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import tkinter as tk  # noqa: E402

from pymappr.app import PyMapprApp  # noqa: E402
from pymappr.data_loader import load_csv  # noqa: E402
from pymappr.layers import LayerStore  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "images"


def load_sample(app: PyMapprApp, name: str) -> None:
    """Load a bundled CSV exactly as the Add data file flow would."""
    from pymappr.projects import DatasetEntry

    dataset = load_csv(str(REPO_ROOT / "sample_data" / name))
    labels = dataset.name_labels
    app._add_entry(DatasetEntry(dataset=dataset, name=name,
                                group_by=labels[0] if labels else ""))


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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    store = LayerStore()
    if (err := store.check_data()):
        print(err)
        return 1

    root = tk.Tk()
    root.geometry("1500x950+0+0")
    app = PyMapprApp(root, store, restore_session=False)
    root.update()

    # 1. Grouped points with a legend, states + blue water (Data tab).
    load_sample(app, "us_cities.csv")
    app.panel.layer_vars["states"].set(True)
    app.on_layer("states")
    app.panel.ocean_var.set("blue")
    app.on_ocean()
    app.panel.lake_fill_var.set("blue")
    app.on_lake_fill()
    app.canvas.draw()
    grab_window(root, OUT_DIR / "app_points.png")

    # 2. The Layers tab with the physical layers on a world view.
    app.panel.notebook.select(2)  # Layers tab
    app.panel.continent_var.set("World")
    app.on_continent()
    app.panel.layer_vars["states"].set(False)
    app.on_layer("states")
    app.panel.legend_show_var.set(False)
    app.on_legend_options()
    app.panel.ocean_var.set("none")
    app.on_ocean()
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
