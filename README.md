# PyMappr

PyMappr is a remake of [SimpleMappr](https://www.simplemappr.net/) as an
offline desktop application, written in Python. Load a table of localities,
style the points, and export a map ready for a paper.

![PyMappr](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21522496.svg)](https://doi.org/10.5281/zenodo.21522496)

![PyMappr main window with grouped beetle localities and a legend](docs/images/app_points.png)

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
- Palettes: the default, a colourblind-safe one (Okabe-Ito), and black &
  white with a settable point outline for outlined markers.
- Legend position, columns, marker scale and spacing, with bold, italic or
  underline for the labels and title. Customize legend renames, hides,
  reorders and restyles individual rows.
- One-click publication style (see [below](#publication-ready-figures)).

![European orchids grouped by genus](docs/images/orchids_europe.png)

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
- Landscape or portrait framing.

![Cities, airports, and ports](docs/images/cities_europe.png)

Portrait reframes the map as a tall page instead of a wide band of ocean:

![Portrait orientation in the app](docs/images/app_portrait.png)

| Portrait | Landscape |
|----------|-----------|
| ![Portrait beetle map](docs/images/beetles_portrait.png) | ![Landscape beetle map](docs/images/beetles_landscape.png) |

More examples, including bathymetry, boundaries, time zones, and basemap
renders, are in [`docs/images/`](docs/images).

### Output

- Save the map as PNG, JPEG, TIFF, PDF, SVG or WebP at the DPI you choose.
- Export it as a self-contained Python (matplotlib) or R (ggplot2) script
  that redraws it outside PyMappr. Run the script with `--install-deps` to
  have it install what it needs.
- Projects (`.pymappr` files) save your datasets and settings, with
  autosave/restore, and export/import for sharing.

## Publication-ready figures

1. **Data tab > Combine columns...** joins Genus and Species into one name
   column and groups by it, so each legend line reads *Eleusis chapadensis*.
   The source file is left as it is.
2. **Map tab > Apply publication style** switches to black & white points
   with black outlines and varied shapes, a plain boxed legend with italic
   names sorted A-Z and shaded by genus, and 600 DPI export. Datasets with
   no Color by are colored by the parent name column, and a legend order you
   set by hand is kept. Rows you restyled with Customize legend keep their
   styling.
3. **File > Save map as...** and pick TIFF or PDF.

![The app after Combine columns and Apply publication style](docs/images/app_publication.png)

![Beetle localities in the publication style: black and white markers and one italic "Genus species" per legend line](docs/images/publication_style.png)

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

[`sample_data/`](sample_data) has sample datasets for beetles, seabirds, and
orchids.

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
