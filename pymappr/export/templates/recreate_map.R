

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

# ggplot2 sizes things in its own units; these convert the app's points.
LINEWIDTH_PT <- 72.27 / 25.4 * 0.75  # points per ggplot2 linewidth unit
STROKE_PT <- 72 / 50.8               # points per ggplot2 point stroke unit
Z_GRID <- 1.8                        # the app's grid z, above fills/lines
GRID_COLOR <- grDevices::adjustcolor("#787878", 0.7)
MARKER_LAYER_EDGE <- 0.5             # city/airport marker outline (points)
BASEMAP_WIDTH <- 5400                # PyMappr's basemap resample width
# How a label with no entry in STYLE_* draws: the app's default grey dot.
FALLBACK_STYLE <- list(fill = "#7f7f7f", shape = 21, size = 1.93)

zip_is_readable <- function(zip_path) {
  listing <- tryCatch(suppressWarnings(utils::unzip(zip_path, list = TRUE)),
                      error = function(e) NULL)
  !is.null(listing) && nrow(listing) > 0
}

download_archive <- function(scale, category, name) {
  # Download a Natural Earth zip (cached in ./naturalearth_cache). It lands
  # under a .part name first, so an interrupted download is never mistaken
  # for a finished one; a damaged zip already in the cache is fetched again.
  dir.create("naturalearth_cache", showWarnings = FALSE)
  stem <- if (category == "raster") name else
    sprintf("ne_%s_%s", scale, name)
  zip_path <- file.path("naturalearth_cache", paste0(stem, ".zip"))
  if (file.exists(zip_path) && !zip_is_readable(zip_path)) {
    message("Re-downloading the damaged ", basename(zip_path))
    file.remove(zip_path)
  }
  if (!file.exists(zip_path)) {
    url <- sprintf("https://naturalearth.s3.amazonaws.com/%s_%s/%s.zip",
                   scale, category, stem)
    part <- paste0(zip_path, ".part")
    message("Downloading ", url)
    download.file(url, part, mode = "wb", quiet = TRUE)
    file.rename(part, zip_path)
  }
  zip_path
}

extract_archive <- function(zip_path, folder, wanted, junkpaths = TRUE) {
  # Unzip into a scratch folder and move it into place once complete, so a
  # failed extraction never leaves a folder that looks finished. unzip()
  # only warns about a member it cannot decode, so a warning - or a file
  # missing from what it wrote - counts as a failure, and the zip is
  # deleted so the next run downloads it again.
  if (!is.null(wanted) && all(file.exists(file.path(folder, wanted)))) {
    return(folder)
  }
  scratch <- paste0(folder, ".part")
  unlink(scratch, recursive = TRUE)
  members <- utils::unzip(zip_path, list = TRUE)$Name
  members <- members[!grepl("/$", members)]
  written <- tryCatch(
    withCallingHandlers(
      utils::unzip(zip_path, exdir = scratch, junkpaths = junkpaths),
      warning = function(w) stop(conditionMessage(w), call. = FALSE)),
    error = function(e) e)
  if (inherits(written, "error") || length(written) != length(members)) {
    unlink(scratch, recursive = TRUE)
    file.remove(zip_path)
    stop("Could not unpack ", basename(zip_path), " (",
         if (inherits(written, "error")) conditionMessage(written) else
           "files missing", "); it was deleted, so run the script again ",
         "to download it afresh.", call. = FALSE)
  }
  unlink(folder, recursive = TRUE)
  file.rename(scratch, folder)
  folder
}

load_natural_earth <- function(name, category, scale, member = NULL) {
  # Load a Natural Earth vector layer, downloading it if needed.
  zip_path <- download_archive(scale, category, name)
  stem <- sprintf("ne_%s_%s", scale, name)
  shp <- if (is.null(member)) paste0(stem, ".shp") else paste0(member, ".shp")
  folder <- extract_archive(zip_path, file.path("naturalearth_cache", stem),
                            shp)
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
  # Read one dataset (file or embedded CSV) with numeric lon/lat. Every
  # column is read as text, like PyMappr does, so labels such as "007",
  # "1.50", "T" or "NA" stay exactly as written.
  if (!is.null(spec$inline_data)) {
    df <- read.csv(text = spec$inline_data, check.names = FALSE,
                   colClasses = "character", na.strings = character(0))
  } else if (grepl("\\.(tsv|txt)$", tolower(spec$path))) {
    df <- read.delim(spec$path, check.names = FALSE, encoding = "UTF-8",
                     colClasses = "character", na.strings = character(0))
  } else {
    # Excel files need readxl:
    # df <- readxl::read_excel(spec$path, col_types = "text")
    df <- read.csv(spec$path, check.names = FALSE, encoding = "UTF-8",
                   colClasses = "character", na.strings = character(0))
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
  # Every dataset's points as lon/lat plus the STYLE_* key each is drawn
  # with: its legend label, made unique where two datasets share a label.
  frames <- lapply(DATASETS, function(spec) {
    df <- load_points(spec)
    labels <- point_labels(df, spec)
    keys <- labels
    if (length(spec$style_keys) > 0) {
      renamed <- labels %in% names(spec$style_keys)
      keys[renamed] <- spec$style_keys[labels[renamed]]
    }
    data.frame(lon = df$`_lon`, lat = df$`_lat`, key = unname(keys))
  })
  merged <- do.call(rbind, frames)
  sf::st_as_sf(merged, coords = c("lon", "lat"), crs = "EPSG:4326")
}

cap_ring <- function(lon0, lat0, radius, n) {
  # Lon/lat points `radius` degrees from (lon0, lat0), all the way round.
  az <- seq(0, 2 * pi, length.out = n)
  phi0 <- lat0 * pi / 180
  r <- radius * pi / 180
  lat <- asin(sin(phi0) * cos(r) + cos(phi0) * sin(r) * cos(az))
  dlon <- atan2(sin(az) * sin(r) * cos(phi0),
                cos(r) - sin(phi0) * sin(lat))
  cbind(lon0 + dlon * 180 / pi, lat * 180 / pi)
}

cap_polygon <- function(lon0, lat0, radius) {
  # The visible spherical cap (a lon/lat polygon) for clipping to an
  # orthographic globe's near hemisphere, with +/-360 copies so a cap
  # crossing the antimeridian still covers data stored in [-180, 180].
  ring <- cap_ring(lon0, lat0, radius, 181)
  lon <- ring[, 1]
  lat <- ring[, 2]
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
    # sin(2 * pi) misses 0 by ~1e-14, so close the ring explicitly.
    coords <- rbind(cbind(lon, lat), c(lon[1], lat[1]))
  }
  base <- sf::st_polygon(list(coords))
  parts <- lapply(c(-360, 0, 360), function(off) base + c(off, 0))
  suppressMessages(sf::st_make_valid(
    sf::st_union(sf::st_sfc(parts, crs = "EPSG:4326"))))
}

to_map_crs <- function(data) {
  # Reproject into the map projection like the app: clip to the visible
  # cap / latitude band first; leave plain lon/lat data untouched.
  if (GEOGRAPHIC) return(data)
  # Clip on the plane, like shapely in the app: Natural Earth polygons and
  # the band/cap rings are not valid s2 geometry. Only for this call - the
  # scale bar's st_distance needs s2 on lon/lat (or lwgeom without it).
  old <- suppressMessages(sf::sf_use_s2(FALSE))
  on.exit(suppressMessages(sf::sf_use_s2(old)))
  if (!is.null(CLIP_CAP)) {
    cap <- cap_polygon(CLIP_CAP[1], CLIP_CAP[2], CLIP_CAP[3])
    data <- suppressMessages(suppressWarnings(
      sf::st_intersection(data, cap)))
  } else if (MAX_LAT < 90 || MIN_LAT > -90) {
    band <- sf::st_as_sfc(sf::st_bbox(
      c(xmin = -180, ymin = MIN_LAT, xmax = 180, ymax = MAX_LAT),
      crs = sf::st_crs("EPSG:4326")))
    data <- suppressMessages(suppressWarnings(
      sf::st_intersection(data, band)))
  }
  sf::st_transform(data, MAP_CRS)
}

project_points <- function(data) {
  # Points like the app: clamped into the projection's usable band rather
  # than clipped away, and dropped only where the globe's far side hides
  # them.
  if (GEOGRAPHIC || nrow(data) == 0) return(data)
  xy <- sf::st_coordinates(data)
  lon <- xy[, 1]
  lat <- pmin(pmax(xy[, 2], MIN_LAT), MAX_LAT)
  if (LON_HALFSPAN < 180) {
    lon <- pmin(pmax(lon, LON_0 - LON_HALFSPAN), LON_0 + LON_HALFSPAN)
  }
  clamped <- sf::st_as_sf(data.frame(lon = lon, lat = lat),
                          coords = c("lon", "lat"), crs = "EPSG:4326")
  data <- sf::st_set_geometry(data, sf::st_geometry(clamped))
  data <- sf::st_transform(data, MAP_CRS)
  xy <- sf::st_coordinates(data)
  data[is.finite(xy[, 1]) & is.finite(xy[, 2]), ]
}

wrap_offsets <- function() {
  # Horizontal world copies needed to cover the view (the app draws
  # wrapped copies when the view crosses a world edge).
  if (HEMISPHERE) return(0)
  width <- PROJ_X[2] - PROJ_X[1]
  offsets <- 0
  if (min(VIEW[1:2]) < PROJ_X[1]) offsets <- c(offsets, -width)
  if (max(VIEW[1:2]) > PROJ_X[2]) offsets <- c(offsets, width)
  offsets
}

wrapped <- function(data) {
  # `data` (already in the map projection) plus its wrapped world copies.
  offsets <- wrap_offsets()
  if (length(offsets) == 1 || nrow(data) == 0) return(data)
  crs <- sf::st_crs(data)
  copies <- lapply(offsets, function(off) {
    if (off == 0) return(data)
    moved <- sf::st_geometry(data) + c(off, 0)
    sf::st_crs(moved) <- crs
    sf::st_set_geometry(data, moved)
  })
  do.call(rbind, copies)
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
  data <- if (layer$kind == "point") project_points(data) else
    to_map_crs(data)
  data <- wrapped(data)
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
            size = layer$size, shape = layer$shape,
            stroke = MARKER_LAYER_EDGE / STROKE_PT)
  } else {
    geom_sf(data = data, color = layer$color, size = layer$size,
            shape = layer$shape, stroke = MARKER_LAYER_EDGE / STROKE_PT)
  }
}

graticule_layers <- function() {
  # The lon/lat grid as map lines, drawn at the app's grid z (above every
  # fill and line layer, below the points), plus the globe's horizon.
  layers <- list()
  if (!is.null(GRID_INTERVAL)) {
    lats <- seq(-90, 90, by = GRID_INTERVAL)
    meridians <- lapply(seq(-180, 180, by = GRID_INTERVAL), function(lon) {
      sf::st_linestring(cbind(lon, seq(-MAX_LAT, MAX_LAT, length.out = 91)))
    })
    parallels <- lapply(lats[abs(lats) <= MAX_LAT], function(lat) {
      sf::st_linestring(cbind(seq(-180, 180, length.out = 181), lat))
    })
    grid <- sf::st_sf(geometry = sf::st_sfc(c(meridians, parallels),
                                            crs = "EPSG:4326"))
    layers <- c(layers, list(geom_sf(
      data = wrapped(to_map_crs(grid)), color = GRID_COLOR,
      linewidth = 0.4 / LINEWIDTH_PT)))
  }
  if (HEMISPHERE) {
    ring <- cap_ring(CLIP_CAP[1], CLIP_CAP[2], 89.9, 361)
    horizon <- sf::st_sfc(sf::st_linestring(ring), crs = "EPSG:4326")
    layers <- c(layers, list(geom_sf(
      data = sf::st_transform(horizon, MAP_CRS), color = "#787878",
      linewidth = 0.8 / LINEWIDTH_PT)))
  }
  layers
}

basemap_archives <- list(
  relief     = list(scale = "50m", cat = "raster", name = "NE1_50M_SR_W"),
  relief_alt = list(scale = "50m", cat = "raster", name = "NE2_50M_SR_W"),
  relief_grey = list(scale = "50m", cat = "raster", name = "GRAY_50M_SR_W"),
  blue_marble = list(scale = "50m", cat = "raster", name = "HYP_50M_SR_W")
)

basemap_layers <- function() {
  # The raster basemap via terra + tidyterra (best effort: the
  # vector map still draws if these packages cannot be installed).
  if (BASEMAP == "simple" || is.null(basemap_archives[[BASEMAP]])) {
    return(list())
  }
  ok <- tryCatch({
    ensure_packages(c("terra", "tidyterra"))
    TRUE
  }, error = function(e) FALSE)
  if (!ok || !requireNamespace("terra", quietly = TRUE) ||
      !requireNamespace("tidyterra", quietly = TRUE)) {
    message("note: terra/tidyterra unavailable; skipping the basemap raster")
    return(list())
  }
  info <- basemap_archives[[BASEMAP]]
  zip_path <- download_archive(info$scale, info$cat, info$name)
  folder <- file.path("naturalearth_cache", info$name)
  find_tif <- function() {
    list.files(folder, pattern = "\\.tif$", full.names = TRUE,
               recursive = TRUE)
  }
  if (length(find_tif()) == 0) {
    extract_archive(zip_path, folder, NULL, junkpaths = FALSE)
  }
  raster <- terra::rast(find_tif()[1])
  # The grey relief is a single band; drawn as RGB it needs three.
  if (terra::nlyr(raster) == 1) raster <- c(raster, raster, raster)
  # PyMappr draws a 5400 x 2700 resample of the raster; match that instead
  # of tidyterra's default 500,000-cell preview.
  shrink <- floor(terra::ncol(raster) / BASEMAP_WIDTH)
  if (shrink > 1) raster <- terra::aggregate(raster, fact = shrink)
  offsets <- wrap_offsets()
  # A copy shifted by a world width only lines up in map coordinates.
  if (length(offsets) > 1 && !GEOGRAPHIC) {
    raster <- terra::project(raster, MAP_CRS)
  }
  lapply(offsets, function(off) {
    copy <- if (off == 0) raster else terra::shift(raster, dx = off)
    tidyterra::geom_spatraster_rgb(data = copy, maxcell = Inf)
  })
}

lon_label <- function(value) {
  value <- ((value + 180) %% 360) - 180
  ifelse(value %in% c(0, 180, -180), sprintf("%g°", abs(value)),
         sprintf("%g°%s", abs(value),
                 ifelse(value < 0, "W", "E")))
}

lat_label <- function(value) {
  ifelse(value == 0, "0°",
         sprintf("%g°%s", abs(value), ifelse(value < 0, "S", "N")))
}

legend_labels <- function(keys) {
  # The text shown for each STYLE_* key (they differ only where two
  # datasets share a label).
  labels <- keys
  renamed <- keys %in% names(STYLE_LABELS)
  labels[renamed] <- STYLE_LABELS[keys[renamed]]
  unname(labels)
}

point_layers <- function() {
  # The datasets' points, with one legend row per STYLE_* entry in
  # LEGEND_ROWS order - including rows whose points are all off the map,
  # as the app keeps them.
  if (length(DATASETS) == 0) return(list())
  points <- wrapped(project_points(load_all_points()))
  keys <- names(STYLE_COLORS)
  # A label with no configured style draws in grey, like the app's default.
  extra <- setdiff(unique(points$key), keys)
  with_extra <- function(values, default) {
    c(values, stats::setNames(rep(default, length(extra)), extra))
  }
  colors <- with_extra(STYLE_COLORS, POINT_EDGE_COLOR)
  fills <- with_extra(STYLE_FILLS, FALLBACK_STYLE$fill)
  shapes <- with_extra(STYLE_SHAPES, FALLBACK_STYLE$shape)
  sizes <- with_extra(STYLE_SIZES, FALLBACK_STYLE$size)
  strokes <- with_extra(STYLE_STROKES, POINT_STROKE)
  limits <- names(colors)
  points$key <- factor(points$key, levels = limits)
  shown <- if (is.null(LEGEND_ROWS)) keys else LEGEND_ROWS
  title <- if (LEGEND$title == "") NULL else LEGEND$title
  manual <- function(scale, values) {
    scale(values = values, limits = limits, breaks = shown,
          labels = legend_labels(shown), drop = FALSE, name = title)
  }
  # Legend key marker sizes = the mapped point sizes scaled by
  # marker_scale, matching matplotlib's markerscale.
  key_aes <- list(size = unname(sizes[shown]) * LEGEND$marker_scale,
                  stroke = unname(strokes[shown]) / STROKE_PT)
  legend <- if (length(shown) == 0) {
    guides(color = "none", fill = "none", shape = "none")
  } else {
    guides(color = guide_legend(ncol = LEGEND$columns,
                                override.aes = key_aes),
           fill = guide_legend(ncol = LEGEND$columns),
           shape = guide_legend(ncol = LEGEND$columns))
  }
  list(
    geom_sf(data = points,
            aes(color = key, fill = key, shape = key, size = key),
            alpha = POINT_ALPHA,
            stroke = unname(strokes[as.character(points$key)]) / STROKE_PT,
            # TRUE, not the default NA: a row whose points are all off the
            # map still gets its swatch.
            show.legend = TRUE),
    manual(scale_color_manual, colors),
    manual(scale_fill_manual, fills),
    manual(scale_shape_manual, shapes),
    scale_size_manual(values = sizes, limits = limits, guide = "none"),
    legend)
}

legend_anchor <- function(location) {
  # The panel corner (or edge midpoint) a matplotlib legend location sits
  # against. "best" picks a spot clear of the data in the app; ggplot2 has
  # no equivalent, so it takes the upper right.
  location <- switch(location, best = "upper right",
                     right = "center right", center = "center center",
                     location)
  parts <- strsplit(location, " ")[[1]]
  c(switch(parts[2], left = 0, right = 1, 0.5),
    switch(parts[1], upper = 1, lower = 0, 0.5))
}

legend_frame <- function() {
  if (!isTRUE(LEGEND$frame)) return(element_blank())
  edge <- LEGEND$frame_edge_color
  if (LEGEND$frame_width <= 0 || identical(edge, "none")) edge <- NA
  fill <- if (identical(LEGEND$frame_color, "none")) NA else
    grDevices::adjustcolor(LEGEND$frame_color, LEGEND$frame_alpha)
  element_rect(fill = fill, colour = edge,
               linewidth = LEGEND$frame_width / LINEWIDTH_PT)
}

legend_text <- function(size, bold, italic, colour) {
  family <- if (nzchar(LEGEND$font_family)) LEGEND$font_family else NULL
  element_text(size = size, face = text_face(bold, italic), colour = colour,
               family = family)
}

build_map <- function() {
  p <- ggplot() + basemap_layers()
  grid_drawn <- FALSE
  for (layer in NE_LAYERS) {
    if (!grid_drawn && layer$z > Z_GRID) {
      p <- p + graticule_layers()
      grid_drawn <- TRUE
    }
    p <- p + base_layer_geom(layer)
  }
  if (!grid_drawn) p <- p + graticule_layers()
  p <- p + point_layers()
  labelled <- !is.null(GRID_INTERVAL) && GRID_LABELS
  # The grid is drawn as a layer above, so coord_sf only labels the axes.
  datum <- if (labelled) sf::st_crs("EPSG:4326") else NA
  p <- p + coord_sf(crs = MAP_CRS, xlim = VIEW[1:2], ylim = VIEW[3:4],
                    expand = FALSE, datum = datum)
  if (labelled) {
    p <- p +
      scale_x_continuous(breaks = seq(-540, 540, by = GRID_INTERVAL),
                         labels = lon_label) +
      scale_y_continuous(breaks = seq(-90, 90, by = GRID_INTERVAL),
                         labels = lat_label)
  }
  p <- p + scale_bar_layers() + compass_layers()
  anchor <- legend_anchor(LEGEND$location)
  # matplotlib's borderaxespad: half the legend font size off the frame.
  inset <- 0.5 * LEGEND$fontsize / 72 / FIGSIZE
  p + theme_void() + theme(
    panel.background = element_rect(fill = "white", color = NA),
    plot.background = element_rect(fill = "white", color = NA),
    panel.grid.major = element_blank(),
    axis.text = if (labelled) element_text(size = 7) else element_blank(),
    axis.ticks = element_blank(),
    legend.text = legend_text(LEGEND$fontsize, LEGEND$label_bold,
                              LEGEND$label_italic, LEGEND$label_color),
    legend.title = legend_text(LEGEND$title_fontsize, LEGEND$title_bold,
                               LEGEND$title_italic, LEGEND$title_color),
    # Approximates matplotlib's labelspacing (vertical gap per entry).
    legend.key.height = grid::unit(1 + LEGEND$label_spacing, "lines"),
    legend.key = element_blank(),
    legend.position = if (LEGEND$show) "inside" else "none",
    legend.position.inside = anchor + sign(0.5 - anchor) * inset,
    legend.justification.inside = anchor,
    legend.background = legend_frame())
}

# --------------------------------------------- compass and scale bar

METRES_PER_MILE <- 1609.344
BAR_HEIGHT <- 0.011
BAR_GAP <- 0.005
LABEL_GAP <- 0.012
LABEL_ROOM <- 0.030

view_crs <- function() {
  if (is.null(MAP_CRS)) sf::st_crs("EPSG:4326") else sf::st_crs(MAP_CRS)
}

axes_to_data <- function(fx, fy) {
  # coord_sf() is given VIEW with expand = FALSE, so a fraction of VIEW is
  # exactly a fraction of the drawn panel.
  c(VIEW[1] + (VIEW[2] - VIEW[1]) * fx,
    VIEW[3] + (VIEW[4] - VIEW[3]) * fy)
}

span_metres <- function(fx0, fx1, fy) {
  # Ground metres between two panel-fraction x positions on row fy.
  # Measured from lon/lat: a projected metre is not a ground metre, and the
  # plain lon/lat projection is in degrees anyway. NA where the row is off
  # the map, as a corner of a Robinson or orthographic view is.
  a <- axes_to_data(fx0, fy)
  b <- axes_to_data(fx1, fy)
  pts <- try(sf::st_sfc(sf::st_point(a), sf::st_point(b), crs = view_crs()),
             silent = TRUE)
  if (inherits(pts, "try-error")) return(NA_real_)
  geo <- try(sf::st_transform(pts, 4326), silent = TRUE)
  if (inherits(geo, "try-error")) return(NA_real_)
  coords <- sf::st_coordinates(geo)
  if (any(!is.finite(coords))) return(NA_real_)
  d <- try(as.numeric(sf::st_distance(geo)[1, 2]), silent = TRUE)
  if (inherits(d, "try-error") || !is.finite(d)) return(NA_real_)
  d
}

scale_reference_row <- function(fy) {
  # A row where the scale can actually be measured; the bar's own row is
  # preferred, because a bar should describe the scale where it stands.
  for (step in c(0, 0.25, 0.5, 0.75, 1)) {
    row <- fy + (0.5 - fy) * step
    if (is.finite(span_metres(0.45, 0.55, row))) return(row)
  }
  0.5
}

estimate_scale <- function(fx, fy) {
  # Ground metres per unit of panel x-fraction: a first guess, refined
  # against the bar's real endpoints in fit_bar_width().
  left <- max(0, min(0.9, fx - 0.05))
  m <- span_metres(left, left + 0.1, fy)
  if (!is.finite(m) || m <= 0) m <- span_metres(0.45, 0.55, fy)
  if (!is.finite(m) || m <= 0) return(NA_real_)
  m / 0.1
}

unit_metres <- function(units) {
  if (identical(units, "mi")) METRES_PER_MILE else 1000
}

nice_length <- function(metres, units) {
  # A round bar length at or just below `metres`, so a long label can never
  # run off the map.
  per <- unit_metres(units)
  value <- metres / per
  if (!is.finite(value) || value <= 0) return(0)
  decade <- 10 ^ floor(log10(value))
  for (cand in c(5, 3, 2, 1)) {
    if (cand * decade <= value) return(cand * decade * per)
  }
  decade / 10 * per
}

format_length <- function(metres, units) {
  if (!identical(units, "mi") && metres < 1000) {
    return(paste0(format(metres, trim = TRUE, scientific = FALSE), " m"))
  }
  value <- metres / unit_metres(units)
  suffix <- if (identical(units, "mi")) " mi" else " km"
  paste0(format(value, trim = TRUE, scientific = FALSE), suffix)
}

corner_anchor <- function(corner, pad = 0.03) {
  corner <- if (is.null(corner)) "lower left" else corner
  parts <- strsplit(corner, " ")[[1]]
  x <- if (identical(parts[2], "left")) pad else 1 - pad
  y <- if (identical(parts[1], "lower")) pad else 1 - pad
  c(x, y)
}

fit_bar_width <- function(metres, x, row, right_anchored) {
  # The estimate is local, but a scale bar is long and the map scale varies
  # across it, so refine the width against the bar's own endpoints until the
  # drawing really is the length its label claims.
  per <- estimate_scale(x, row)
  if (!is.finite(per) || per <= 0) return(NA_real_)
  width <- metres / per
  for (i in 1:6) {
    if (!is.finite(width) || width <= 0 || width > 0.95) return(NA_real_)
    x0 <- if (right_anchored) x - width else x
    actual <- span_metres(x0, x0 + width, row)
    if (!is.finite(actual) || actual <= 0) {
      # The bar's own span is off the map: refine against the same width
      # centred on the reference row instead.
      actual <- span_metres(0.5 - width / 2, 0.5 + width / 2, row)
    }
    if (!is.finite(actual) || actual <= 0) break
    adjust <- metres / actual
    if (abs(adjust - 1) < 0.001) break
    width <- width * adjust
  }
  if (!is.finite(width) || width <= 0 || width > 0.95) return(NA_real_)
  width
}

scale_bar_layers <- function() {
  if (!isTRUE(SCALE_BAR$show)) return(list())
  units_shown <- if (identical(SCALE_BAR$units, "both")) {
    c("km", "mi")
  } else {
    SCALE_BAR$units
  }
  dragged <- !is.null(SCALE_BAR$anchor_x) && !is.null(SCALE_BAR$anchor_y)
  anchor <- if (dragged) {
    c(SCALE_BAR$anchor_x, SCALE_BAR$anchor_y)
  } else {
    corner_anchor(SCALE_BAR$position)
  }
  x <- anchor[1]
  y <- anchor[2]
  right_anchored <- x > 0.5 && !dragged
  top_anchored <- y > 0.5 && !dragged
  n <- length(units_shown)
  stack <- n * BAR_HEIGHT + (n - 1) * BAR_GAP
  base_y <- if (top_anchored) y - stack else y
  # A second unit is labelled underneath, so lift the stack off the frame.
  if (n > 1 && !top_anchored && !dragged) base_y <- base_y + LABEL_ROOM

  layers <- list()
  for (i in seq_along(units_shown)) {
    unit <- units_shown[i]
    y0 <- base_y + (n - i) * (BAR_HEIGHT + BAR_GAP)
    row <- scale_reference_row(y0 + BAR_HEIGHT / 2)
    fixed <- (i == 1 && identical(SCALE_BAR$length_mode, "fixed")
              && !is.null(SCALE_BAR$fixed_length))
    if (fixed) {
      metres <- SCALE_BAR$fixed_length * unit_metres(SCALE_BAR$units)
    } else {
      est <- estimate_scale(x, row)
      if (!is.finite(est) || est <= 0) {
        message("Scale bar: the map scale cannot be measured at this view.")
        return(list())
      }
      # Each unit gets its own round length, so "3000 km" is never paired
      # with an unreadable "1864 mi".
      metres <- nice_length(est * SCALE_BAR$width, unit)
    }
    if (metres <= 0) return(list())
    width <- fit_bar_width(metres, x, row, right_anchored)
    if (!is.finite(width)) {
      message("Scale bar: scale varies too much across this view to draw ",
              "an accurate bar.")
      return(list())
    }
    x0 <- if (right_anchored) x - width else x
    segments <- if (identical(SCALE_BAR$style, "segmented")) {
      max(as.integer(SCALE_BAR$segments), 1L)
    } else {
      1L
    }
    for (seg in seq_len(segments)) {
      lo <- axes_to_data(x0 + width * (seg - 1) / segments, y0)
      hi <- axes_to_data(x0 + width * seg / segments, y0 + BAR_HEIGHT)
      layers <- c(layers, list(annotate(
        "rect", xmin = lo[1], xmax = hi[1], ymin = lo[2], ymax = hi[2],
        fill = if (seg %% 2 == 1) SCALE_BAR$color else "white",
        color = SCALE_BAR$color, linewidth = 0.28)))
    }
    above <- i == 1
    lab <- axes_to_data(
      x0 + width / 2,
      if (above) y0 + BAR_HEIGHT + LABEL_GAP else y0 - LABEL_GAP)
    layers <- c(layers, list(annotate(
      "text", x = lab[1], y = lab[2], label = format_length(metres, unit),
      size = SCALE_BAR$fontsize / 2.845, colour = SCALE_BAR$color,
      hjust = 0.5, vjust = if (above) 0 else 1)))
  }
  layers
}

# Half the width of the triangle compass at size 1, in panel fraction, and
# of the arrow's bold "N", in ems.
COMPASS_TRIANGLE_HALF_WIDTH <- 0.016
COMPASS_N_HALF_WIDTH_EM <- 0.425

compass_layers <- function() {
  if (!isTRUE(COMPASS$show)) return(list())
  anchor <- corner_anchor(COMPASS$position, pad = 0.025)
  x <- anchor[1]
  y <- anchor[2]
  size <- max(COMPASS$size, 0.1)
  triangle <- identical(COMPASS$style, "triangle")
  fontsize <- (if (triangle) 10 else 11) * size
  # North is up the page in every corner: the head (or tip) sits `reach`
  # above the "N". In a top corner the head is at the anchor and the
  # compass hangs below it; in a bottom corner the "N" rests on the anchor,
  # lifted by half its height (points, as fonts are, over the panel size).
  reach <- 0.07 * size
  top <- if (y > 0.5) y else y + reach + 0.5 * fontsize / 72 / FIGSIZE[2]
  label_y <- top - reach
  # Grown past size 1, the compass grows inwards, so its outer edge stays
  # where size 1 puts it, inside the map.
  inwards <- if (x > 0.5) -1 else 1
  growth <- max(size - 1, 0)
  if (triangle) {
    x <- x + inwards * COMPASS_TRIANGLE_HALF_WIDTH * growth
  } else {
    x <- x + inwards * COMPASS_N_HALF_WIDTH_EM * 11 * growth / 72 /
      FIGSIZE[1]
  }
  tip <- axes_to_data(x, top)
  label <- axes_to_data(x, label_y)
  if (triangle) {
    half <- COMPASS_TRIANGLE_HALF_WIDTH * size
    base_y <- label_y + 0.02 * size
    b1 <- axes_to_data(x - half, base_y)
    b2 <- axes_to_data(x + half, base_y)
    return(list(
      annotate("polygon", x = c(tip[1], b1[1], b2[1]),
               y = c(tip[2], b1[2], b2[2]), fill = COMPASS$color,
               colour = "white", linewidth = 0.28 * size),
      annotate("text", x = label[1], y = label[2], label = "N",
               fontface = "bold", size = fontsize / 2.845,
               colour = COMPASS$color)))
  }
  # Start the shaft clear of the "N", the way the app's shrinkA does.
  start <- axes_to_data(x, label_y + 0.014 * size)
  list(
    annotate("segment", x = start[1], y = start[2],
             xend = tip[1], yend = tip[2],
             arrow = grid::arrow(length = grid::unit(0.16 * size, "cm"),
                                 type = "closed"),
             colour = COMPASS$color, linewidth = 0.5 * size),
    annotate("text", x = label[1], y = label[2], label = "N",
             fontface = "bold", size = fontsize / 2.845,
             colour = COMPASS$color))
}


text_face <- function(bold, italic) {
  # ggplot2 element_text face: bold/italic combinations (no underline).
  if (isTRUE(bold) && isTRUE(italic)) "bold.italic"
  else if (isTRUE(bold)) "bold"
  else if (isTRUE(italic)) "italic"
  else "plain"
}

main <- function() {
  p <- build_map()
  ggsave(OUTPUT_FILE, plot = p, width = FIGSIZE[1], height = FIGSIZE[2],
         dpi = DPI, bg = "white", limitsize = FALSE)
  message("Saved ", OUTPUT_FILE)
}

main()
