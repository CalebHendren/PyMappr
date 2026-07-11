"""Download and prepare the map data bundled with PyMappr.

Run once before starting the app from source, and as part of every packaged
build. The core layers are public domain (naturalearthdata.com); a handful of
optional biodiversity / ecoregion overlays come from other openly licensed
sources (RESOLVE, Conservation International, WWF/TNC - see EXTRA_LAYERS).
Downloads are cached in data/downloads/ so re-runs are cheap; use --force to
rebuild outputs and --skip-extras to skip the optional overlays.

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

# Optional biodiversity / ecoregion overlays from external, openly licensed
# sources (the same datasets SimpleMappr uses, in their open-licensed forms).
# These are extras: unlike the Natural Earth core, a failure to fetch one is
# non-fatal and PyMappr simply runs without that layer.
#
# Each entry: (output dir under data/shapes/, source, member, credit) where
# *source* is ("direct", url) for a plain zip, or ("zenodo", record_id) to
# resolve the newest .zip via the Zenodo API, and *member* is the basename of
# the shapefile inside the archive (None = the first .shp found). The chosen
# shapefile is renamed to "<output dir>.shp" so the layer store finds it.
EXTRA_LAYERS = [
    ("ecoregions_2017",
     ("direct", "https://storage.googleapis.com/teow2016/Ecoregions2017.zip"),
     "Ecoregions2017",
     "RESOLVE Ecoregions 2017 (Dinerstein et al. 2017), CC-BY 4.0"),
    ("biodiversity_hotspots",
     ("zenodo", "3261807"),
     None,
     "Conservation International Biodiversity Hotspots (2016.1), CC-BY"),
    ("marine_ecoregions",
     ("direct",
      "https://hub.arcgis.com/api/download/v1/items/"
      "903c3ae05b264c00a3b5e58a4561b7e6/shapefile?redirect=true&layers=0"),
     None,
     "WWF/TNC Marine Ecoregions of the World (MEOW), CC-BY 4.0"),
]

_ZIP_MAGIC = b"PK\x03\x04"


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


def _http_bytes(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "PyMappr-fetch-data"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _resolve_zenodo(record_id: str) -> str:
    """Resolve a Zenodo record to the download URL of its (first) .zip file.

    Resolving at fetch time keeps us robust to filename changes and needs no
    login - Zenodo serves records openly."""
    import json

    api = f"https://zenodo.org/api/records/{record_id}"
    data = json.loads(_http_bytes(api, timeout=60).decode("utf-8"))
    files = data.get("files", [])
    zips = [f for f in files if str(f.get("key", "")).lower().endswith(".zip")]
    chosen = (zips or sorted(files, key=lambda f: f.get("size", 0),
                             reverse=True))
    if not chosen:
        raise RuntimeError(f"Zenodo record {record_id} has no downloadable files")
    links = chosen[0].get("links", {})
    url = links.get("self") or links.get("download")
    if not url:
        raise RuntimeError(f"Zenodo record {record_id}: no file link")
    return url


def _source_url(source: tuple[str, str]) -> str:
    kind, ref = source
    if kind == "direct":
        return ref
    if kind == "zenodo":
        return _resolve_zenodo(ref)
    raise RuntimeError(f"unknown source kind: {kind}")


def _extract_extra(zip_bytes: bytes, out_dir: Path, target: str,
                   member: str | None) -> None:
    """Extract one shapefile (and its siblings) from *zip_bytes*, renaming it
    to ``<target>.<ext>`` so the layer store finds ``<target>/<target>.shp``."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        shps = [n for n in names if n.lower().endswith(".shp")]
        if not shps:
            raise RuntimeError("no .shp inside archive")
        chosen = None
        if member is not None:
            chosen = next((n for n in shps
                           if Path(n).stem.lower() == member.lower()), None)
        chosen = chosen or shps[0]
        stem = Path(chosen).stem
        out_dir.mkdir(parents=True, exist_ok=True)
        wrote_shp = False
        for name in names:
            path = Path(name)
            if path.stem == stem and path.suffix.lower() in SHAPE_EXTS:
                (out_dir / f"{target}{path.suffix.lower()}").write_bytes(
                    zf.read(name))
                wrote_shp = wrote_shp or path.suffix.lower() == ".shp"
        if not wrote_shp:
            raise RuntimeError("archive missing shapefile components")


def fetch_extras(force: bool) -> None:
    """Download the optional biodiversity / ecoregion overlays. Failures are
    reported but never abort the run - these datasets are optional."""
    for target, source, member, credit in EXTRA_LAYERS:
        out_dir = DATA_DIR / "shapes" / target
        if (out_dir / f"{target}.shp").exists() and not force:
            print(f"  ready    {target}")
            continue
        try:
            url = _source_url(source)
            print(f"  fetching {url.split('?', 1)[0]}")
            payload = _http_bytes(url)
            if not payload.startswith(_ZIP_MAGIC):
                raise RuntimeError("download was not a ZIP archive "
                                   "(source may require manual download)")
            _extract_extra(payload, out_dir, target, member)
            print(f"  ready    {target}  [{credit}]")
        except Exception as exc:  # noqa: BLE001 - optional layers are best-effort
            print(f"  SKIPPED  {target}: {exc}")
            print(f"           (optional - {credit})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="rebuild outputs even if they already exist")
    parser.add_argument("--skip-extras", action="store_true",
                        help="skip the optional biodiversity/ecoregion layers")
    args = parser.parse_args()

    print("Vector layers:")
    fetch_vectors(args.force)
    print("Basemap raster:")
    fetch_basemap(args.force)
    print("App icon:")
    make_icon(args.force)
    if not args.skip_extras:
        print("Optional biodiversity & ecoregion layers:")
        fetch_extras(args.force)
    print("Done. Data ready in", DATA_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
