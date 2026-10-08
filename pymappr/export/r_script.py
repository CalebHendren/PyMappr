"""The R script: its header and configuration block, and the files an R
working directory export adds."""

from __future__ import annotations

from pymappr.export.literals import (REPO_URL, _comment_text, _linewidth_mm,
                                     _r, _r_linetype, _r_named, _size_mm,
                                     _template, _wrapped_items)
from pymappr.styling.legend import LegendOptions
from pymappr.styling.styles import OPEN_SUFFIX, open_form

# PyMappr marker name -> R pch code. Shapes with a filled+outlined R
# variant (21-25) get it, so filled markers carry the app's outline;
# open variants use the hollow codes. Shapes base R lacks fall back.
# The R script keys an open-symbol row "<key> [open]", and the legend's
# note on what open symbols mark by this key.
_R_OPEN_SUFFIX = " [open]"
_R_OPEN_NOTE_KEY = "[open symbols]"

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
    lines.append(f"OPEN_KEY_SUFFIX <- {_r(_R_OPEN_SUFFIX)}")
    lines.append("DATASETS <- list(")
    dataset_blocks = []
    style_keys, groups, legend_keys = _r_style_keys(config)
    note = config.get("open_note")
    if note is not None:
        # Open-symbol rows are keyed "<key> [open]" by load_all_points, in
        # the open form of their group's style, and never get a legend row
        # of their own; one note row says what they mark.
        base = [key for key, _label, _style in groups]
        groups = (groups
                  + [(key + _R_OPEN_SUFFIX, label, open_form(style))
                     for key, label, style in groups]
                  + [(_R_OPEN_NOTE_KEY, note[0], note[1])])
        legend_keys = ((base if legend_keys is None else legend_keys)
                       + [_R_OPEN_NOTE_KEY])
    for spec, keys in zip(config["datasets"], style_keys):
        pairs = [(key, _r(spec[key]))
                 for key in ("name", "path", "inline_data", "lon_col",
                             "lat_col", "group_col", "color_col",
                             "symbol_col", "default_label", "open_col")]
        pairs.append(("open_values",
                      "c(" + ", ".join(_r(v) for v in spec["open_values"])
                      + ")" if spec["open_values"] else "character(0)"))
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
        if style.is_open and style.fill:
            # A filled open symbol: the fillable shape, outlined in the
            # style's colour around its fill.
            pch = _R_PCH.get(style.marker[:-len(OPEN_SUFFIX)], pch)
        shapes.append((key, _r(pch)))
        if style.is_open and style.fill:
            colors.append((key, _r(style.color)))
            fills.append((key, _r(style.fill)))
        elif pch in _R_FILLABLE_PCH:
            colors.append((key, _r(edge["color"])))
            fills.append((key, _r(style.color)))
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
    lines.append("")
    lines += _r_inset(config.get("inset"))
    return "\n".join(lines) + "\n"


def _r_numbers(values, indent: str) -> str:
    """An R numeric vector, wrapped over lines; None (a point that does not
    project) becomes NA, which breaks a drawn path there."""
    items = ["NA_real_" if v is None else _r(float(v)) for v in values]
    if not items:
        return "numeric(0)"
    return "c(\n" + "\n".join(_wrapped_items(items, indent)) + ")"


def _r_inset(inset: dict | None) -> list[str]:
    lines = ["# The inset map, as PyMappr drew it (NULL = no inset): rect is "
             "its place in the",
             "# map's panel fraction (x, y, width, height), limits its axis "
             "limits in its own",
             "# CRS, clip_cap / band what layers are clipped to before "
             "reprojecting, and box",
             "# the outline linking the two maps, drawn on the inset or on "
             "the main map (NA",
             "# in x/y breaks the line)."]
    if inset is None:
        return lines + ["INSET <- NULL"]

    def vector(values) -> str:
        if values is None:
            return "NULL"
        return "c(" + ", ".join(_r(v) for v in values) + ")"

    clear = inset["clear"]
    pairs = [("projection", _r(inset["projection"])),
             ("crs", _r(inset["crs"] or "EPSG:4326")),
             ("geographic", _r(inset["crs"] is None)),
             ("rect", vector(inset["rect"])),
             ("lon_0", _r(inset["lon_0"])), ("lat_0", _r(inset["lat_0"])),
             ("min_lat", _r(inset["min_lat"])),
             ("max_lat", _r(inset["max_lat"])),
             ("lon_halfspan", _r(inset["lon_halfspan"])),
             ("hemisphere", _r(inset["hemisphere"])),
             ("clip_cap", vector(inset["clip_cap"])),
             ("band", vector(inset["band"])),
             ("limits", vector(inset["limits"])),
             ("points", _r(inset["points"])),
             ("point_scale", _r(inset["point_scale"])),
             ("frame_width", _r(inset["frame_width"])),
             ("clear", "NULL" if clear is None else
              f"list(corner = {_r(clear[0])}, y = {_r(clear[1])})")]
    layers = ",\n".join("\n".join("  " + line for line in
                                  _r_layer(layer).splitlines())
                        for layer in inset["layers"])
    pairs.append(("layers", f"list(\n{layers}\n  )" if layers else "list()"))
    horizon = inset["horizon"]
    if horizon is None:
        pairs.append(("horizon", "NULL"))
    else:
        pairs.append(("horizon",
                      f"list(\n    x = {_r_numbers(horizon[0], '      ')},"
                      f"\n    y = {_r_numbers(horizon[1], '      ')})"))
    box = inset["box"]
    if box is None:
        pairs.append(("box", "NULL"))
    else:
        pairs.append(("box",
                      f"list(\n    target = {_r(box['target'])}, "
                      f"color = {_r(box['color'])}, "
                      f"width = {_r(box['width'])},"
                      f"\n    x = {_r_numbers(box['x'], '      ')},"
                      f"\n    y = {_r_numbers(box['y'], '      ')})"))
    lines.append(f"INSET <- list({_r_named(pairs, '  ')})")
    return lines


def _r_script(config: dict) -> str:
    return (_r_header(config) + _r_config(config)
            + _template("recreate_map.R"))


# -------------------------------------------------- working directory export

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
