"""Download and prepare the Natural Earth map data bundled with PyMappr.

Run once before starting the app from source, and as part of every packaged
build. All data is public domain (naturalearthdata.com). Downloads are cached
in data/downloads/ so re-runs are cheap; use --force to rebuild outputs.

Produces:
    data/shapes/<layer>/<layer>.shp (+ .shx/.dbf/.prj)   vector layers
    data/basemap/ne1_world.jpg                            "Satellite" basemap
    data/icon/pymappr.ico                                  application icon
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Mirrors tried in order: the official S3 bucket, then the NACIS CDN.
MIRRORS = [
    "https://naturalearth.s3.amazonaws.com/{scale}_{category}/{name}.zip",
    "https://naciscdn.org/naturalearth/{scale}/{category}/{name}.zip",
]

# (scale, category, archive name[, probe shapefile]) - the probe is the
# shapefile checked to decide whether the layer is already extracted; it
# defaults to "<archive name>.shp" and only multi-shapefile archives (parks,
# bathymetry) need to name one member explicitly.
VECTOR_LAYERS = [
    # Core political layers, in three resolutions for zoom-dependent detail.
    ("110m", "cultural", "ne_110m_admin_0_countries"),
    ("50m", "cultural", "ne_50m_admin_0_countries"),
    ("10m", "cultural", "ne_10m_admin_0_countries"),
    ("10m", "cultural", "ne_10m_admin_1_states_provinces"),
    ("10m", "cultural", "ne_10m_admin_2_counties"),
    # Alternate admin-0 views: sovereignty, map units, subunits.
    ("50m", "cultural", "ne_50m_admin_0_sovereignty"),
    ("50m", "cultural", "ne_50m_admin_0_map_units"),
    ("50m", "cultural", "ne_50m_admin_0_map_subunits"),
    # Boundary detail: disputed areas/lines and 200-nm maritime indicators.
    ("10m", "cultural", "ne_10m_admin_0_disputed_areas"),
    ("10m", "cultural", "ne_10m_admin_0_boundary_lines_disputed_areas"),
    ("10m", "cultural", "ne_10m_admin_0_boundary_lines_maritime_indicator"),
    # Cultural point/polygon layers.
    ("10m", "cultural", "ne_10m_populated_places_simple"),
    ("10m", "cultural", "ne_10m_urban_areas"),
    ("10m", "cultural", "ne_10m_airports"),
    ("10m", "cultural", "ne_10m_ports"),
    ("10m", "cultural", "ne_10m_parks_and_protected_lands",
     "ne_10m_parks_and_protected_lands_area.shp"),
    ("10m", "cultural", "ne_10m_time_zones"),
    ("10m", "cultural", "ne_10m_roads"),
    # Water, in three resolutions where useful.
    ("110m", "physical", "ne_110m_lakes"),
    ("50m", "physical", "ne_50m_lakes"),
    ("10m", "physical", "ne_10m_lakes"),
    ("110m", "physical", "ne_110m_rivers_lake_centerlines"),
    ("50m", "physical", "ne_50m_rivers_lake_centerlines"),
    ("10m", "physical", "ne_10m_rivers_lake_centerlines"),
    ("110m", "physical", "ne_110m_ocean"),
    ("50m", "physical", "ne_50m_ocean"),
    ("10m", "physical", "ne_10m_ocean"),
    ("110m", "physical", "ne_110m_land"),
    ("50m", "physical", "ne_50m_land"),
    ("10m", "physical", "ne_10m_land"),
    # Physical features.
    ("10m", "physical", "ne_10m_glaciated_areas"),
    ("50m", "physical", "ne_50m_antarctic_ice_shelves_polys"),
    ("10m", "physical", "ne_10m_bathymetry_all",
     "ne_10m_bathymetry_L_0.shp"),
    ("10m", "physical", "ne_10m_reefs"),
    ("10m", "physical", "ne_10m_playas"),
    ("10m", "physical", "ne_10m_geography_regions_polys"),
]

RASTER = ("50m", "raster", "NE1_50M_SR_W")
RASTER_TIF = "NE1_50M_SR_W/NE1_50M_SR_W.tif"
BASEMAP_JPG = DATA_DIR / "basemap" / "ne1_world.jpg"
BASEMAP_SIZE = (5400, 2700)

SHAPE_EXTS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}


def download(scale: str, category: str, name: str, dest: Path,
             retries: int = 3) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached   {dest.name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_exc: Exception | None = None
    for mirror in MIRRORS:
        url = mirror.format(scale=scale, category=category, name=name)
        for attempt in range(retries):
            try:
                print(f"  fetching {url}")
                tmp = dest.with_suffix(".part")
                with urllib.request.urlopen(url, timeout=120) as resp, \
                        open(tmp, "wb") as out:
                    while chunk := resp.read(1 << 20):
                        out.write(chunk)
                tmp.rename(dest)
                return dest
            except Exception as exc:  # noqa: BLE001 - retry any network failure
                last_exc = exc
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  retry in {wait}s ({exc})")
                    time.sleep(wait)
                else:
                    print(f"  mirror failed ({exc})")
    raise RuntimeError(f"all mirrors failed for {name}: {last_exc}")


def fetch_vectors(force: bool) -> None:
    for scale, category, name, *probe in VECTOR_LAYERS:
        probe_shp = probe[0] if probe else f"{name}.shp"
        out_dir = DATA_DIR / "shapes" / name
        if (out_dir / probe_shp).exists() and not force:
            print(f"  ready    {name}")
            continue
        zip_path = download(scale, category, name,
                            DATA_DIR / "downloads" / f"{name}.zip")
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                suffix = Path(member).suffix.lower()
                if suffix in SHAPE_EXTS and not member.endswith("/"):
                    target = out_dir / Path(member).name
                    target.write_bytes(zf.read(member))
        print(f"  ready    {name}")


def fetch_basemap(force: bool) -> None:
    if BASEMAP_JPG.exists() and not force:
        print(f"  ready    {BASEMAP_JPG.name}")
        return
    from PIL import Image

    scale, category, name = RASTER
    zip_path = download(scale, category, name,
                        DATA_DIR / "downloads" / f"{name}.zip")
    print("  converting raster to JPEG basemap (this can take a minute)...")
    with zipfile.ZipFile(zip_path) as zf:
        tif_name = next(
            (m for m in zf.namelist() if m.lower().endswith(".tif")), None
        )
        if tif_name is None:
            raise RuntimeError(f"no .tif found inside {zip_path.name}")
        with zf.open(tif_name) as fh:
            img = Image.open(io.BytesIO(fh.read()))
            img.load()
    img = img.convert("RGB").resize(BASEMAP_SIZE, Image.LANCZOS)
    BASEMAP_JPG.parent.mkdir(parents=True, exist_ok=True)
    img.save(BASEMAP_JPG, "JPEG", quality=85)
    print(f"  ready    {BASEMAP_JPG.name}")


def make_icon(force: bool) -> None:
    """Draw a simple globe-with-pin application icon."""
    ico_path = DATA_DIR / "icon" / "pymappr.ico"
    if ico_path.exists() and not force:
        print(f"  ready    {ico_path.name}")
        return
    from PIL import Image, ImageDraw

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Globe
    m = 20
    d.ellipse([m, m, size - m, size - m], fill=(38, 118, 200, 255),
              outline=(20, 60, 110, 255), width=8)
    # Graticule arcs
    cx = size // 2
    for off in (55, 105):
        d.arc([cx - off, m, cx + off, size - m], 0, 360,
              fill=(220, 235, 250, 220), width=6)
    for off in (55, 105):
        d.arc([m, cx - off, size - m, cx + off], 0, 360,
              fill=(220, 235, 250, 220), width=6)
    # Pin
    d.ellipse([150, 40, 230, 120], fill=(226, 61, 45, 255),
              outline=(140, 30, 20, 255), width=6)
    d.polygon([(158, 100), (222, 100), (190, 185)], fill=(226, 61, 45, 255))
    d.ellipse([172, 62, 208, 98], fill=(255, 255, 255, 255))

    ico_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                              (128, 128), (256, 256)])
    print(f"  ready    {ico_path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="rebuild outputs even if they already exist")
    args = parser.parse_args()

    print("Vector layers:")
    fetch_vectors(args.force)
    print("Basemap raster:")
    fetch_basemap(args.force)
    print("App icon:")
    make_icon(args.force)
    print("Done. Data ready in", DATA_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
