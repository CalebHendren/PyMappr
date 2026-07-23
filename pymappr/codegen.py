from __future__ import annotations

import math
import re

from pymappr import __version__
from pymappr.layers import (BATHYMETRY_STEPS, CONTINENT_EXTENTS,
                            LAYER_SPECS)
from pymappr.projections import (CAP_CLIP_RADIUS, get_projection, is_globe,
                                 proj4_string)
from pymappr.renderer import (BATHYMETRY_COLORS, FILL_COLORS, FILL_LAYERS,
                              LABEL_STYLES, LINE_LAYERS, POINT_LAYERS,
                              Z_BATHYMETRY, Z_LAKE_FILL, Z_OCEAN,
                              Z_POINT_LAYERS)
from pymappr.styles import (NEUTRAL_MARKER_COLOR, PointStyle,
                            attribute_style_maps, default_styles,
                            group_points, style_by_attributes)
from pymappr.updates import GITHUB_REPO

LANGUAGES = ("Python", "R")
CODE_EXTENSIONS = {"Python": ".py", "R": ".R"}

# Home page for the attribution comment at the top of every script.
REPO_URL = f"https://github.com/{GITHUB_REPO}"

WORLD_EXTENT = (-180.0, 180.0, -90.0, 90.0)

# Default figure size (inches): the app's initial canvas.
DEFAULT_FIGSIZE = (9.0, 6.5)

# Axes margins as figure fractions, mirroring pymappr.renderer.
MARGINS_WITH_TICKS = (0.055, 0.045, 0.99, 0.99)   # left, bottom, right, top
MARGINS_PLAIN = (0.01, 0.012, 0.99, 0.988)

# Grid spacing dropdown -> degrees (mirrors the control panel choices).
_GRATICULE_DEGREES = {"1\N{DEGREE SIGN}": 1.0, "5\N{DEGREE SIGN}": 5.0,
                      "10\N{DEGREE SIGN}": 10.0}

# Natural Earth category per source layer key (for download URLs).
_CATEGORY = {
    "countries": "cultural", "continents": "cultural", "states": "cultural",
    "counties": "cultural", "sovereignty": "cultural",
    "map_units": "cultural", "subunits": "cultural",
    "dependencies": "cultural", "disputed": "cultural",
    "disputed_lines": "cultural", "maritime_all": "cultural",
    "maritime": "cultural", "eez": "cultural",
    "timezones": "cultural", "cities": "cultural", "capitals": "cultural",
    "urban": "cultural", "airports": "cultural", "ports": "cultural",
    "parks": "cultural", "roads": "cultural",
    "lakes": "physical", "rivers": "physical", "wadis": "physical",
    "ocean": "physical", "land": "physical", "glaciers": "physical",
    "ice_shelves": "physical", "reefs": "physical", "playas": "physical",
    "regions": "physical", "deserts": "physical", "bathymetry": "physical",
}

# Derived layers: renderer source key -> (spec key of the real data, filter)
# where filter is (column, values, keep) applied after download. Derived
# layers always come from the most detailed resolution, like the app.
_DERIVED_SOURCES = {
    "dependencies": ("countries", ("type", ["Dependency", "Lease"], True)),
    "deserts": ("regions", ("featurecla", ["Desert"], True)),
    "wadis": ("rivers", ("featurecla", ["River (Intermittent)"], True)),
    "capitals": ("cities", ("adm0cap", ["1"], True)),
    "maritime": ("maritime_all",
                 ("featurecla", ["Marine Indicator 200 mi nl"], False)),
    "eez": ("maritime_all",
            ("featurecla", ["Marine Indicator 200 mi nl"], True)),
}

# Layers whose data is not a Natural Earth download - never reproduced.
_EXTERNAL_FILLS = {
    "biodiversity": "Biodiversity hotspots overlay (Conservation "
                    "International data, not Natural Earth)",
    "ecoregions": "Terrestrial ecoregions overlay (RESOLVE data, not "
                  "Natural Earth)",
    "marine_ecoregions": "Marine ecoregions overlay (WWF/TNC data, not "
                         "Natural Earth)",
}

# Natural Earth raster basemaps: mode -> (archive tuple, JPEG filename).
# The archive tuple is (scale, category, name) for download_archive().
BASEMAP_RASTERS = {
    "relief": (("50m", "raster", "NE1_50M_SR_W"), "ne1_world.jpg"),
    "relief_alt": (("50m", "raster", "NE2_50M_SR_W"), "ne2_world.jpg"),
    "relief_grey": (("50m", "raster", "GRAY_50M_SR_W"), "gray_world.jpg"),
    "blue_marble": (("50m", "raster", "HYP_50M_SR_W"), "hyp_world.jpg"),
}
BASEMAP_SIZE = (5400, 2700)

# PyMappr marker name -> R pch code. Shapes with a filled+outlined R
# variant (21-25) get it, so filled markers carry the app's white edge;
# open variants use the hollow codes. Shapes base R lacks fall back.
_R_PCH = {
    "Circle": 21, "Circle (open)": 1,
    "Square": 22, "Square (open)": 0,
    "Triangle": 24, "Triangle (open)": 2,
    "Triangle down": 25, "Triangle down (open)": 6,
    "Triangle left": 24, "Triangle left (open)": 2,
    "Triangle right": 24, "Triangle right (open)": 2,
    "Diamond": 23, "Diamond (open)": 5,
    "Thin diamond": 23, "Thin diamond (open)": 5,
    "Star": 8, "Star (open)": 8,
    "Plus": 3, "Plus (open)": 3,
    "X": 4, "X (open)": 4,
    "Pentagon": 21, "Pentagon (open)": 1,
    "Hexagon": 21, "Hexagon (open)": 1,
    "Octagon": 21, "Octagon (open)": 1,
    "Dot": 20, "Dot (open)": 20,
}
_R_FILLABLE_PCH = {21, 22, 23, 24, 25}

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
    """The Lambert/Globe origin from the stored map state ("" = default)."""

    def parse(key):
        raw = str(state_map.get(key, "")).strip()
        try:
            return float(raw)
        except ValueError:
            return None

    return parse("proj_lon0"), parse("proj_lat0")


def _split_directory(directory: str) -> tuple[str, str]:
    """"ne_50m_admin_0_countries" -> ("50m", "admin_0_countries")."""
    parts = directory.split("_", 2)
    return parts[1], parts[2]


def _source_archive(source: str, zoom: float) -> tuple[str, str, str,
                                                       str | None]:
    """(scale, category, dataset name, member) for a renderer source key,
    at the resolution the app would draw for *zoom*."""
    category = _CATEGORY[source]
    if source == "continents":
        # Continent outlines dissolve the default-resolution countries.
        directory = LAYER_SPECS["countries"].directory
        scale, name = _split_directory(directory)
        return scale, category, name, None
    if source in _DERIVED_SOURCES:
        spec_key, _filter = _DERIVED_SOURCES[source]
        spec = LAYER_SPECS[spec_key]
        directory = spec.directories()[-1]  # most detailed, like the app
        scale, name = _split_directory(directory)
        member = spec.shapefile
        return scale, category, name, member
    spec = LAYER_SPECS[source]
    directory = spec.directory_for_zoom(zoom)
    scale, name = _split_directory(directory)
    return scale, category, name, spec.shapefile


def _view_and_zoom(state: dict, figsize: tuple[float, float],
                   margins: tuple[float, float, float, float]
                   ) -> tuple[tuple[float, float, float, float], float]:
    """The stored view (projected map coordinates, verbatim) and the zoom
    level, replicating the renderer.

    Without a stored view, the continent preset is projected and padded
    to the axes box aspect exactly like ``MapRenderer.set_extent``.
    """
    m = dict(state.get("map", {}))
    lon0, lat0 = _origin(m)
    projection = get_projection(str(m.get("projection", "Equirectangular")),
                                lon0, lat0)
    view = dict(state.get("view", {}))
    xlim, ylim = view.get("xlim"), view.get("ylim")
    box = None
    if (isinstance(xlim, (list, tuple)) and len(xlim) == 2
            and isinstance(ylim, (list, tuple)) and len(ylim) == 2):
        try:
            box = (float(xlim[0]), float(xlim[1]),
                   float(ylim[0]), float(ylim[1]))
        except (TypeError, ValueError):
            box = None
    if box is None:
        extent = CONTINENT_EXTENTS.get(str(m.get("continent", "World")),
                                       WORLD_EXTENT)
        x0, x1, y0, y1 = projection.project_extent(extent)
        wx0, wx1, wy0, wy1 = projection.bounds
        left, bottom, right, top = margins
        box_ratio = max((figsize[0] * (right - left))
                        / (figsize[1] * (top - bottom)), 1e-6)
        width, height = x1 - x0, y1 - y0
        if width / height < box_ratio:
            new_w = height * box_ratio
            if new_w <= wx1 - wx0:
                cx = min(max((x0 + x1) / 2, wx0 + new_w / 2),
                         wx1 - new_w / 2)
                x0, x1 = cx - new_w / 2, cx + new_w / 2
        else:
            new_h = width / box_ratio
            if new_h <= wy1 - wy0:
                cy = min(max((y0 + y1) / 2, wy0 + new_h / 2),
                         wy1 - new_h / 2)
                y0, y1 = cy - new_h / 2, cy + new_h / 2
        box = (x0, x1, y0, y1)
    width = max(abs(box[1] - box[0]), 1e-9)
    zoom = math.log2(projection.world_width / width)
    return box, zoom


def _base_layers(m: dict, zoom: float) -> tuple[list[dict], list[str]]:
    """The enabled base layers as config dicts (any order - each carries
    the renderer's true zorder), plus notes about enabled features not
    reproduced (external overlays only)."""
    scale = _num(m.get("line_width", 1.0), 1.0)
    enabled = {section: [key for key, on in dict(m.get(section, {})).items()
                         if on]
               for section in ("lines", "fills", "points")}
    layers: list[dict] = []
    notes: list[str] = []

    def ne_layer(source: str, key: str, kind: str, z: float,
                 filt=None, **style) -> dict:
        arc_scale, category, name, member = _source_archive(source, zoom)
        if filt is None:
            filt = _DERIVED_SOURCES.get(source, (None, None))[1]
        return {"key": key, "name": name, "category": category,
                "scale": arc_scale, "member": member, "filter": filt,
                "kind": kind, "z": z, **style}

    for mode_key, z, mode in (
            ("ocean", Z_OCEAN, str(m.get("ocean", "none"))),
            ("lakes", Z_LAKE_FILL, str(m.get("lake_fill", "none")))):
        if mode != "none":
            layers.append(ne_layer(
                mode_key, mode_key + "_fill", "fill", z,
                color=FILL_COLORS[(mode_key, mode)], edgecolor="none",
                width=0.0, alpha=1.0))
    if bool(m.get("bathymetry", False)):
        for letter, depth in BATHYMETRY_STEPS:
            layers.append({
                "key": f"bathymetry_{depth}", "name": "bathymetry_all",
                "category": "physical", "scale": "10m",
                "member": f"ne_10m_bathymetry_{letter}_{depth}",
                "filter": None, "kind": "fill",
                "z": Z_BATHYMETRY + depth * 1e-6,
                "color": BATHYMETRY_COLORS[depth], "edgecolor": "none",
                "width": 0.0, "alpha": 1.0})
    for key in enabled["fills"]:
        if key in _EXTERNAL_FILLS:
            notes.append(_EXTERNAL_FILLS[key])
            continue
        source, face, edge, edge_width, alpha, z = FILL_LAYERS[key]
        layers.append(ne_layer(source, key, "fill", z, color=face,
                               edgecolor=edge, width=edge_width,
                               alpha=alpha))
    for key in enabled["lines"]:
        source, color, width, z, linestyle = LINE_LAYERS[key]
        layers.append(ne_layer(source, key, "line", z, color=color,
                               width=width * scale, linestyle=linestyle))
    if "countries" not in enabled["lines"]:
        # Countries off: the app swaps in dissolved continent outlines.
        source, color, width, z, linestyle = LINE_LAYERS["continents"]
        layers.append(ne_layer("continents", "continents", "continents", z,
                               color=color, width=width * scale,
                               linestyle=linestyle))
    capitals_only = bool(m.get("capitals_only", False))
    for key in enabled["points"]:
        if key == "cities" and capitals_only:
            key = "capitals"
        source, marker, size, face, edge, bias = POINT_LAYERS[key]
        # A feature shows once min_zoom <= zoom + bias, like the app.
        threshold = None if bias >= 99.0 else round(zoom + bias, 4)
        layers.append(ne_layer(source, key, "point", Z_POINT_LAYERS,
                               color=face, edgecolor=edge, marker=marker,
                               size=size, min_zoom_max=threshold))
    layers.sort(key=lambda layer: layer["z"])
    return layers, notes


def _label_layers(m: dict, zoom: float) -> list[dict]:
    """Config for the enabled label layers, mirroring the renderer's
    LABEL_STYLES tables and per-layer culling inputs."""
    enabled = [key for key, on in dict(m.get("labels", {})).items() if on]
    capitals_only = bool(m.get("capitals_only", False))
    labels: list[dict] = []
    for key in LABEL_STYLES:
        if key not in enabled:
            continue
        source, font, min_zoom, feature_bias = LABEL_STYLES[key]
        if zoom < min_zoom:
            continue  # the app would draw nothing at this zoom
        if key == "cities" and capitals_only:
            source = "capitals"
        spec_key = _DERIVED_SOURCES.get(source, (source, None))[0]
        spec = LAYER_SPECS[spec_key]
        # Label anchors come from the default resolution, like the app.
        scale, name = _split_directory(spec.directory)
        filt = _DERIVED_SOURCES.get(source, (None, None))[1]
        cap_key = "cities" if source == "capitals" else source
        labels.append({
            "key": key, "name": name,
            "category": _CATEGORY[spec_key], "scale": scale,
            "member": spec.shapefile, "filter": filt,
            "column": spec.label_column, "geometry": spec.geometry,
            "cap": LAYER_SPECS[cap_key].label_cap,
            "min_label_from_min_zoom": key in ("cities",),
            "dedupe_longest": key in ("rivers", "wadis"),
            "feature_bias": feature_bias,
            "point_layer": key in POINT_LAYERS,
            "font": dict(font),
        })
    return labels


def _display_labels(raw_labels: list[str], entry_name: str, multi: bool,
                    attribute_mode: bool,
                    used: set[str]) -> dict[str, str]:
    """Raw group label -> legend label, disambiguated across datasets the
    same way the app does it."""
    mapping: dict[str, str] = {}
    for label in raw_labels:
        display = label
        if multi and attribute_mode:
            display = label
        elif multi and label == "All points":
            display = entry_name
        elif multi and label in used:
            display = f"{label} ({entry_name})"
        used.add(display)
        mapping[label] = display
    return mapping


def _dataset_filename(name: str, used: set[str]) -> str:
    """A filesystem-safe ``<name>.csv`` unique within *used*."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("._-")
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]
    stem = stem or "dataset"
    candidate = f"{stem}.csv"
    counter = 2
    while candidate in used:
        candidate = f"{stem}_{counter}.csv"
        counter += 1
    used.add(candidate)
    return candidate


def _style_dict(style: PointStyle) -> dict:
    return {"color": style.color, "marker": style.mpl_marker,
            "size": style.size, "open": style.is_open}


def _dataset_configs(entries, data_mode: str = "inline"
                     ) -> tuple[list[dict], dict[str, PointStyle],
                                dict[str, str], list | None]:
    """Per-dataset script configs, the combined legend-label -> style map
    (in render order), the point data to write as ``data/<name>.csv`` in
    ``"files"`` mode, and the structured legend sections (None in plain
    mode) - replicating the app's ``_push_points`` exactly.
    """
    visible = [e for e in entries if e.visible and len(e.dataset)]
    multi = len(visible) > 1
    any_attr = False
    for entry in visible:
        key_by_label = dict(zip(entry.dataset.name_labels,
                                entry.dataset.name_keys))
        if key_by_label.get(entry.symbol_by) is not None:
            any_attr = True
    used: set[str] = set()
    used_files: set[str] = set()
    styles: dict[str, PointStyle] = {}
    configs: list[dict] = []
    data_files: dict[str, str] = {}
    sections: list = []
    palette_offset = 0
    for entry in visible:
        frame = entry.dataset.frame
        key_by_label = dict(zip(entry.dataset.name_labels,
                                entry.dataset.name_keys))
        color_key = key_by_label.get(entry.color_by)
        symbol_key = key_by_label.get(entry.symbol_by)
        # Every dataset is normalized to CSV (labels + Longitude/Latitude)
        # so the script never depends on the original file's format.
        csv_text = _inline_csv(entry)
        config = {
            "name": entry.name,
            "path": None,
            "inline_data": None,
            "lon_col": "Longitude",
            "lat_col": "Latitude",
            "group_col": None,
            "color_col": None,
            "symbol_col": None,
            "default_label": entry.name,
            "label_map": {},
            # Original source path, for a provenance comment only (not read
            # by the generated loader).
            "source": entry.dataset.source_path or None,
        }
        if data_mode == "files":
            rel = "data/" + _dataset_filename(entry.name, used_files)
            config["path"] = rel
            data_files[rel] = csv_text
        else:
            config["inline_data"] = csv_text
        if symbol_key is not None:
            # Two-attribute styling: one render group per (color, symbol)
            # pair, and a sectioned legend keyed by the two columns.
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
            prefix = f"{entry.name}: " if multi else ""
            if color_map:
                sections.append((prefix + (entry.color_by or "Color"),
                                 [(value, PointStyle(color=color,
                                                     marker="Circle"))
                                  for value, color in color_map.items()]))
            if symbol_map:
                sections.append((prefix + (entry.symbol_by or "Symbol"),
                                 [(value,
                                   PointStyle(color=NEUTRAL_MARKER_COLOR,
                                              marker=marker))
                                  for value, marker in symbol_map.items()]))
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
            entry_styles = {}
            for label in labels:
                style = entry.styles.get(label, fresh[label])
                styles[display[label]] = style
                entry_styles[display[label]] = style
            if group_key is not None:
                config["group_col"] = entry.group_by
            if entry_styles:
                sections.append((entry.name, list(entry_styles.items())))
        config["label_map"] = display
        configs.append(config)
    return configs, styles, data_files, (sections if any_attr else None)


def _inline_csv(entry) -> str:
    """A dataset's points as normalized CSV text (label columns plus
    Longitude/Latitude), embedded in the script or written to data/."""
    frame = entry.dataset.frame
    columns = dict(zip(entry.dataset.name_keys, entry.dataset.name_labels))
    columns.update({"lon": "Longitude", "lat": "Latitude"})
    subset = frame[[c for c in frame.columns if c in columns]]
    return subset.rename(columns=columns).to_csv(index=False)


def build_config(state: dict, entries, project_name: str = "map",
                 data_mode: str = "inline",
                 figure_size: tuple[float, float] | None = None) -> dict:
    """Everything the script templates need, from the app state.

    *data_mode* is ``"inline"`` (point data embedded in the script) or
    ``"files"`` (point data written as ``data/<name>.csv``). *figure_size*
    is the app canvas size in inches; the export mirrors its geometry so
    fonts and markers keep the same relative scale.
    """
    m = dict(state.get("map", {}))
    legend = dict(state.get("legend", {}))
    lon0, lat0 = _origin(m)
    projection_name = str(m.get("projection", "Equirectangular"))
    projection = get_projection(projection_name, lon0, lat0)

    graticule = _GRATICULE_DEGREES.get(str(m.get("graticule", "Off")))
    labels_on = (graticule is not None
                 and not bool(m.get("hide_grid_labels", False))
                 and projection.is_geographic)
    margins = MARGINS_WITH_TICKS if labels_on else MARGINS_PLAIN

    base_size = figure_size or DEFAULT_FIGSIZE
    view, zoom = _view_and_zoom(state, base_size, margins)
    # Square map units: derive the figure height from the view aspect so
    # the exported geometry matches the app canvas (whose extent was
    # padded to the same aspect).
    left, bottom, right, top = margins
    axes_w = base_size[0] * (right - left)
    view_w = max(abs(view[1] - view[0]), 1e-9)
    view_h = max(abs(view[3] - view[2]), 1e-9)
    fig_h = axes_w * (view_h / view_w) / (top - bottom)
    figsize = (round(float(base_size[0]), 3), round(float(fig_h), 3))

    layers, notes = _base_layers(m, zoom)
    label_layers = _label_layers(m, zoom)
    datasets, styles, data_files, sections = _dataset_configs(entries,
                                                              data_mode)
    title = str(legend.get("title", "")).strip()
    if not title and len(datasets) == 1 and datasets[0]["group_col"]:
        title = datasets[0]["group_col"]
    clip_cap = None
    if is_globe(projection_name):
        clip_cap = (round(projection.lon_0, 6), round(projection.lat_0, 6),
                    round(CAP_CLIP_RADIUS, 6))
    return {
        "project": project_name,
        "generator": f"PyMappr {__version__}",
        "projection": projection_name,
        "crs": projection.crs,   # None = plain lon/lat degrees
        "crs_r": projection.crs or "EPSG:4326",
        "proj": {
            "bounds": tuple(round(v, 6) for v in projection.bounds),
            "max_lat": projection.max_lat,
            "min_lat": projection.min_lat,
            "lon_0": projection.lon_0,
            "lon_halfspan": projection.lon_halfspan,
            "hemisphere": projection.hemisphere,
        },
        "clip_cap": clip_cap,
        "view": tuple(round(float(v), 6) for v in view),
        "zoom": round(zoom, 4),
        "figsize": figsize,
        "margins": margins,
        "basemap": str(m.get("basemap", "simple")),
        "layers": layers,
        "label_layers": label_layers,
        "graticule": {"interval": graticule, "labels": labels_on},
        "compass": bool(m.get("compass", False)),
        "datasets": datasets,
        "data_mode": data_mode,
        "data_files": data_files,
        "styles": styles,
        "legend_sections": sections,
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
    if config["data_mode"] == "files":
        data_note = ("Your point data is in the data/ folder as CSV - edit "
                     "or replace those files\nto update the map.")
    else:
        data_note = ("Your point data is embedded below in DATASETS, so "
                     "this single file is\nself-contained - nothing else "
                     "to download or keep alongside it.")
    return f'''\
#!/usr/bin/env python3
# Made with {config["generator"]} - {REPO_URL}
"""Recreate the PyMappr map "{_safe_name(config["project"])}" outside PyMappr.

Generated by {config["generator"]} from pre-made function templates and
the map's saved settings

Just run it: open this file in an IDE (PyCharm, VS Code, ...) and click
Run, or `python recreate_map.py` in a terminal. Any missing packages
(pandas, geopandas, matplotlib) are installed automatically on first run,
and the map data is downloaded from Natural Earth and cached in
naturalearth_cache/ next to this script.

Output:  map.png (also opens an interactive window).

{data_note}
"""
# Projection: {config["projection"]}{notes}
'''


def _py_layer_entry(layer: dict) -> dict:
    entry = {"name": layer["name"], "category": layer["category"],
             "scale": layer["scale"], "kind": layer["kind"],
             "z": round(layer["z"], 6), "color": layer["color"]}
    if layer.get("member"):
        entry["member"] = layer["member"]
    if layer.get("filter"):
        entry["filter"] = layer["filter"]
    if layer["kind"] == "fill":
        entry.update(edgecolor=layer["edgecolor"],
                     width=round(layer["width"], 3), alpha=layer["alpha"])
    elif layer["kind"] in ("line", "continents"):
        entry.update(width=round(layer["width"], 3),
                     linestyle=layer["linestyle"])
    else:
        entry.update(marker=layer["marker"], size=layer["size"],
                     edgecolor=layer["edgecolor"])
        if layer.get("min_zoom_max") is not None:
            entry["min_zoom_max"] = layer["min_zoom_max"]
    return entry


def _py_config(config: dict) -> str:
    lines = ["", "# ------------------------- map configuration (from "
                 "PyMappr) -------------------------", ""]
    lines.append(f'MAP_CRS = {_py(config["crs"])}'
                 "  # proj4 string, or None for plain lon/lat degrees")
    proj = config["proj"]
    lines.append(f"PROJ = {{'bounds': {_py(proj['bounds'])}, "
                 f"'max_lat': {_py(proj['max_lat'])}, "
                 f"'min_lat': {_py(proj['min_lat'])}, "
                 f"'lon_0': {_py(proj['lon_0'])}, "
                 f"'lon_halfspan': {_py(proj['lon_halfspan'])}, "
                 f"'hemisphere': {_py(proj['hemisphere'])}}}")
    lines.append(f'CLIP_CAP = {_py(config["clip_cap"])}'
                 "  # (lon0, lat0, radius) visible cap for the globe, "
                 "else None")
    lines.append(f'VIEW = {_py(config["view"])}'
                 "  # axis limits in map coordinates (x0, x1, y0, y1)")
    lines.append(f'ZOOM = {_py(config["zoom"])}'
                 "  # log2(world width / view width), used for culling")
    lines.append(f'FIGSIZE = {_py(config["figsize"])}'
                 "  # inches; the app canvas geometry")
    lines.append(f'MARGINS = {_py(config["margins"])}'
                 "  # axes box as figure fractions (l, b, r, t)")
    lines.append(f'BASEMAP = {_py(config["basemap"])}'
                 "  # raster basemap mode (\"simple\" = none)")
    grat = config["graticule"]
    lines.append(f"GRATICULE = {{'interval': {_py(grat['interval'])}, "
                 f"'labels': {_py(grat['labels'])}}}")
    lines.append(f'COMPASS = {_py(config["compass"])}')
    lines.append(f'POINT_ALPHA = {_py(config["point_alpha"])}')
    lines.append(f'DPI = {_py(config["dpi"])}')
    lines.append('OUTPUT_FILE = "map.png"')
    lines.append("")
    lines.append("# Natural Earth layers enabled in PyMappr, with the "
                 "renderer's true draw")
    lines.append("# order (z). A filter is (column, kept values, keep?) "
                 "applied after download.")
    lines.append("LAYERS = [")
    for layer in config["layers"]:
        entry = _py_layer_entry(layer)
        body = ", ".join(f"{_py(k)}: {_py(v)}" for k, v in entry.items())
        lines.append(f"    # PyMappr layer: {layer['key']}")
        lines.append(f"    {{{body}}},")
    lines.append("]")
    lines.append("")
    lines.append("# Map label layers (country/city/... names), like the "
                 "app draws them.")
    lines.append("LABEL_LAYERS = [")
    for spec in config["label_layers"]:
        body = ", ".join(f"{_py(k)}: {_py(v)}" for k, v in spec.items())
        lines.append(f"    {{{body}}},")
    lines.append("]")
    lines.append("")
    lines.append("# One entry per dataset. lon_col/lat_col name the "
                 "coordinate columns")
    lines.append("# (None = auto-detect by column name).")
    lines.append("DATASETS = [")
    for spec in config["datasets"]:
        if spec.get("source"):
            lines.append(f"    # originally imported from: {spec['source']}")
        lines.append("    {")
        for key in ("name", "path", "inline_data", "lon_col", "lat_col",
                    "group_col", "color_col", "symbol_col",
                    "default_label", "label_map"):
            lines.append(f"        {_py(key)}: {_py(spec[key])},")
        lines.append("    },")
    lines.append("]")
    lines.append("")
    lines.append("# Legend label -> point style, in render order "
                 "(open = outline-only marker).")
    lines.append("STYLES = {")
    for label, style in config["styles"].items():
        body = ", ".join(f"{_py(k)}: {_py(v)}"
                         for k, v in _style_dict(style).items())
        lines.append(f"    {_py(label)}: {{{body}}},")
    lines.append("}")
    lines.append("")
    sections = config["legend_sections"]
    if sections is None:
        lines.append("LEGEND_SECTIONS = None"
                     "  # plain legend: one row per STYLES entry")
    else:
        lines.append("# Sectioned legend (color key + symbol key), like "
                     "the app's.")
        lines.append("LEGEND_SECTIONS = [")
        for title, entries in sections:
            lines.append(f"    ({_py(title)}, [")
            for label, style in entries:
                body = ", ".join(f"{_py(k)}: {_py(v)}"
                                 for k, v in _style_dict(style).items())
                lines.append(f"        ({_py(label)}, {{{body}}}),")
            lines.append("    ]),")
        lines.append("]")
    lines.append("")
    legend = config["legend"]
    body = ", ".join(f"{_py(k)}: {_py(v)}" for k, v in legend.items())
    lines.append(f"LEGEND = {{{body}}}")
    return "\n".join(lines) + "\n"


# The pre-made functions pasted verbatim into every generated Python
# script; only the configuration block above them changes. They replicate
# pymappr/renderer.py for a single static view.
_PY_FUNCTIONS = '''

# ------------------- pre-made functions (identical for every export) -----

import importlib
import io
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve


def ensure_dependencies():
    """Install any missing third-party packages into this interpreter, so
    the script runs on a fresh Python with nothing set up - paste it into
    an IDE and click Run. Installs with pip in the current environment."""
    required = {"numpy": "numpy", "pandas": "pandas",
                "geopandas": "geopandas", "matplotlib": "matplotlib"}
    missing = []
    for module, package in required.items():
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if not missing:
        return
    print("Installing missing packages: " + ", ".join(missing) + " ...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               *missing])
    except Exception as exc:  # no pip, offline, no permission, ...
        raise SystemExit(
            "Could not auto-install " + ", ".join(missing) + " (" + str(exc)
            + ").\\nInstall them yourself, then rerun:\\n    "
            + sys.executable + " -m pip install " + " ".join(missing))
    importlib.invalidate_caches()


ensure_dependencies()

import matplotlib.patheffects as patheffects
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np
import pandas as pd
import geopandas as gpd
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator

# Resolve the cache and any data/ files next to this script, so it runs
# the same no matter which directory it is launched from.
SCRIPT_DIR = (Path(__file__).resolve().parent
              if "__file__" in globals() else Path.cwd())

LON_HINTS = ("lon", "lng", "long", "longitude", "x")
LAT_HINTS = ("lat", "latitude", "y")
FALLBACK_STYLE = {"color": "#7f7f7f", "marker": "o", "size": 30.0,
                  "open": False}
LABEL_HALO = [patheffects.withStroke(linewidth=2.2, foreground="white",
                                     alpha=0.85)]
Z_GRID, Z_POINTS, Z_LABELS, Z_COMPASS = 1.8, 2.6, 3.0, 4.0
BASEMAP_ARCHIVES = {
    "relief": (("50m", "raster", "NE1_50M_SR_W"), "ne1_world.jpg"),
    "relief_alt": (("50m", "raster", "NE2_50M_SR_W"), "ne2_world.jpg"),
    "relief_grey": (("50m", "raster", "GRAY_50M_SR_W"), "gray_world.jpg"),
    "blue_marble": (("50m", "raster", "HYP_50M_SR_W"), "hyp_world.jpg"),
}
BASEMAP_IMG_SIZE = (5400, 2700)
WARP_GRID = (1600, 800)


def download_archive(scale, category, name):
    """Download a Natural Earth zip (cached next to this script)."""
    cache = SCRIPT_DIR / "naturalearth_cache"
    cache.mkdir(exist_ok=True)
    stem = name if category == "raster" else f"ne_{scale}_{name}"
    zip_path = cache / f"{stem}.zip"
    if not zip_path.exists():
        url = (f"https://naturalearth.s3.amazonaws.com/"
               f"{scale}_{category}/{stem}.zip")
        print(f"Downloading {url}")
        urlretrieve(url, zip_path)
    return zip_path


def load_natural_earth(name, category, scale, member=None):
    """Load a Natural Earth vector layer, downloading it if needed."""
    zip_path = download_archive(scale, category, name)
    stem = f"ne_{scale}_{name}"
    folder = zip_path.parent / stem
    if not folder.exists():
        folder.mkdir()
        with zipfile.ZipFile(zip_path) as archive:
            for entry in archive.namelist():
                base = Path(entry).name
                if base and not entry.endswith("/"):
                    (folder / base).write_bytes(archive.read(entry))
    shp = folder / f"{member or stem}.shp"
    gdf = gpd.read_file(shp)
    gdf.columns = [c.lower() for c in gdf.columns]
    return gdf


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


def feature_min_zoom(gdf):
    """Per-feature zoom rank: min_zoom, else scalerank, else 5."""
    if "min_zoom" in gdf.columns:
        ranks = pd.to_numeric(gdf["min_zoom"], errors="coerce")
    elif "scalerank" in gdf.columns:
        ranks = pd.to_numeric(gdf["scalerank"], errors="coerce")
    else:
        ranks = pd.Series(0.0, index=gdf.index)
    return ranks.fillna(5.0)


# ------------------------------------------------------------- projection

def _transformer():
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", MAP_CRS, always_xy=True)


def proj_forward(lons, lats):
    """Project lon/lat arrays into map coordinates, like the app: clip to
    the projection's usable band, NaN out the globe's far hemisphere."""
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    if MAP_CRS is None:
        return lons, lats
    lats = np.clip(lats, PROJ["min_lat"], PROJ["max_lat"])
    if PROJ["lon_halfspan"] < 180.0:
        lons = np.clip(lons, PROJ["lon_0"] - PROJ["lon_halfspan"],
                       PROJ["lon_0"] + PROJ["lon_halfspan"])
    xs, ys = _transformer().transform(lons, lats)
    xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    if PROJ["hemisphere"]:
        bad = ~(np.isfinite(xs) & np.isfinite(ys))
        if bad.any():
            xs = np.where(bad, np.nan, xs)
            ys = np.where(bad, np.nan, ys)
    return xs, ys


def cap_polygon(lon0, lat0, radius):
    """The visible spherical cap (a lon/lat polygon) for clipping to an
    orthographic globe's near hemisphere, with +/-360 copies so a cap
    crossing the antimeridian still covers data stored in [-180, 180]."""
    from shapely import affinity
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    az = np.linspace(0.0, 2.0 * np.pi, 181)
    phi0, r = np.radians(lat0), np.radians(radius)
    lat = np.arcsin(np.sin(phi0) * np.cos(r)
                    + np.cos(phi0) * np.sin(r) * np.cos(az))
    dlon = np.arctan2(np.sin(az) * np.sin(r) * np.cos(phi0),
                      np.cos(r) - np.sin(phi0) * np.sin(lat))
    lon, lat = lon0 + np.degrees(dlon), np.degrees(lat)
    if lat0 + radius >= 90.0:      # cap encloses the north pole
        order = np.argsort(lon)
        shell = list(zip(lon[order], lat[order]))
        shell += [(lon0 + 180.0, 90.0), (lon0 - 180.0, 90.0)]
    elif lat0 - radius <= -90.0:   # ... or the south pole
        order = np.argsort(lon)
        shell = list(zip(lon[order], lat[order]))
        shell += [(lon0 + 180.0, -90.0), (lon0 - 180.0, -90.0)]
    else:
        shell = list(zip(lon, lat))
    cap = Polygon(shell).buffer(0)
    return unary_union([affinity.translate(cap, xoff=off)
                        for off in (-360.0, 0.0, 360.0)])


def to_map_crs(gdf):
    """Reproject a GeoDataFrame into the map projection exactly like the
    app: clip to the visible cap / latitude band first, and leave the
    data untouched on the plain lon/lat projection."""
    if MAP_CRS is None:
        return gdf
    from shapely.geometry import box

    if CLIP_CAP is not None:
        gdf = gdf.clip(cap_polygon(*CLIP_CAP))
    elif PROJ["max_lat"] < 90.0 or PROJ["min_lat"] > -90.0:
        gdf = gdf.clip(box(-180, PROJ["min_lat"], 180, PROJ["max_lat"]))
    return gdf.to_crs(MAP_CRS)


def wrap_offsets():
    """Horizontal world copies needed to cover the view (the app draws
    wrapped copies when the view crosses a world edge)."""
    if PROJ["hemisphere"]:
        return (0.0,)
    wx0, wx1 = PROJ["bounds"][0], PROJ["bounds"][1]
    world_w = wx1 - wx0
    offsets = [0.0]
    if min(VIEW[0], VIEW[1]) < wx0:
        offsets.append(-world_w)
    if max(VIEW[0], VIEW[1]) > wx1:
        offsets.append(world_w)
    return tuple(offsets)


# ---------------------------------------------------------------- basemap

def basemap_image():
    """The raster basemap, prepared exactly like PyMappr does it:
    the Natural Earth raster resampled to a JPEG-compressed world image."""
    from PIL import Image

    if BASEMAP not in BASEMAP_ARCHIVES:
        return None
    archive_args, jpg_name = BASEMAP_ARCHIVES[BASEMAP]
    cache = SCRIPT_DIR / "naturalearth_cache"
    jpg = cache / jpg_name
    if not jpg.exists():
        zip_path = download_archive(*archive_args)
        print("Preparing the basemap raster (one-time)...")
        with zipfile.ZipFile(zip_path) as archive:
            tif_name = next(m for m in archive.namelist()
                            if m.lower().endswith(".tif"))
            with archive.open(tif_name) as handle:
                img = Image.open(io.BytesIO(handle.read()))
                img.load()
        img = img.convert("RGB").resize(BASEMAP_IMG_SIZE, Image.LANCZOS)
        img.save(jpg, "JPEG", quality=85)
    with Image.open(jpg) as img:
        return np.asarray(img.convert("RGB"))


def warped_basemap():
    """The basemap image in the map projection, plus its extent."""
    img = basemap_image()
    if img is None:
        return None
    if MAP_CRS is None:
        return img, (-180, 180, -90, 90)
    wx0, wx1, wy0, wy1 = PROJ["bounds"]
    nx, ny = WARP_GRID
    xs = np.linspace(wx0, wx1, nx)
    ys = np.linspace(wy1, wy0, ny)  # top row first (origin="upper")
    gx, gy = np.meshgrid(xs, ys)
    with np.errstate(all="ignore"):
        lons, lats = _transformer().transform(gx.ravel(), gy.ravel(),
                                              direction="INVERSE")
    lons = np.asarray(lons, float).reshape(gy.shape)
    lats = np.asarray(lats, float).reshape(gy.shape)
    valid = (np.isfinite(lons) & np.isfinite(lats)
             & (np.abs(lons) <= 180.001) & (np.abs(lats) <= 90.001))
    h, w = img.shape[:2]
    lons = np.clip(np.nan_to_num(lons, nan=0.0, posinf=0.0, neginf=0.0),
                   -360.0, 360.0)
    lats = np.clip(np.nan_to_num(lats, nan=0.0, posinf=0.0, neginf=0.0),
                   -90.0, 90.0)
    cols = np.clip(((lons + 180) / 360 * w).astype(int), 0, w - 1)
    rows = np.clip(((90 - lats) / 180 * h).astype(int), 0, h - 1)
    warped = np.zeros((ny, nx, 4), dtype=np.uint8)
    warped[..., :3] = img[rows, cols]
    warped[..., 3] = np.where(valid, 255, 0)
    return warped, (wx0, wx1, wy0, wy1)


def draw_basemap_raster(ax):
    if BASEMAP == "simple":
        return
    result = warped_basemap()
    if result is None:
        return
    img, extent = result
    x0, x1, y0, y1 = extent
    for off in wrap_offsets():
        ax.imshow(img, extent=(x0 + off, x1 + off, y0, y1),
                  origin="upper", interpolation="bilinear", zorder=0.1)


# ------------------------------------------------------------ base layers

def plot_wrapped(ax, gdf, zorder, **plot_kwargs):
    """Plot a GeoDataFrame plus wrapped world copies where the view needs
    them (aspect=None keeps the app's canvas-driven geometry)."""
    for off in wrap_offsets():
        shifted = gdf if not off else gdf.set_geometry(
            gdf.geometry.translate(xoff=off))
        shifted.plot(ax=ax, zorder=zorder, aspect=None, **plot_kwargs)


def add_base_layers(ax):
    """Draw every configured Natural Earth layer with the renderer's true
    draw order, colors, and styling."""
    for layer in LAYERS:
        print(f"Layer: {layer['name']} ({layer['scale']})")
        gdf = load_natural_earth(layer["name"], layer["category"],
                                 layer["scale"], layer.get("member"))
        gdf = filter_layer(gdf, layer.get("filter"))
        if layer["kind"] == "continents":
            gdf = (gdf[["continent", "geometry"]]
                   .dissolve(by="continent").reset_index())
        if layer["kind"] == "point":
            threshold = layer.get("min_zoom_max")
            if threshold is not None:
                gdf = gdf[feature_min_zoom(gdf) <= threshold]
            xs, ys = proj_forward(gdf.geometry.x.to_numpy(),
                                  gdf.geometry.y.to_numpy())
            offsets = wrap_offsets()
            px = np.concatenate([xs + off for off in offsets])
            py = np.tile(ys, len(offsets))
            ax.scatter(px, py, s=layer["size"], c=layer["color"],
                       marker=layer["marker"],
                       edgecolors=layer["edgecolor"], linewidths=0.5,
                       zorder=layer["z"])
            continue
        gdf = to_map_crs(gdf)
        if layer["kind"] == "fill":
            plot_wrapped(ax, gdf, layer["z"], facecolor=layer["color"],
                         edgecolor=layer["edgecolor"],
                         linewidth=layer["width"], alpha=layer["alpha"])
        else:  # line / continents outline
            plot_wrapped(ax, gdf, layer["z"], facecolor="none",
                         edgecolor=layer["color"],
                         linewidth=layer["width"],
                         linestyle=layer["linestyle"])


# -------------------------------------------------------------- graticule

def _norm_lon(value):
    return (value + 180.0) % 360.0 - 180.0


def format_lon(value, _pos=None):
    value = _norm_lon(value)
    if value in (0, 180, -180):
        return f"{abs(value):g}\\N{DEGREE SIGN}"
    return f"{abs(value):g}\\N{DEGREE SIGN}{'W' if value < 0 else 'E'}"


def format_lat(value, _pos=None):
    if value == 0:
        return "0\\N{DEGREE SIGN}"
    return f"{abs(value):g}\\N{DEGREE SIGN}{'S' if value < 0 else 'N'}"


def draw_graticule(ax):
    """The lon/lat grid exactly like the app: labelled axis ticks on the
    plain projection, projected polylines on curved ones."""
    interval = GRATICULE["interval"]
    labels_on = bool(interval) and GRATICULE["labels"] and MAP_CRS is None
    if interval and MAP_CRS is None:
        ax.xaxis.set_major_locator(MultipleLocator(interval))
        ax.yaxis.set_major_locator(MultipleLocator(interval))
        ax.grid(True, color="#787878", linewidth=0.4, alpha=0.7)
        for line in (*ax.get_xgridlines(), *ax.get_ygridlines()):
            line.set_zorder(Z_GRID)
    elif interval:
        max_lat = PROJ["max_lat"]
        segments = []
        for lon in np.arange(-180, 180 + interval / 2, interval):
            lats = np.linspace(-max_lat, max_lat, 91)
            xs, ys = proj_forward(np.full_like(lats, lon), lats)
            segments.append(np.column_stack([xs, ys]))
        for lat in np.arange(-90, 90 + interval / 2, interval):
            if abs(lat) > max_lat:
                continue
            lons = np.linspace(-180, 180, 181)
            xs, ys = proj_forward(lons, np.full_like(lons, lat))
            segments.append(np.column_stack([xs, ys]))
        for off in wrap_offsets():
            col = LineCollection(segments, colors="#787878",
                                 linewidths=0.4, alpha=0.7, zorder=Z_GRID)
            if off:
                col.set_transform(mtransforms.Affine2D().translate(off, 0)
                                  + ax.transData)
            ax.add_collection(col)
    ax.tick_params(labelbottom=labels_on, labelleft=labels_on,
                   bottom=labels_on, left=labels_on)
    if PROJ["hemisphere"]:  # the globe's horizon circle
        az = np.linspace(0.0, 2.0 * np.pi, 361)
        phi0 = np.radians(CLIP_CAP[1])
        r = np.radians(89.9)
        lat = np.arcsin(np.sin(phi0) * np.cos(r)
                        + np.cos(phi0) * np.sin(r) * np.cos(az))
        dlon = np.arctan2(np.sin(az) * np.sin(r) * np.cos(phi0),
                          np.cos(r) - np.sin(phi0) * np.sin(lat))
        lons = CLIP_CAP[0] + np.degrees(dlon)
        xs, ys = proj_forward(lons, np.degrees(lat))
        ax.plot(xs, ys, color="#787878", linewidth=0.8, zorder=Z_GRID)


# ----------------------------------------------------------------- labels

def label_anchors(spec):
    """Label anchor points for a layer: x, y (lon/lat), text, min_label -
    like the app's label store."""
    gdf = load_natural_earth(spec["name"], spec["category"], spec["scale"],
                             spec.get("member"))
    gdf = filter_layer(gdf, spec.get("filter"))
    column = spec["column"]
    if column not in gdf.columns:
        return pd.DataFrame(columns=["x", "y", "text", "min_label"])
    gdf = gdf[gdf[column].notna() & (gdf[column] != "")].copy()
    if spec["min_label_from_min_zoom"] or "min_label" not in gdf.columns:
        if "min_zoom" in gdf.columns:
            gdf["min_label"] = pd.to_numeric(gdf["min_zoom"],
                                             errors="coerce")
        elif "scalerank" in gdf.columns:
            gdf["min_label"] = pd.to_numeric(gdf["scalerank"],
                                             errors="coerce")
        else:
            gdf["min_label"] = 5.0
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if spec["dedupe_longest"]:
            gdf["_len"] = gdf.geometry.length
            gdf = (gdf.sort_values("_len", ascending=False)
                      .drop_duplicates(subset=column))
        if spec["geometry"] == "point":
            pts = gdf.geometry
        elif spec["geometry"] == "line":
            pts = gdf.geometry.interpolate(0.5, normalized=True)
        else:
            pts = gdf.geometry.representative_point()
    return pd.DataFrame({
        "x": pts.x.to_numpy(), "y": pts.y.to_numpy(),
        "text": gdf[column].astype(str).to_numpy(),
        "min_label": pd.to_numeric(gdf["min_label"],
                                   errors="coerce").fillna(5.0).to_numpy(),
    })


def estimate_rect(to_pixels, x, y, text, fontsize_px):
    sx, sy = to_pixels.transform((x, y))
    half_w = (len(text) * 0.31 + 0.3) * fontsize_px
    half_h = 0.72 * fontsize_px
    return (sx - half_w, sy - half_h, sx + half_w, sy + half_h)


def overlaps_any(rect, rects):
    ax0, ay0, ax1, ay1 = rect
    for bx0, by0, bx1, by1 in rects:
        if ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0:
            return True
    return False


def draw_labels(ax, fig):
    """Map labels with the app's font scaling and overlap culling."""
    if not LABEL_LAYERS:
        return
    x0, x1 = sorted(VIEW[:2])
    y0, y1 = sorted(VIEW[2:])
    font_scale = float(np.clip(0.78 + 0.06 * ZOOM, 0.78, 1.15))
    placed = []
    to_pixels = ax.transData
    px_per_pt = fig.dpi / 72.0
    for spec in LABEL_LAYERS:
        points = label_anchors(spec)
        xs, ys = proj_forward(points["x"].to_numpy(),
                              points["y"].to_numpy())
        font = dict(spec["font"])
        font["fontsize"] = font["fontsize"] * font_scale
        candidates = []
        for off in wrap_offsets():
            in_view = ((xs + off >= x0) & (xs + off <= x1)
                       & (ys >= y0) & (ys <= y1)
                       & np.isfinite(xs) & np.isfinite(ys))
            sub = points[in_view].copy()
            sub["px"] = xs[in_view] + off
            sub["py"] = ys[in_view]
            candidates.append(sub)
        eligible = pd.concat(candidates)
        if spec["feature_bias"] is not None:
            eligible = eligible[eligible["min_label"]
                                <= ZOOM + spec["feature_bias"]]
        eligible = eligible.nsmallest(spec["cap"], "min_label")
        va = "bottom" if spec["point_layer"] else "center"
        for row in eligible.itertuples():
            rect = estimate_rect(to_pixels, row.px, row.py, row.text,
                                 font["fontsize"] * px_per_pt)
            if overlaps_any(rect, placed):
                continue
            placed.append(rect)
            ax.text(row.px, row.py, row.text, ha="center", va=va,
                    zorder=Z_LABELS, clip_on=True,
                    path_effects=LABEL_HALO, **font)


# ---------------------------------------------------------------- compass

def draw_compass(ax):
    if not COMPASS:
        return
    ax.annotate(
        "N", xy=(0.975, 0.975), xytext=(0.975, 0.905),
        xycoords="axes fraction", textcoords="axes fraction",
        ha="center", va="center", fontsize=11, fontweight="bold",
        color="#1a1a1a", path_effects=LABEL_HALO, zorder=Z_COMPASS,
        annotation_clip=False,
        arrowprops=dict(arrowstyle="-|>,head_width=0.28,head_length=0.55",
                        color="#1a1a1a", linewidth=1.4,
                        shrinkA=6, shrinkB=0))


# ------------------------------------------------------------- point data

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
        path = Path(spec["path"])
        if not path.is_absolute():
            path = SCRIPT_DIR / path
        suffix = path.suffix.lower()
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
    """Scatter one dataset group by group with the app's marker styling:
    filled markers get a white edge, open markers draw outline-only."""
    df = load_points(spec)
    labels = point_labels(df, spec)
    xs, ys = proj_forward(df["_lon"].to_numpy(), df["_lat"].to_numpy())
    offsets = wrap_offsets()
    order = list(dict.fromkeys(list(STYLES) + sorted(set(labels))))
    for label in order:
        mask = (labels == label).to_numpy()
        if not mask.any():
            continue
        style = STYLES.get(label, FALLBACK_STYLE)
        px = np.concatenate([xs[mask] + off for off in offsets])
        py = np.tile(ys[mask], len(offsets))
        if style["open"]:
            face, edge, lw = "none", style["color"], 1.2
        else:
            face, edge, lw = style["color"], "white", 0.5
        ax.scatter(px, py, s=style["size"], c=face,
                   marker=style["marker"], zorder=Z_POINTS,
                   edgecolors=edge, linewidths=lw, alpha=POINT_ALPHA)


# ----------------------------------------------------------------- legend

def legend_handle(style, size=None):
    area = style["size"] if size is None else size
    if style["open"]:
        face, edge, edge_w = "none", style["color"], 1.2
    else:
        face, edge, edge_w = style["color"], "white", 0.5
    return Line2D([], [], linestyle="", marker=style["marker"],
                  markersize=max(np.sqrt(area), 2),
                  markerfacecolor=face, color=style["color"],
                  markeredgecolor=edge, markeredgewidth=edge_w)


def add_legend(ax):
    """The app's legend: one row per group, or titled sections when the
    map is styled by two attribute columns."""
    if not LEGEND["show"] or not STYLES:
        return
    title = LEGEND["title"] or None
    if LEGEND_SECTIONS is None:
        handles = [legend_handle(style) for style in STYLES.values()]
        for handle, label in zip(handles, STYLES):
            handle.set_label(label)
        ax.legend(handles=handles, loc=LEGEND["location"], title=title,
                  fontsize=LEGEND["fontsize"],
                  title_fontsize=LEGEND["title_fontsize"],
                  ncols=LEGEND["columns"],
                  markerscale=LEGEND["marker_scale"],
                  labelspacing=LEGEND["label_spacing"],
                  frameon=LEGEND["frame"], framealpha=0.85)
        return
    handles, labels, header_rows = [], [], []

    def blank():
        return Line2D([], [], linestyle="", marker="")

    for section_title, entries in LEGEND_SECTIONS:
        if handles:  # spacer between sections
            header_rows.append(len(labels))
            handles.append(blank())
            labels.append(" ")
        header_rows.append(len(labels))
        handles.append(blank())
        labels.append(section_title)
        for label, style in entries:
            handles.append(legend_handle(style, size=45))
            labels.append("   " + label)
    leg = ax.legend(handles, labels, loc=LEGEND["location"], title=title,
                    fontsize=LEGEND["fontsize"],
                    title_fontsize=LEGEND["title_fontsize"],
                    ncols=LEGEND["columns"],
                    markerscale=LEGEND["marker_scale"],
                    frameon=LEGEND["frame"], framealpha=0.85,
                    handletextpad=0.4,
                    labelspacing=LEGEND["label_spacing"])
    texts = leg.get_texts()
    for row in header_rows:
        if row < len(texts):
            texts[row].set_fontweight("bold")


# ------------------------------------------------------------------- main

def main():
    fig = plt.figure(figsize=FIGSIZE, dpi=100, facecolor="white")
    left, bottom, right, top = MARGINS
    ax = fig.add_axes([left, bottom, right - left, top - bottom])
    ax.set_autoscale_on(False)
    ax.xaxis.set_major_formatter(FuncFormatter(format_lon))
    ax.yaxis.set_major_formatter(FuncFormatter(format_lat))
    ax.tick_params(labelsize=7, length=2.5, direction="out")
    ax.set_xlim(VIEW[0], VIEW[1])
    ax.set_ylim(VIEW[2], VIEW[3])
    draw_basemap_raster(ax)
    add_base_layers(ax)
    draw_graticule(ax)
    for spec in DATASETS:
        plot_dataset(ax, spec)
    draw_labels(ax, fig)
    draw_compass(ax)
    ax.set_xlim(VIEW[0], VIEW[1])
    ax.set_ylim(VIEW[2], VIEW[3])
    add_legend(ax)
    output = SCRIPT_DIR / OUTPUT_FILE
    fig.savefig(output, dpi=DPI, facecolor="white")
    print(f"Saved {output}")
    plt.show()


if __name__ == "__main__":
    main()
'''


def _python_script(config: dict) -> str:
    return _py_header(config) + _py_config(config) + _PY_FUNCTIONS


# -------------------------------------------------------------- R template

def _r_header(config: dict) -> str:
    notes = list(config["notes"])
    notes.append("The compass (north arrow)")
    notes.append("Map labels (country/city/... name placement)")
    if config["legend_sections"] is not None:
        notes.append("The sectioned two-attribute legend (rendered as one "
                     "row per combination)")
    listed = "".join(f"\n#   - {note}" for note in notes)
    listed = ("\n# Shown in PyMappr but NOT reproduced by this script:"
              + listed)
    if config["data_mode"] == "files":
        data_note = ("# Your point data is in the data/ folder as CSV - "
                     "edit or replace those\n# files to update the map.")
    else:
        data_note = ("# Your point data is embedded below in DATASETS, so "
                     "this single file is\n# self-contained.")
    return f'''\
# Made with {config["generator"]} - {REPO_URL}
# Recreate the PyMappr map {_r(config["project"])} outside PyMappr.
#
# Generated by {config["generator"]} from pre-made function templates and
# the map's saved settings - deterministically. The layers, colors, view,
# and styling mirror PyMappr's renderer as closely as sf + ggplot2 allow.
#
# Just run it: open this file in RStudio and click Source, or run
# `Rscript recreate_map.R` in a terminal. Missing packages (sf, ggplot2)
# are installed automatically on first run, and the map data is
# downloaded from Natural Earth and cached in naturalearth_cache/ next to
# this script.
#
# Output: map.png
#
{data_note}
# Some marker shapes are approximated (base R has no pentagon/hexagon/
# octagon point shapes). The satellite basemap needs the terra and
# tidyterra packages; without them the script draws the vector map only.
#
# Projection: {config["projection"]}{listed}

ensure_packages <- function(pkgs) {{
  missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1),
                          quietly = TRUE)]
  if (length(missing) > 0) {{
    message("Installing missing packages: ",
            paste(missing, collapse = ", "))
    install.packages(missing, repos = "https://cloud.r-project.org")
  }}
}}
ensure_packages(c("sf", "ggplot2"))

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
    pairs.append(("min_zoom_max", _r(layer.get("min_zoom_max"))))
    if layer["kind"] == "fill":
        pairs += [("fill", _r(layer["color"])),
                  ("edgecolor", _r(None if layer["edgecolor"] == "none"
                                   else layer["edgecolor"])),
                  ("linewidth", _r(_linewidth_mm(layer["width"]))),
                  ("alpha", _r(layer["alpha"])),
                  ("linetype", _r("solid")), ("size", "NULL"),
                  ("shape", "NULL")]
    elif layer["kind"] in ("line", "continents"):
        pairs += [("fill", "NULL"), ("edgecolor", "NULL"),
                  ("linewidth", _r(_linewidth_mm(layer["width"]))),
                  ("alpha", _r(1.0)),
                  ("linetype", _r(_r_linetype(layer["linestyle"]))),
                  ("size", "NULL"), ("shape", "NULL")]
    else:
        pairs += [("fill", "NULL"), ("edgecolor", _r(layer["edgecolor"])),
                  ("linewidth", "NULL"), ("alpha", _r(1.0)),
                  ("linetype", _r("solid")),
                  ("size", _r(_size_mm(layer["size"]))),
                  ("shape", _r({"o": 21, "*": 8, "^": 24,
                                "v": 25}.get(layer["marker"], 21)))]
    body = _r_named(pairs, "    ")
    return f"  list({body})"


def _r_config(config: dict) -> str:
    lines = ["", "# ------------------------- map configuration (from "
                 "PyMappr) -------------------------", ""]
    lines.append(f'MAP_CRS <- {_r(config["crs_r"])}')
    view = config["view"]
    lines.append(f'VIEW <- c({", ".join(_r(v) for v in view)})'
                 "  # axis limits in map coordinates (x0, x1, y0, y1)")
    clip_cap = config["clip_cap"]
    if clip_cap is None:
        lines.append("CLIP_CAP <- NULL  # (lon0, lat0, radius) visible cap "
                     "for the globe, else NULL")
    else:
        lines.append(f'CLIP_CAP <- c({", ".join(_r(v) for v in clip_cap)})'
                     "  # (lon0, lat0, radius) visible cap for the globe")
    proj = config["proj"]
    lines.append(f'MAX_LAT <- {_r(proj["max_lat"])}')
    lines.append(f'MIN_LAT <- {_r(proj["min_lat"])}')
    figsize = config["figsize"]
    lines.append(f'FIGSIZE <- c({_r(figsize[0])}, {_r(figsize[1])})'
                 "  # inches; the app canvas geometry")
    lines.append(f'GEOGRAPHIC <- {_r(config["crs"] is None)}'
                 "  # plain lon/lat degrees?")
    lines.append(f'BASEMAP <- {_r(config["basemap"])}'
                 "  # raster basemap mode (\"simple\" = none)")
    grat = config["graticule"]
    lines.append(f'GRID_INTERVAL <- {_r(grat["interval"])}'
                 "  # graticule spacing in degrees (NULL = off)")
    lines.append(f'GRID_LABELS <- {_r(grat["labels"])}')
    lines.append(f'POINT_ALPHA <- {_r(config["point_alpha"])}')
    lines.append(f'DPI <- {_r(config["dpi"])}')
    lines.append('OUTPUT_FILE <- "map.png"')
    lines.append("")
    lines.append("# Natural Earth layers enabled in PyMappr, in draw "
                 "order.")
    lines.append("NE_LAYERS <- list(")
    lines.append(",\n".join(_r_layer(layer) for layer in config["layers"]))
    lines.append(")")
    lines.append("")
    lines.append("# One entry per dataset. lon_col/lat_col name the "
                 "coordinate columns")
    lines.append("# (NULL = auto-detect by column name).")
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
        block = f"  list({_r_named(pairs, '    ')})"
        if spec.get("source"):
            block = f"  # originally imported from: {spec['source']}\n" + block
        dataset_blocks.append(block)
    lines.append(",\n".join(dataset_blocks))
    lines.append(")")
    lines.append("")
    lines.append("# Legend label -> style, in render order. Fillable "
                 "shapes (21-25) carry the")
    lines.append("# app's white marker edge; sizes approximate PyMappr's "
                 "marker areas.")
    styles = config["styles"]
    shapes, colors, fills, sizes = [], [], [], []
    for label, style in styles.items():
        pch = _R_PCH.get(style.marker, 21)
        shapes.append((label, _r(pch)))
        if pch in _R_FILLABLE_PCH:
            colors.append((label, _r("white")))
            fills.append((label, _r(style.color)))
        else:
            colors.append((label, _r(style.color)))
            fills.append((label, _r(style.color)))
        sizes.append((label, _r(_size_mm(style.size))))
    for name, pairs in (("STYLE_COLORS", colors), ("STYLE_FILLS", fills),
                        ("STYLE_SHAPES", shapes), ("STYLE_SIZES", sizes)):
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

# Run from this script's own folder, so the cache and any data/ files
# resolve the same no matter where the script is launched from.
local({
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  path <- if (length(file_arg) > 0) {
    sub("^--file=", "", file_arg[1])
  } else if (requireNamespace("rstudioapi", quietly = TRUE) &&
             rstudioapi::isAvailable()) {
    rstudioapi::getSourceEditorContext()$path
  } else {
    ""
  }
  if (nzchar(path)) setwd(dirname(normalizePath(path)))
})

LON_HINTS <- c("lon", "lng", "long", "longitude", "x")
LAT_HINTS <- c("lat", "latitude", "y")

download_archive <- function(scale, category, name) {
  # Download a Natural Earth zip (cached in ./naturalearth_cache).
  dir.create("naturalearth_cache", showWarnings = FALSE)
  stem <- if (category == "raster") name else
    sprintf("ne_%s_%s", scale, name)
  zip_path <- file.path("naturalearth_cache", paste0(stem, ".zip"))
  if (!file.exists(zip_path)) {
    url <- sprintf("https://naturalearth.s3.amazonaws.com/%s_%s/%s.zip",
                   scale, category, stem)
    message("Downloading ", url)
    download.file(url, zip_path, mode = "wb", quiet = TRUE)
  }
  zip_path
}

load_natural_earth <- function(name, category, scale, member = NULL) {
  # Load a Natural Earth vector layer, downloading it if needed.
  zip_path <- download_archive(scale, category, name)
  stem <- sprintf("ne_%s_%s", scale, name)
  folder <- file.path("naturalearth_cache", stem)
  if (!dir.exists(folder)) unzip(zip_path, exdir = folder, junkpaths = TRUE)
  shp <- if (is.null(member)) paste0(stem, ".shp") else paste0(member, ".shp")
  data <- sf::read_sf(file.path(folder, shp))
  names(data) <- tolower(names(data))
  data
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

zoom_filter <- function(data, threshold) {
  # Per-feature zoom culling like the app: min_zoom (or scalerank)
  # must be <= threshold for a marker to show.
  if (is.null(threshold)) return(data)
  ranks <- if ("min_zoom" %in% names(data)) {
    suppressWarnings(as.numeric(data$min_zoom))
  } else if ("scalerank" %in% names(data)) {
    suppressWarnings(as.numeric(data$scalerank))
  } else {
    rep(0, nrow(data))
  }
  ranks[is.na(ranks)] <- 5
  data[ranks <= threshold, ]
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

cap_polygon <- function(lon0, lat0, radius) {
  # The visible spherical cap (a lon/lat polygon) for clipping to an
  # orthographic globe's near hemisphere, with +/-360 copies so a cap
  # crossing the antimeridian still covers data stored in [-180, 180].
  az <- seq(0, 2 * pi, length.out = 181)
  phi0 <- lat0 * pi / 180
  r <- radius * pi / 180
  lat <- asin(sin(phi0) * cos(r) + cos(phi0) * sin(r) * cos(az))
  dlon <- atan2(sin(az) * sin(r) * cos(phi0),
                cos(r) - sin(phi0) * sin(lat))
  lon <- lon0 + dlon * 180 / pi
  lat <- lat * 180 / pi
  if (lat0 + radius >= 90) {          # cap encloses the north pole
    ord <- order(lon)
    coords <- rbind(cbind(lon[ord], lat[ord]),
                    c(lon0 + 180, 90), c(lon0 - 180, 90),
                    c(lon[ord][1], lat[ord][1]))
  } else if (lat0 - radius <= -90) {  # ... or the south pole
    ord <- order(lon)
    coords <- rbind(cbind(lon[ord], lat[ord]),
                    c(lon0 + 180, -90), c(lon0 - 180, -90),
                    c(lon[ord][1], lat[ord][1]))
  } else {
    coords <- cbind(lon, lat)         # az 0..2pi already closes the ring
  }
  base <- sf::st_polygon(list(coords))
  parts <- lapply(c(-360, 0, 360), function(off) base + c(off, 0))
  sf::st_make_valid(sf::st_union(sf::st_sfc(parts, crs = "EPSG:4326")))
}

to_map_crs <- function(data) {
  # Reproject into the map projection like the app: clip to the visible
  # cap / latitude band first; leave plain lon/lat data untouched.
  if (GEOGRAPHIC) return(data)
  if (!is.null(CLIP_CAP)) {
    cap <- cap_polygon(CLIP_CAP[1], CLIP_CAP[2], CLIP_CAP[3])
    data <- suppressWarnings(sf::st_intersection(data, cap))
  } else if (MAX_LAT < 90 || MIN_LAT > -90) {
    band <- sf::st_as_sfc(sf::st_bbox(
      c(xmin = -180, ymin = MIN_LAT, xmax = 180, ymax = MAX_LAT),
      crs = sf::st_crs("EPSG:4326")))
    data <- suppressWarnings(sf::st_intersection(data, band))
  }
  sf::st_transform(data, MAP_CRS)
}

base_layer_geom <- function(layer) {
  # One ggplot2 geom_sf for a configured Natural Earth layer.
  data <- load_natural_earth(layer$name, layer$category, layer$scale,
                             layer$member)
  data <- filter_layer(data, layer$filter_column, layer$filter_values,
                       layer$filter_keep)
  if (layer$kind == "continents") {
    parts <- split(data, data$continent)
    data <- do.call(rbind, lapply(parts, function(part) {
      sf::st_sf(geometry = sf::st_union(sf::st_geometry(part)))
    }))
  }
  data <- zoom_filter(data, layer$min_zoom_max)
  data <- to_map_crs(data)
  if (layer$kind == "fill") {
    geom_sf(data = data, fill = layer$fill,
            color = if (is.null(layer$edgecolor)) NA else layer$edgecolor,
            linewidth = layer$linewidth, alpha = layer$alpha)
  } else if (layer$kind %in% c("line", "continents")) {
    geom_sf(data = data, fill = NA, color = layer$color,
            linewidth = layer$linewidth, linetype = layer$linetype)
  } else if (layer$shape %in% 21:25) {
    # Filled marker with the app's white edge.
    geom_sf(data = data, fill = layer$color, color = layer$edgecolor,
            size = layer$size, shape = layer$shape, stroke = 0.3)
  } else {
    geom_sf(data = data, color = layer$color, size = layer$size,
            shape = layer$shape, stroke = 0.3)
  }
}

basemap_archives <- list(
  relief     = list(scale = "50m", cat = "raster", name = "NE1_50M_SR_W"),
  relief_alt = list(scale = "50m", cat = "raster", name = "NE2_50M_SR_W"),
  relief_grey = list(scale = "50m", cat = "raster", name = "GRAY_50M_SR_W"),
  blue_marble = list(scale = "50m", cat = "raster", name = "HYP_50M_SR_W")
)

basemap_geom <- function() {
  # The raster basemap via terra + tidyterra (best effort: the
  # vector map still draws if these packages cannot be installed).
  if (BASEMAP == "simple" || is.null(basemap_archives[[BASEMAP]])) return(NULL)
  ok <- tryCatch({
    ensure_packages(c("terra", "tidyterra"))
    TRUE
  }, error = function(e) FALSE)
  if (!ok || !requireNamespace("terra", quietly = TRUE) ||
      !requireNamespace("tidyterra", quietly = TRUE)) {
    message("note: terra/tidyterra unavailable; skipping the basemap raster")
    return(NULL)
  }
  info <- basemap_archives[[BASEMAP]]
  zip_path <- download_archive(info$scale, info$cat, info$name)
  folder <- file.path("naturalearth_cache", info$name)
  if (!dir.exists(folder)) unzip(zip_path, exdir = folder)
  tif <- list.files(folder, pattern = "\\\\.tif$", full.names = TRUE,
                    recursive = TRUE)[1]
  tidyterra::geom_spatraster_rgb(data = terra::rast(tif))
}

lon_label <- function(value) {
  value <- ((value + 180) %% 360) - 180
  ifelse(value %in% c(0, 180, -180), sprintf("%g\\u00b0", abs(value)),
         sprintf("%g\\u00b0%s", abs(value),
                 ifelse(value < 0, "W", "E")))
}

lat_label <- function(value) {
  ifelse(value == 0, "0\\u00b0",
         sprintf("%g\\u00b0%s", abs(value), ifelse(value < 0, "S", "N")))
}

build_map <- function() {
  p <- ggplot()
  if (BASEMAP != "simple") {
    raster_layer <- basemap_geom()
    if (!is.null(raster_layer)) p <- p + raster_layer
  }
  for (layer in NE_LAYERS) p <- p + base_layer_geom(layer)
  if (length(DATASETS) > 0) {
    points <- to_map_crs(load_all_points())
    title <- if (LEGEND$title == "") NULL else LEGEND$title
    # Legend key marker sizes = the mapped point sizes scaled by
    # marker_scale, matching matplotlib's markerscale.
    key_sizes <- unname(STYLE_SIZES) * LEGEND$marker_scale
    p <- p +
      geom_sf(data = points,
              aes(color = label, fill = label, shape = label,
                  size = label),
              alpha = POINT_ALPHA, stroke = 0.5) +
      scale_color_manual(values = STYLE_COLORS, name = title) +
      scale_fill_manual(values = STYLE_FILLS, name = title) +
      scale_shape_manual(values = STYLE_SHAPES, name = title) +
      scale_size_manual(values = STYLE_SIZES, name = title,
                        guide = "none") +
      guides(
        color = guide_legend(ncol = LEGEND$columns,
                             override.aes = list(size = key_sizes)),
        fill = guide_legend(ncol = LEGEND$columns),
        shape = guide_legend(ncol = LEGEND$columns))
  }
  datum <- if (!is.null(GRID_INTERVAL)) sf::st_crs("EPSG:4326") else NULL
  p <- p + coord_sf(crs = MAP_CRS, xlim = VIEW[1:2], ylim = VIEW[3:4],
                    expand = FALSE, datum = datum)
  if (!is.null(GRID_INTERVAL)) {
    p <- p +
      scale_x_continuous(breaks = seq(-180, 180, by = GRID_INTERVAL),
                         labels = lon_label) +
      scale_y_continuous(breaks = seq(-90, 90, by = GRID_INTERVAL),
                         labels = lat_label)
  }
  grid_line <- if (!is.null(GRID_INTERVAL)) {
    element_line(color = grDevices::adjustcolor("#787878", 0.7),
                 linewidth = 0.19)
  } else {
    element_blank()
  }
  axis_text <- if (!is.null(GRID_INTERVAL) && GRID_LABELS) {
    element_text(size = 7)
  } else {
    element_blank()
  }
  p <- p + theme_void() + theme(
    panel.background = element_rect(fill = "white", color = NA),
    plot.background = element_rect(fill = "white", color = NA),
    panel.grid.major = grid_line,
    axis.text = axis_text,
    axis.ticks = element_blank(),
    legend.text = element_text(size = LEGEND$fontsize),
    legend.title = element_text(size = LEGEND$title_fontsize),
    # Approximates matplotlib's labelspacing (vertical gap per entry).
    legend.key.height = grid::unit(1 + LEGEND$label_spacing, "lines"),
    legend.position = if (LEGEND$show) legend_position(LEGEND$location)
                      else "none",
    legend.background = if (LEGEND$frame)
      element_rect(fill = grDevices::adjustcolor("white", 0.85),
                   color = "#999999") else element_blank())
  p
}

legend_position <- function(location) {
  # PyMappr legend locations approximated by ggplot2 sides.
  if (location %in% c("upper left", "lower left")) "left" else "right"
}

main <- function() {
  p <- build_map()
  ggsave(OUTPUT_FILE, plot = p, width = FIGSIZE[1], height = FIGSIZE[2],
         dpi = DPI, bg = "white", limitsize = FALSE)
  message("Saved ", OUTPUT_FILE)
}

main()
'''


def _r_script(config: dict) -> str:
    return _r_header(config) + _r_config(config) + _R_FUNCTIONS


# -------------------------------------------------- working directory export

_PY_REQUIREMENTS = ("geopandas>=1.0\n"
                    "matplotlib>=3.8\n"
                    "numpy>=1.26\n"
                    "pandas>=2.1\n")

_PY_GITIGNORE = "naturalearth_cache/\nmap.png\n__pycache__/\n"

_R_INSTALL = ('install.packages(c("sf", "ggplot2"),\n'
              '                 repos = "https://cloud.r-project.org")\n')

_R_GITIGNORE = ("naturalearth_cache/\nmap.png\n.Rproj.user/\n"
                ".Rhistory\n.RData\n")

# A minimal RStudio project file, so "open this folder in RStudio" works.
_RPROJ = ("Version: 1.0\n\n"
          "RestoreWorkspace: Default\n"
          "SaveWorkspace: Default\n"
          "AlwaysSaveHistory: Default\n\n"
          "EnableCodeIndexing: Yes\n"
          "UseSpacesForTab: Yes\n"
          "NumSpacesForTab: 2\n"
          "Encoding: UTF-8\n")


def _slug(name: str) -> str:
    """A filesystem-safe slug for a project/folder name."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("._-")
    return slug or "map"


def _py_readme(project: str) -> str:
    return f'''# {project} - PyMappr map export

A ready-to-run Python recreation of the PyMappr map "{project}"
(pandas + geopandas + matplotlib), replicating PyMappr's own renderer.

## Run it

Open this folder in your IDE (PyCharm, VS Code, ...) and run
`recreate_map.py`. Or, from a terminal in this folder:

    python recreate_map.py

The script installs any missing packages on first run - or set up the
environment yourself with:

    pip install -r requirements.txt

It downloads its map data from Natural Earth into
`naturalearth_cache/` and reads your point data from the CSV files in
`data/`. The finished map is written to `map.png`.
'''


def _r_readme(project: str, slug: str) -> str:
    return f'''# {project} - PyMappr map export

A ready-to-run R recreation of the PyMappr map "{project}"
(sf + ggplot2).

## Run it

Open `{slug}.Rproj` in RStudio, open `recreate_map.R`, and click Source.
Or, from a terminal in this folder:

    Rscript recreate_map.R

The script installs sf and ggplot2 if they are missing - or install them
yourself with:

    Rscript install.R

It downloads its map data from Natural Earth into
`naturalearth_cache/` and reads your point data from the CSV files in
`data/`. The finished map is written to `map.png`.
'''


def generate_working_directory(state: dict, entries, language: str,
                               project_name: str = "Untitled",
                               figure_size: tuple[float, float] | None = None
                               ) -> dict[str, str]:
    """A ready-to-run project folder recreating the map, as a mapping of
    relative path -> text content.

    Alongside the script it includes the point data as CSV under
    ``data/``, a dependency manifest (``requirements.txt`` or
    ``install.R``), a ``README.md``, a ``.gitignore``, and - for R - an
    RStudio ``.Rproj`` file. Point an IDE at the folder and run.
    """
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    config = build_config(state, entries, project_name, data_mode="files",
                          figure_size=figure_size)
    project = _safe_name(project_name)
    if language == "Python":
        files = {
            "recreate_map.py": _python_script(config),
            "requirements.txt": _PY_REQUIREMENTS,
            "README.md": _py_readme(project),
            ".gitignore": _PY_GITIGNORE,
        }
    else:
        slug = _slug(project)
        files = {
            "recreate_map.R": _r_script(config),
            "install.R": _R_INSTALL,
            f"{slug}.Rproj": _RPROJ,
            "README.md": _r_readme(project, slug),
            ".gitignore": _R_GITIGNORE,
        }
    files.update(config["data_files"])  # data/<name>.csv -> CSV text
    return files


# ----------------------------------------------------------------- entry

def generate_code(state: dict, entries, language: str,
                  project_name: str = "Untitled",
                  figure_size: tuple[float, float] | None = None) -> str:
    """The complete Python or R script recreating the given map state.

    The script is self-contained: point data is embedded inline and
    missing packages install themselves on first run, so it can be pasted
    into an IDE and run as-is. The Python script replicates PyMappr's
    renderer; pass *figure_size* (the app canvas in inches) so the
    exported geometry matches the canvas exactly. Use
    :func:`generate_working_directory` for a folder-based export with the
    data kept as separate CSV files.
    """
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    config = build_config(state, entries, project_name,
                          figure_size=figure_size)
    if language == "Python":
        return _python_script(config)
    return _r_script(config)
