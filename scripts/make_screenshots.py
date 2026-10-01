"""Render the README's example maps headlessly.

    python scripts/make_screenshots.py                 # docs/images/*.png
    python scripts/make_screenshots.py --out preview --all

``--out`` writes somewhere else (a quick render check without touching the
docs), and ``--all`` adds a few extra scenes that exercise more layers.
Points are styled through pymappr.styling.layout, exactly as the app styles
them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pymappr.files.data_loader import (  # noqa: E402
    combine_name_columns, load_csv)
from pymappr.files.projects import DatasetEntry  # noqa: E402
from pymappr.geo.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styling.decorations import CompassOptions  # noqa: E402
from pymappr.styling.layout import (  # noqa: E402
    layout_points, with_default_title)
from pymappr.styling.legend import (  # noqa: E402
    PUBLICATION_LEGEND, LegendOptions)
from pymappr.styling.styles import (  # noqa: E402
    BLACK_AND_WHITE, DEFAULT_PALETTE, PUBLICATION_POINT_EDGE)

DPI = 110
SAMPLES = REPO_ROOT / "sample_data"

# A tall frame around South America has no open water big enough for a
# legend, so the portrait scenes widen it westward and start it at 60 S: the
# legend then sits in the lower left over empty Pacific, clear of the Chilean
# coast, the Juan Fernandez islands and Antarctica. The extra height goes to
# the north, where nothing is drawn over it.
PORTRAIT_SOUTH_AMERICA = (-105, -33, -60, 40)


def new_renderer(store: LayerStore,
                 figsize: tuple[float, float] = (10, 6.5)) -> MapRenderer:
    return MapRenderer(Figure(figsize=figsize), store)


def sample(name: str, **styling) -> DatasetEntry:
    dataset = load_csv(str(SAMPLES / name))
    return DatasetEntry(dataset=dataset, name=name, **styling)


def show_points(renderer: MapRenderer, entry: DatasetEntry,
                palette: list[str] = DEFAULT_PALETTE, **legend) -> None:
    """Draw a dataset and its legend the way the app does."""
    options = with_default_title([entry], LegendOptions(**legend))
    layout = layout_points([entry], options, palette)
    renderer.set_points(
        [(label, style, rows["lon"].to_numpy(), rows["lat"].to_numpy())
         for label, style, rows in layout.groups],
        layout.sections, layout.row_order, options)


def readme_scenes(store: LayerStore) -> dict:
    """File name -> (renderer, crop to the map box?) for the README."""
    beetles = sample("south_america_beetles.csv", color_by="Genus",
                     symbol_by="Species")
    seabirds = sample("world_seabirds.csv", group_by="Family")
    orchids = sample("europe_orchids.csv", group_by="Genus")
    scenes = {}

    # Portrait orientation: beetles coloured by genus, shaped by species,
    # framed as a tall page and cropped to it. The orientation goes first so
    # the extent is fitted to the tall box rather than cropped into it.
    r = new_renderer(store)
    r.set_basemap("blue_marble")
    r.set_layer("countries", True)
    r.set_orientation("portrait")
    r.set_extent(PORTRAIT_SOUTH_AMERICA)
    show_points(r, beetles, location="lower left", fontsize=7)
    scenes["beetles_portrait.png"] = (r, True)

    # The same map in landscape, for the orientation comparison. The wide
    # frame has Pacific to spare in the lower left; the upper right would
    # cover West Africa.
    r = new_renderer(store)
    r.set_basemap("blue_marble")
    r.set_layer("countries", True)
    r.set_extent("South America")
    show_points(r, beetles, location="lower left", fontsize=7)
    scenes["beetles_landscape.png"] = (r, False)

    # The publication style: Genus and Species combined into one legend
    # line, black & white outlined markers in varied shapes, and a plain
    # boxed legend with italic names. Shading by genus and sorting A-Z make
    # each genus a block of rows in one shade, its shapes restarting. The
    # figure is page-sized rather than window-sized, so the 9 pt legend
    # takes the share of the map it would in print and fits over the
    # Pacific.
    dataset, label = combine_name_columns(beetles.dataset,
                                          ["Genus", "Species"])
    r = new_renderer(store, figsize=(13, 9))
    r.set_layer("countries", True)
    r.set_orientation("portrait")
    r.set_extent(PORTRAIT_SOUTH_AMERICA)
    r.set_point_edge(*PUBLICATION_POINT_EDGE)
    show_points(r, DatasetEntry(dataset=dataset, name=beetles.name,
                                group_by=label, color_by="Genus",
                                vary_symbols=True),
                BLACK_AND_WHITE, location="lower left", order="az",
                **PUBLICATION_LEGEND)
    scenes["publication_style.png"] = (r, True)

    # Seabirds grouped by family on Mollweide, with a plain legend.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_projection("Mollweide")
    r.set_ocean("blue")
    show_points(r, seabirds, location="lower left", fontsize=7)
    scenes["seabirds_world.png"] = (r, False)

    # The same seabirds coloured by family and shaped by genus: the compact
    # colour + symbol key.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_ocean("blue")
    r.set_point_alpha(0.75)
    show_points(r, sample("world_seabirds.csv", color_by="Family",
                          symbol_by="Genus"),
                location="lower left", fontsize=7)
    scenes["seabirds_compact.png"] = (r, False)

    # Orchids by genus over shaded relief, with country labels.
    r = new_renderer(store)
    r.set_basemap("relief")
    r.set_extent((-11, 30, 35, 61))
    r.set_layer("countries", True)
    r.set_labels("countries", True)
    show_points(r, orchids, location="upper right", fontsize=7)
    scenes["orchids_europe.png"] = (r, False)

    r = new_renderer(store)
    r.set_basemap("blue_marble")
    r.set_layer("countries", True)
    r.set_labels("countries", True)
    scenes["blue_marble_world.png"] = (r, False)

    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_projection("Robinson")
    r.set_graticule(10)
    r.set_labels("countries", True)
    scenes["robinson_world.png"] = (r, False)

    # Countries off: borders removed, continent outlines kept.
    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_layer("countries", False)
    r.set_ocean("blue")
    scenes["continent_outlines.png"] = (r, False)

    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_bathymetry(True)
    for key in ("land", "glaciers", "ice_shelves", "deserts", "playas"):
        r.set_fill_layer(key, True)
    r.set_layer("reefs", True)
    r.set_compass(CompassOptions(show=True))
    scenes["physical_world.png"] = (r, False)

    # Scale-dependent city markers and labels; the coastline switches to
    # 10m on its own at this zoom.
    r = new_renderer(store)
    r.set_extent((-12, 32, 35, 62))
    r.set_layer("countries", True)
    r.set_ocean("blue")
    for key in ("cities", "airports", "ports"):
        r.set_point_layer(key, True)
    r.set_labels("cities", True)
    scenes["cities_europe.png"] = (r, False)

    r = new_renderer(store)
    r.set_extent((40, 110, -5, 45))
    r.set_layer("countries", True)
    r.set_fill_layer("disputed", True)
    r.set_fill_layer("urban", True)
    for key in ("disputed_lines", "maritime", "eez"):
        r.set_layer(key, True)
    r.set_ocean("blue")
    scenes["boundaries_asia.png"] = (r, False)

    r = new_renderer(store)
    r.set_layer("countries", True)
    r.set_layer("timezones", True)
    r.set_labels("timezones", True)
    r.set_point_layer("cities", True)
    r.set_capitals_only(True)
    scenes["timezones_capitals.png"] = (r, False)
    return scenes


def extra_scenes(store: LayerStore) -> dict:
    """Layers the README images do not show, for a wider render check."""
    scenes = {}
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
    scenes["north_america_full.png"] = (r, False)

    r = new_renderer(store)
    r.set_extent((-107, -88, 25, 37))
    for key in ("countries", "states", "counties"):
        r.set_layer(key, True)
    r.set_ocean("grey")
    r.set_lake_fill("grey")
    r.set_labels("counties", True)
    r.set_labels("states", True)
    r.set_graticule(1, show_labels=False)
    scenes["texas_counties.png"] = (r, False)

    r = new_renderer(store)
    r.set_extent((-130, -60, 20, 55))
    r.set_layer("sovereignty", True)
    r.set_layer("states", True)
    r.set_layer("dependencies", True)
    r.set_fill_layer("parks", True)
    r.set_labels("countries", True)
    scenes["sovereignty_parks.png"] = (r, False)
    return scenes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "docs" / "images",
                        help="folder to write the images to")
    parser.add_argument("--all", action="store_true",
                        help="also render the extra layer scenes")
    args = parser.parse_args()
    store = LayerStore()
    if (err := store.check_data()):
        print(err)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    scenes = readme_scenes(store)
    if args.all:
        scenes.update(extra_scenes(store))
    for name, (renderer, cropped) in scenes.items():
        path = args.out / name
        if cropped:
            # Portrait renders drop their blank orientation side bars.
            renderer.save_image(str(path), fmt="png", dpi=DPI)
        else:
            # Saving the figure directly still needs the basemap cut for the
            # export dpi, not for the notional screen.
            with renderer.basemap_detail_for(DPI):
                renderer.fig.savefig(path, dpi=DPI, facecolor="white")
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
