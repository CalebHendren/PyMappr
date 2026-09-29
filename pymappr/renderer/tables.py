"""What the map draws and in which order: the style of every Natural Earth
layer, the z-order of each kind of artist, and the fixed framing values.

Public because the code export (pymappr.codegen) bakes the same values into
the scripts it writes, so an exported map looks like the app's."""

import matplotlib.patheffects as patheffects

# Vector line layers:
# layer key -> (source layer, edge color, width, zorder, linestyle).
# "continents" is the countries layer dissolved by continent; it stands in
# for the countries layer when political borders are switched off.
LINE_LAYERS = {
    "countries": ("countries", "#000000", 0.8, 1.6, "solid"),
    "continents": ("continents", "#000000", 0.8, 1.55, "solid"),
    "sovereignty": ("sovereignty", "#5b2d8b", 0.9, 1.58, "solid"),
    "map_units": ("map_units", "#2d6b8b", 0.6, 1.57, "solid"),
    "subunits": ("subunits", "#8b6b2d", 0.5, 1.56, "solid"),
    "dependencies": ("dependencies", "#c2571a", 0.9, 1.62, "solid"),
    "disputed_lines": ("disputed_lines", "#c0392b", 0.9, 1.65, (0, (4, 2))),
    "maritime": ("maritime", "#3b7bbf", 0.7, 1.3, (0, (5, 3))),
    "eez": ("eez", "#1c5c99", 0.8, 1.31, (0, (1, 2))),
    "timezones": ("timezones", "#8a5fbf", 0.6, 1.35, (0, (6, 3))),
    "states": ("states", "#5a5a5a", 0.5, 1.5, "solid"),
    "counties": ("counties", "#8a8a8a", 0.35, 1.4, "solid"),
    "lakes_outline": ("lakes", "#2d5f8a", 0.6, 1.2, "solid"),
    "rivers": ("rivers", "#4a90c4", 0.5, 1.0, "solid"),
    "wadis": ("wadis", "#b3985c", 0.6, 1.0, (0, (3, 2))),
    "reefs": ("reefs", "#25a08c", 0.7, 1.15, "solid"),
    "regions": ("regions", "#a8763e", 0.5, 1.12, (0, (3, 3))),
    "roads": ("roads", "#b0693c", 0.35, 1.1, "solid"),
}

# Mode fills (lakes/ocean support "none"/"grey"/"blue").
FILL_COLORS = {
    ("lakes", "grey"): "#c9c9c9",
    ("lakes", "blue"): "#a6cae0",
    ("ocean", "grey"): "#dcdcdc",
    ("ocean", "blue"): "#d4e6f4",
}

# Simple on/off fill layers:
# layer key -> (source, facecolor, edgecolor, edge width, alpha, zorder).
FILL_LAYERS = {
    "land": ("land", "#f0ece1", "none", 0.0, 1.0, 0.35),
    "deserts": ("deserts", "#f3e6c0", "none", 0.0, 0.65, 0.52),
    "playas": ("playas", "#efe7c3", "#d8c98a", 0.3, 1.0, 0.55),
    "urban": ("urban", "#d95f4e", "none", 0.0, 0.55, 0.58),
    "parks": ("parks", "#bfe3b4", "#4e9a51", 0.4, 0.85, 0.6),
    "ice_shelves": ("ice_shelves", "#d8ecf7", "#a8cfe6", 0.3, 1.0, 0.61),
    "glaciers": ("glaciers", "#e6f3fb", "#b9d9ec", 0.3, 1.0, 0.62),
    "disputed": ("disputed", "#e8b4b8", "#b03a48", 0.5, 0.75, 0.66),
    # Optional biodiversity / ecoregion overlays (translucent thematic fills).
    "ecoregions": ("ecoregions", "#8fbf6f", "#4e7a3a", 0.25, 0.42, 0.44),
    "marine_ecoregions": ("marine_ecoregions", "#5fa8c4", "#2d6b8b",
                          0.25, 0.42, 0.43),
    "biodiversity": ("biodiversity", "#e0954a", "#a85f16", 0.5, 0.5, 0.53),
}

# Bathymetry: depth in meters -> fill color, shallow to deep. The polygons
# nest, so drawing shallow-to-deep stacks darker blues into the trenches.
BATHYMETRY_COLORS = {
    0: "#e3f2fa", 200: "#d2e9f5", 1000: "#c0dff0", 2000: "#a8d1e8",
    3000: "#8fc2e0", 4000: "#74b2d8", 5000: "#5a9fcd", 6000: "#4489bd",
    7000: "#3273aa", 8000: "#245e94", 9000: "#194a7d", 10000: "#103862",
}
Z_BATHYMETRY = 0.32

# Point-marker layers:
# key -> (source, marker, size, facecolor, edgecolor, zoom bias).
# A feature is shown once ``min_zoom <= zoom + bias`` (min_zoom falls back
# to scalerank for layers without one), so markers fade in while zooming.
POINT_LAYERS = {
    "cities": ("cities", "o", 11.0, "#333333", "white", 2.0),
    "capitals": ("capitals", "*", 60.0, "#b03a2e", "white", 99.0),
    "airports": ("airports", "^", 18.0, "#4757a8", "white", 4.0),
    "ports": ("ports", "v", 16.0, "#1f7a70", "white", 3.5),
}
Z_POINT_LAYERS = 2.45

# Label layers: key -> (source, font kwargs, min zoom, feature bias).
# Once the view is zoomed in at least to *min zoom* (zoom 0 = whole world,
# +1 per 2x magnification), features inside the view are labelled, up to
# the per-layer cap in LAYER_SPECS. Countries use min zoom 0 so every
# country in view is labelled even fully zoomed out. A non-None *feature
# bias* additionally culls per feature: a label is eligible only once its
# ``min_label`` (Natural Earth's curated zoom rank) is <= zoom + bias, so
# e.g. city labels appear gradually, biggest cities first.
LABEL_STYLES = {
    "countries": ("countries", dict(fontsize=9, color="#1a1a1a", fontweight="bold"), 0.0, None),
    "states": ("states", dict(fontsize=8, color="#3a3a3a"), 1.2, None),
    "counties": ("counties", dict(fontsize=6.5, color="#4a4a4a"), 3.6, None),
    "cities": ("cities", dict(fontsize=7.5, color="#222222"), 0.0, 2.0),
    "airports": ("airports", dict(fontsize=6.5, color="#3a4c8c"), 2.0, 3.0),
    "ports": ("ports", dict(fontsize=6.5, color="#14614f", fontstyle="italic"), 2.0, 3.0),
    "lakes": ("lakes", dict(fontsize=7.5, color="#14477a", fontstyle="italic"), 1.5, None),
    "rivers": ("rivers", dict(fontsize=7, color="#14477a", fontstyle="italic"), 1.5, None),
    "regions": ("regions", dict(fontsize=8, color="#7a5230", fontstyle="italic"), 0.5, 3.0),
    "timezones": ("timezones", dict(fontsize=8, color="#6a4a9c"), 0.0, None),
}

LABEL_HALO = [patheffects.withStroke(linewidth=2.2, foreground="white", alpha=0.85)]

Z_SATELLITE = 0.1
Z_OCEAN = 0.3
Z_LAKE_FILL = 0.5
Z_GRID = 1.8
Z_POINTS = 2.6
Z_LABELS = 3.0
Z_COMPASS = 4.0
Z_SCALE_BAR = 4.0

# Axes margins as figure fractions. Public: the code export bakes the same
# values into the script it writes, so an exported map keeps the app's framing.
MARGINS_WITH_TICKS = (0.055, 0.045, 0.99, 0.99)   # left, bottom, right, top
MARGINS_PLAIN = (0.01, 0.012, 0.99, 0.988)

# Map orientation -> target width:height for the map axes box. "landscape"
# is None, meaning the map fills the whole canvas (the original behaviour);
# "portrait" constrains it to a tall box, centered with blank side margins,
# so tall regions (e.g. South America) fill the frame instead of floating in
# a band of ocean. The value is the inverse of the ~9:6.5 default figure so
# portrait reads as the page simply turned on its side.
_PORTRAIT_ASPECT = 6.5 / 9.0
ORIENTATION_ASPECT = {"landscape": None, "portrait": _PORTRAIT_ASPECT}
