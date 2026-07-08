"""Render the README images into docs/images/ (headless).

Usage: python scripts/make_screenshots.py

Exercises the same renderer the app uses, on the bundled sample datasets:
US cities, Wyoming cities (four name columns), the felines & canines
dataset, and the insect taxonomy (color-by + symbol-by). Requires the map
data (python scripts/fetch_data.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pymappr.data_loader import load_csv  # noqa: E402
from pymappr.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styles import (NEUTRAL_MARKER_COLOR,  # noqa: E402
                            PointStyle, attribute_style_maps,
                            default_styles, group_points,
                            style_by_attributes)

OUT_DIR = REPO_ROOT / "docs" / "images"
DPI = 110


def new_renderer(store: LayerStore) -> MapRenderer:
    return MapRenderer(Figure(figsize=(10, 6.5)), store)


def point_groups_for(dataset, key: str, color_by: str | None = None):
    groups = group_points(dataset.frame, key)
    color_keys = None
    if color_by is not None:
        color_keys = [str(sub[color_by].iloc[0]) for _label, sub in groups]
    styles = default_styles([label for label, _ in groups],
                            color_keys=color_keys)
    return [(label, styles[label], sub["lon"].to_numpy(),
             sub["lat"].to_numpy()) for label, sub in groups]


def attribute_render(dataset, color_key: str, symbol_key: str):
    """Render groups + a compact color/symbol legend for two columns."""
    color_map, symbol_map = attribute_style_maps(
        dataset.frame, color_key, symbol_key)
    groups = style_by_attributes(dataset.frame, color_key, symbol_key,
                                 color_map, symbol_map)
    point_groups = [(label, style, sub["lon"].to_numpy(),
                     sub["lat"].to_numpy())
                    for label, style, sub in groups]
    keys = dict(zip(dataset.name_keys, dataset.name_labels))
    sections = [
        (keys.get(color_key, "Color"),
         [(v, PointStyle(color=c, marker="Circle"))
          for v, c in color_map.items()]),
        (keys.get(symbol_key, "Symbol"),
         [(v, PointStyle(color=NEUTRAL_MARKER_COLOR, marker=m))
          for v, m in symbol_map.items()]),
    ]
    return point_groups, sections


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
    animals = load_csv(str(sample / "felines_and_canines.csv"))
    insects = load_csv(str(sample / "insects.csv"))

    # 1. Satellite world basemap with every country labelled.
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

    # 4. Felines & canines: color by family (Name 1), shape per animal
    #    (Name 2) - cats share one color with a shape per species, dogs
    #    share another color.
    r = new_renderer(store)
    r.set_extent("World")
    r.set_layer("countries", True)
    r.set_ocean("blue")
    r.set_point_groups(point_groups_for(animals, "name2", color_by="name1"))
    r.set_legend(True, title=animals.name_labels[1], location="lower left",
                 fontsize=7, columns=2)
    save(r, "felines_canines_points.png")

    # 4b. Insects (1500 rows, Order>Family>Genus>Species): color by Order,
    #     symbol by Family. The compact color/symbol legend decodes every
    #     point with 3 colors + 7 shapes instead of one row per species.
    r = new_renderer(store)
    r.set_extent("World")
    r.set_layer("countries", True)
    r.set_ocean("blue")
    r.set_point_alpha(0.6)
    point_groups, sections = attribute_render(insects, "name1", "name2")
    r.set_point_groups(point_groups)
    r.set_structured_legend(sections)
    r.set_legend(True, location="upper left", fontsize=7)
    save(r, "insects_points.png")

    # 5. Robinson projection: world map with graticule and country labels.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_projection("Robinson")
    r.set_graticule(10)
    r.set_labels("countries", True)
    save(r, "robinson_world.png")

    # 6. Countries layer off: political borders removed, continent
    #    outlines kept.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_layer("countries", False)
    r.set_ocean("blue")
    save(r, "continent_outlines.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())
