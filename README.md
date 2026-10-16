# RustyMappr

A Rust and TypeScript port of [PyMappr](https://github.com/CalebHendren/PyMappr): load a table of
localities, style the points, and save a publication-ready distribution map. It is a desktop app
built with [Tauri 2](https://tauri.app); the map logic is in Rust and the interface is Svelte 5
with Tailwind CSS.

RustyMappr reads and writes PyMappr's `.pymappr` projects and `.pymappr-preset` presets, so a
project moves between the two apps. Its maps are checked against PyMappr's own output (see
[Checking against PyMappr](#checking-against-pymappr)).

## What it does

- **Import** CSV, TSV, text (delimiter sniffed) and Excel/OpenDocument files through a column
  mapper that guesses longitude, latitude and name columns as PyMappr does. Rows without usable
  coordinates are listed, and points far from the rest (often a missing minus sign) are flagged.
  Coordinates can be typed in too (Manual entry).
- **Coordinates** in decimal degrees or DMS, with hemisphere letters and decimal commas: a port
  of PyMappr's parser, tested with PyMappr's cases.
- **Projections**: all 13 of PyMappr's, from Equirectangular to the globe and the Lambert
  presets, written in Rust and tested against pyproj.
- **Layers**: every Natural Earth layer PyMappr offers, at 1:110m, 1:50m or 1:10m depending on
  zoom, plus bathymetry, raster basemaps (relief and Blue Marble), labels, a graticule with tick
  labels, and the optional biodiversity and ecoregion overlays. Political extras (sovereign
  states, map units, disputed areas, time zones, maritime and EEZ lines) sit behind
  **Show advanced options**.
- **Counties and districts**: US counties from Natural Earth, and district (ADM2) boundaries for
  other countries downloaded on request from [geoBoundaries](https://www.geoboundaries.org).
- **Symbols and legend**: a port of PyMappr's styling and legend code: group, colour and symbol
  by any column, nested and crossed keys, open symbols for holotypes, per-row overrides, every
  legend layout option, and the built-in **Standard** preset (Zootaxa/Phytotaxa figure).
- **Map furniture**: scale bar, compass, inset map, portrait orientation; the legend, scale bar,
  inset and labels can be dragged.
- **Save** as PNG, JPEG, TIFF (LZW, greyscale when the map has no colour), PDF, SVG or WebP at a
  print width and DPI. Text and symbols print at their point sizes.
- **Export as code**: a standalone Python (matplotlib) or R (ggplot2) script that recreates the
  map, byte-identical to PyMappr's. An optional **AI check** (bring your own OpenRouter key) reads
  the script and suggests fixes as a diff; you choose what is sent, and point data is held back
  unless you include it.
- Projects, presets, the session (saved on exit, restored at launch), a light and dark theme, and
  an update check.

## Map data

On first run RustyMappr offers to download the Natural Earth data (about 70 MB, plus about
290 MB for the relief basemaps) into `%LOCALAPPDATA%\RustyMappr\data`. It can use PyMappr's
`data` folder instead (Layers > Map data > Use another folder). Natural Earth data is public
domain; the optional overlays and geoBoundaries districts carry their own open licences, shown in
Help > About.

## Run

Needs Rust 1.88+ and Node 20+.

```bash
npm install
npm run tauri dev
```

Release build: `npm run tauri build -- --no-bundle`.

## Layout

| Path | What it holds |
|---|---|
| `crates/mappr-core/` | Everything that is not UI: coordinates, tables, projections, Natural Earth layers, rendering (clipping, labels, graticule, scale bar, inset, rasters), districts, image export |
| `crates/mappr-codegen/` | The Python/R code export, ported from PyMappr with its templates |
| `src-tauri/` | The app shell: one `core` command dispatching to `cmd_*.rs`; a dev HTTP bridge in `src/bin/devbridge.rs` |
| `src/lib/` | The Svelte UI: `store.svelte.ts`, `model.ts` (PyMappr's project schema), `symbology.ts` and `legend.ts` (PyMappr's styling), `layout.ts` (figure geometry), components |
| `scripts/` | Reference generators that run PyMappr itself, and the parity check |

## Tests

```bash
cargo test --workspace
npm test
npm run check
```

Some tests read PyMappr's sample data and map data (`PYMAPPR_DIR`, default `C:\PyCharm\PyMappr`)
and skip themselves when it is missing.

## Checking against PyMappr

`scripts/parity.py` renders each fixture project in PyMappr and in RustyMappr and compares them:
every text, marker, legend frame and map box must match within 0.01 pt, and pixels may differ
only in anti-aliasing. It needs the dev bridge and the Vite dev server:

```bash
npm run bridge
npm run dev
C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/parity.py <out dir>
```
