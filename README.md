# EzMaps

Simple desktop mapping software focused on high-quality point-distribution
maps. Load point data from a CSV, style it, explore Natural Earth base layers
in real time in several map projections, and export the result as a PNG.

![EzMaps](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue)

![EzMaps main window with grouped points and a legend](docs/images/app_points.png)

## Features

- **CSV input** with a Longitude column, a Latitude column, and any number of
  name columns (e.g. `Country, State, County, City, Longitude, Latitude`).
  Any column order works.
- **Column mapping on import**: when a CSV is opened you always choose which
  column is Latitude and which is Longitude, tick the columns to use as
  names, and pick whether the name labels use the CSV headers or the generic
  `Name 1, Name 2, Name 3, ...` numbering.
- **Coordinates in decimal degrees or DMS**: `-97.7431`, `97°44'35"W`,
  `97 44 35 W`, `97d 44m 35s W`, `37°46.493'N`, and more.
- **Real-time map view** - pan, zoom, and toggle layers live. Panning east or
  west **loops around the globe** seamlessly.
- **Map projections**: Equirectangular (default), Mercator, Robinson,
  Mollweide, Natural Earth, and Winkel Tripel - every layer, label, point,
  and the satellite basemap is reprojected live.
- **Basemaps**: *Simple* (white with black borders) or *Satellite*
  (full-color Natural Earth shaded relief, fully offline).
- **Layer toggles**: Countries, States/Provinces, US Counties,
  Lakes (outlines), Lakes fill (greyscale or blue), Rivers,
  Oceans (greyscale or blue), Roads. Switching Countries off removes the
  political borders but keeps the continent outlines.
- **Line thickness** control for all border/line layers.
- **Label toggles**: Countries, States/Provinces, US Counties, Lakes, Rivers.
  Every country in view is labelled even fully zoomed out; every state and
  county in view is labelled once you zoom in to its level.
- **Continent presets**: limit the view to Africa, Antarctica, Asia, Europe,
  North America, Oceania, South America, or the World.
- **Graticule** at 1°, 5°, or 10° with optional grid labels, drawn as
  projected curves in non-rectangular projections.
- **Customizable legend**:
  - per-group color, symbol, and size - symbols include circle, square,
    star, diamond, triangles, plus, X, pentagon, hexagon, octagon, and more
  - *Group by* any name column, and *Color by* another: group by Animal and
    color by Family, and every feline species gets its own shape in one
    color while canines get their own shapes in another color
  - *Vary symbols per group* to cycle shapes automatically
  - position, font size, column count, frame on/off, and a custom title
- **Save map as PNG** at 100-300 DPI.

## Screenshots

Every country labelled on the offline satellite basemap:

![Satellite basemap](docs/images/satellite_world.png)

The Robinson projection with a 10° graticule:

![Robinson projection](docs/images/robinson_world.png)

Countries layer off: political borders removed, continent outlines kept:

![Continent outlines](docs/images/continent_outlines.png)

The column-mapping dialog shown on every import - latitude/longitude
selection is required, name columns are ticked on and off:

![Column mapping dialog](docs/images/column_mapper.png)

US cities grouped and styled per group:

![US cities with legend](docs/images/us_cities_points.png)

## CSV format

The expected layout - any number of name columns followed by coordinates
(order is flexible; you confirm the mapping on import):

| Country       | State   | County  | City     | Longitude   | Latitude   |
|---------------|---------|---------|----------|-------------|------------|
| United States | Wyoming | Laramie | Cheyenne | -104.8202   | 41.1400    |
| United States | Wyoming | Natrona | Casper   | 106°18'47"W | 42°52'00"N |

Working examples in [`sample_data/`](sample_data):

- [`us_cities.csv`](sample_data/us_cities.csv) - two name columns, mixed
  decimal and DMS notation
- [`wyoming_cities.csv`](sample_data/wyoming_cities.csv) - four name columns
  (Country, State, County, City)
- [`felines_and_canines.csv`](sample_data/felines_and_canines.csv) - Family +
  Animal + Place, for the grouped-styling test case below
- [`dog_breeds.csv`](sample_data/dog_breeds.csv) - Species + Breed with the
  place of origin of ~90 dog breeds

## Test cases

### Wyoming cities by county (four name columns)

[`sample_data/wyoming_cities.csv`](sample_data/wyoming_cities.csv) lists the
largest town in every Wyoming county as
`United States, Wyoming, <county>, <city>` - Name 1 is the country, Name 2
the state, Name 3 the county, and Name 4 the city (Cheyenne, Casper,
Gillette, Laramie, ...). Grouping by the County column labels every group in
the legend, and the County labels layer names every county in view:

![Wyoming cities grouped by county](docs/images/wyoming_points.png)

### Felines and canines (Group by + Color by)

[`sample_data/felines_and_canines.csv`](sample_data/felines_and_canines.csv)
maps sightings/ranges of cat and dog species. Name 1 is the Family (Felines
or Canines) and Name 2 the Animal. Set *Group by* to Animal and *Color by*
to Family: domestic cats, lions, cheetahs, and tigers each get their own
shape in the feline color, while wolves, coyotes, and dingoes get their own
shapes in the canine color:

![Felines and canines styled by family](docs/images/felines_canines_points.png)

To reproduce these renders: `python scripts/make_screenshots.py`
(writes to `docs/images/`).

## Installing

Grab the latest build for your platform from the
[releases page](../../releases). Releases are built automatically whenever a
pull request is merged; each release also carries `EzMaps-<version>-source.zip`
and `EzMaps-<version>-source.tar.gz` archives of the source code.

| Platform       | File                                     | Install |
|----------------|------------------------------------------|---------|
| Windows        | `EzMaps-Setup-<version>.exe`             | Run the installer (asks about a desktop shortcut) |
| macOS          | `EzMaps-<version>-macOS.dmg`             | Open the DMG and drag EzMaps to Applications |
| Linux (Ubuntu) | `ezmaps_<version>_amd64.deb`             | `sudo apt install ./ezmaps_<version>_amd64.deb`, then run `ezmaps` |
| Linux (Fedora) | `ezmaps-<version>-1.<dist>.x86_64.rpm`   | `sudo dnf install ./ezmaps-<version>-*.x86_64.rpm`, then run `ezmaps` |
| Linux (Arch)   | `ezmaps-<version>-1-x86_64.pkg.tar.zst`  | `sudo pacman -U ezmaps-<version>-1-x86_64.pkg.tar.zst`, then run `ezmaps` |
| Any Linux      | `EzMaps-<version>-linux-<distro>-x86_64.tar.gz` | Extract and run `EzMaps/EzMaps` |

## Running from source

Requires Python 3.11+ with Tk support.

```bash
pip install -r requirements.txt
python scripts/fetch_data.py   # one-time download of Natural Earth data (~130 MB)
python -m ezmaps
```

## Building the packages

Automated: the
[`build-release.yml`](.github/workflows/build-release.yml) GitHub Actions
workflow builds the Windows installer, the macOS DMG, the Ubuntu `.deb` +
tarball, the Fedora `.rpm` + tarball, and the Arch `pkg.tar.zst` + tarball,
and attaches all of them - plus source `.zip`/`.tar.gz` archives - to a
GitHub release. It runs automatically when a pull request is merged into
`main` (and for `v*` tags or manual dispatch).

Locally:

- **Windows** (needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) with
  `iscc` on PATH): `packaging\build_windows.bat`
- **macOS**: `pyinstaller packaging/ezmaps.spec` then create a DMG from
  `dist/EzMaps.app`
- **Linux**: `pyinstaller packaging/ezmaps.spec` then
  `packaging/build_linux.sh ubuntu --deb` (Debian/Ubuntu),
  `packaging/build_rpm.sh` (Fedora), or
  `cd packaging/arch && makepkg` (Arch)

## Development

```bash
python -m pytest tests/            # coordinate parser + CSV loader + styling tests
python scripts/render_preview.py   # headless render smoke test -> preview/*.png
python scripts/make_screenshots.py # regenerate the README images
```

Project layout:

- `ezmaps/coords.py` - decimal/DMS coordinate parsing
- `ezmaps/data_loader.py` - CSV reading and column mapping (N name columns)
- `ezmaps/layers.py` - Natural Earth layer store (lazy loading, continents)
- `ezmaps/projections.py` - map projections (pyproj)
- `ezmaps/renderer.py` - matplotlib map rendering (layers, labels, graticule,
  projections, wrap-around panning, legend)
- `ezmaps/styles.py` - point styles, marker symbols, group/color-by styling
- `ezmaps/app.py`, `ezmaps/ui/` - Tkinter application
- `scripts/fetch_data.py` - downloads and prepares the bundled map data
- `packaging/` - PyInstaller spec, Inno Setup script, Linux/Fedora/Arch
  packaging

## Support Me

If EzMaps is useful to you, you can support its development on Patreon:

[**patreon.com/cw/CalebHendren**](https://www.patreon.com/cw/CalebHendren)

There is also a *Support Me* section in the app's side panel and a
*Support me on Patreon* entry in the Help menu.

## Citation

Citing EzMaps is not necessary, but it is welcome. If EzMaps was useful in
your work - a map in a paper, a poster, a blog post, anything - you can
credit it like this:

> Hendren, Caleb. *EzMaps* [computer software].
> https://github.com/CalebHendren/EzMaps

## Data credits

Map data from [Natural Earth](https://www.naturalearthdata.com/) (public
domain): country/state/county boundaries, lakes, rivers, oceans, roads, and
the Natural Earth I shaded-relief raster.
