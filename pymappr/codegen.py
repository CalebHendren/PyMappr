"""Deterministic Python/R code export: recreate the current map in an IDE.

Unlike the experimental LLM assist (``pymappr/llm.py``), nothing here
talks to a model or the network at generation time. Selecting a language
in the export dialog simply pastes the **pre-made function templates**
below into a ``.py`` or ``.R`` file, together with one configuration
block filled in from the current map state. Same input, same output,
every time - so the result is testable and trustworthy.

The generated script recreates the map with common open toolchains:
pandas + geopandas + matplotlib for Python, and sf + ggplot2 for R.
Base layers are downloaded straight from Natural Earth (the same data
PyMappr renders, cached in a local folder); the user's point data is
loaded from the original file (manually entered datasets are embedded
inline so the script stays standalone). A few renderer niceties - map
labels, the compass, bathymetry shading, the satellite basemap, and the
optional biodiversity overlays - are listed in the script header as not
reproduced instead of being silently dropped.

This module is UI-free; the dialog lives in ``pymappr/ui/code_export.py``.
"""

from __future__ import annotations

import math

from pymappr import __version__
from pymappr.layers import CONTINENT_EXTENTS
from pymappr.projections import get_projection, proj4_string
from pymappr.renderer import (FILL_COLORS, FILL_LAYERS, LINE_LAYERS,
                              POINT_LAYERS)
from pymappr.styles import (PointStyle, attribute_style_maps,
                            default_styles, group_points,
                            style_by_attributes)
from pymappr.updates import GITHUB_REPO

LANGUAGES = ("Python", "R")
CODE_EXTENSIONS = {"Python": ".py", "R": ".R"}

# Home page for the attribution comment at the top of every script.
REPO_URL = f"https://github.com/{GITHUB_REPO}"

WORLD_EXTENT = (-180.0, 180.0, -90.0, 90.0)

# Grid spacing dropdown -> degrees (mirrors the control panel choices).
_GRATICULE_DEGREES = {"1\N{DEGREE SIGN}": 1.0, "5\N{DEGREE SIGN}": 5.0,
                      "10\N{DEGREE SIGN}": 10.0}

# PyMappr layer key -> (Natural Earth dataset, category, scale, member,
# filter). *member* names the shapefile inside multi-shapefile archives;
# *filter* is (column, values, keep) applied after download, mirroring
# pymappr.layers.DERIVED. Scales follow what PyMappr itself renders.
_NE = {
    "countries": ("admin_0_countries", "cultural", "50m", None, None),
    "states": ("admin_1_states_provinces", "cultural", "10m", None, None),
    "counties": ("admin_2_counties", "cultural", "10m", None, None),
    "sovereignty": ("admin_0_sovereignty", "cultural", "50m", None, None),
    "map_units": ("admin_0_map_units", "cultural", "50m", None, None),
    "subunits": ("admin_0_map_subunits", "cultural", "50m", None, None),
    "dependencies": ("admin_0_countries", "cultural", "10m", None,
                     ("type", ["Dependency", "Lease"], True)),
    "disputed": ("admin_0_disputed_areas", "cultural", "10m", None, None),
    "disputed_lines": ("admin_0_boundary_lines_disputed_areas", "cultural",
                       "10m", None, None),
    "timezones": ("time_zones", "cultural", "10m", None, None),
    "maritime": ("admin_0_boundary_lines_maritime_indicator", "cultural",
                 "10m", None,
                 ("featurecla", ["Marine Indicator 200 mi nl"], False)),
    "eez": ("admin_0_boundary_lines_maritime_indicator", "cultural", "10m",
            None, ("featurecla", ["Marine Indicator 200 mi nl"], True)),
    "rivers": ("rivers_lake_centerlines", "physical", "10m", None, None),
    "wadis": ("rivers_lake_centerlines", "physical", "10m", None,
              ("featurecla", ["River (Intermittent)"], True)),
    "lakes_outline": ("lakes", "physical", "50m", None, None),
    "reefs": ("reefs", "physical", "10m", None, None),
    "regions": ("geography_regions_polys", "physical", "10m", None, None),
    "deserts": ("geography_regions_polys", "physical", "10m", None,
                ("featurecla", ["Desert"], True)),
    "roads": ("roads", "cultural", "10m", None, None),
    "land": ("land", "physical", "50m", None, None),
    "glaciers": ("glaciated_areas", "physical", "10m", None, None),
    "ice_shelves": ("antarctic_ice_shelves_polys", "physical", "50m",
                    None, None),
    "playas": ("playas", "physical", "10m", None, None),
    "urban": ("urban_areas", "cultural", "10m", None, None),
    "parks": ("parks_and_protected_lands", "cultural", "10m",
              "ne_10m_parks_and_protected_lands_area", None),
    "ocean": ("ocean", "physical", "50m", None, None),
    "lakes": ("lakes", "physical", "50m", None, None),
    "cities": ("populated_places_simple", "cultural", "10m", None, None),
    "capitals": ("populated_places_simple", "cultural", "10m", None,
                 ("adm0cap", ["1"], True)),
    "airports": ("airports", "cultural", "10m", None, None),
    "ports": ("ports", "cultural", "10m", None, None),
}

# Layers PyMappr draws that the generated script deliberately does not:
# their data is not a single Natural Earth download.
_NOT_REPRODUCED_FILLS = {
    "biodiversity": "Biodiversity hotspots overlay (Conservation "
                    "International data, not Natural Earth)",
    "ecoregions": "Terrestrial ecoregions overlay (RESOLVE data, not "
                  "Natural Earth)",
    "marine_ecoregions": "Marine ecoregions overlay (WWF/TNC data, not "
                         "Natural Earth)",
}

# PyMappr marker name -> R pch code, honoring open (outline-only)
# variants where base R has one. Shapes base R lacks (pentagon, hexagon,
# octagon) fall back to circles; the generated script says so.
_R_PCH = {
    "Circle": 16, "Circle (open)": 1,
    "Square": 15, "Square (open)": 0,
    "Triangle": 17, "Triangle (open)": 2,
    "Triangle down": 6, "Triangle down (open)": 6,
    "Triangle left": 17, "Triangle left (open)": 2,
    "Triangle right": 17, "Triangle right (open)": 2,
    "Diamond": 18, "Diamond (open)": 5,
    "Thin diamond": 18, "Thin diamond (open)": 5,
    "Star": 8, "Star (open)": 8,
    "Plus": 3, "Plus (open)": 3,
    "X": 4, "X (open)": 4,
    "Pentagon": 16, "Pentagon (open)": 1,
    "Hexagon": 16, "Hexagon (open)": 1,
    "Octagon": 16, "Octagon (open)": 1,
    "Dot": 20, "Dot (open)": 20,
}

# ggplot2 linetype names approximating the renderer's dash tuples.
_R_LINETYPES = {
    (0, (1, 2)): "dotted",
    (0, (3, 2)): "dashed",
    (0, (3, 3)): "dashed",
    (0, (4, 2)): "dashed",
    (0, (5, 3)): "longdash",
    (0, (6, 3)): "longdash",
}


# ----------------------------------------------------------- configuration

def _num(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _origin(state_map: dict) -> tuple[float | None, float | None]:
    """The Lambert origin from the stored map state ("" = default)."""

    def parse(key):
        raw = str(state_map.get(key, "")).strip()
        try:
            return float(raw)
        except ValueError:
            return None

    return parse("proj_lon0"), parse("proj_lat0")


def view_extent_lonlat(state: dict) -> tuple[float, float, float, float]:
    """The current view as a (lon_min, lon_max, lat_min, lat_max) box.

    The stored view is in projected coordinates; the box edges are
    densified and inverse-projected so curved edges are bounded
    correctly. Falls back to the continent preset (then the world) when
    the view is missing, covers the whole projection, or inverse-projects
    to nothing finite.
    """
    import numpy as np

    m = dict(state.get("map", {}))
    fallback = CONTINENT_EXTENTS.get(str(m.get("continent", "World")),
                                     WORLD_EXTENT)
    view = dict(state.get("view", {}))
    xlim, ylim = view.get("xlim"), view.get("ylim")
    if (not isinstance(xlim, (list, tuple)) or len(xlim) != 2
            or not isinstance(ylim, (list, tuple)) or len(ylim) != 2):
        return fallback
    try:
        x0, x1 = sorted(float(v) for v in xlim)
        y0, y1 = sorted(float(v) for v in ylim)
    except (TypeError, ValueError):
        return fallback
    lon0, lat0 = _origin(m)
    projection = get_projection(str(m.get("projection", "Equirectangular")),
                                lon0, lat0)
    bx0, bx1, by0, by1 = projection.bounds
    # A view covering (almost) the whole projected world is just the
    # continent preset; the corners of e.g. Robinson's bounding box lie
    # off the globe and would inverse-project to nothing useful.
    if (x1 - x0) >= 0.99 * (bx1 - bx0) and (y1 - y0) >= 0.99 * (by1 - by0):
        return fallback
    if projection.is_geographic:
        return (max(x0, -180.0), min(x1, 180.0),
                max(y0, -90.0), min(y1, 90.0))
    n = 40
    xs = np.concatenate([np.linspace(x0, x1, n), np.linspace(x0, x1, n),
                         np.full(n, x0), np.full(n, x1)])
    ys = np.concatenate([np.full(n, y0), np.full(n, y1),
                         np.linspace(y0, y1, n), np.linspace(y0, y1, n)])
    lons, lats = projection.inverse(xs, ys)
    good = np.isfinite(lons) & np.isfinite(lats)
    if not good.any():
        return fallback
    return (max(float(lons[good].min()), -180.0),
            min(float(lons[good].max()), 180.0),
            max(float(lats[good].min()), -90.0),
            min(float(lats[good].max()), 90.0))


def _base_layers(m: dict) -> tuple[list[dict], list[str]]:
    """The enabled base layers as config dicts (draw order), plus notes
    about enabled features the script does not reproduce."""
    scale = _num(m.get("line_width", 1.0), 1.0)
    enabled = {section: [key for key, on in dict(m.get(section, {})).items()
                         if on]
               for section in ("lines", "fills", "points")}
    layers: list[dict] = []
    notes: list[str] = []

    def ne_layer(key: str, kind: str, **style) -> dict:
        name, category, ne_scale, member, filt = _NE[key]
        return {"key": key, "name": name, "category": category,
                "scale": ne_scale, "member": member, "filter": filt,
                "kind": kind, **style}

    for mode_key, mode in (("ocean", str(m.get("ocean", "none"))),
                           ("lakes", str(m.get("lake_fill", "none")))):
        if mode != "none":
            layers.append(ne_layer(
                mode_key, "fill", z=0.3 if mode_key == "ocean" else 0.5,
                color=FILL_COLORS[(mode_key, mode)], edgecolor="none",
                width=0.0, alpha=1.0))
    for key in enabled["fills"]:
        if key in _NOT_REPRODUCED_FILLS:
            notes.append(_NOT_REPRODUCED_FILLS[key])
            continue
        source, face, edge, edge_width, alpha, z = FILL_LAYERS[key]
        layers.append(ne_layer(key, "fill", z=z, color=face, edgecolor=edge,
                               width=edge_width * scale, alpha=alpha))
    for key in enabled["lines"]:
        source, color, width, z, linestyle = LINE_LAYERS[key]
        layers.append(ne_layer(key, "line", z=z, color=color,
                               width=width * scale, linestyle=linestyle))
    capitals_only = bool(m.get("capitals_only", False))
    for key in enabled["points"]:
        if key == "cities" and capitals_only:
            key = "capitals"
        source, marker, size, face, edge, _bias = POINT_LAYERS[key]
        layers.append(ne_layer(key, "point", z=2.45, color=face,
                               edgecolor=edge, marker=marker, size=size))

    if bool(m.get("bathymetry", False)):
        notes.append("Bathymetry (12 stacked Natural Earth depth layers)")
    if str(m.get("basemap", "simple")) == "satellite":
        notes.append("The satellite (shaded relief) basemap raster")
    if bool(m.get("compass", False)):
        notes.append("The compass (north arrow)")
    layers.sort(key=lambda layer: layer["z"])
    return layers, notes


def _display_labels(raw_labels: list[str], entry_name: str, multi: bool,
                    attribute_mode: bool,
                    used: set[str]) -> dict[str, str]:
    """Raw group label -> legend label, disambiguated across datasets the
    same way the app does it."""
    mapping: dict[str, str] = {}
    for label in raw_labels:
        display = label
        if multi and attribute_mode:
            display = f"{entry_name}: {label}"
        elif multi and label == "All points":
            display = entry_name
        elif multi and label in used:
            display = f"{label} ({entry_name})"
        used.add(display)
        mapping[label] = display
    return mapping


def _dataset_configs(entries) -> tuple[list[dict], dict[str, PointStyle]]:
    """Per-dataset script configs plus the combined legend-label -> style
    map, replicating how the app assigns styles at render time."""
    visible = [e for e in entries if e.visible and len(e.dataset)]
    multi = len(visible) > 1
    used: set[str] = set()
    styles: dict[str, PointStyle] = {}
    configs: list[dict] = []
    palette_offset = 0
    for entry in visible:
        frame = entry.dataset.frame
        key_by_label = dict(zip(entry.dataset.name_labels,
                                entry.dataset.name_keys))
        color_key = key_by_label.get(entry.color_by)
        symbol_key = key_by_label.get(entry.symbol_by)
        config = {
            "name": entry.name,
            "path": entry.dataset.source_path or None,
            "inline_data": None,
            "lon_col": None,   # auto-detected by the pre-made loader
            "lat_col": None,
            "group_col": None,
            "color_col": None,
            "symbol_col": None,
            "default_label": entry.name,
            "label_map": {},
        }
        if entry.manual is not None or not entry.dataset.source_path:
            config["path"] = None
            config["inline_data"] = _inline_csv(entry)
            config["lon_col"], config["lat_col"] = "Longitude", "Latitude"
        if symbol_key is not None:
            # Two-attribute styling: one style per (color, symbol) pair.
            config["color_col"] = entry.color_by or None
            config["symbol_col"] = entry.symbol_by or None
            color_map, symbol_map = attribute_style_maps(frame, color_key,
                                                         symbol_key)
            combos = style_by_attributes(frame, color_key, symbol_key,
                                         color_map, symbol_map)
            raw = [label for label, _style, _sub in combos]
            display = _display_labels(raw, entry.name, multi, True, used)
            for label, style, _sub in combos:
                styles[display[label]] = style
        else:
            group_key = key_by_label.get(entry.group_by)
            groups = group_points(frame, group_key)
            labels = [label for label, _sub in groups]
            color_keys = None
            if color_key is not None and color_key in frame.columns:
                color_keys = [str(sub[color_key].iloc[0]) if len(sub) else ""
                              for _label, sub in groups]
            fresh = default_styles(labels, color_keys=color_keys,
                                   vary_symbols=entry.vary_symbols,
                                   palette_offset=palette_offset)
            palette_offset += len(labels)
            display = _display_labels(labels, entry.name, multi, False, used)
            for label in labels:
                styles[display[label]] = entry.styles.get(label,
                                                          fresh[label])
            if group_key is not None:
                config["group_col"] = entry.group_by
        config["label_map"] = display
        configs.append(config)
    return configs, styles


def _inline_csv(entry) -> str:
    """A manual/pathless dataset as CSV text, embedded in the script."""
    frame = entry.dataset.frame
    columns = dict(zip(entry.dataset.name_keys, entry.dataset.name_labels))
    columns.update({"lon": "Longitude", "lat": "Latitude"})
    subset = frame[[c for c in frame.columns if c in columns]]
    return subset.rename(columns=columns).to_csv(index=False)


def build_config(state: dict, entries, project_name: str = "map") -> dict:
    """Everything the script templates need, from the app state."""
    m = dict(state.get("map", {}))
    legend = dict(state.get("legend", {}))
    layers, notes = _base_layers(m)
    if any(dict(m.get("labels", {})).values()):
        notes.append("Map labels (country/city/... name placement)")
    datasets, styles = _dataset_configs(entries)
    lon0, lat0 = _origin(m)
    projection = str(m.get("projection", "Equirectangular"))
    title = str(legend.get("title", "")).strip()
    if not title and len(datasets) == 1 and datasets[0]["group_col"]:
        title = datasets[0]["group_col"]
    return {
        "project": project_name,
        "generator": f"PyMappr {__version__}",
        "projection": projection,
        "crs": proj4_string(projection, lon0, lat0) or "EPSG:4326",
        "extent": view_extent_lonlat(state),
        "layers": layers,
        "datasets": datasets,
        "styles": styles,
        "legend": {
            "show": bool(legend.get("show", True)),
            "frame": bool(legend.get("frame", True)),
            "location": str(legend.get("location", "best")),
            "fontsize": _num(legend.get("fontsize", 8), 8.0),
            "title_fontsize": _num(legend.get("title_fontsize", 9), 9.0),
            "columns": max(1, int(_num(legend.get("columns", 1), 1.0))),
            "marker_scale": max(0.1, _num(legend.get("marker_scale", 1.0),
                                          1.0)),
            "label_spacing": max(0.0, _num(legend.get("label_spacing", 0.5),
                                           0.5)),
            "title": title,
        },
        "point_alpha": _num(state.get("point_alpha", 1.0), 1.0),
        "dpi": int(_num(m.get("dpi", 200), 200.0)),
        "graticule": _GRATICULE_DEGREES.get(str(m.get("graticule", "Off"))),
        "notes": notes,
    }


# ----------------------------------------------------- literal formatting

def _py(value) -> str:
    """A Python literal for a config value (round-trips through repr)."""
    if isinstance(value, float):
        return repr(round(value, 6))
    return repr(value)


def _r(value) -> str:
    """An R literal for a config value."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(round(float(value), 6)) if isinstance(value, float) \
            else str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\n", "\\n").replace("\r", "").replace("\t", "\\t")
    return f'"{text}"'


def _r_named(pairs: list[tuple[str, str]], indent: str) -> str:
    """An R c(...) or list(...) body: one `name = value` per line."""
    inner = f",\n{indent}".join(f"{_r(name)} = {value}"
                                for name, value in pairs)
    return f"\n{indent}{inner}\n{indent[:-2]}"


def _size_mm(area: float) -> float:
    """Matplotlib scatter area (points^2) -> approximate ggplot2 size."""
    return round(max(math.sqrt(max(area, 1.0)) / 2.845, 0.3), 2)


def _linewidth_mm(width: float) -> float:
    """Matplotlib line width (points) -> approximate ggplot2 linewidth."""
    return round(max(width / 2.13, 0.05), 2)


def _r_linetype(linestyle) -> str:
    if isinstance(linestyle, tuple):
        return _R_LINETYPES.get(
            (linestyle[0], tuple(linestyle[1])), "dashed")
    return "solid"


# --------------------------------------------------------- Python template

def _safe_name(name: str) -> str:
    """A project name safe to embed in a docstring/comment."""
    return str(name).replace('"', "'").replace("\n", " ").strip() or "map"


def _py_header(config: dict) -> str:
    notes = "".join(f"\n#   - {note}" for note in config["notes"])
    if notes:
        notes = ("\n# Shown in PyMappr but NOT reproduced by this script:"
                 + notes)
    return f'''\
#!/usr/bin/env python3
# Made with {config["generator"]} - {REPO_URL}
"""Recreate the PyMappr map "{_safe_name(config["project"])}" outside PyMappr.

Generated by {config["generator"]} from pre-made function templates and
the map's saved settings - deterministically, with no AI involved.

Requires:  pip install pandas geopandas matplotlib
Run:       python this_script.py
Output:    map.png (also opens an interactive window)

Base layers are downloaded from Natural Earth on first run and cached
in ./naturalearth_cache. Point data is loaded from the original file
path(s) below (edit them if the files moved); longitude/latitude
columns are auto-detected from their names and can be pinned in
DATASETS. PyMappr parsed DMS coordinates on import - if your file
stores DMS (e.g. 97\N{DEGREE SIGN}44'W), convert to decimal degrees first.
"""
# Projection: {config["projection"]}{notes}
'''


def _py_config(config: dict) -> str:
    lines = ["", "# ------------------------- map configuration (from "
                 "PyMappr) -------------------------", ""]
    lines.append(f'MAP_CRS = {_py(config["crs"])}')
    extent = tuple(round(v, 4) for v in config["extent"])
    lines.append(f"EXTENT_LONLAT = {_py(extent)}"
                 "  # lon_min, lon_max, lat_min, lat_max")
    lines.append(f'POINT_ALPHA = {_py(config["point_alpha"])}')
    lines.append(f'DPI = {_py(config["dpi"])}')
    lines.append(f'GRID_INTERVAL = {_py(config["graticule"])}'
                 "  # graticule spacing in degrees (None = off)")
    lines.append('OUTPUT_FILE = "map.png"')
    lines.append("")
    lines.append("# Natural Earth base layers enabled in PyMappr, in draw "
                 "order. A filter is")
    lines.append("# (column, kept values, keep?) applied after download.")
    lines.append("NE_LAYERS = [")
    for layer in config["layers"]:
        entry = {"name": layer["name"], "category": layer["category"],
                 "scale": layer["scale"], "kind": layer["kind"],
                 "color": layer["color"]}
        if layer.get("member"):
            entry["member"] = layer["member"]
        if layer.get("filter"):
            entry["filter"] = layer["filter"]
        if layer["kind"] == "fill":
            entry.update(edgecolor=layer["edgecolor"],
                         width=round(layer["width"], 3),
                         alpha=layer["alpha"])
        elif layer["kind"] == "line":
            entry.update(width=round(layer["width"], 3),
                         linestyle=layer["linestyle"])
        else:
            entry.update(marker=layer["marker"], size=layer["size"],
                         edgecolor=layer["edgecolor"])
        body = ", ".join(f"{_py(k)}: {_py(v)}" for k, v in entry.items())
        lines.append(f"    # PyMappr layer: {layer['key']}")
        lines.append(f"    {{{body}}},")
    lines.append("]")
    lines.append("")
    lines.append("# One entry per dataset. lon_col/lat_col None = "
                 "auto-detect by column name.")
    lines.append("DATASETS = [")
    for spec in config["datasets"]:
        lines.append("    {")
        for key in ("name", "path", "inline_data", "lon_col", "lat_col",
                    "group_col", "color_col", "symbol_col",
                    "default_label", "label_map"):
            lines.append(f"        {_py(key)}: {_py(spec[key])},")
        lines.append("    },")
    lines.append("]")
    lines.append("")
    lines.append("# Legend label -> point style, in legend order "
                 "(open = outline-only marker).")
    lines.append("STYLES = {")
    for label, style in config["styles"].items():
        value = {"color": style.color, "marker": style.mpl_marker,
                 "size": style.size, "open": style.is_open}
        body = ", ".join(f"{_py(k)}: {_py(v)}" for k, v in value.items())
        lines.append(f"    {_py(label)}: {{{body}}},")
    lines.append("}")
    lines.append("")
    legend = config["legend"]
    body = ", ".join(f"{_py(k)}: {_py(v)}" for k, v in legend.items())
    lines.append(f"LEGEND = {{{body}}}")
    return "\n".join(lines) + "\n"


# The pre-made functions pasted verbatim into every generated Python
# script; only the configuration block above them changes.
_PY_FUNCTIONS = '''

# ------------------- pre-made functions (identical for every export) -----

import io
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

LON_HINTS = ("lon", "lng", "long", "longitude", "x")
LAT_HINTS = ("lat", "latitude", "y")
FALLBACK_STYLE = {"color": "#7f7f7f", "marker": "o", "size": 30.0,
                  "open": False}


def load_natural_earth(name, category, scale, member=None):
    """Download a Natural Earth layer (cached in ./naturalearth_cache)."""
    cache = Path("naturalearth_cache")
    cache.mkdir(exist_ok=True)
    stem = f"ne_{scale}_{name}"
    zip_path = cache / f"{stem}.zip"
    if not zip_path.exists():
        url = (f"https://naturalearth.s3.amazonaws.com/"
               f"{scale}_{category}/{stem}.zip")
        print(f"Downloading {url}")
        urlretrieve(url, zip_path)
    folder = cache / stem
    if not folder.exists():
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(folder)
    return gpd.read_file(folder / f"{member or stem}.shp")


def filter_layer(gdf, spec):
    """Keep (or drop) features matching (column, values, keep)."""
    if not spec:
        return gdf
    column, values, keep = spec

    def norm(value):
        text = str(value).strip().lower()
        try:
            return str(float(text))
        except ValueError:
            return text

    match = next((c for c in gdf.columns
                  if c.lower() == str(column).lower()), None)
    if match is None:
        print(f"  note: column {column!r} not found; keeping every feature")
        return gdf
    mask = gdf[match].map(norm).isin({norm(v) for v in values})
    return gdf[mask] if keep else gdf[~mask]


def to_map_crs(gdf):
    """Reproject any GeoDataFrame/GeoSeries into the map projection."""
    return gdf.to_crs(MAP_CRS)


def find_column(df, wanted, hints, what):
    """Resolve a column by configured name, else by common-name hints."""
    if wanted:
        for column in df.columns:
            if str(column).strip().lower() == str(wanted).strip().lower():
                return column
        raise SystemExit(f"Column {wanted!r} not found for {what}; "
                         f"available: {list(df.columns)}")
    names = {str(c).strip().lower(): c for c in df.columns}
    for hint in hints:
        if hint in names:
            return names[hint]
    for lowered, column in names.items():
        if hints and lowered.startswith(hints[0]):
            return column
    raise SystemExit(f"Could not auto-detect the {what} column; set "
                     f"lon_col/lat_col in DATASETS. "
                     f"Available: {list(df.columns)}")


def load_points(spec):
    """Read one dataset (file or embedded CSV) with numeric lon/lat."""
    if spec["inline_data"] is not None:
        df = pd.read_csv(io.StringIO(spec["inline_data"]))
    else:
        path = spec["path"]
        suffix = Path(path).suffix.lower()
        if suffix in (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls", ".ods"):
            df = pd.read_excel(path)
        elif suffix in (".tsv", ".txt"):
            df = pd.read_csv(path, sep="\\t")
        else:
            df = pd.read_csv(path)
    lon = find_column(df, spec["lon_col"], LON_HINTS, "longitude")
    lat = find_column(df, spec["lat_col"], LAT_HINTS, "latitude")
    df["_lon"] = pd.to_numeric(df[lon], errors="coerce")
    df["_lat"] = pd.to_numeric(df[lat], errors="coerce")
    bad = df["_lon"].isna() | df["_lat"].isna()
    if bad.any():
        print(f"  {spec['name']}: skipped {int(bad.sum())} row(s) without "
              "numeric coordinates")
    return df[~bad].copy()


def point_labels(df, spec):
    """The legend label for every row, like PyMappr's grouping rules."""
    blank = pd.Series([""] * len(df), index=df.index)

    def column_values(name):
        if not name:
            return blank
        column = find_column(df, name, (), name)
        return df[column].fillna("").astype(str)

    if spec["color_col"] or spec["symbol_col"]:
        cvals = column_values(spec["color_col"])
        svals = column_values(spec["symbol_col"])
        raw = pd.Series(
            [" / ".join(p for p in pair if p) or "All points"
             for pair in zip(cvals, svals)], index=df.index)
    elif spec["group_col"]:
        raw = column_values(spec["group_col"])
        raw = raw.where(raw != "", "(blank)")
    else:
        raw = pd.Series([spec["default_label"]] * len(df), index=df.index)
    return raw.map(lambda value: spec["label_map"].get(value, value))


def plot_dataset(ax, spec):
    """Scatter one dataset group by group, in legend (STYLES) order."""
    df = load_points(spec)
    labels = point_labels(df, spec)
    points = to_map_crs(gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["_lon"], df["_lat"]),
        crs="EPSG:4326"))
    order = list(dict.fromkeys(list(STYLES) + sorted(set(labels))))
    for label in order:
        sub = points[labels == label]
        if sub.empty:
            continue
        style = STYLES.get(label, FALLBACK_STYLE)
        kwargs = dict(s=style["size"], marker=style["marker"],
                      alpha=POINT_ALPHA, zorder=len(NE_LAYERS) + 2,
                      label=label)
        if style["open"]:
            ax.scatter(sub.geometry.x, sub.geometry.y, facecolors="none",
                       edgecolors=style["color"], **kwargs)
        else:
            ax.scatter(sub.geometry.x, sub.geometry.y,
                       color=style["color"], **kwargs)


def add_base_layers(ax):
    """Draw every configured Natural Earth layer, in order."""
    for z, layer in enumerate(NE_LAYERS):
        print(f"Layer: {layer['name']} ({layer['scale']})")
        gdf = load_natural_earth(layer["name"], layer["category"],
                                 layer["scale"], layer.get("member"))
        gdf = to_map_crs(filter_layer(gdf, layer.get("filter")))
        if layer["kind"] == "fill":
            gdf.plot(ax=ax, facecolor=layer["color"],
                     edgecolor=layer["edgecolor"],
                     linewidth=layer["width"], alpha=layer["alpha"],
                     zorder=z + 1)
        elif layer["kind"] == "line":
            shapes = gdf.geometry
            if shapes.geom_type.isin(["Polygon", "MultiPolygon"]).any():
                shapes = shapes.boundary
            shapes.plot(ax=ax, color=layer["color"],
                        linewidth=layer["width"],
                        linestyle=layer["linestyle"], zorder=z + 1)
        else:
            ax.scatter(gdf.geometry.x, gdf.geometry.y, s=layer["size"],
                       marker=layer["marker"], color=layer["color"],
                       edgecolors=layer["edgecolor"], linewidths=0.3,
                       zorder=z + 1)


def densified_box(lon_min, lon_max, lat_min, lat_max, n=40):
    """The box outline as lon/lat points (dense, for curved edges)."""
    lons = np.concatenate([np.linspace(lon_min, lon_max, n),
                           np.linspace(lon_min, lon_max, n),
                           np.full(n, lon_min), np.full(n, lon_max)])
    lats = np.concatenate([np.full(n, lat_min), np.full(n, lat_max),
                           np.linspace(lat_min, lat_max, n),
                           np.linspace(lat_min, lat_max, n)])
    return lons, lats


def set_extent(ax):
    """Zoom the axes to EXTENT_LONLAT, projected into the map CRS."""
    lons, lats = densified_box(*EXTENT_LONLAT)
    edge = to_map_crs(gpd.GeoSeries(gpd.points_from_xy(lons, lats),
                                    crs="EPSG:4326"))
    xs, ys = edge.x, edge.y
    good = np.isfinite(xs) & np.isfinite(ys)
    ax.set_xlim(float(xs[good].min()), float(xs[good].max()))
    ax.set_ylim(float(ys[good].min()), float(ys[good].max()))
    ax.set_aspect("equal")


def draw_graticule(ax):
    """Lon/lat grid lines at GRID_INTERVAL degrees (labels not drawn),
    above the base layers but below the data points, like PyMappr."""
    if not GRID_INTERVAL:
        return
    from shapely.geometry import LineString

    lines = []
    for lon in np.arange(-180.0, 180.0 + GRID_INTERVAL, GRID_INTERVAL):
        lines.append(LineString([(lon, lat)
                                 for lat in np.linspace(-90, 90, 91)]))
    for lat in np.arange(-90.0, 90.0 + GRID_INTERVAL, GRID_INTERVAL):
        lines.append(LineString([(lon, lat)
                                 for lon in np.linspace(-180, 180, 181)]))
    to_map_crs(gpd.GeoSeries(lines, crs="EPSG:4326")).plot(
        ax=ax, color="#b0b0b0", linewidth=0.4, alpha=0.7,
        zorder=len(NE_LAYERS) + 1)


def add_legend(ax):
    if not LEGEND["show"]:
        return
    handles, _labels = ax.get_legend_handles_labels()
    if not handles:
        return
    ax.legend(loc=LEGEND["location"], title=LEGEND["title"] or None,
              fontsize=LEGEND["fontsize"],
              title_fontsize=LEGEND["title_fontsize"],
              ncol=LEGEND["columns"], markerscale=LEGEND["marker_scale"],
              labelspacing=LEGEND["label_spacing"],
              frameon=LEGEND["frame"])


def main():
    fig, ax = plt.subplots(figsize=(9, 6.5), dpi=100, facecolor="white")
    add_base_layers(ax)
    draw_graticule(ax)
    for spec in DATASETS:
        plot_dataset(ax, spec)
    set_extent(ax)
    add_legend(ax)
    ax.set_axis_off()
    fig.savefig(OUTPUT_FILE, dpi=DPI, facecolor="white",
                bbox_inches="tight")
    print(f"Saved {OUTPUT_FILE}")
    plt.show()


if __name__ == "__main__":
    main()
'''


def _python_script(config: dict) -> str:
    return _py_header(config) + _py_config(config) + _PY_FUNCTIONS


# -------------------------------------------------------------- R template

def _r_header(config: dict) -> str:
    notes = "".join(f"\n#   - {note}" for note in config["notes"])
    if notes:
        notes = ("\n# Shown in PyMappr but NOT reproduced by this script:"
                 + notes)
    return f'''\
# Made with {config["generator"]} - {REPO_URL}
# Recreate the PyMappr map {_r(config["project"])} outside PyMappr.
#
# Generated by {config["generator"]} from pre-made function templates and
# the map's saved settings - deterministically, with no AI involved.
#
# Requires:  install.packages(c("sf", "ggplot2"))
# Run:       Rscript this_script.R
# Output:    map.png
#
# Base layers are downloaded from Natural Earth on first run and cached
# in ./naturalearth_cache. Point data is loaded from the original file
# path(s) below (edit them if the files moved); longitude/latitude
# columns are auto-detected from their names and can be pinned in
# DATASETS. PyMappr parsed DMS coordinates on import - if your file
# stores DMS (e.g. 97d44'W), convert to decimal degrees first.
# Some marker shapes and legend placement are approximated (base R has
# no pentagon/hexagon/octagon point shapes).
#
# Projection: {config["projection"]}{notes}

library(sf)
library(ggplot2)
'''


def _r_layer(layer: dict) -> str:
    pairs = [("name", _r(layer["name"])),
             ("category", _r(layer["category"])),
             ("scale", _r(layer["scale"])),
             ("member", _r(layer.get("member"))),
             ("kind", _r(layer["kind"])), ("color", _r(layer["color"]))]
    filt = layer.get("filter")
    if filt:
        column, values, keep = filt
        values_r = ", ".join(_r(v) for v in values)
        pairs += [("filter_column", _r(column)),
                  ("filter_values", f"c({values_r})"),
                  ("filter_keep", _r(bool(keep)))]
    else:
        pairs += [("filter_column", "NULL"), ("filter_values", "NULL"),
                  ("filter_keep", "TRUE")]
    if layer["kind"] == "fill":
        pairs += [("fill", _r(layer["color"])),
                  ("edgecolor", _r(None if layer["edgecolor"] == "none"
                                   else layer["edgecolor"])),
                  ("linewidth", _r(_linewidth_mm(layer["width"]))),
                  ("alpha", _r(layer["alpha"])),
                  ("linetype", _r("solid")), ("size", "NULL"),
                  ("shape", "NULL")]
    elif layer["kind"] == "line":
        pairs += [("fill", "NULL"), ("edgecolor", "NULL"),
                  ("linewidth", _r(_linewidth_mm(layer["width"]))),
                  ("alpha", _r(1.0)),
                  ("linetype", _r(_r_linetype(layer["linestyle"]))),
                  ("size", "NULL"), ("shape", "NULL")]
    else:
        pairs += [("fill", "NULL"), ("edgecolor", "NULL"),
                  ("linewidth", "NULL"), ("alpha", _r(1.0)),
                  ("linetype", _r("solid")),
                  ("size", _r(_size_mm(layer["size"]))),
                  ("shape", _r(_R_PCH.get(
                      {"o": "Circle", "*": "Star", "^": "Triangle",
                       "v": "Triangle down"}.get(layer["marker"], "Circle"),
                      16)))]
    body = _r_named(pairs, "    ")
    return f"  list({body})"


def _r_config(config: dict) -> str:
    lines = ["", "# ------------------------- map configuration (from "
                 "PyMappr) -------------------------", ""]
    lines.append(f'MAP_CRS <- {_r(config["crs"])}')
    extent = tuple(round(v, 4) for v in config["extent"])
    lines.append(f'EXTENT_LONLAT <- c({", ".join(_r(v) for v in extent)})'
                 "  # lon_min, lon_max, lat_min, lat_max")
    lines.append(f'POINT_ALPHA <- {_r(config["point_alpha"])}')
    lines.append(f'DPI <- {_r(config["dpi"])}')
    lines.append(f'GRID_INTERVAL <- {_r(config["graticule"])}'
                 "  # graticule spacing in degrees (NULL = off)")
    lines.append('OUTPUT_FILE <- "map.png"')
    lines.append("")
    lines.append("# Natural Earth base layers enabled in PyMappr, in "
                 "draw order.")
    lines.append("NE_LAYERS <- list(")
    lines.append(",\n".join(_r_layer(layer) for layer in config["layers"]))
    lines.append(")")
    lines.append("")
    lines.append("# One entry per dataset. lon_col/lat_col NULL = "
                 "auto-detect by column name.")
    lines.append("DATASETS <- list(")
    dataset_blocks = []
    for spec in config["datasets"]:
        pairs = [(key, _r(spec[key]))
                 for key in ("name", "path", "inline_data", "lon_col",
                             "lat_col", "group_col", "color_col",
                             "symbol_col", "default_label")]
        label_map = spec["label_map"]
        if label_map:
            body = _r_named(list((k, _r(v)) for k, v in label_map.items()),
                            "      ")
            pairs.append(("label_map", f"c({body})"))
        else:
            pairs.append(("label_map", "c()"))
        dataset_blocks.append(f"  list({_r_named(pairs, '    ')})")
    lines.append(",\n".join(dataset_blocks))
    lines.append(")")
    lines.append("")
    lines.append("# Legend label -> style, in legend order. Sizes are "
                 "approximate ggplot2")
    lines.append("# equivalents of PyMappr's marker areas.")
    styles = config["styles"]
    colors = [(label, _r(style.color)) for label, style in styles.items()]
    shapes = [(label, _r(_R_PCH.get(style.marker, 16)))
              for label, style in styles.items()]
    sizes = [(label, _r(_size_mm(style.size)))
             for label, style in styles.items()]
    for name, pairs in (("STYLE_COLORS", colors), ("STYLE_SHAPES", shapes),
                        ("STYLE_SIZES", sizes)):
        if pairs:
            lines.append(f"{name} <- c({_r_named(pairs, '  ')})")
        else:
            lines.append(f"{name} <- c()")
    lines.append("")
    legend = config["legend"]
    pairs = [(key, _r(value)) for key, value in legend.items()]
    lines.append(f"LEGEND <- list({_r_named(pairs, '  ')})")
    return "\n".join(lines) + "\n"


# The pre-made functions pasted verbatim into every generated R script;
# only the configuration block above them changes.
_R_FUNCTIONS = '''

# ------------------- pre-made functions (identical for every export) -----

LON_HINTS <- c("lon", "lng", "long", "longitude", "x")
LAT_HINTS <- c("lat", "latitude", "y")

load_natural_earth <- function(name, category, scale, member = NULL) {
  # Download a Natural Earth layer (cached in ./naturalearth_cache).
  dir.create("naturalearth_cache", showWarnings = FALSE)
  stem <- sprintf("ne_%s_%s", scale, name)
  zip_path <- file.path("naturalearth_cache", paste0(stem, ".zip"))
  if (!file.exists(zip_path)) {
    url <- sprintf("https://naturalearth.s3.amazonaws.com/%s_%s/%s.zip",
                   scale, category, stem)
    message("Downloading ", url)
    download.file(url, zip_path, mode = "wb", quiet = TRUE)
  }
  folder <- file.path("naturalearth_cache", stem)
  if (!dir.exists(folder)) unzip(zip_path, exdir = folder)
  shp <- if (is.null(member)) paste0(stem, ".shp") else paste0(member, ".shp")
  sf::read_sf(file.path(folder, shp))
}

normalize_values <- function(x) {
  # "1", "1.0", and 1 compare equal; everything else lower-cased text.
  x <- tolower(trimws(as.character(x)))
  numbers <- suppressWarnings(as.numeric(x))
  ifelse(is.na(numbers), x, as.character(numbers))
}

filter_layer <- function(data, column, values, keep = TRUE) {
  # Keep (or drop) features whose column matches one of the values.
  if (is.null(column)) return(data)
  match <- names(data)[tolower(names(data)) == tolower(column)]
  if (length(match) == 0) {
    message("  note: column ", column, " not found; keeping every feature")
    return(data)
  }
  mask <- normalize_values(data[[match[1]]]) %in% normalize_values(values)
  if (keep) data[mask, ] else data[!mask, ]
}

find_column <- function(df, wanted, hints, what) {
  # Resolve a column by configured name, else by common-name hints.
  lowered <- tolower(trimws(names(df)))
  if (!is.null(wanted)) {
    hit <- which(lowered == tolower(trimws(wanted)))
    if (length(hit) > 0) return(names(df)[hit[1]])
    stop(sprintf("Column '%s' not found for %s; available: %s", wanted,
                 what, paste(names(df), collapse = ", ")))
  }
  for (hint in hints) {
    hit <- which(lowered == hint)
    if (length(hit) > 0) return(names(df)[hit[1]])
  }
  stop(sprintf("Could not auto-detect the %s column; available: %s",
               what, paste(names(df), collapse = ", ")))
}

load_points <- function(spec) {
  # Read one dataset (file or embedded CSV) with numeric lon/lat.
  if (!is.null(spec$inline_data)) {
    df <- read.csv(text = spec$inline_data, check.names = FALSE)
  } else if (grepl("\\\\.(tsv|txt)$", tolower(spec$path))) {
    df <- read.delim(spec$path, check.names = FALSE)
  } else {
    # Excel files need readxl: df <- readxl::read_excel(spec$path)
    df <- read.csv(spec$path, check.names = FALSE)
  }
  lon <- find_column(df, spec$lon_col, LON_HINTS, "longitude")
  lat <- find_column(df, spec$lat_col, LAT_HINTS, "latitude")
  df$`_lon` <- suppressWarnings(as.numeric(df[[lon]]))
  df$`_lat` <- suppressWarnings(as.numeric(df[[lat]]))
  bad <- is.na(df$`_lon`) | is.na(df$`_lat`)
  if (any(bad)) {
    message("  ", spec$name, ": skipped ", sum(bad),
            " row(s) without numeric coordinates")
  }
  df[!bad, , drop = FALSE]
}

point_labels <- function(df, spec) {
  # The legend label for every row, like PyMappr's grouping rules.
  column_values <- function(name) {
    if (is.null(name)) return(rep("", nrow(df)))
    column <- find_column(df, name, c(), name)
    values <- as.character(df[[column]])
    ifelse(is.na(values), "", values)
  }
  if (!is.null(spec$color_col) || !is.null(spec$symbol_col)) {
    cvals <- column_values(spec$color_col)
    svals <- column_values(spec$symbol_col)
    raw <- ifelse(cvals == "" & svals == "", "All points",
                  ifelse(cvals == "", svals,
                         ifelse(svals == "", cvals,
                                paste(cvals, svals, sep = " / "))))
  } else if (!is.null(spec$group_col)) {
    raw <- column_values(spec$group_col)
    raw <- ifelse(raw == "", "(blank)", raw)
  } else {
    raw <- rep(spec$default_label, nrow(df))
  }
  if (length(spec$label_map) == 0) return(raw)
  mapped <- unname(spec$label_map[raw])
  ifelse(is.na(mapped), raw, mapped)
}

load_all_points <- function() {
  # Every dataset as one sf object with a legend `label` column.
  frames <- lapply(DATASETS, function(spec) {
    df <- load_points(spec)
    data.frame(lon = df$`_lon`, lat = df$`_lat`,
               label = point_labels(df, spec))
  })
  merged <- do.call(rbind, frames)
  merged$label <- factor(merged$label,
                         levels = unique(c(names(STYLE_COLORS),
                                           merged$label)))
  sf::st_as_sf(merged, coords = c("lon", "lat"), crs = "EPSG:4326")
}

base_layer_geom <- function(layer) {
  # One ggplot2 geom_sf for a configured Natural Earth layer.
  data <- load_natural_earth(layer$name, layer$category, layer$scale,
                             layer$member)
  data <- filter_layer(data, layer$filter_column, layer$filter_values,
                       layer$filter_keep)
  data <- sf::st_transform(data, MAP_CRS)
  if (layer$kind == "fill") {
    geom_sf(data = data, fill = layer$fill,
            color = if (is.null(layer$edgecolor)) NA else layer$edgecolor,
            linewidth = layer$linewidth, alpha = layer$alpha)
  } else if (layer$kind == "line") {
    geom_sf(data = data, fill = NA, color = layer$color,
            linewidth = layer$linewidth, linetype = layer$linetype)
  } else {
    geom_sf(data = data, color = layer$color, size = layer$size,
            shape = layer$shape)
  }
}

projected_extent <- function() {
  # EXTENT_LONLAT projected into the map CRS (edges densified).
  n <- 40
  lons <- c(seq(EXTENT_LONLAT[1], EXTENT_LONLAT[2], length.out = n),
            seq(EXTENT_LONLAT[1], EXTENT_LONLAT[2], length.out = n),
            rep(EXTENT_LONLAT[1], n), rep(EXTENT_LONLAT[2], n))
  lats <- c(rep(EXTENT_LONLAT[3], n), rep(EXTENT_LONLAT[4], n),
            seq(EXTENT_LONLAT[3], EXTENT_LONLAT[4], length.out = n),
            seq(EXTENT_LONLAT[3], EXTENT_LONLAT[4], length.out = n))
  edge <- sf::st_as_sf(data.frame(lon = lons, lat = lats),
                       coords = c("lon", "lat"), crs = "EPSG:4326")
  xy <- sf::st_coordinates(sf::st_transform(edge, MAP_CRS))
  xy <- xy[is.finite(xy[, 1]) & is.finite(xy[, 2]), , drop = FALSE]
  list(xlim = range(xy[, 1]), ylim = range(xy[, 2]))
}

legend_position <- function(location) {
  # PyMappr legend locations approximated by ggplot2 sides.
  if (location %in% c("upper left", "lower left")) "left" else "right"
}

build_map <- function() {
  p <- ggplot()
  for (layer in NE_LAYERS) p <- p + base_layer_geom(layer)
  if (!is.null(GRID_INTERVAL)) {
    # Above the base layers but below the points, like PyMappr.
    grid <- sf::st_graticule(
      crs = sf::st_crs("EPSG:4326"),
      lon = seq(-180, 180, by = GRID_INTERVAL),
      lat = seq(-90, 90, by = GRID_INTERVAL))
    p <- p + geom_sf(data = sf::st_transform(grid, MAP_CRS),
                     color = "#b0b0b0", linewidth = 0.15, alpha = 0.7)
  }
  if (length(DATASETS) > 0) {
    points <- sf::st_transform(load_all_points(), MAP_CRS)
    title <- if (LEGEND$title == "") NULL else LEGEND$title
    # Legend key marker sizes = the mapped point sizes scaled by
    # marker_scale, matching matplotlib's markerscale (the sizes drawn on
    # the map itself are left untouched).
    key_sizes <- unname(STYLE_SIZES) * LEGEND$marker_scale
    p <- p +
      geom_sf(data = points,
              aes(color = label, shape = label, size = label),
              alpha = POINT_ALPHA) +
      scale_color_manual(values = STYLE_COLORS, name = title) +
      scale_shape_manual(values = STYLE_SHAPES, name = title) +
      scale_size_manual(values = STYLE_SIZES, name = title,
                        guide = "none") +
      guides(
        color = guide_legend(ncol = LEGEND$columns,
                             override.aes = list(size = key_sizes)),
        shape = guide_legend(ncol = LEGEND$columns))
  }
  extent <- projected_extent()
  p <- p + coord_sf(crs = MAP_CRS, xlim = extent$xlim, ylim = extent$ylim,
                    expand = FALSE, datum = sf::st_crs("EPSG:4326"))
  p <- p + theme_void() + theme(
    panel.background = element_rect(fill = "white", color = NA),
    plot.background = element_rect(fill = "white", color = NA),
    legend.text = element_text(size = LEGEND$fontsize),
    legend.title = element_text(size = LEGEND$title_fontsize),
    # Approximates matplotlib's labelspacing (vertical gap per entry).
    legend.key.height = grid::unit(1 + LEGEND$label_spacing, "lines"),
    legend.position = if (LEGEND$show) legend_position(LEGEND$location)
                      else "none",
    legend.background = if (LEGEND$frame)
      element_rect(fill = "white", color = "#999999") else element_blank())
  p
}

main <- function() {
  p <- build_map()
  ggsave(OUTPUT_FILE, plot = p, width = 9, height = 6.5, dpi = DPI,
         bg = "white")
  message("Saved ", OUTPUT_FILE)
}

main()
'''


def _r_script(config: dict) -> str:
    return _r_header(config) + _r_config(config) + _R_FUNCTIONS


# ----------------------------------------------------------------- entry

def generate_code(state: dict, entries, language: str,
                  project_name: str = "Untitled") -> str:
    """The complete Python or R script recreating the given map state."""
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    config = build_config(state, entries, project_name)
    if language == "Python":
        return _python_script(config)
    return _r_script(config)
