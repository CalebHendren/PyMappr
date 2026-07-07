"""Render the README images into docs/images/ (headless).

Usage: python scripts/make_screenshots.py

Exercises the same renderer the app uses, on the bundled sample datasets:
US cities, Wyoming cities (four name columns), and the dog-breed diversity
dataset. Requires the map data (python scripts/fetch_data.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ezmaps.data_loader import load_csv  # noqa: E402
from ezmaps.layers import LayerStore  # noqa: E402
from ezmaps.renderer import MapRenderer  # noqa: E402
from ezmaps.styles import default_styles, group_points  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "images"
DPI = 110


def new_renderer(store: LayerStore) -> MapRenderer:
    return MapRenderer(Figure(figsize=(10, 6.5)), store)


def point_groups_for(dataset, key: str):
    groups = group_points(dataset.frame, key)
    styles = default_styles([label for label, _ in groups])
    return [(label, styles[label], sub["lon"].to_numpy(),
             sub["lat"].to_numpy()) for label, sub in groups]


def save(renderer: MapRenderer, name: str) -> None:
    path = OUT_DIR / name
    renderer.fig.savefig(path, dpi=DPI, facecolor="white")
    print("wrote", path.relative_to(REPO_ROOT))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    store = LayerStore()
    if (err := store.check_data()):
        print(err)
        return 1

    sample = REPO_ROOT / "sample_data"
    us = load_csv(str(sample / "us_cities.csv"))
    wyoming = load_csv(str(sample / "wyoming_cities.csv"))
    dogs = load_csv(str(sample / "dog_breeds.csv"))

    # 1. Satellite world basemap with country labels.
    r = new_renderer(store)
    r.set_basemap("satellite")
    r.set_layer("countries", True)
    r.set_labels("countries", True)
    save(r, "satellite_world.png")

    # 2. US cities: grouped points + legend on a simple map.
    r = new_renderer(store)
    r.set_extent((-127, -65, 23, 51))
    r.set_layer("countries", True)
    r.set_layer("states", True)
    r.set_point_groups(point_groups_for(us, "name1"))
    r.set_legend(True, title=us.name1_label, location="lower left")
    save(r, "us_cities_points.png")

    # 3. Wyoming cities grouped by county (Name 3 of 4), labelled counties.
    r = new_renderer(store)
    r.set_extent((-112.5, -103.5, 40.4, 45.6))
    for key in ("countries", "states", "counties"):
        r.set_layer(key, True)
    r.set_labels("counties", True)
    r.set_point_groups(point_groups_for(wyoming, "name3"))
    r.set_legend(True, title=wyoming.name_labels[2], location="lower left")
    save(r, "wyoming_points.png")

    # 4. Wyoming heatmap: bandwidth + intensity + points on top.
    r = new_renderer(store)
    r.set_extent((-112.5, -103.5, 40.4, 45.6))
    for key in ("countries", "states", "counties"):
        r.set_layer(key, True)
    r.set_point_groups(point_groups_for(wyoming, "name4"))
    r.set_heatmap(True, radius=18, blur=4, intensity=1.6, cmap="hot",
                  opacity=0.8, show_points=True)
    r.set_legend(False)
    save(r, "wyoming_heatmap.png")

    # 5. Dog-breed diversity heatmap of the world, with bloom.
    r = new_renderer(store)
    r.set_extent("World")
    r.set_layer("countries", True)
    r.set_ocean("grey")
    r.set_point_groups(point_groups_for(dogs, "name1"))
    r.set_heatmap(True, radius=14, blur=3, intensity=1.8, cmap="plasma",
                  opacity=0.85, bloom=True, show_points=True)
    r.set_legend(False)
    save(r, "dogs_heatmap.png")

    # 6. Classified (5-band) heatmap with a threshold, Europe detail.
    r = new_renderer(store)
    r.set_extent((-15, 45, 34, 62))
    r.set_layer("countries", True)
    r.set_ocean("blue")
    r.set_point_groups(point_groups_for(dogs, "name1"))
    r.set_heatmap(True, radius=20, intensity=1.5, threshold=0.15,
                  levels=5, cmap="viridis", opacity=0.75)
    r.set_legend(False)
    save(r, "heatmap_classified.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())
