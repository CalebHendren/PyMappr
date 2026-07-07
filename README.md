# EzMaps

Simple desktop mapping software. Load point data from a CSV, style it, explore
Natural Earth base layers in real time, build heatmaps, and export the result
as a PNG.

![EzMaps](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue)

## Features

- **CSV input** with four columns - Name 1, Name 2, Longitude, Latitude
  (e.g. `County, City, Longitude, Latitude`). Any column order works; a
  column-mapping dialog lets you confirm or fix the guess before import.
- **Coordinates in decimal degrees or DMS**: `-97.7431`, `97°44'35"W`,
  `97 44 35 W`, `97d 44m 35s W`, `37°46.493'N`, and more.
- **Real-time map view** - pan, zoom, and toggle layers live.
- **Basemaps**: *Simple* (white with black country borders) or *Satellite*
  (full-color Natural Earth shaded relief, fully offline).
- **Layer toggles**: Countries, States/Provinces, US Counties,
  Lakes (outlines), Lakes fill (greyscale or blue), Rivers,
  Oceans (greyscale or blue), Roads.
- **Label toggles**: Countries, States/Provinces, US Counties, Lakes, Rivers.
- **Continent presets**: limit the view to Africa, Antarctica, Asia, Europe,
  North America, Oceania, South America, or the World.
- **Graticule** at 1°, 5°, or 10° with optional grid labels.
- **Customizable legend**: per-group color, symbol (circle, square, triangle,
  diamond, star, ...), and size.
- **Heatmap** mode with radius, opacity, and color-scheme controls, plus an
  option to draw the raw data points on top.
- **Save map as PNG** at 100-300 DPI.

## CSV format

The expected layout (headers are flexible - you can remap columns on import):

| Name 1 | Name 2 | Longitude  | Latitude  |
|--------|--------|------------|-----------|
| County | City   | -97.7431   | 30.2672   |
| King   | Seattle| 122°19'59"W| 47°36'35"N|

See [`sample_data/us_cities.csv`](sample_data/us_cities.csv) for a working
example mixing decimal and DMS notation.

## Installing on Windows

Download `EzMaps-Setup-<version>.exe` from the
[releases page](../../releases) (or the latest
[build artifact](../../actions/workflows/build-windows.yml)) and run it.
The installer asks whether to create a desktop shortcut.

## Running from source

Requires Python 3.11+ with Tk support.

```bash
pip install -r requirements.txt
python scripts/fetch_data.py   # one-time download of Natural Earth data (~130 MB)
python -m ezmaps
```

## Building the Windows installer

Automated: the [`build-windows.yml`](.github/workflows/build-windows.yml)
GitHub Actions workflow builds `EzMaps-Setup-<version>.exe` on every push and
attaches it to releases for `v*` tags.

Locally on Windows (needs [Inno Setup 6](https://jrsoftware.org/isinfo.php)
with `iscc` on PATH):

```bat
packaging\build_windows.bat
```

## Development

```bash
python -m pytest tests/            # coordinate parser + CSV loader tests
python scripts/render_preview.py   # headless render smoke test -> preview/*.png
```

Project layout:

- `ezmaps/coords.py` - decimal/DMS coordinate parsing
- `ezmaps/data_loader.py` - CSV reading and column mapping
- `ezmaps/layers.py` - Natural Earth layer store (lazy loading)
- `ezmaps/renderer.py` - matplotlib map rendering (layers, labels, graticule,
  heatmap, legend)
- `ezmaps/app.py`, `ezmaps/ui/` - Tkinter application
- `scripts/fetch_data.py` - downloads and prepares the bundled map data
- `packaging/` - PyInstaller spec, Inno Setup script, local build script

## Data credits

Map data from [Natural Earth](https://www.naturalearthdata.com/) (public
domain): country/state/county boundaries, lakes, rivers, oceans, roads, and
the Natural Earth I shaded-relief raster.
