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
    """Save a full-canvas (landscape) render at the figure size."""
    path = OUT_DIR / name
    renderer.fig.savefig(path, dpi=DPI, facecolor="white")
    print("wrote", path.relative_to(REPO_ROOT))


def save_cropped(renderer: MapRenderer, name: str) -> None:
    """Save cropped to the map box - used for portrait renders so the tall
    frame comes out without its blank orientation side bars."""
    path = OUT_DIR / name
    renderer.save_image(str(path), fmt="png", dpi=DPI)
    print("wrote", path.relative_to(REPO_ROOT))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    store = LayerStore()
    if (err := store.check_data()):
        print(err)
        return 1

    sample = REPO_ROOT / "sample_data"
    beetles = load_csv(str(sample / "south_america_beetles.csv"))
    seabirds = load_csv(str(sample / "world_seabirds.csv"))
    orchids = load_csv(str(sample / "europe_orchids.csv"))

    # 1. Portrait orientation: South American beetles, color by Genus and
    #    shape by Species, framed as a tall page (the headline of this
    #    release). Cropped to the portrait frame.
    beetle_groups, beetle_sections = attribute_render(beetles, "name1", "name2")
    r = new_renderer(store)
    r.set_basemap("blue_marble")
    r.set_layer("countries", True)
    r.set_extent("South America")
    r.set_orientation("portrait")
    r.set_point_groups(beetle_groups)
    r.set_structured_legend(beetle_sections)
    r.set_legend(True, location="upper right", fontsize=7)
    save_cropped(r, "beetles_portrait.png")

    # 2. The same map in landscape: it fills the canvas instead of a tall
    #    frame. Side by side with #1 this shows the orientation switch.
    r = new_renderer(store)
    r.set_basemap("blue_marble")
    r.set_layer("countries", True)
    r.set_extent("South America")
    r.set_point_groups(beetle_groups)
    r.set_structured_legend(beetle_sections)
    r.set_legend(True, location="upper right", fontsize=7)
    save(r, "beetles_landscape.png")

    # 3. World seabirds grouped by Family on a Mollweide projection with a
    #    plain per-group legend.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_projection("Mollweide")
    r.set_ocean("blue")
    r.set_point_groups(point_groups_for(seabirds, "name1"))
    r.set_legend(True, title=seabirds.name_labels[0], location="lower left",
                 fontsize=7)
    save(r, "seabirds_world.png")

    # 4. The same seabirds, but color by Family and shape by Genus: the
    #    compact color + symbol key decodes every point with a handful of
    #    colors and shapes.
    r = new_renderer(store)
    r.set_extent("World")
    r.set_layer("countries", True)
    r.set_ocean("blue")
    r.set_point_alpha(0.75)
    point_groups, sections = attribute_render(seabirds, "name1", "name2")
    r.set_point_groups(point_groups)
    r.set_structured_legend(sections)
    r.set_legend(True, location="lower left", fontsize=7)
    save(r, "seabirds_compact.png")

    # 5. European orchids grouped by Genus over a shaded-relief basemap, with
    #    country labels.
    r = new_renderer(store)
    r.set_basemap("relief")
    r.set_extent((-11, 30, 35, 61))
    r.set_layer("countries", True)
    r.set_labels("countries", True)
    r.set_point_groups(point_groups_for(orchids, "name1"))
    r.set_legend(True, title=orchids.name_labels[0], location="upper right",
                 fontsize=7)
    save(r, "orchids_europe.png")

    # 6. Every country labelled on the offline Blue Marble basemap.
    r = new_renderer(store)
    r.set_basemap("blue_marble")
    r.set_layer("countries", True)
    r.set_labels("countries", True)
    save(r, "blue_marble_world.png")

    # 7. The Robinson projection with a 10 degree graticule and country
    #    labels.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_projection("Robinson")
    r.set_graticule(10)
    r.set_labels("countries", True)
    save(r, "robinson_world.png")

    # 8. Countries layer off: political borders removed, continent outlines
    #    kept.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_layer("countries", False)
    r.set_ocean("blue")
    save(r, "continent_outlines.png")

    # 9. Physical world: bathymetry, land fill, glaciers, ice shelves,
    #    deserts, playas, reefs, and the compass.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_bathymetry(True)
    for key in ("land", "glaciers", "ice_shelves", "deserts", "playas"):
        r.set_fill_layer(key, True)
    r.set_layer("reefs", True)
    r.set_compass(True)
    save(r, "physical_world.png")

    # 10. Cities, airports, and ports over Europe: markers and labels are
    #     scale-dependent, and the coastline switches to 10m automatically.
    r = new_renderer(store)
    r.set_extent((-12, 32, 35, 62))
    r.set_layer("countries", True)
    r.set_ocean("blue")
    for key in ("cities", "airports", "ports"):
        r.set_point_layer(key, True)
    r.set_labels("cities", True)
    save(r, "cities_europe.png")

    # 11. Boundary detail: disputed areas and boundaries, maritime
    #     boundaries, EEZ / 200 nm limits, urban areas.
    r = new_renderer(store)
    r.set_extent((40, 110, -5, 45))
    r.set_layer("countries", True)
    r.set_fill_layer("disputed", True)
    r.set_fill_layer("urban", True)
    for key in ("disputed_lines", "maritime", "eez"):
        r.set_layer(key, True)
    r.set_ocean("blue")
    save(r, "boundaries_asia.png")

    # 12. Time zones with capitals only.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_layer("timezones", True)
    r.set_labels("timezones", True)
    r.set_point_layer("cities", True)
    r.set_capitals_only(True)
    save(r, "timezones_capitals.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())
