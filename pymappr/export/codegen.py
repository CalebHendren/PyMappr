from __future__ import annotations

import math
import numbers
import re
from functools import lru_cache
from pathlib import Path

from pymappr import __version__
from pymappr.files.projects import safe_filename
from pymappr.geo.layers import BATHYMETRY_STEPS, CONTINENT_EXTENTS, LAYER_SPECS
from pymappr.geo.projections import CAP_CLIP_RADIUS, get_projection, is_globe
from pymappr.renderer.tables import (BATHYMETRY_COLORS, FILL_COLORS,
                                     FILL_LAYERS, LABEL_STYLES, LINE_LAYERS,
                                     MARGINS_PLAIN, MARGINS_WITH_TICKS,
                                     POINT_LAYERS, Z_BATHYMETRY, Z_LAKE_FILL,
                                     Z_OCEAN, Z_POINT_LAYERS)
from pymappr.styling.decorations import CompassOptions, ScaleBarOptions
from pymappr.styling.layout import (column_key, layout_points,
                                    with_default_title)
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import (DEFAULT_PALETTE, POINT_EDGE_COLOR,
                                    POINT_EDGE_WIDTH, PointStyle, palette_for)
from pymappr.updates import GITHUB_REPO

LANGUAGES = ("Python", "R")
CODE_EXTENSIONS = {"Python": ".py", "R": ".R"}

# Home page for the attribution comment at the top of every script.
REPO_URL = f"https://github.com/{GITHUB_REPO}"

WORLD_EXTENT = (-180.0, 180.0, -90.0, 90.0)

# Default figure size (inches): the app's initial canvas.
DEFAULT_FIGSIZE = (9.0, 6.5)

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
# variant (21-25) get it, so filled markers carry the app's outline;
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

# How the R shapes above differ from the app's markers, for the script
# header. Keyed by PyMappr marker name; only markers a map uses are listed.
_R_MARKER_NOTES = {
    "Star": "stars are drawn as asterisks (R pch 8)",
    "Star (open)": "stars are drawn as asterisks (R pch 8)",
    "Plus": "plus markers are thin crosses (R pch 3)",
    "Plus (open)": "plus markers are thin crosses (R pch 3)",
    "X": "X markers are thin crosses (R pch 4)",
    "X (open)": "X markers are thin crosses (R pch 4)",
    "Triangle left": "left/right triangles point up",
    "Triangle left (open)": "left/right triangles point up",
    "Triangle right": "left/right triangles point up",
    "Triangle right (open)": "left/right triangles point up",
    "Thin diamond": "thin diamonds are regular diamonds",
    "Thin diamond (open)": "thin diamonds are regular diamonds",
    "Pentagon": "pentagons, hexagons and octagons are circles",
    "Pentagon (open)": "pentagons, hexagons and octagons are circles",
    "Hexagon": "pentagons, hexagons and octagons are circles",
    "Hexagon (open)": "pentagons, hexagons and octagons are circles",
    "Octagon": "pentagons, hexagons and octagons are circles",
    "Octagon (open)": "pentagons, hexagons and octagons are circles",
    "Dot (open)": "open dots are filled dots",
}

# Outline width (points) of an open marker, as the app draws it.
OPEN_MARKER_EDGE = 1.2

# ggplot2 linetype names approximating the renderer's dash tuples.
_R_LINETYPES = {
    (0, (1, 2)): "dotted",
    (0, (3, 2)): "dashed",
    (0, (3, 3)): "dashed",
    (0, (4, 2)): "dashed",
    (0, (5, 3)): "longdash",
    (0, (6, 3)): "longdash",
}


# The pre-made functions pasted verbatim below every script's configuration
# block. They replicate pymappr/renderer/ for a single static view, and live
# in real .py/.R files so editors, linters and diffs treat them as code.
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=None)
def _template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


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


# Device names Windows will not create a file under, whatever the extension.
_RESERVED_FILENAMES = {"con", "prn", "aux", "nul",
                       *(f"com{i}" for i in range(1, 10)),
                       *(f"lpt{i}" for i in range(1, 10))}


def _export_filename(name: str, extension: str, used: set[str],
                     fallback: str) -> str:
    """A filesystem-safe ``<name><extension>`` that is unique within *used*
    (and is added to it).

    The name is cleaned by the same rule as a saved project's file name,
    which keeps spaces and accented letters. Uniqueness ignores case,
    because Windows and macOS do: "Sites" and "sites" would otherwise write
    one file. A Windows device name such as "CON" gets an underscore, since
    Windows refuses to create that file under any extension.
    """
    stem = safe_filename(str(name)) if str(name).strip() else fallback
    if extension and stem.lower().endswith(extension.lower()):
        stem = stem[:-len(extension)].rstrip(". ") or fallback
    if stem.split(".")[0].strip().lower() in _RESERVED_FILENAMES:
        stem += "_"
    taken = {item.casefold() for item in used}
    candidate = f"{stem}{extension}"
    counter = 2
    while candidate.casefold() in taken:
        candidate = f"{stem}_{counter}{extension}"
        counter += 1
    used.add(candidate)
    return candidate


def _style_dict(style: PointStyle | None) -> dict | None:
    # None is a legend row that takes no swatch.
    if style is None:
        return None
    return {"color": style.color, "marker": style.mpl_marker,
            "size": style.size, "open": style.is_open}


def _dataset_configs(entries, data_mode: str = "inline",
                     options: LegendOptions | None = None,
                     palette: list[str] | None = None
                     ) -> tuple[list[dict], dict[str, str], list | None,
                                list | None]:
    """Per-dataset script configs, the point data to write as
    ``data/<name>.csv`` in ``"files"`` mode, the sectioned legend (None in
    plain mode) and the plain legend's row order (None when sectioned).

    Each config carries its own ``styles`` (legend label -> style, in
    render order): labels are not unique across datasets - two ungrouped
    datasets can both be "Sites" - and the app draws each dataset in its
    own style.

    Everything about what is drawn comes from :func:`layout_points`, the
    same function the app draws with, so the script matches the map.
    """
    layout = layout_points(entries, options or LegendOptions(),
                           palette or DEFAULT_PALETTE)
    used_files: set[str] = set()
    configs: list[dict] = []
    data_files: dict[str, str] = {}
    for dataset in layout.datasets:
        entry = dataset.entry
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
            # The label an ungrouped dataset's points are keyed by, before
            # label_map turns it into the legend text.
            "default_label": "All points",
            "label_map": dataset.label_map,
            # Keyed by group value, like label_map: two groups renamed to
            # the same label are still two groups, each in its own style.
            "styles": _group_styles(dataset),
            # Original source path, for a provenance comment only (not read
            # by the generated loader).
            "source": entry.dataset.source_path or None,
        }
        if data_mode == "files":
            rel = "data/" + _export_filename(entry.name, ".csv",
                                             used_files, "dataset")
            config["path"] = rel
            data_files[rel] = csv_text
        else:
            config["inline_data"] = csv_text
        if dataset.attribute:
            # Only columns the app resolves: a stale Color by that names no
            # column is ignored there, so it must not stop the script.
            for key, label in (("color_col", entry.color_by),
                               ("symbol_col", entry.symbol_by)):
                if column_key(entry, label) is not None:
                    config[key] = label
        elif column_key(entry, entry.group_by) is not None:
            config["group_col"] = entry.group_by
        configs.append(config)
    return configs, data_files, layout.sections, layout.row_order


def _group_styles(dataset) -> dict:
    """A drawn dataset's group value -> style, in render order.

    In group-by mode the groups are label_map's keys, in the same order;
    otherwise each group's label is its value."""
    values = list(dataset.label_map) or [label for label, _style, _rows
                                         in dataset.groups]
    return {value: style for value, (_label, style, _rows)
            in zip(values, dataset.groups)}


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
    options = LegendOptions.from_dict(legend)
    if not (options.title or "").strip():
        options.title = None
    options = with_default_title(entries, options)
    datasets, data_files, sections, row_order = _dataset_configs(
        entries, data_mode, options, palette_for(m.get("palette")))
    edge = dict(state.get("point_edge") or {})
    title = (options.title or "").strip()
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
        "compass_options": CompassOptions.from_dict(
            m.get("compass_options")).to_dict(),
        "scale_bar": ScaleBarOptions.from_dict(m.get("scale_bar")).to_dict(),
        "datasets": datasets,
        "data_mode": data_mode,
        "data_files": data_files,
        "legend_sections": sections,
        # None = no explicit ordering (the sectioned legend owns its rows).
        # An empty list is different: it means every row was hidden.
        "legend_rows": row_order,
        # Straight from LegendOptions, so a new setting reaches the exported
        # script without another entry here. "title" is the resolved one.
        "legend": {**options.to_dict(), "title": title,
                   "handle_text_pad": options.pad_for(sections is not None)},
        "point_alpha": _num(state.get("point_alpha", 1.0), 1.0),
        "point_edge": {"color": str(edge.get("color") or POINT_EDGE_COLOR),
                       "width": _num(edge.get("width", POINT_EDGE_WIDTH),
                                     POINT_EDGE_WIDTH)},
        "dpi": int(_num(m.get("dpi", 200), 200.0)),
        "notes": notes,
    }


# ----------------------------------------------------- literal formatting

def _py(value) -> str:
    """A Python literal for a config value, containers included.

    Floats are rounded to 6 places; NaN and infinity, which repr() would
    write as the undefined names ``nan`` and ``inf``, become ``float()``
    calls.
    """
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, numbers.Integral):
        return repr(int(value))
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            return 'float("nan")'
        if math.isinf(number):
            return 'float("inf")' if number > 0 else '-float("inf")'
        return repr(round(number, 6))
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_py(k)}: {_py(v)}"
                               for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_py(item) for item in value) + "]"
    if isinstance(value, tuple):
        items = [_py(item) for item in value]
        return "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"
    return repr(value)


def _r(value) -> str:
    """An R literal for a config value. NaN and infinity become R's own
    ``NA_real_``, ``Inf`` and ``-Inf`` rather than undefined names."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            return "NA_real_"
        if math.isinf(number):
            return "Inf" if number > 0 else "-Inf"
        return repr(round(number, 6))
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\n", "\\n").replace("\r", "").replace("\t", "\\t")
    return f'"{text}"'


def _comment_text(text) -> str:
    """*text* made safe for a one-line ``#`` comment in either language: a
    line break in it would end the comment and run the rest as code."""
    return re.sub(r"[\r\n]+", " ", str(text)).strip()


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
    """A project name on one line and free of double quotes, so it can sit
    in quotes in a docstring, comment or README."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(name)).replace('"', "'")
    return text.strip() or "map"


def _py_docstring_text(text: str) -> str:
    """*text* escaped for a normal (non-raw) docstring, where a backslash
    starts an escape: "Field\\Notes" would otherwise read as a malformed
    \\N{...} escape and stop the script compiling."""
    return text.replace("\\", "\\\\")


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
"""Recreate the PyMappr map "{_py_docstring_text(_safe_name(config["project"]))}" outside PyMappr.

Generated by {config["generator"]} from pre-made function templates and
the map's saved settings

Just run it: open this file in an IDE (PyCharm, VS Code, ...) and click
Run, or `python recreate_map.py` in a terminal. If a package it needs
(pandas, geopandas, matplotlib) is missing, it prints the pip command to
install it - or run `python recreate_map.py --install-deps` to have it
installed for you. The map data is downloaded from Natural Earth and cached
in naturalearth_cache/ next to this script.

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
    compass = dict(config["compass_options"])
    compass["show"] = config["compass"]
    lines.append(f'COMPASS = {_py(compass)}')
    lines.append(f'SCALE_BAR = {_py(config["scale_bar"])}')
    lines.append(f'POINT_ALPHA = {_py(config["point_alpha"])}')
    lines.append(f'POINT_EDGE = {_py(config["point_edge"])}'
                 "  # outline around filled markers")
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
    lines.append("# label_map renames groups for the legend; 'styles' maps "
                 "each group to its")
    lines.append("# point style, in render order (open = outline-only "
                 "marker).")
    lines.append("DATASETS = [")
    for spec in config["datasets"]:
        if spec.get("source"):
            lines.append("    # originally imported from: "
                         + _comment_text(spec["source"]))
        lines.append("    {")
        for key in ("name", "path", "inline_data", "lon_col", "lat_col",
                    "group_col", "color_col", "symbol_col",
                    "default_label", "label_map"):
            lines.append(f"        {_py(key)}: {_py(spec[key])},")
        lines.append("        'styles': {")
        for value, style in spec["styles"].items():
            lines.append(f"            {_py(value)}: "
                         f"{_py(_style_dict(style))},")
        lines.append("        },")
        lines.append("    },")
    lines.append("]")
    lines.append("")
    sections = config["legend_sections"]
    if sections is None:
        lines.append("LEGEND_SECTIONS = None"
                     "  # plain legend: one row per style, in DATASETS")
    else:
        lines.append("# Sectioned legend, like the app's: (label, style, "
                     "depth) rows, where")
        lines.append("# depth indents a row under the one above it (a "
                     "nested genus/species key).")
        lines.append("LEGEND_SECTIONS = [")
        for title, entries in sections:
            lines.append(f"    ({_py(title)}, [")
            for label, style, *rest in entries:
                depth = rest[0] if rest else 0
                fields = _style_dict(style)
                if fields is None:
                    drawn = "None"
                else:
                    drawn = "{" + ", ".join(f"{_py(k)}: {_py(v)}"
                                            for k, v in fields.items()) + "}"
                lines.append(
                    f"        ({_py(label)}, {drawn}, {depth}),")
            lines.append("    ]),")
        lines.append("]")
    lines.append("")
    rows = config.get("legend_rows")
    lines.append("# Legend rows for the plain legend, in order (None = "
                 "every style, in DATASETS order).")
    lines.append(f"LEGEND_ROWS = {_py(rows)}")
    lines.append("")
    legend = config["legend"]
    body = ", ".join(f"{_py(k)}: {_py(v)}" for k, v in legend.items())
    lines.append(f"LEGEND = {{{body}}}")
    return "\n".join(lines) + "\n"


def _python_script(config: dict) -> str:
    return (_py_header(config) + _py_config(config)
            + _template("recreate_map.py"))


# -------------------------------------------------------------- R template

def _r_legend_notes(legend: dict) -> list[str]:
    """Legend settings ggplot2's guide/theme system has no equivalent for.

    Only settings the user actually changed are listed, so the header stays
    a short list of real differences rather than a catalogue of everything
    the two renderers disagree about.
    """
    defaults = LegendOptions()
    notes = []
    unsupported = [
        ("group_swatch", "The nested key's group swatch style"),
        ("symbol_swatch_color", "The crossed-key symbol swatch colour"),
        ("indent", "The nested key's indent width"),
        ("bold_groups", "Bolding of the nested key's group rows"),
        ("group_spacer", "Blank rows between nested groups"),
        ("handle_length", "Legend swatch width"),
        ("border_pad", "Legend inner padding"),
        ("column_spacing", "Legend column spacing"),
        ("rounded", "Rounded legend corners"),
        ("shadow", "The legend's drop shadow"),
        ("title_align", "Legend title alignment"),
    ]
    for key, description in unsupported:
        if legend.get(key) != getattr(defaults, key):
            notes.append(f"{description} (no ggplot2 equivalent)")
    # The stored gap is already resolved, so compare against the two values
    # "automatic" can produce rather than against the unset default.
    if legend.get("handle_text_pad") not in (0.4, 0.8):
        notes.append("The swatch-to-label gap (no ggplot2 equivalent)")
    if legend.get("show", True) and legend.get("location") == "best":
        notes.append('Automatic ("best") legend placement: the legend sits '
                     "in the upper right")
    return notes


def _r_marker_notes(config: dict) -> list[str]:
    """How the map's own markers are approximated by R's point shapes."""
    found = dict.fromkeys(
        _R_MARKER_NOTES[style.marker]
        for spec in config["datasets"] for style in spec["styles"].values()
        if style.marker in _R_MARKER_NOTES)
    if not found:
        return []
    return ["Some marker shapes (R has no exact equivalent): "
            + "; ".join(found)]


def _r_header(config: dict) -> str:
    notes = list(config["notes"])
    notes.append("Map labels (country/city/... name placement)")
    if (config["legend"].get("label_underline")
            or config["legend"].get("title_underline")):
        notes.append("Underlined legend text (ggplot2 element_text has no "
                     "underline; bold/italic are applied)")
    if config["legend_sections"] is not None:
        notes.append("The sectioned two-attribute legend (rendered as one "
                     "row per combination)")
    notes += _r_legend_notes(config["legend"])
    notes += _r_marker_notes(config)
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
# `Rscript recreate_map.R` in a terminal. If sf or ggplot2 is missing it
# stops with the install.packages() line to run - or run
# `Rscript recreate_map.R --install-deps` to have them installed for you.
# The map data is downloaded from Natural Earth and cached in
# naturalearth_cache/ next to this script.
#
# Output: map.png
#
{data_note}
# The satellite basemap needs the terra and tidyterra packages; without
# them the script draws the vector map only.
#
# Projection: {config["projection"]}{listed}

ensure_packages <- function(pkgs) {{
  missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1),
                          quietly = TRUE)]
  if (length(missing) == 0) return(invisible())
  command <- sprintf(
    'install.packages(c(%s), repos = "https://cloud.r-project.org")',
    paste0('"', missing, '"', collapse = ", "))
  if (!("--install-deps" %in% commandArgs(trailingOnly = TRUE))) {{
    stop("This script needs ", paste(missing, collapse = ", "),
         ". Install with:\n    ", command,
         "\nor run it with Rscript ... --install-deps to install them ",
         "automatically.", call. = FALSE)
  }}
  message("Installing missing packages: ", paste(missing, collapse = ", "))
  install.packages(missing, repos = "https://cloud.r-project.org")
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
    pairs.append(("z", _r(round(layer["z"], 6))))
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


def _r_vector(name: str, pairs: list[tuple[str, str]]) -> str:
    """``name <- c(...)`` with one ``"key" = value`` per line."""
    if not pairs:
        return f"{name} <- c()"
    return f"{name} <- c({_r_named(pairs, '  ')})"


def _r_style_keys(config: dict) -> tuple[list[dict], list[tuple],
                                         list | None]:
    """The R script's style keys.

    ggplot2 styles points through one set of manual scales, keyed by name,
    so groups that share a label (two ungrouped datasets both named
    "Sites", or two groups renamed alike) need different keys to keep their
    own styles and legend rows. A key is the label itself, or "label [n]"
    for dataset n when the label is already taken.

    Returns each dataset's group value -> key map (only where the two
    differ),
    every (key, label, style) in render order, and the legend's keys in
    legend order (None when every key is a row, as in the sectioned
    legend), ordered the way the app orders its plain legend.
    """
    taken: set[str] = set()
    per_dataset: list[dict] = []
    groups: list[tuple] = []
    for number, spec in enumerate(config["datasets"], start=1):
        renamed = {}
        for value, style in spec["styles"].items():
            label = spec["label_map"].get(value, value)
            key = label
            suffix = 0
            while key in taken:
                suffix += 1
                key = (f"{label} [{number}]" if suffix == 1
                       else f"{label} [{number}.{suffix}]")
            taken.add(key)
            if key != value:
                renamed[value] = key
            groups.append((key, label, style))
        per_dataset.append(renamed)
    rows = config.get("legend_rows")
    if rows is None:
        return per_dataset, groups, None
    rank = {label: i for i, label in enumerate(rows)}
    shown = sorted((group for group in groups if group[1] in rank),
                   key=lambda group: rank[group[1]])
    return per_dataset, groups, [key for key, _label, _style in shown]


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
    lines.append(f'MAX_LAT <- {_r(proj["max_lat"])}'
                 "  # the projection's usable latitude band")
    lines.append(f'MIN_LAT <- {_r(proj["min_lat"])}')
    lines.append(f'LON_0 <- {_r(proj["lon_0"])}'
                 "  # central meridian, and how far either side is usable")
    lines.append(f'LON_HALFSPAN <- {_r(proj["lon_halfspan"])}')
    bounds = proj["bounds"]
    lines.append(f'PROJ_X <- c({_r(bounds[0])}, {_r(bounds[1])})'
                 "  # the world's x range, for wrapped copies")
    lines.append(f'HEMISPHERE <- {_r(bool(proj["hemisphere"]))}'
                 "  # a globe: only the near side is drawn")
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
    lines.append(f'POINT_STROKE <- {_r(config["point_edge"]["width"])}'
                 "  # outline width of filled markers, in points")
    lines.append(f'POINT_EDGE_COLOR <- {_r(config["point_edge"]["color"])}')
    compass = dict(config["compass_options"])
    compass["show"] = config["compass"]
    lines.append("COMPASS <- list(" + _r_named(
        [(k, _r(v)) for k, v in compass.items()], "  ") + ")")
    lines.append("SCALE_BAR <- list(" + _r_named(
        [(k, _r(v)) for k, v in config["scale_bar"].items()], "  ") + ")")
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
    lines.append("# style_keys maps a group value to its STYLE_* key where "
                 "the two differ.")
    lines.append("DATASETS <- list(")
    dataset_blocks = []
    style_keys, groups, legend_keys = _r_style_keys(config)
    for spec, keys in zip(config["datasets"], style_keys):
        pairs = [(key, _r(spec[key]))
                 for key in ("name", "path", "inline_data", "lon_col",
                             "lat_col", "group_col", "color_col",
                             "symbol_col", "default_label")]
        for name, mapping in (("label_map", spec["label_map"]),
                              ("style_keys", keys)):
            if mapping:
                body = _r_named([(k, _r(v)) for k, v in mapping.items()],
                                "      ")
                pairs.append((name, f"c({body})"))
            else:
                pairs.append((name, "c()"))
        block = f"  list({_r_named(pairs, '    ')})"
        if spec.get("source"):
            block = ("  # originally imported from: "
                     f"{_comment_text(spec['source'])}\n" + block)
        dataset_blocks.append(block)
    lines.append(",\n".join(dataset_blocks))
    lines.append(")")
    lines.append("")
    lines.append("# Legend key -> style, in render order. A key is the "
                 "legend label, with")
    lines.append("# \" [n]\" added where dataset n repeats a label "
                 "another dataset already uses")
    lines.append("# (STYLE_LABELS holds those keys' labels). Fillable "
                 "shapes (21-25) carry")
    lines.append("# the app's marker outline; sizes approximate "
                 "PyMappr's marker areas and")
    lines.append("# strokes are outline widths in points.")
    edge = config["point_edge"]
    shapes, colors, fills, sizes, strokes, renamed = [], [], [], [], [], []
    for key, label, style in groups:
        pch = _R_PCH.get(style.marker, 21)
        shapes.append((key, _r(pch)))
        if pch in _R_FILLABLE_PCH:
            colors.append((key, _r(edge["color"])))
        else:
            colors.append((key, _r(style.color)))
        fills.append((key, _r(style.color)))
        sizes.append((key, _r(_size_mm(style.size))))
        strokes.append((key, _r(OPEN_MARKER_EDGE if style.is_open
                                else edge["width"])))
        if key != label:
            renamed.append((key, _r(label)))
    for name, pairs in (("STYLE_COLORS", colors), ("STYLE_FILLS", fills),
                        ("STYLE_SHAPES", shapes), ("STYLE_SIZES", sizes),
                        ("STYLE_STROKES", strokes),
                        ("STYLE_LABELS", renamed)):
        lines.append(_r_vector(name, pairs))
    lines.append("")
    lines.append("# Legend rows, in order: hidden rows are left out but "
                 "their points still draw")
    lines.append("# (NULL = every STYLE_* key).")
    if legend_keys is None:
        lines.append("LEGEND_ROWS <- NULL")
    elif legend_keys:
        lines.append("LEGEND_ROWS <- c(" + ", ".join(
            _r(key) for key in legend_keys) + ")")
    else:
        lines.append("LEGEND_ROWS <- character(0)  # every row is hidden")
    lines.append("")
    legend = config["legend"]
    pairs = [(key, _r(value)) for key, value in legend.items()]
    lines.append(f"LEGEND <- list({_r_named(pairs, '  ')})")
    return "\n".join(lines) + "\n"


def _r_script(config: dict) -> str:
    return (_r_header(config) + _r_config(config)
            + _template("recreate_map.R"))


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


def _py_readme(project: str) -> str:
    return f'''# {project} - PyMappr map export

A ready-to-run Python recreation of the PyMappr map "{project}"
(pandas + geopandas + matplotlib), replicating PyMappr's own renderer.

## Run it

Open this folder in your IDE (PyCharm, VS Code, ...) and run
`recreate_map.py`. Or, from a terminal in this folder:

    python recreate_map.py

If a package is missing the script tells you; set up the environment
with:

    pip install -r requirements.txt

(or run `python recreate_map.py --install-deps` to let it install them).

It downloads its map data from Natural Earth into
`naturalearth_cache/` and reads your point data from the CSV files in
`data/`. The finished map is written to `map.png`.
'''


def _r_readme(project: str, rproj: str) -> str:
    return f'''# {project} - PyMappr map export

A ready-to-run R recreation of the PyMappr map "{project}"
(sf + ggplot2).

## Run it

Open `{rproj}` in RStudio, open `recreate_map.R`, and click Source.
Or, from a terminal in this folder:

    Rscript recreate_map.R

If sf or ggplot2 is missing the script tells you; install them with:

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
        rproj = _export_filename(project, ".Rproj", set(), "map")
        files = {
            "recreate_map.R": _r_script(config),
            "install.R": _R_INSTALL,
            rproj: _RPROJ,
            "README.md": _r_readme(project, rproj),
            ".gitignore": _R_GITIGNORE,
        }
    files.update(config["data_files"])  # data/<name>.csv -> CSV text
    return files


# ----------------------------------------------------------------- entry

def generate_code(state: dict, entries, language: str,
                  project_name: str = "Untitled",
                  figure_size: tuple[float, float] | None = None) -> str:
    """The complete Python or R script recreating the given map state.

    The script is self-contained: point data is embedded inline, and a
    missing package stops it with the command that installs it (or is
    installed for you with ``--install-deps``). The Python script replicates PyMappr's
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
