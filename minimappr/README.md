# MiniMappr — source

MiniMappr is the lightweight, in-browser edition of PyMappr. It ships as a single
self-contained file, [`../index.html`](../index.html), which is what GitHub Pages
serves. That file is **generated** — this folder holds the readable source it is
built from.

## Build

```sh
python minimappr/build.py
```

This regenerates `../index.html`. No dependencies beyond the Python standard
library. Run it after changing anything in here, and commit the regenerated
`index.html` alongside your source changes.

## Layout

| Path | What it is |
|------|------------|
| `template.html` | Page shell with `@@TOKENS@@` for the injected blocks |
| `styles.css` | The `<style>` block |
| `body.html` | The `<body>` markup — header, side panels, modals |
| `vendor/` | D3 v7, d3-geo-projection v4, topojson-client v3 (verbatim, ISC-licensed) |
| `data/land-110m.json`, `data/countries-110m.json` | world-atlas 110m TopoJSON basemap |
| `data/samples.json` | The three built-in sample datasets |
| `app/*.js` | Application logic, concatenated in filename order |

### How the pieces are wired

`build.py` fills the template's tokens:

- `@@STYLES@@` ← `styles.css`
- `@@BODY@@` ← `body.html`
- `@@VENDOR@@` ← each `vendor/*.js`, wrapped in a `<script>`
- `@@DATA@@` ← each `data/*.json`, wrapped in `<script type="application/json" id="…">`;
  the app reads them back with `JSON.parse(document.getElementById("…").textContent)`
- `@@APP@@` ← every `app/*.js` concatenated, inside one `"use strict"` IIFE

Because the whole app lives in a single IIFE, the `app/*.js` files are **fragments
of one scope**, not standalone modules — they share top-level `const`s and
functions and must stay in filename order. The numeric prefixes fix that order.

### Sample data

`data/samples.json` maps each sample to `{marker, groupBy, name, text}`, where
`text` is a CSV. Columns are the taxonomic ranks
`Kingdom,Phylum,Class,Order,Family,Genus,Species` followed by `Latitude,Longitude`.
Each sample loads with a distinct default marker shape (beetles = circle,
orchids = square, seabirds = triangle) and is grouped by `Genus` by default; the
higher ranks are there so you can re-group or re-colour by any level in the UI.
