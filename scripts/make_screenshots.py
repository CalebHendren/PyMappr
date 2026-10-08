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
from pymappr.styling.decorations import (  # noqa: E402
    CompassOptions, InsetOptions, ScaleBarOptions)
from pymappr.styling.layout import (  # noqa: E402
    layout_points, with_default_title)
from pymappr.styling.legend import (  # noqa: E402
    PUBLICATION_LEGEND, LegendOptions)
from pymappr.styling.styles import (  # noqa: E402
    BLACK_AND_WHITE, DEFAULT_PALETTE, OKABE_ITO, PUBLICATION_POINT_EDGE,
    row_key)

DPI = 110
SAMPLES = REPO_ROOT / "sample_data"

# A tall frame around South America has no open water big enough for a
# legend, so the beetle figure widens it westward and starts it at 60 S: the
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
        layout.sections, layout.row_order, options,
        [layout.open_note] if layout.open_note else None)


def readme_scenes(store: LayerStore) -> dict:
    """File name -> (renderer, crop to the map box?) for the README."""
    beetles = sample("south_america_beetles.csv")
    seabirds = sample("world_seabirds.csv", group_by="Family")
    orchids = sample("europe_orchids.csv", group_by="Genus")
    scenes = {}

    # The Standard preset on the beetles: Genus and Species combined into
    # one legend line, black & white outlined markers in varied shapes, and
    # a plain boxed legend with italic names and no heading. Shading by genus
    # and sorting A-Z make each genus a block of rows in one shade, its
    # shapes restarting. The figure is page-sized rather than window-sized,
    # so the 9 pt legend takes the share of the map it would in print and
    # fits over the Pacific. The orientation goes first so the extent is
    # fitted to the tall box rather than cropped into it.
    dataset, label = combine_name_columns(beetles.dataset,
                                          ["Genus", "Species"])
    r = new_renderer(store, figsize=(13, 9))
    r.set_layer("countries", True)
    r.set_orientation("portrait")
    r.set_extent(PORTRAIT_SOUTH_AMERICA)
    r.set_graticule(10, show_labels=True)
    r.set_point_edge(*PUBLICATION_POINT_EDGE)
    show_points(r, DatasetEntry(dataset=dataset, name=beetles.name,
                                group_by=label, color_by="Genus",
                                vary_symbols=True),
                BLACK_AND_WHITE, location="lower left", order="az",
                show_title=False, **PUBLICATION_LEGEND)
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


# What the Standard preset sets, for the gallery maps that use it.
STANDARD = dict(
    palette=BLACK_AND_WHITE, combine=True, edge=PUBLICATION_POINT_EDGE,
    entry=dict(color_by="Genus", vary_symbols=True),
    legend=dict(order="az", show_title=False, **PUBLICATION_LEGEND))


def gallery_map(store: LayerStore, name: str, *, extent="World",
                figsize=(11, 7), portrait=False, projection=None,
                basemap=None, ocean=None, bathymetry=False,
                lines=(), fills=(), lake_fill=None,
                palette=DEFAULT_PALETTE, combine=False, entry=None,
                edge=None, alpha=None, legend=None, grid=10,
                scale_bar: str | None = None, compass=False, inset=None,
                labels=()):
    """One distribution map from the generated sample_data/gallery datasets.

    Every look setting is an argument, so each map picks what suits its data:
    *lines* and *fills* are layer keys, *entry* holds the DatasetEntry
    styling (color_by, symbol_by, open_by ...), *legend* the LegendOptions
    fields (location included), *edge* a (colour, width) point outline,
    *inset* the InsetOptions fields of an inset map, *labels* label layer
    keys. Returns (renderer, cropped)."""
    data = sample(f"gallery/{name}.csv")
    dataset = data.dataset
    entry = dict(entry or {})
    if combine:
        dataset, label = combine_name_columns(dataset, ["Genus", "Species"])
        entry["group_by"] = label
    r = new_renderer(store, figsize=figsize)
    if basemap:
        r.set_basemap(basemap)
    for key in ("countries", *lines):
        r.set_layer(key, True)
    for key in fills:
        r.set_fill_layer(key, True)
    if lake_fill:
        r.set_lake_fill(lake_fill)
    if ocean:
        r.set_ocean(ocean)
    if bathymetry:
        r.set_bathymetry(True)
    if projection:
        r.set_projection(projection)
    if portrait:
        r.set_orientation("portrait")
    r.set_extent(extent)
    r.set_graticule(grid, show_labels=True)
    if scale_bar:
        r.set_scale_bar(ScaleBarOptions(show=True, position=scale_bar,
                                        fontsize=9.0))
    if compass:
        r.set_compass(CompassOptions(show=True))
    for key in labels:
        r.set_labels(key, True)
    if inset:
        r.set_inset(InsetOptions(show=True, **inset))
    if edge:
        r.set_point_edge(*edge)
    if alpha is not None:
        r.set_point_alpha(alpha)
    show_points(r, DatasetEntry(dataset=dataset, name=data.name, **entry),
                palette, **(legend or {}))
    return r, portrait


def gallery_scenes(store: LayerStore) -> dict:
    """Distribution maps from sample_data/gallery, each styled the way its
    data suggests (scripts/make_gallery_data.py writes the datasets)."""
    def g(name, **kw):
        return gallery_map(store, name, **kw)

    return {
        # Migratory butterflies over grey relief: colour-blind safe colours
        # with the default white outline, and a wide three-column legend
        # along the bottom.
        "gallery_monarchs.png": g(
            "gallery_monarchs", figsize=(12, 6.6), projection="Robinson",
            basemap="relief_grey", grid=30, palette=OKABE_ITO,
            combine=True,
            legend=dict(location="lower center", columns=3, rounded=False,
                        label_italic=True, show_title=False)),
        # Marine: blue ocean with bathymetry, black and white outlined
        # symbols, counts in the legend.
        "gallery_sea_turtles.png": g(
            "gallery_sea_turtles", figsize=(12, 6.6), projection="Mollweide",
            ocean="blue", bathymetry=True, grid=30, **{
                **STANDARD,
                "legend": dict(location="lower left", counts=True,
                               count_format="(n)",
                               show_title=False, order="az",
                               **PUBLICATION_LEGEND)}),
        # Forest apes split by the Congo: rivers and lakes, nested
        # genus > species key.
        "gallery_great_apes.png": g(
            "gallery_great_apes", extent="Africa", figsize=(10, 9),
            projection="Lambert: Africa", lines=("rivers", "lakes_outline"),
            lake_fill="blue", palette=OKABE_ITO, grid=10,
            entry=dict(color_by="Genus", symbol_by="Species"),
            legend=dict(location="lower left", section_titles=True,
                        bold_groups=True, label_italic=True),
            scale_bar="lower right"),
        # Red kangaroo of the arid interior: deserts, playas, state borders.
        "gallery_kangaroos.png": g(
            "gallery_kangaroos", extent=(108, 156, -46, -8), figsize=(11, 8),
            lines=("states",), fills=("deserts", "playas"), grid=10,
            scale_bar="lower right", compass=True,
            legend=dict(location="lower left", **STANDARD["legend"]),
            **{k: v for k, v in STANDARD.items() if k != "legend"}),
        # Alpine A. haastii: colour relief shows the Southern Alps.
        "gallery_kiwi.png": g(
            "gallery_kiwi", extent=(165, 179.5, -48.5, -34), figsize=(10, 9),
            portrait=True, basemap="relief", grid=2, palette=OKABE_ITO,
            edge=("#000000", 0.6), combine=True,
            legend=dict(location="upper left", marker_scale=1.3,
                        label_italic=True, show_title=False),
            scale_bar="lower right"),
        # Spiny vs humid forest: ecoregions, holotypes drawn open.
        "gallery_lemurs.png": g(
            "gallery_lemurs", extent=(41, 53, -27, -11), figsize=(10, 9),
            portrait=True, fills=("ecoregions",), grid=2,
            palette=BLACK_AND_WHITE, edge=PUBLICATION_POINT_EDGE,
            combine=True, entry=dict(vary_symbols=True,
                       open_by="Type status", open_values=["Holotype"],
                       legend_overrides={
                           row_key("group", name): {"size": 46}
                           for name in ("Lemur catta", "Eulemur fulvus",
                                        "Propithecus verreauxi")}),
            legend=dict(location="lower right", label_italic=True,
                        show_title=False),
            scale_bar="lower left",
            # A globe turned to face the map, to place the island.
            inset=dict(projection="Globe", region="World",
                       position="upper left", size=0.32, points=False,
                       box_color="#000000")),
        # County-level records: counties, rivers, lakes, ocean.
        "gallery_florida_herps.png": g(
            "gallery_florida_herps", extent=(-88, -79, 24, 31.5),
            figsize=(10, 9), portrait=True, lines=("states", "counties",
                                                   "rivers"),
            lake_fill="blue", ocean="blue", grid=2,
            combine=True,
            legend=dict(location="center left", show_title=True,
                        title="Species", label_italic=True),
            scale_bar="upper left"),
        # Topography separates the valley, foothill and coast oaks.
        "gallery_california_oaks.png": g(
            "gallery_california_oaks", extent=(-125, -113.5, 32, 42.5),
            figsize=(9, 9.5), lines=("states",), basemap="relief_alt",
            grid=2, palette=BLACK_AND_WHITE, edge=PUBLICATION_POINT_EDGE,
            combine=True, entry=dict(vary_symbols=True),
            legend=dict(location="lower left", frame=False,
                        label_italic=True, show_title=False),
            scale_bar="upper right", compass=True),
        # A worldwide map with a close-up: the Hawaiian records are a speck
        # at world scale, so the inset blows them up and the box on the map
        # shows where they are.
        "gallery_lady_beetles.png": g(
            "gallery_lady_beetles", figsize=(12, 6.6), projection="Robinson",
            grid=30, palette=OKABE_ITO, combine=True,
            legend=dict(location="lower right", label_italic=True,
                        show_title=False),
            inset=dict(region="custom", lon_min=-160.6, lon_max=-154.4,
                       lat_min=18.6, lat_max=22.6, position="lower left",
                       size=0.24, ocean="blue")),
        # A country with outlying islands: the Galapagos are off the map of
        # the mainland, so they get an inset of their own (no box - the two
        # areas do not overlap), and their records show only there.
        "gallery_ecuador_beetles.png": g(
            "gallery_ecuador_beetles", extent=(-81.3, -75.0, -5.1, 1.6),
            figsize=(10, 9), lines=("states", "rivers"), grid=1,
            ocean="blue", palette=OKABE_ITO, edge=("#000000", 0.6),
            combine=True,
            legend=dict(location="lower left", label_italic=True,
                        show_title=False),
            scale_bar="lower right",
            inset=dict(region="custom", lon_min=-92.1, lon_max=-89.1,
                       lat_min=-1.5, lat_max=0.7, position="upper left",
                       size=0.3, ocean="blue", land=False)),
        # County records around Lincoln, Nebraska, with the state as the
        # locator: its counties, and a box on the two the map shows.
        "gallery_tiger_beetles.png": g(
            "gallery_tiger_beetles", extent=(-97.2, -96.2, 40.45, 41.45),
            figsize=(10, 9), lines=("states", "counties", "rivers",
                                    "lakes_outline"),
            lake_fill="blue", grid=0.2, palette=OKABE_ITO,
            edge=("#000000", 0.6), combine=True,
            legend=dict(location="upper left", label_italic=True,
                        show_title=False),
            scale_bar="lower left", labels=("counties",),
            inset=dict(region="state", states=True, counties=True,
                       points=False, position="lower right", size=0.45)),
        # A few counties on the Tennessee - North Carolina line in the
        # Standard look, with the contiguous United States as the locator.
        "gallery_salamanders.png": g(
            "gallery_salamanders", extent=(-84.25, -82.75, 35.2, 36.05),
            figsize=(11, 7.6), lines=("states", "counties", "rivers"),
            grid=0.25, scale_bar="lower left", labels=("counties",),
            legend=dict(location="upper left", **STANDARD["legend"]),
            inset=dict(region="country", states=True, points=False,
                       position="lower right", size=0.32,
                       box_color="#000000"),
            **{k: v for k, v in STANDARD.items() if k != "legend"}),
    }


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
    scenes.update(gallery_scenes(store))
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
