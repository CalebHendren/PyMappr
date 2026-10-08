"""Where each map layer's data comes from: the Natural Earth archive, file
and style behind every layer the code export draws, the inset's included."""

from __future__ import annotations

from pymappr.geo.layers import BATHYMETRY_STEPS, LAYER_SPECS
from pymappr.geo.projections import CAP_CLIP_RADIUS
from pymappr.renderer.tables import (BATHYMETRY_COLORS, FILL_COLORS,
                                     FILL_LAYERS, LABEL_STYLES, LINE_LAYERS,
                                     POINT_LAYERS, Z_BATHYMETRY, Z_LAKE_FILL,
                                     Z_OCEAN, Z_POINT_LAYERS)
from pymappr.styling.decorations import InsetOptions

# Gap between the inset map and a legend sharing its corner, in axes
# fraction - the renderer's own (pymappr/renderer/inset.py).
_INSET_GAP = 0.015

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


def _num(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


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


def _ne_layer(source: str, key: str, kind: str, z: float, zoom: float,
              filt=None, **style) -> dict:
    """A Natural Earth layer's config dict: the archive the app would draw
    *source* from at *zoom*, plus its kind, zorder and style."""
    arc_scale, category, name, member = _source_archive(source, zoom)
    if filt is None:
        filt = _DERIVED_SOURCES.get(source, (None, None))[1]
    return {"key": key, "name": name, "category": category,
            "scale": arc_scale, "member": member, "filter": filt,
            "kind": kind, "z": z, **style}


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
        return _ne_layer(source, key, kind, z, zoom, filt, **style)

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


def _inset_clear(options: InsetOptions, rect) -> tuple[str, float] | None:
    """(corner, axes-fraction y) a legend in the inset's corner keeps
    beyond, as the renderer works it out; None once the inset was dragged
    out of its corner."""
    if options.anchor is not None:
        return None
    _x, y, _width, height = rect
    if options.position.startswith("upper"):
        return options.position, round(y - _INSET_GAP, 6)
    return options.position, round(y + height + _INSET_GAP, 6)


def _inset_config(state: dict) -> dict | None:
    """The inset map for the script templates, or None without one.

    Everything comes resolved from ``MapRenderer.inset_export()`` (passed in
    as ``state["inset_export"]``): the region, projection, frame and box are
    exactly what the app drew, so the script needs no state lookup. Only
    the layers are turned into Natural Earth archives, at the inset's own
    zoom, like the main map's.
    """
    data = state.get("inset_export")
    if not isinstance(data, dict):
        return None
    zoom = _num(data.get("zoom"), 0.0)
    layers = []
    for source, kwargs in data.get("layers") or []:
        if source not in _CATEGORY:
            continue
        kwargs = dict(kwargs)
        z = _num(kwargs.get("zorder"), 1.0)
        face = kwargs.get("facecolor", "none")
        if face != "none":
            layers.append(_ne_layer(
                source, source, "fill", z, zoom, color=face,
                edgecolor=kwargs.get("edgecolor", "none"),
                width=_num(kwargs.get("linewidth"), 0.0), alpha=1.0))
            continue
        linestyle = kwargs.get("linestyle", "solid")
        if isinstance(linestyle, list):  # a dash pattern, after JSON
            linestyle = (linestyle[0], tuple(linestyle[1]))
        kind = "continents" if source == "continents" else "line"
        layers.append(_ne_layer(
            source, source, kind, z, zoom,
            color=kwargs.get("edgecolor", "#000000"),
            width=_num(kwargs.get("linewidth"), 0.5), linestyle=linestyle))
    layers.sort(key=lambda layer: layer["z"])

    crs = data.get("crs")
    hemisphere = bool(data.get("hemisphere"))
    min_lat = _num(data.get("min_lat"), -90.0)
    max_lat = _num(data.get("max_lat"), 90.0)
    lon_0 = _num(data.get("lon_0"), 0.0)
    lat_0 = _num(data.get("lat_0"), 0.0)
    lon_halfspan = _num(data.get("lon_halfspan"), 180.0)
    # The clip before reprojection, as LayerStore.frame_projected does it:
    # the globe's visible cap, a regional projection's latitude band, or a
    # world projection's symmetric band (Mercator).
    clip_cap = band = None
    if crs is not None:
        if hemisphere:
            clip_cap = (round(lon_0, 6), round(lat_0, 6),
                        round(CAP_CLIP_RADIUS, 6))
        elif lon_halfspan < 180.0 or min_lat != -max_lat:
            band = (min_lat, max_lat)
        elif max_lat < 90.0:
            band = (-max_lat, max_lat)
    rect = [_num(v, 0.0) for v in data.get("rect", (0.0, 0.0, 0.3, 0.3))]
    horizon = data.get("horizon") if hemisphere else None
    box = data.get("box")
    if isinstance(box, dict) and box.get("target") in ("inset", "main"):
        box = {"target": box["target"], "x": list(box.get("x") or []),
               "y": list(box.get("y") or []),
               "color": str(box.get("color") or "#d62728"),
               "width": _num(box.get("width"), 1.2)}
    else:
        box = None
    options = InsetOptions.from_dict(dict(state.get("map", {})).get("inset"))
    return {
        "projection": str(data.get("projection", "Equirectangular")),
        "crs": crs,
        "rect": rect,
        "lon_0": lon_0, "lat_0": lat_0,
        "min_lat": min_lat, "max_lat": max_lat,
        "lon_halfspan": lon_halfspan, "hemisphere": hemisphere,
        "clip_cap": clip_cap, "band": band,
        "limits": [_num(v, 0.0) for v in data.get("limits", (0, 1, 0, 1))],
        "zoom": round(zoom, 4),
        "layers": layers,
        "points": bool(data.get("points", True)),
        "point_scale": _num(data.get("point_scale"), 0.3),
        "frame_width": _num(data.get("frame_width"), 0.8),
        "horizon": (None if not horizon else
                    [list(horizon[0]), list(horizon[1])]),
        "box": box,
        "clear": _inset_clear(options, rect),
    }


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
