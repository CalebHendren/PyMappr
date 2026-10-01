

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
  } else if (grepl("\\.(tsv|txt)$", tolower(spec$path))) {
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
  tif <- list.files(folder, pattern = "\\.tif$", full.names = TRUE,
                    recursive = TRUE)[1]
  tidyterra::geom_spatraster_rgb(data = terra::rast(tif))
}

lon_label <- function(value) {
  value <- ((value + 180) %% 360) - 180
  ifelse(value %in% c(0, 180, -180), sprintf("%g\u00b0", abs(value)),
         sprintf("%g\u00b0%s", abs(value),
                 ifelse(value < 0, "W", "E")))
}

lat_label <- function(value) {
  ifelse(value == 0, "0\u00b0",
         sprintf("%g\u00b0%s", abs(value), ifelse(value < 0, "S", "N")))
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
              alpha = POINT_ALPHA, stroke = POINT_STROKE) +
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
  p <- p + scale_bar_layers() + compass_layers()
  p <- p + theme_void() + theme(
    panel.background = element_rect(fill = "white", color = NA),
    plot.background = element_rect(fill = "white", color = NA),
    panel.grid.major = grid_line,
    axis.text = axis_text,
    axis.ticks = element_blank(),
    legend.text = element_text(size = LEGEND$fontsize,
                               face = text_face(LEGEND$label_bold,
                                                LEGEND$label_italic)),
    legend.title = element_text(size = LEGEND$title_fontsize,
                                face = text_face(LEGEND$title_bold,
                                                 LEGEND$title_italic)),
    # Approximates matplotlib's labelspacing (vertical gap per entry).
    legend.key.height = grid::unit(1 + LEGEND$label_spacing, "lines"),
    legend.position = if (LEGEND$show) legend_position(LEGEND$location)
                      else "none",
    legend.background = if (LEGEND$frame)
      element_rect(fill = grDevices::adjustcolor("white", 0.85),
                   color = "#999999") else element_blank())
  p
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

compass_layers <- function() {
  if (!isTRUE(COMPASS$show)) return(list())
  anchor <- corner_anchor(COMPASS$position, pad = 0.025)
  x <- anchor[1]
  y <- anchor[2]
  size <- max(COMPASS$size, 0.1)
  reach <- 0.07 * size
  # The arrow runs downwards from the anchor at the top of the map and
  # upwards at the bottom, so it never points off the panel.
  tail_y <- if (y > 0.5) y - reach else y + reach
  tip <- axes_to_data(x, y)
  tail <- axes_to_data(x, tail_y)
  if (identical(COMPASS$style, "triangle")) {
    half <- 0.016 * size
    up <- y > tail_y
    base_y <- tail_y + (if (up) 0.02 * size else -0.02 * size)
    b1 <- axes_to_data(x - half, base_y)
    b2 <- axes_to_data(x + half, base_y)
    return(list(
      annotate("polygon", x = c(tip[1], b1[1], b2[1]),
               y = c(tip[2], b1[2], b2[2]), fill = COMPASS$color,
               colour = "white", linewidth = 0.28 * size),
      annotate("text", x = tail[1], y = tail[2], label = "N",
               fontface = "bold", size = 10 * size / 2.845,
               colour = COMPASS$color)))
  }
  # Start the shaft clear of the "N", the way the app's shrinkA does.
  shrink <- 0.014 * size
  start_y <- tail_y + sign(y - tail_y) * shrink
  start <- axes_to_data(x, start_y)
  list(
    annotate("segment", x = start[1], y = start[2],
             xend = tip[1], yend = tip[2],
             arrow = grid::arrow(length = grid::unit(0.16 * size, "cm"),
                                 type = "closed"),
             colour = COMPASS$color, linewidth = 0.5 * size),
    annotate("text", x = tail[1], y = tail[2], label = "N",
             fontface = "bold", size = 11 * size / 2.845,
             colour = COMPASS$color))
}


legend_position <- function(location) {
  # PyMappr legend locations approximated by ggplot2 sides.
  if (location %in% c("upper left", "lower left")) "left" else "right"
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
