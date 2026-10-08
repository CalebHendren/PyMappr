# PyMappr

PyMappr is a remake of [SimpleMappr](https://www.simplemappr.net/) as an
offline desktop application, written in Python. Load a table of localities,
style the points, and export a map ready for a paper.

![PyMappr](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21522496.svg)](https://doi.org/10.5281/zenodo.21522496)

![PyMappr main window with hornbill localities across South and Southeast Asia, grouped by genus](docs/images/app_points.png)

## Download

Get the latest build for your platform from the
[releases page](../../releases). A new release is built each time a pull
request is merged into `main`.

| Platform       | File                                     | Install |
|----------------|------------------------------------------|---------|
| Windows        | `PyMappr-Setup-<version>.exe`             | Run the installer |
| macOS          | `PyMappr-<version>-macOS.dmg`             | Open and drag to Applications |
| Linux (Ubuntu) | `pymappr_<version>_amd64.deb`             | `sudo apt install ./pymappr_<version>_amd64.deb` |
| Linux (Fedora) | `pymappr-<version>-1.<dist>.x86_64.rpm`   | `sudo dnf install ./pymappr-<version>-*.x86_64.rpm` |
| Linux (Arch)   | `pymappr-<version>-1-x86_64.pkg.tar.zst`  | `sudo pacman -U pymappr-<version>-1-x86_64.pkg.tar.zst` |
| Any Linux      | `PyMappr-<version>-linux-<distro>-x86_64.tar.gz` | Extract and run `PyMappr/PyMappr` |

The [Releases tab](../../releases) is the only official download source.

## Quick start from source

Requires Python 3.11+ with Tk support.

```bash
pip install -r requirements.txt
python scripts/fetch_data.py   # one-time data download (~165 MB core;
                                # add --skip-extras to skip biodiversity/ecoregion overlays)
python -m pymappr
```

## What it does

### Getting points in

- Load points from CSV, TSV or Excel. Every import starts with a
  column-mapping step, so the columns can be in any order.
- Type points in by hand, in decimal degrees or DMS, or click to place them
  on the map.

![Column mapping dialog shown on import](docs/images/column_mapper.png)

### Styling and legend

- Group, color or shape points by any name column. Two attributes at once
  (e.g. color by Family, symbol by Genus) give a compact legend.
- Open symbols for chosen rows: with Type status = Holotype, type
  localities draw as the outline of their species' symbol, and a legend row
  says what the open symbols mark.
- Palettes: the default, a colourblind-safe one (Okabe-Ito), and black &
  white with a settable point outline for outlined markers.
- Legend position, columns, marker scale and spacing, with bold, italic or
  underline for the labels and title. Customize legend renames, hides,
  reorders and restyles individual rows.
- Presets save every setting except your data and zoom, to apply to any
  other project in one click. The built-in Standard preset sets up a
  journal figure (see [below](#publication-ready-figures)).

### The map

- About 30 Natural Earth layers you can switch on and off (borders, cities,
  water, physical features, infrastructure). Detail switches between 110m,
  50m and 10m as you zoom.
- Six map projections, a Globe (orthographic) view you can drag to spin, and
  regional Lambert projections, all reprojected live.
- Continent presets, a graticule, a compass, and a legend and labels you can
  drag into place.
- A geodesically measured scale bar in kilometres, miles or both, with
  corner, segmented or plain styling, an automatic or fixed length, and
  drag-to-place. The north arrow takes the same placement controls.
- An inset map in any corner. As a locator it shows the state, country,
  continent or world around the map, with a box marking the area the map
  covers. As a close-up it shows an area too small to see on the map
  (Hawaii on a world map, say), and the box goes on the map instead. Pick
  the inset's projection (a globe turned to face the map is one choice),
  its layers and whether it shows your points. **Use current view** sets a
  close-up's area: zoom in on it, click, and zoom back out.
- Landscape or portrait framing. The New Zealand, Madagascar and Florida
  maps in the [gallery](#gallery) are portrait.

More examples, including bathymetry, boundaries, time zones, and basemap
renders, are in [`docs/images/`](docs/images).

### Output

- Save the map as PNG, JPEG, TIFF, PDF, SVG or WebP at the DPI you choose,
  as on screen or at a print width (17 cm for a Zootaxa / Phytotaxa page,
  8 cm for one column, or any width in cm), so text prints at its point
  size. TIFFs are LZW-compressed and greyscale when the map has no colour;
  PDF and SVG text stays editable.
- Export it as a self-contained Python (matplotlib) or R (ggplot2) script
  that redraws it, inset map included, outside PyMappr. Run the script with
  `--install-deps` to have it install what it needs.
- Projects (`.pymappr` files) save your datasets and settings, with
  autosave/restore, and export/import for sharing.

## Publication-ready figures

1. **Data tab > Combine columns...** joins Genus and Species into one name
   column and groups by it, so each legend line reads *Eleusis chapadensis*.
   The source file is left as it is.
2. **Data tab > Presets**, choose **Standard** and
   click **Apply**. It sets the map up for Zootaxa,
   Phytotaxa and similar journals: black & white points with black outlines
   and varied shapes, a plain boxed legend with italic names sorted A-Z,
   shaded by genus and without a heading (unless you typed one), holotypes
   as open symbols when a Type status column names them, and export at
   600 DPI and 17 cm wide. Datasets with no Color by are colored by the
   parent name column, and a legend order you set by hand is kept. Rows you
   restyled with Customize legend keep their styling. Adjust anything
   else, then **Save current as...** to keep it as your own preset.
3. **File > Save map as...** and pick TIFF or PDF. A 600-DPI black & white
   TIFF comes out greyscale and LZW-compressed, well under the 2 MB at which
   Zootaxa asks for JPEG instead.

![The app after Combine columns and the Standard preset](docs/images/app_publication.png)

![Beetle localities with the Standard preset: black and white markers and one italic "Genus species" per legend line](docs/images/publication_style.png)

### Gallery

The settings in each map below suit its data, and every map has a
labelled grid. The localities are generated for illustration, not real
records. They are in [`sample_data/gallery/`](sample_data/gallery) if you
want to try them.

| Worldwide | Worldwide |
|---|---|
| ![Danaus plexippus, D. chrysippus and D. genutia on a Robinson world map over grey relief](docs/images/gallery_monarchs.png) | ![Chelonia mydas, Caretta caretta and Dermochelys coriacea on a Mollweide map with bathymetry](docs/images/gallery_sea_turtles.png) |
| Robinson over grey shaded relief, colourblind-safe colours, and a one-row legend. | Mollweide with bathymetry for marine species, black & white symbols, and point counts in the legend. |
| **Continent: Africa** | **Continent: Australia** |
| ![Pan troglodytes, Pan paniscus and Gorilla gorilla on a Lambert map of Africa with rivers and lakes](docs/images/gallery_great_apes.png) | ![Macropus giganteus, M. fuliginosus and Osphranter rufus across Australia with deserts and state borders](docs/images/gallery_kangaroos.png) |
| Lambert projection with rivers and lakes (the Congo divides chimpanzees from bonobos), and a nested genus / species key. | The Standard preset, with deserts and playas for the arid interior, state borders, a scale bar and a north arrow. |
| **Country: New Zealand** | **Country: Madagascar** |
| ![Apteryx mantelli, A. haastii and A. owenii in New Zealand over colour shaded relief](docs/images/gallery_kiwi.png) | ![Lemur catta, Eulemur fulvus and Propithecus verreauxi in Madagascar over ecoregions, holotypes as open symbols](docs/images/gallery_lemurs.png) |
| Colour shaded relief showing the Southern Alps, outlined colour points, and a larger legend key. | Terrestrial ecoregions, black & white symbols, holotypes as open symbols, and a globe inset placing the island. |
| **US state: Florida** | **US state: California** |
| ![Alligator mississippiensis, Crocodylus acutus and Gopherus polyphemus in Florida with counties, rivers and lakes](docs/images/gallery_florida_herps.png) | ![Quercus lobata, Q. douglasii and Q. agrifolia in California over shaded relief](docs/images/gallery_california_oaks.png) |
| County lines for county records, rivers and lakes, and a titled legend. | Shaded relief separating the valley, foothill and coast species, and a frameless legend. |
| **US counties: Lancaster and Saunders, Nebraska** | **US counties: Great Smoky Mountains** |
| ![Cicindela nevadica lincolniana, C. circumpicta and C. togata around Lincoln, Nebraska, with an inset map of Nebraska](docs/images/gallery_tiger_beetles.png) | ![Plethodon jordani, P. glutinosus and Desmognathus imitator in Tennessee and North Carolina counties, with an inset map of the United States](docs/images/gallery_salamanders.png) |
| Labelled counties, and an inset of the state with its counties, the two on the map boxed. | The Standard preset across four counties on the state line, with the contiguous United States as the inset. |
| **Worldwide, with a close-up inset** | **Country with outlying islands: Ecuador** |
| ![Harmonia axyridis, Coccinella septempunctata and Hippodamia variegata worldwide, with an inset of the Hawaiian Islands](docs/images/gallery_lady_beetles.png) | ![Dynastes hercules and Megasoma actaeon in mainland Ecuador, with Stomion helopoides and S. laevigatum in an inset of the Galapagos](docs/images/gallery_ecuador_beetles.png) |
| The Hawaiian records are a speck at world scale, so an inset blows them up and a box on the map shows where they are. | The Galapagos lie off the map of the mainland, so they get an inset of their own, and their records show there. |

## Why PyMappr over AI

You can ask a chatbot to draw a distribution map, and it may draw a good one.
Ask again with the same data and the same prompt, though, and you will
usually get a different map. Large language models are non-deterministic:
their output varies from run to run, and the model behind a chat service can
change without notice. A figure made that way cannot be reproduced exactly,
which matters when it has to hold up through revisions and replication.

PyMappr draws the same map from the same data and settings every time. There
is no sampling step, so the inputs fully describe the figure:

- Save the map as a project (`.pymappr`) and reopen it later to get the same
  map, or send it to a co-author.
- Export a Python or R script that redraws the map without PyMappr, and
  archive it with your data or include it as supplementary material.
- Every release stays on the [releases page](../../releases). If a reviewer
  asks for a change a year from now, install the version you used (shown
  under **Help > About PyMappr**) and you are back where you were. Give that
  version number in your methods section.

## CSV format

Any number of name columns followed by Longitude/Latitude, in any order. You
confirm the mapping on import.

| Genus       | Species       | Longitude   | Latitude    |
|-------------|---------------|-------------|-------------|
| Eleusis     | chapadensis   | -68.4349    | -12.3541    |
| Xanthopygus | orinocensis   | 67°33'37"W  | 10°18'29"N  |

With Genus and Species in separate columns like this, **Combine columns...**
on the Data tab puts both on one legend line without editing the file:

![Combine columns dialog joining Genus and Species](docs/images/combine_columns.png)

[`sample_data/`](sample_data) has sample datasets for beetles, hornbills,
seabirds, and orchids.

## MiniMappr (browser version)

**MiniMappr** is a browser-only edition of PyMappr at
[calebhendren.github.io/PyMappr](https://calebhendren.github.io/PyMappr/),
served by GitHub Pages from [`index.html`](index.html). It covers the core
workflow with nothing to install.

![MiniMappr in the browser with the beetle sample loaded](docs/images/minimappr.png)

What it has:

- Points from a CSV/TSV (with a column-mapping step), a pasted table, manual
  entry, or click-to-place, in decimal degrees or DMS.
- Group, color and symbol styling, with Combine columns and the filter bar.
- The same projections: Equirectangular, Mercator, Robinson, Mollweide,
  Natural Earth, Winkel Tripel, orthographic Globe, and regional and custom
  Lambert.
- The same legend options, scale bar, compass and grid.
- The one-click publication style.
- Export as PNG, JPEG, WebP, TIFF, PDF or SVG at the DPI you choose.
- **Reset** in the header removes every dataset and puts all settings back to
  their defaults, after asking first.

What it leaves out: the ~30 Natural Earth layers, relief/Blue Marble
basemaps, bathymetry, labels, Excel import, project files, and Python/R code
export. The page is self-contained (D3, d3-geo-projection, topojson-client,
and a simplified world outline are all inlined) and is kept out of the
PyInstaller build.

## Development

```bash
python -m pytest tests/            # the test suite (a few tests need the map data)
python scripts/make_screenshots.py # regenerate the README map images
python scripts/make_screenshots.py --out preview --all  # render check, more layers
python scripts/make_app_screenshot.py  # the app screenshots (needs a display)
python minimappr/build.py          # rebuild index.html from minimappr/
```

Project layout:

- `pymappr/files/coords.py` - decimal/DMS coordinate parsing
- `pymappr/files/data_loader.py` - CSV/TSV/Excel reading and column mapping
- `pymappr/files/projects.py` - project files, settings, session autosave
- `pymappr/geo/layers.py` - Natural Earth layer store and on-disk frame cache
- `pymappr/geo/projections.py` - map projections (pyproj)
- `pymappr/renderer/` - matplotlib map rendering, one module per concern
  (view, layers, overlays, labels, points and legend, mouse, blit), plus the
  layer style tables shared with code export
- `pymappr/styling/styles.py` - point styles and group/color-by styling
- `pymappr/styling/legend.py` - legend options and legend rows
- `pymappr/styling/decorations.py` - scale bar and compass options
- `pymappr/styling/layout.py` - what every dataset draws (shared by the app
  and code export)
- `pymappr/export/codegen.py`, `pymappr/export/templates/` - Python/R code export
- `pymappr/updates.py` - daily update check against the GitHub releases API
- `pymappr/app.py`, `pymappr/ui/` - Tkinter application
- `scripts/fetch_data.py` - downloads and prepares the bundled map data
- `minimappr/` - MiniMappr source; `minimappr/build.py` generates `index.html`
- `packaging/` - PyInstaller spec, Inno Setup script, Linux/Fedora/Arch packaging

Building the release packages is automated by
[`build-release.yml`](.github/workflows/build-release.yml); see
`packaging/` for local build scripts per platform.

## Support Me

If PyMappr is useful to you, you can support its development on Ko-fi:
[**ko-fi.com/calebhendren**](https://ko-fi.com/calebhendren)

## Citation

Citing PyMappr is not necessary, but it is welcome:

> Hendren, Caleb. *PyMappr* [computer software].
> https://github.com/CalebHendren/PyMappr
> https://doi.org/10.5281/zenodo.21522496

## Data credits

Map data from [Natural Earth](https://www.naturalearthdata.com/) (public
domain). The optional Biodiversity & ecoregions overlays (Terrestrial
ecoregions from [RESOLVE Ecoregions 2017](https://ecoregions.appspot.com/),
Biodiversity hotspots from [Conservation International, 2016.1](https://zenodo.org/records/3261807),
and Marine ecoregions from [WWF/TNC MEOW](https://hub.arcgis.com/datasets/903c3ae05b264c00a3b5e58a4561b7e6))
are CC-BY licensed and fetched by `scripts/fetch_data.py`. If a source is
unavailable, that layer is skipped and the rest of PyMappr works as usual.

MiniMappr (the browser version) uses a simplified, Natural Earth-derived world
outline from [world-atlas](https://github.com/topojson/world-atlas) (public
domain), rendered with [D3](https://d3js.org) and d3-geo-projection and decoded
with topojson-client (all ISC licensed).
