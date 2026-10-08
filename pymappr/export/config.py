"""The code export's configuration: the app state turned into the plain
data both scripts are written from."""

from __future__ import annotations

import math

from pymappr import __version__
from pymappr.export.layers_config import (_base_layers, _inset_config,
                                          _label_layers, _num)
from pymappr.files.projects import safe_filename
from pymappr.geo.layers import CONTINENT_EXTENTS
from pymappr.geo.projections import CAP_CLIP_RADIUS, get_projection, is_globe
from pymappr.renderer.tables import MARGINS_PLAIN, MARGINS_WITH_TICKS
from pymappr.styling.decorations import CompassOptions, ScaleBarOptions
from pymappr.styling.layout import (column_key, layout_points,
                                    with_default_title)
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import (DEFAULT_PALETTE, POINT_EDGE_COLOR,
                                    POINT_EDGE_WIDTH, PointStyle, palette_for)

WORLD_EXTENT = (-180.0, 180.0, -90.0, 90.0)

# Default figure size (inches): the app's initial canvas.
DEFAULT_FIGSIZE = (9.0, 6.5)

# Grid spacing dropdown -> degrees (mirrors the control panel choices).
_GRATICULE_DEGREES = {"1\N{DEGREE SIGN}": 1.0, "5\N{DEGREE SIGN}": 5.0,
                      "10\N{DEGREE SIGN}": 10.0}

# Natural Earth raster basemaps: mode -> (archive tuple, JPEG filename).
# The archive tuple is (scale, category, name) for download_archive().
BASEMAP_RASTERS = {
    "relief": (("50m", "raster", "NE1_50M_SR_W"), "ne1_world.jpg"),
    "relief_alt": (("50m", "raster", "NE2_50M_SR_W"), "ne2_world.jpg"),
    "relief_grey": (("50m", "raster", "GRAY_50M_SR_W"), "gray_world.jpg"),
    "blue_marble": (("50m", "raster", "HYP_50M_SR_W"), "hyp_world.jpg"),
}
BASEMAP_SIZE = (5400, 2700)


def _origin(state_map: dict) -> tuple[float | None, float | None]:
    """The Lambert/Globe origin from the stored map state ("" or a
    non-finite value = default, as the control panel reads it)."""

    def parse(key):
        raw = str(state_map.get(key, "")).strip()
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    return parse("proj_lon0"), parse("proj_lat0")


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


def _export_filename(name: str, extension: str, used: set[str],
                     fallback: str) -> str:
    """A filesystem-safe ``<name><extension>`` that is unique within *used*
    (and is added to it).

    The name is cleaned by the same rule as a saved project's file name,
    which keeps spaces and accented letters. Uniqueness ignores case,
    because Windows and macOS do: "Sites" and "sites" would otherwise write
    one file. A Windows device name such as "CON" gets an underscore, since
    Windows refuses to create that file under any extension - and only the
    part before the first dot counts, so "NUL.tar" becomes "NUL_.tar".
    """
    # Drop the extension before cleaning, so the device-name rule sees the
    # bare stem ("CON.csv" -> "CON_.csv", not "CON.csv").
    raw = str(name).strip().rstrip(". ")
    if extension and raw.lower().endswith(extension.lower()):
        raw = raw[:-len(extension)].rstrip(". ")
    stem = safe_filename(raw) if raw else fallback
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
            "size": style.size, "open": style.is_open, "fill": style.fill}


def _dataset_configs(entries, data_mode: str = "inline",
                     options: LegendOptions | None = None,
                     palette: list[str] | None = None
                     ) -> tuple[list[dict], dict[str, str], list | None,
                                list | None, tuple | None]:
    """Per-dataset script configs, the point data to write as
    ``data/<name>.csv`` in ``"files"`` mode, the sectioned legend (None in
    plain mode), the plain legend's row order (None when sectioned) and
    the legend row explaining open symbols (None when none are drawn).

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
            # Rows whose open_col value is one of open_values draw with the
            # open form of their group's symbol (type localities, say).
            "open_col": None,
            "open_values": [],
        }
        if dataset.open_groups:
            config["open_col"] = entry.open_by
            config["open_values"] = [str(v) for v in entry.open_values]
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
    return (configs, data_files, layout.sections, layout.row_order,
            layout.open_note)


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
    # Without NULs, like every other string in the scripts (see _py, _r).
    return subset.rename(columns=columns).to_csv(index=False).replace(
        "\x00", "")


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
    # As in the app: every projection but the globe (whose grid never
    # reaches the frame) labels its grid.
    labels_on = (graticule is not None
                 and not bool(m.get("hide_grid_labels", False))
                 and not projection.hemisphere)
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
    datasets, data_files, sections, row_order, open_note = _dataset_configs(
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
        # (label, PointStyle) closing the legend: what open symbols mark.
        "open_note": open_note,
        # Straight from LegendOptions, so a new setting reaches the exported
        # script without another entry here. "title" is the resolved one.
        "legend": {**options.to_dict(), "title": title,
                   "handle_text_pad": options.pad_for(sections is not None)},
        "point_alpha": _num(state.get("point_alpha", 1.0), 1.0),
        "point_edge": {"color": str(edge.get("color") or POINT_EDGE_COLOR),
                       "width": _num(edge.get("width", POINT_EDGE_WIDTH),
                                     POINT_EDGE_WIDTH)},
        "dpi": int(_num(m.get("dpi", 200), 200.0)),
        # None without an inset map (and for states saved before insets).
        "inset": _inset_config(state),
        "notes": notes,
    }
