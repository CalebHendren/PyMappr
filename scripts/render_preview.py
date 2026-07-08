"""Headless smoke test: render several map configurations to PNG files.

Usage: python scripts/render_preview.py [output_dir]

Useful for checking that the data and renderer work without starting the
GUI - it exercises basemaps, layer toggles, labels, graticules, points,
legend, projections, and the continent-outline fallback.
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
from pymappr.styles import default_styles, group_points  # noqa: E402


def new_renderer(store: LayerStore) -> MapRenderer:
    return MapRenderer(Figure(figsize=(11, 7)), store)


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "preview")
    out_dir.mkdir(parents=True, exist_ok=True)
    store = LayerStore()
    if (err := store.check_data()):
        print(err)
        return 1

    dataset = load_csv(str(REPO_ROOT / "sample_data" / "us_cities.csv"))
    print(f"sample data: {len(dataset)} points, {len(dataset.skipped)} skipped")
    groups = group_points(dataset.frame, "name1")
    styles = default_styles([label for label, _ in groups])
    point_groups = [(label, styles[label], sub["lon"].to_numpy(),
                     sub["lat"].to_numpy()) for label, sub in groups]

    # 1. Simple world map: black country borders + 10 degree graticule.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_graticule(10, show_labels=True)
    r.save_png(out_dir / "1_simple_world.png")

    # 2. Satellite world with country labels (all countries labelled).
    r = new_renderer(store)
    r.set_basemap("satellite")
    r.set_layer("countries", True)
    r.set_labels("countries", True)
    r.save_png(out_dir / "2_satellite_world.png")

    # 3. North America, everything on, blue water, 5 degree grid.
    r = new_renderer(store)
    r.set_extent("North America")
    for key in ("countries", "states", "counties", "lakes_outline",
                "rivers", "roads"):
        r.set_layer(key, True)
    r.set_lake_fill("blue")
    r.set_ocean("blue")
    r.set_graticule(5, show_labels=True)
    for key in ("countries", "states", "lakes", "rivers"):
        r.set_labels(key, True)
    r.save_png(out_dir / "3_north_america_full.png")

    # 4. Zoomed to Texas-ish: county lines + county labels, greyscale water.
    r = new_renderer(store)
    r.set_extent((-107, -88, 25, 37))
    for key in ("countries", "states", "counties"):
        r.set_layer(key, True)
    r.set_ocean("grey")
    r.set_lake_fill("grey")
    r.set_labels("counties", True)
    r.set_labels("states", True)
    r.set_graticule(1, show_labels=False)
    r.save_png(out_dir / "4_texas_counties.png")

    # 5. Points + legend on a simple US map.
    r = new_renderer(store)
    r.set_extent((-127, -65, 23, 51))
    r.set_layer("countries", True)
    r.set_layer("states", True)
    r.set_point_groups(point_groups)
    r.set_legend(True, title=dataset.name1_label, location="lower left")
    r.save_png(out_dir / "5_points_legend.png")

    # 6. Countries off: political borders gone, continent outlines stay.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_layer("countries", False)
    r.set_ocean("blue")
    r.save_png(out_dir / "6_continent_outlines.png")

    # 7. Robinson projection with a graticule and country labels.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_projection("Robinson")
    r.set_graticule(10)
    r.set_labels("countries", True)
    r.save_png(out_dir / "7_robinson_world.png")

    print("previews written to", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
