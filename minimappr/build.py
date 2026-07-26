#!/usr/bin/env python3
"""Assemble the self-contained MiniMappr page.

MiniMappr ships as a single self-contained ``index.html`` at the repo root
(that is what GitHub Pages serves). The *source* for that page lives here, split
into readable pieces:

    minimappr/
      template.html   page shell with @@TOKENS@@ for the injected blocks
      styles.css      the <style> block
      body.html       the <body> markup (header, panels, modals)
      vendor/         D3, d3-geo-projection, topojson-client (verbatim)
      data/           land-110m.json, countries-110m.json, samples.json
      app/            application JS, in load order (concatenated inside one IIFE)

Run ``python minimappr/build.py`` after editing any of these to regenerate the
root ``index.html``. No dependencies beyond the standard library.
"""
from __future__ import annotations
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "index.html")

# vendor libraries, in the order they must load
VENDOR = [
    "vendor/d3.v7.9.0.min.js",
    "vendor/d3-geo-projection.v4.0.0.min.js",
    "vendor/topojson-client.v3.1.0.min.js",
]
# basemap + sample data, injected as <script type="application/json"> the app reads by id
DATA = [
    ("land-topo", "data/land-110m.json"),
    ("countries-topo", "data/countries-110m.json"),
    ("samples", "data/samples.json"),
]


def read(rel: str) -> str:
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


def build() -> str:
    template = read("template.html")
    styles = read("styles.css")
    body = read("body.html")

    vendor = "\n".join(f"<script>{read(p)}</script>" for p in VENDOR)

    data_parts = []
    for tag_id, path in DATA:
        raw = read(path)
        json.loads(raw)  # fail loudly on malformed data
        data_parts.append(f'<script type="application/json" id="{tag_id}">{raw}</script>')
    data = "\n".join(data_parts)

    # app/*.js are concatenated in filename order inside the IIFE the template opens
    app_files = sorted(glob.glob(os.path.join(HERE, "app", "*.js")))
    if not app_files:
        raise SystemExit("no app/*.js fragments found")
    app = "".join(open(f, encoding="utf-8").read() for f in app_files)

    html = (template
            .replace("@@STYLES@@", styles)
            .replace("@@BODY@@", body)
            .replace("@@VENDOR@@", vendor)
            .replace("@@DATA@@", data)
            .replace("@@APP@@", app))
    return html


def main() -> None:
    html = build()
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"built {OUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    sys.exit(main())
