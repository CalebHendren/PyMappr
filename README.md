# RustyMappr

A proof-of-concept rewrite of [PyMappr](https://github.com/CalebHendren/PyMappr) in Rust and
TypeScript. Load a table of localities, see the points on a Natural Earth base map in any of
PyMappr's projections, and save a publication-ready PNG or SVG.

It is a desktop app built with [Tauri 2](https://tauri.app). The map logic runs in Rust; the
interface is Svelte 5 with Tailwind CSS.

## What works

- **Import** CSV, TSV, text (delimiter sniffed) and Excel/OpenDocument files. Every import goes
  through a column mapper that guesses the longitude, latitude and name columns the way PyMappr
  does; rows without usable coordinates are skipped and listed.
- **Coordinates** in decimal degrees or DMS, with hemisphere letters, decimal commas and every
  marker PyMappr accepts. This is a straight port of PyMappr's parser, and it is tested against
  PyMappr's own cases.
- **Projections**: all 13 of PyMappr's, from Equirectangular to the globe and the Lambert presets,
  with a custom centre for the globe and the Lambert projections. They are implemented in Rust
  with no PROJ dependency, and the tests check them against pyproj.
- **Base layers**: land, ocean, lakes, rivers, countries, states and provinces, and a graticule.
  The Natural Earth scale switches with zoom (1:110m, 1:50m, 1:10m), as in PyMappr.
- **Symbols**: points are grouped by any name column, all name columns (binomials), or the
  whole file. Palettes are Default, Okabe-Ito and black and white. Colour and shape can be set
  per group, and holotypes in a type-status column get open symbols.
- **Legend** in any corner, with an optional title, italic names, counts and a frame.
- **Standard preset**: black-and-white varied symbols, italic legend, 600 DPI at 17 cm
  (Zootaxa/Phytotaxa).
- **Save** the current view as SVG, or as PNG at a print width and DPI. The DPI is written into
  the file.

Not yet ported: projects, saved presets, inset maps, scale bar, compass, labels, raster
basemaps, bathymetry and the other thematic layers, Python/R code export, TIFF/PDF/JPEG/WebP,
installers and CI.

## Map data

RustyMappr reads the Natural Earth shapefiles that PyMappr downloads; it does not bundle them.
On first run it looks for, in order:

1. the folder saved in its settings;
2. `RUSTYMAPPR_DATA`;
3. `../PyMappr/data/shapes` beside this checkout.

If none of these exist, it asks for the folder. To fetch the data, run
`python scripts/fetch_data.py` in a PyMappr checkout.

## Run

Needs Rust 1.88+ and Node 20+.

```bash
npm install
npm run tauri dev
```

## Layout

| Path | What it holds |
|---|---|
| `crates/mappr-core/` | Everything that is not UI: `coords` (parser), `table` (reading and column guessing), `projection`, `basemap` (shapefiles), `render` (clipping, projection, SVG paths), `export` (PNG) |
| `src-tauri/` | Tauri commands wrapping `mappr-core` |
| `src/lib/` | Svelte UI: `state.svelte.ts` (app state), `api.ts` (typed commands), `styles.ts` (PyMappr's palettes and layer styles), `components/` |
| `scripts/pyproj_reference.py` | Regenerates the projection reference values from PyMappr's PROJ strings |

## Tests

```bash
cargo test -p mappr-core
npm run check
```

Some tests read `../PyMappr/sample_data` and `../PyMappr/data/shapes` and skip themselves when
those folders are missing. To eyeball every projection, run
`cargo run -p mappr-core --example preview --release -- <data/shapes> <out dir>`.
