

# ------------------- pre-made functions (identical for every export) -----

import functools
import importlib
import io
import math
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve


def ensure_dependencies():
    """Stop with the command that installs any missing package - or, when
    run with --install-deps, install them with pip into this interpreter.
    Nothing is installed unless you ask."""
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
    command = [sys.executable, "-m", "pip", "install", *missing]
    if "--install-deps" not in sys.argv[1:]:
        raise SystemExit(
            "This script needs " + ", ".join(missing) + ". Install with:\n"
            "    " + " ".join(command) + "\n"
            "or rerun it with --install-deps to install them automatically.")
    print("Installing missing packages: " + ", ".join(missing) + " ...")
    try:
        subprocess.check_call(command)
    except Exception as exc:  # no pip, offline, no permission, ...
        raise SystemExit(
            "Could not install " + ", ".join(missing) + " (" + str(exc)
            + ").\nInstall them yourself, then rerun:\n    "
            + " ".join(command))
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
from matplotlib.patches import Polygon, Rectangle
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
Z_SCALE_BAR = 4.0
BASEMAP_ARCHIVES = {
    "relief": (("50m", "raster", "NE1_50M_SR_W"), "ne1_world.jpg"),
    "relief_alt": (("50m", "raster", "NE2_50M_SR_W"), "ne2_world.jpg"),
    "relief_grey": (("50m", "raster", "GRAY_50M_SR_W"), "gray_world.jpg"),
    "blue_marble": (("50m", "raster", "HYP_50M_SR_W"), "hyp_world.jpg"),
}
BASEMAP_IMG_SIZE = (5400, 2700)
WARP_GRID = (1600, 800)


def download_archive(scale, category, name):
    """Download a Natural Earth zip (cached next to this script).

    The download lands under a .part name and is renamed once complete, so
    an interrupted one is never mistaken for a finished zip; a damaged zip
    already in the cache is fetched again."""
    cache = SCRIPT_DIR / "naturalearth_cache"
    cache.mkdir(exist_ok=True)
    stem = name if category == "raster" else f"ne_{scale}_{name}"
    zip_path = cache / f"{stem}.zip"
    if zip_path.exists() and not zipfile.is_zipfile(zip_path):
        print(f"Re-downloading the damaged {zip_path.name}")
        zip_path.unlink()
    if not zip_path.exists():
        url = (f"https://naturalearth.s3.amazonaws.com/"
               f"{scale}_{category}/{stem}.zip")
        part = zip_path.with_name(zip_path.name + ".part")
        print(f"Downloading {url}")
        urlretrieve(url, part)
        part.replace(zip_path)
    return zip_path


def extract_archive(zip_path, folder, wanted):
    """Unzip every file of *zip_path* flat into *folder*, unless *wanted* is
    already there. It unpacks into a scratch folder that is renamed into
    place at the end, so a failed extraction never looks finished."""
    if (folder / wanted).exists():
        return folder
    scratch = folder.with_name(folder.name + ".part")
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir()
    with zipfile.ZipFile(zip_path) as archive:
        for entry in archive.namelist():
            base = Path(entry).name
            if base and not entry.endswith("/"):
                (scratch / base).write_bytes(archive.read(entry))
    shutil.rmtree(folder, ignore_errors=True)
    scratch.replace(folder)
    return folder


def load_natural_earth(name, category, scale, member=None):
    """Load a Natural Earth vector layer, downloading it if needed."""
    zip_path = download_archive(scale, category, name)
    stem = f"ne_{scale}_{name}"
    shp = f"{member or stem}.shp"
    folder = extract_archive(zip_path, zip_path.parent / stem, shp)
    gdf = gpd.read_file(folder / shp)
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

@functools.lru_cache(maxsize=None)
def _transformer():
    # Built once: a fine graticule alone projects hundreds of lines.
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", MAP_CRS, always_xy=True)


def proj_forward(lons, lats, clamp=True):
    """Project lon/lat arrays into map coordinates, like the app: wrap
    longitudes around a regional centre, clamp into the projection's
    usable band (or, with clamp=False, NaN out what lies outside it), and
    NaN out the globe's far hemisphere."""
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    if MAP_CRS is None:
        return lons, lats
    lon_0, halfspan = PROJ["lon_0"], PROJ["lon_halfspan"]
    if halfspan < 180.0:
        lons = lon_0 + ((lons - lon_0 + 180.0) % 360.0) - 180.0
    if not clamp:
        outside = (lats < PROJ["min_lat"]) | (lats > PROJ["max_lat"])
        if halfspan < 180.0:
            outside |= np.abs(lons - lon_0) > halfspan
        lons = np.where(outside, np.nan, lons)
        lats = np.where(outside, np.nan, lats)
    else:
        lats = np.clip(lats, PROJ["min_lat"], PROJ["max_lat"])
        if halfspan < 180.0:
            lons = np.clip(lons, lon_0 - halfspan, lon_0 + halfspan)
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
    # Newer geopandas names the axes after the CRS; the map has no labels.
    ax.set_xlabel("")
    ax.set_ylabel("")


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
            # Markers outside a regional projection are dropped, not
            # stacked along its edge.
            xs, ys = proj_forward(gdf.geometry.x.to_numpy(),
                                  gdf.geometry.y.to_numpy(), clamp=False)
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
        return f"{abs(value):g}\N{DEGREE SIGN}"
    return f"{abs(value):g}\N{DEGREE SIGN}{'W' if value < 0 else 'E'}"


def format_lat(value, _pos=None):
    if value == 0:
        return "0\N{DEGREE SIGN}"
    return f"{abs(value):g}\N{DEGREE SIGN}{'S' if value < 0 else 'N'}"


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
            # Across the region around its centre, so a regional
            # projection never wraps part of the line to its far edge.
            span = PROJ["lon_halfspan"]
            lons = PROJ["lon_0"] + np.linspace(-span, span, 181)
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
                              points["y"].to_numpy(), clamp=False)
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


# ------------------------------------------------- compass and scale bar

METRES_PER_MILE = 1609.344
_NICE = (1.0, 2.0, 3.0, 5.0)
# Half the width of the triangle compass at size 1, in axes fraction, and
# of the arrow's bold "N", in ems.
COMPASS_TRIANGLE_HALF_WIDTH = 0.016
COMPASS_N_HALF_WIDTH_EM = 0.425


@functools.lru_cache(maxsize=None)
def _geod():
    from pyproj import Geod

    return Geod(ellps="WGS84")


def proj_inverse(xs, ys):
    """Map coordinates back to lon/lat (non-finite where undefined)."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if MAP_CRS is None:
        return xs, ys
    with np.errstate(all="ignore"):
        return _transformer().transform(xs, ys, direction="INVERSE")


def ground_distance(x0, y0, x1, y1):
    """Metres on the WGS84 ellipsoid between two points in map coordinates.

    Axis units are degrees on the plain lon/lat projection and metres on a
    projected CRS, and a projected metre is not a ground metre anyway - so
    this measures from lon/lat, which is right for every projection.
    """
    lons, lats = proj_inverse(np.array([x0, x1]), np.array([y0, y1]))
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    if not np.isfinite(lons).all() or not np.isfinite(lats).all():
        return float("nan")
    _, _, metres = _geod().inv(lons[0], lats[0], lons[1], lats[1])
    return abs(float(metres))


def unit_metres(units):
    return METRES_PER_MILE if units == "mi" else 1000.0


def nice_length(metres, units):
    """A round bar length, in metres, at or just below *metres*."""
    per_unit = unit_metres(units)
    value = metres / per_unit
    if not math.isfinite(value) or value <= 0:
        return 0.0
    decade = 10.0 ** math.floor(math.log10(value))
    for candidate in reversed(_NICE):
        if candidate * decade <= value:
            return candidate * decade * per_unit
    return _NICE[-1] * decade / 10.0 * per_unit


def format_length(metres, units):
    """A bar's label. A metric bar under a kilometre is labelled in metres."""
    if units != "mi" and metres < 1000.0:
        return "%g m" % metres
    value = metres / unit_metres(units)
    text = ("%g" % value) if value >= 1 else ("%.3g" % value)
    return text + (" mi" if units == "mi" else " km")


def corner_anchor(corner, pad=0.03):
    vertical, horizontal = (corner or "lower left").split()
    x = pad if horizontal == "left" else 1.0 - pad
    y = pad if vertical == "lower" else 1.0 - pad
    return x, y


def axes_to_data(ax, fx, fy):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    return x0 + (x1 - x0) * fx, y0 + (y1 - y0) * fy


def span_metres(ax, fx0, fx1, fy):
    ax0, ay = axes_to_data(ax, fx0, fy)
    ax1, _ = axes_to_data(ax, fx1, fy)
    return ground_distance(ax0, ay, ax1, ay)


def scale_reference_row(ax, fy):
    """An axes row where the scale can actually be measured: a corner of a
    Robinson or orthographic map lies outside the map itself."""
    for step in (0.0, 0.25, 0.5, 0.75, 1.0):
        row = fy + (0.5 - fy) * step
        if np.isfinite(span_metres(ax, 0.45, 0.55, row)):
            return row
    return 0.5


def estimate_scale(ax, fx, fy):
    """Ground metres per unit of axes x-fraction near *fx* - a first guess,
    refined against the bar's real endpoints below."""
    left = float(np.clip(fx - 0.05, 0.0, 0.9))
    metres = span_metres(ax, left, left + 0.1, fy)
    if not np.isfinite(metres) or metres <= 0:
        metres = span_metres(ax, 0.45, 0.55, fy)
    if not np.isfinite(metres) or metres <= 0:
        return float("nan")
    return metres / 0.1


def draw_compass(ax):
    if not COMPASS["show"]:
        return
    x, y = corner_anchor(COMPASS["position"], pad=0.025)
    size = max(float(COMPASS["size"]), 0.1)
    color = COMPASS["color"]
    triangle = COMPASS["style"] == "triangle"
    fontsize = (10 if triangle else 11) * size
    # North is up the page in every corner: the head (or tip) sits *reach*
    # above the "N". In a top corner the head is at the anchor and the
    # compass hangs below it; in a bottom corner the "N" rests on the
    # anchor, lifted by half its height (in points, as fonts are).
    reach = 0.07 * size
    top = y if y > 0.5 else y + reach
    lift = 0.0 if y > 0.5 else 0.5 * fontsize
    # Grown past size 1, the compass grows inwards, so its outer edge stays
    # where size 1 puts it, inside the map.
    inwards = -1.0 if x > 0.5 else 1.0
    growth = max(size - 1.0, 0.0)
    shift = 0.0
    if triangle:
        x += inwards * COMPASS_TRIANGLE_HALF_WIDTH * growth
    else:
        shift = inwards * COMPASS_N_HALF_WIDTH_EM * 11 * growth
    coords = ax.transAxes + mtransforms.ScaledTranslation(
        shift / 72, lift / 72, ax.figure.dpi_scale_trans)
    if triangle:
        half = COMPASS_TRIANGLE_HALF_WIDTH * size
        label_y = top - reach
        base = label_y + 0.02 * size
        ax.add_patch(Polygon(
            [(x, top), (x - half, base), (x + half, base)], closed=True,
            transform=coords, facecolor=color, edgecolor="white",
            linewidth=0.8 * size, zorder=Z_COMPASS, clip_on=False))
        ax.text(x, label_y, "N", transform=coords, ha="center",
                va="center", fontsize=fontsize, fontweight="bold",
                color=color, path_effects=LABEL_HALO, zorder=Z_COMPASS,
                clip_on=False)
        return
    ax.annotate(
        "N", xy=(x, top), xytext=(x, top - reach),
        xycoords=coords, textcoords=coords,
        ha="center", va="center", fontsize=fontsize, fontweight="bold",
        color=color, path_effects=LABEL_HALO, zorder=Z_COMPASS,
        annotation_clip=False,
        arrowprops=dict(arrowstyle="-|>,head_width=0.28,head_length=0.55",
                        color=color, linewidth=1.4 * size,
                        shrinkA=6 * size, shrinkB=0))


BAR_HEIGHT = 0.011
BAR_GAP = 0.005
LABEL_GAP = 0.012
LABEL_ROOM = 0.030


def fit_bar_width(ax, metres, x, row, right_anchored):
    """The axes-fraction width a bar of *metres* needs, or None when no
    honest bar of that length fits.

    The first guess is a short local sample, but a scale bar is long and the
    map scale varies across it, so the width is refined against the bar's own
    endpoints until the drawing really is the length its label claims.
    """
    per_fraction = estimate_scale(ax, x, row)
    if not np.isfinite(per_fraction) or per_fraction <= 0:
        return None
    width = metres / per_fraction
    for _ in range(6):
        if not np.isfinite(width) or width <= 0 or width > 0.95:
            return None
        x0 = x - width if right_anchored else x
        actual = span_metres(ax, x0, x0 + width, row)
        if not np.isfinite(actual) or actual <= 0:
            # The bar's own span is off the map - a corner of an orthographic
            # globe, or outside a Robinson ellipse. Refine against the same
            # width centred on the reference row instead.
            actual = span_metres(ax, 0.5 - width / 2, 0.5 + width / 2, row)
        if not np.isfinite(actual) or actual <= 0:
            break
        adjust = metres / actual
        if abs(adjust - 1.0) < 0.001:
            break
        width *= adjust
    if not np.isfinite(width) or width <= 0 or width > 0.95:
        return None
    return width


def draw_scale_bar(ax):
    """A geodesically measured scale bar, drawn in axes-fraction coordinates
    so it keeps its place at any figure size."""
    opts = SCALE_BAR
    if not opts["show"]:
        return
    units = ["km", "mi"] if opts["units"] == "both" else [opts["units"]]
    dragged = opts["anchor_x"] is not None and opts["anchor_y"] is not None
    if dragged:
        x, y = opts["anchor_x"], opts["anchor_y"]
    else:
        x, y = corner_anchor(opts["position"])
    right_anchored = x > 0.5 and not dragged
    top_anchored = y > 0.5 and not dragged

    n = len(units)
    stack = n * BAR_HEIGHT + (n - 1) * BAR_GAP
    base_y = y - stack if top_anchored else y
    # A second unit is labelled underneath, so lift the stack off the frame.
    if n > 1 and not top_anchored and not dragged:
        base_y += LABEL_ROOM

    # Each unit gets its own round length, so "3000 km" is never paired with
    # an unreadable "1864 mi" - two bars, each honest in its own unit, each
    # measured on the row it is actually drawn on.
    bars = []
    for i, unit in enumerate(units):
        y0 = base_y + (n - 1 - i) * (BAR_HEIGHT + BAR_GAP)
        row = scale_reference_row(ax, y0 + BAR_HEIGHT / 2)
        if i == 0 and opts["length_mode"] == "fixed" and opts["fixed_length"]:
            metres = float(opts["fixed_length"]) * unit_metres(opts["units"])
        else:
            estimate = estimate_scale(ax, x, row)
            if not np.isfinite(estimate) or estimate <= 0:
                print("Scale bar: the map scale cannot be measured at "
                      "this view.")
                return
            metres = nice_length(estimate * opts["width"], unit)
        if metres <= 0:
            return
        width = fit_bar_width(ax, metres, x, row, right_anchored)
        if width is None:
            print("Scale bar: scale varies too much across this view to "
                  "draw an accurate bar.")
            return
        bars.append((unit, metres, width, y0))

    for i, (unit, metres, width, y0) in enumerate(bars):
        x0 = x - width if right_anchored else x
        if opts["style"] == "segmented":
            segments = max(int(opts["segments"]), 1)
        else:
            segments = 1
        for seg in range(segments):
            ax.add_patch(Rectangle(
                (x0 + width * seg / segments, y0), width / segments,
                BAR_HEIGHT, transform=ax.transAxes,
                facecolor=opts["color"] if seg % 2 == 0 else "white",
                edgecolor=opts["color"], linewidth=0.8,
                zorder=Z_SCALE_BAR, clip_on=False))
        above = i == 0
        ax.text(x0 + width / 2,
                y0 + BAR_HEIGHT + LABEL_GAP if above else y0 - LABEL_GAP,
                format_length(metres, unit), transform=ax.transAxes,
                ha="center", va="bottom" if above else "top",
                fontsize=opts["fontsize"], color=opts["color"],
                path_effects=LABEL_HALO, zorder=Z_SCALE_BAR, clip_on=False)


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
    """Read one dataset (file or embedded CSV) with numeric lon/lat.

    Every column is read as text, like PyMappr does, so labels such as
    "007", "1.50" or "NA" stay exactly as written and match the styles."""
    as_text = {"dtype": str, "keep_default_na": False}
    if spec["inline_data"] is not None:
        df = pd.read_csv(io.StringIO(spec["inline_data"]), **as_text)
    else:
        path = Path(spec["path"])
        if not path.is_absolute():
            path = SCRIPT_DIR / path
        suffix = path.suffix.lower()
        if suffix in (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls", ".ods"):
            df = pd.read_excel(path, **as_text).fillna("")
        elif suffix in (".tsv", ".txt"):
            df = pd.read_csv(path, sep="\t", **as_text)
        else:
            df = pd.read_csv(path, **as_text)
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
    """The legend label for every row: its group, renamed by label_map."""
    return point_groups(df, spec).map(
        lambda value: spec["label_map"].get(value, value))


def point_groups(df, spec):
    """The group every row belongs to, like PyMappr's grouping rules: the
    value its styles are keyed by, before label_map renames it."""
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
    return raw


def marker_paint(style):
    """(face, edge, edge width): open markers draw only an outline in their
    own colour, filled ones take the POINT_EDGE outline."""
    if style["open"]:
        return "none", style["color"], 1.2
    return style["color"], POINT_EDGE["color"], POINT_EDGE["width"]


def plot_dataset(ax, spec):
    """Scatter one dataset group by group with the app's marker styling:
    filled markers get the POINT_EDGE outline, open markers draw
    outline-only."""
    df = load_points(spec)
    groups = point_groups(df, spec)
    xs, ys = proj_forward(df["_lon"].to_numpy(), df["_lat"].to_numpy())
    offsets = wrap_offsets()
    styles = spec["styles"]
    order = list(dict.fromkeys(list(styles) + sorted(set(groups))))
    for group in order:
        mask = (groups == group).to_numpy()
        if not mask.any():
            continue
        style = styles.get(group, FALLBACK_STYLE)
        px = np.concatenate([xs[mask] + off for off in offsets])
        py = np.tile(ys[mask], len(offsets))
        face, edge, lw = marker_paint(style)
        ax.scatter(px, py, s=style["size"], c=face,
                   marker=style["marker"], zorder=Z_POINTS,
                   edgecolors=edge, linewidths=lw, alpha=POINT_ALPHA)


# ----------------------------------------------------------------- legend

def legend_handle(style, size=None):
    # A None style is a row that takes no swatch.
    if style is None:
        return Line2D([], [], linestyle="", marker="")
    area = style["size"] if size is None else size
    face, edge, edge_w = marker_paint(style)
    return Line2D([], [], linestyle="", marker=style["marker"],
                  markersize=max(np.sqrt(area), 2),
                  markerfacecolor=face, color=style["color"],
                  markeredgecolor=edge, markeredgewidth=edge_w)


def legend_kwargs():
    """The legend keywords shared by both draw paths, from LEGEND."""
    return dict(
        loc=LEGEND["location"], title=LEGEND["title"] or None,
        fontsize=LEGEND["fontsize"], title_fontsize=LEGEND["title_fontsize"],
        ncols=LEGEND["columns"], markerscale=LEGEND["marker_scale"],
        labelspacing=LEGEND["label_spacing"],
        columnspacing=LEGEND["column_spacing"],
        handletextpad=LEGEND["handle_text_pad"],
        handlelength=LEGEND["handle_length"],
        borderpad=LEGEND["border_pad"],
        frameon=LEGEND["frame"], framealpha=LEGEND["frame_alpha"],
        facecolor=LEGEND["frame_color"], edgecolor=LEGEND["frame_edge_color"],
        fancybox=LEGEND["rounded"], shadow=LEGEND["shadow"],
        alignment=LEGEND["title_align"])


def style_legend(fig, leg, header_rows):
    """Apply the LEGEND bold/italic/underline formatting to a legend.

    Entry labels use the label_* flags; the title and section headers use
    the title_* flags (so headers stay bold by default). Underlining is
    drawn under each flagged text on every draw, since matplotlib Text has
    no underline property; it fires on savefig too."""
    if leg is None:
        return
    frame = leg.get_frame()
    if frame is not None:
        frame.set_linewidth(LEGEND["frame_width"])
    underline = []

    def apply(text, role):
        text.set_fontweight("bold" if LEGEND[role + "_bold"] else "normal")
        text.set_fontstyle("italic" if LEGEND[role + "_italic"] else "normal")
        text.set_color(LEGEND[role + "_color"])
        if LEGEND["font_family"]:
            text.set_fontfamily(LEGEND["font_family"])
        if LEGEND[role + "_underline"] and text.get_text().strip():
            underline.append(text)

    title = leg.get_title()
    if title is not None and title.get_text():
        apply(title, "title")
    for i, text in enumerate(leg.get_texts()):
        apply(text, "title" if i in header_rows else "label")
    if not underline:
        return

    def _draw_underlines(event):
        renderer = getattr(event, "renderer", None)
        if renderer is None:
            return
        for text in underline:
            if not text.get_visible() or not text.get_text().strip():
                continue
            try:
                bbox = text.get_window_extent(renderer)
            except Exception:
                continue
            y = bbox.y0 - max(bbox.height * 0.1, 1.0)
            line = Line2D([bbox.x0, bbox.x1], [y, y],
                          transform=mtransforms.IdentityTransform(),
                          color=text.get_color(),
                          linewidth=max(text.get_fontsize() / 11.0, 0.6),
                          solid_capstyle="butt")
            line.set_figure(fig)
            line.draw(renderer)

    fig.canvas.mpl_connect("draw_event", _draw_underlines)


def add_legend(ax):
    """The app's legend: one row per group, or titled sections when the
    map is styled by two attribute columns."""
    # One row per group of every dataset, as in the app: groups that share
    # a label (two datasets' "Sites", or two groups renamed alike) keep a
    # row each, in their own style.
    rows = [(spec["label_map"].get(group, group), style) for spec in DATASETS
            for group, style in spec["styles"].items()]
    if not LEGEND["show"] or not rows:
        return
    if LEGEND_SECTIONS is None:
        if LEGEND_ROWS is not None:
            # LEGEND_ROWS is the whole legend, in order: a group left out of
            # it keeps its points but loses its row. Empty means every row
            # was hidden, which is not the same as "no ordering given".
            rank = {label: i for i, label in enumerate(LEGEND_ROWS)}
            rows = sorted((row for row in rows if row[0] in rank),
                          key=lambda row: rank[row[0]])
        if not rows:
            return
        handles = [legend_handle(style) for _label, style in rows]
        for handle, (label, _style) in zip(handles, rows):
            handle.set_label(label)
        leg = ax.legend(handles=handles, **legend_kwargs())
        style_legend(ax.figure, leg, set())
        return
    handles, labels, header_rows = [], [], []
    indent = " " * LEGEND["indent"]

    def blank():
        return Line2D([], [], linestyle="", marker="")

    def spacer():
        header_rows.append(len(labels))
        handles.append(blank())
        labels.append(" ")

    for section_title, entries in LEGEND_SECTIONS:
        if handles:  # spacer between sections
            spacer()
        if section_title:  # section titles can be turned off entirely
            header_rows.append(len(labels))
            handles.append(blank())
            labels.append(section_title)
        # In a nested key the depth-0 rows head a block of children, so they
        # take the header formatting (bold by default) on top of their
        # swatch - indentation alone reads too weakly when every swatch sits
        # in the same column.
        nested = any(len(entry) > 2 and entry[2] for entry in entries)
        for index, entry in enumerate(entries):
            label, style, *rest = entry
            depth = rest[0] if rest else 0
            if nested and depth == 0:
                if index and LEGEND["group_spacer"]:
                    spacer()  # separate this block from the one before
                if LEGEND["bold_groups"]:
                    header_rows.append(len(labels))
            handles.append(legend_handle(style, size=45))
            labels.append(indent * (depth + 1) + label)
    leg = ax.legend(handles, labels, **legend_kwargs())
    style_legend(ax.figure, leg, set(header_rows))


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
    draw_scale_bar(ax)
    ax.set_xlim(VIEW[0], VIEW[1])
    ax.set_ylim(VIEW[2], VIEW[3])
    add_legend(ax)
    output = SCRIPT_DIR / OUTPUT_FILE
    fig.savefig(output, dpi=DPI, facecolor="white")
    print(f"Saved {output}")
    plt.show()


if __name__ == "__main__":
    main()
