"""Generate the sample_data/gallery CSVs behind the README's publication
gallery maps, and sample_data/asia_hornbills.csv behind its app screenshots.

    python scripts/make_gallery_data.py

The records are invented, not field data: each species is scattered through a
few hand-placed ellipses roughly where it lives, and every point is rejected
unless it lands inside the target land (or, for sea turtles, coastal water).
The RNG is seeded, so a rerun reproduces the files exactly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import box
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parent.parent
SHAPES = REPO_ROOT / "data" / "shapes"
SAMPLES = REPO_ROOT / "sample_data"
OUT = SAMPLES / "gallery"

SEED = 20261003


def _read(name: str) -> gpd.GeoDataFrame:
    return gpd.read_file(next((SHAPES / name).glob("*.shp")))


def countries(*names: str):
    gdf = _read("ne_10m_admin_0_countries")
    col = "NAME" if "NAME" in gdf else "name"
    found = gdf[gdf[col].isin(names)]
    missing = set(names) - set(found[col])
    if missing:
        raise SystemExit(f"countries not found: {sorted(missing)}")
    return unary_union(found.geometry)


def state(name: str):
    gdf = _read("ne_10m_admin_1_states_provinces")
    col = "name" if "name" in gdf else "NAME"
    found = gdf[(gdf[col] == name)
                & (gdf["admin"].str.contains("United States"))]
    if found.empty:
        raise SystemExit(f"state not found: {name}")
    return unary_union(found.geometry)


def land():
    return unary_union(_read("ne_50m_land").geometry)


def coastal_water(width: float = 2.0):
    """Sea within *width* degrees of land: where sea turtles are recorded."""
    ld = land()
    return ld.buffer(width).difference(ld)


def sample(rng, mask, ellipses, n: int):
    """*n* points from the union of *ellipses* (cx, cy, rx, ry[, angle])
    that fall inside *mask*; the ellipses are sampled in proportion to
    their area so a big range is not bunched into a small one."""
    weights = np.array([e[2] * e[3] for e in ellipses], dtype=float)
    weights /= weights.sum()
    shapely.prepare(mask)
    points: list[tuple[float, float]] = []
    attempts = 0
    while len(points) < n:
        attempts += 1
        if attempts > 20000:
            raise RuntimeError(f"cannot place {n} points: {ellipses[:1]}")
        cx, cy, rx, ry, *ang = ellipses[rng.choice(len(ellipses), p=weights)]
        radius, theta = np.sqrt(rng.random()), rng.random() * 2 * np.pi
        dx, dy = rx * radius * np.cos(theta), ry * radius * np.sin(theta)
        if ang:
            a = np.radians(ang[0])
            dx, dy = (dx * np.cos(a) - dy * np.sin(a),
                      dx * np.sin(a) + dy * np.cos(a))
        lon, lat = cx + dx, cy + dy
        if shapely.contains_xy(mask, lon, lat):
            points.append((round(float(lat), 5), round(float(lon), 5)))
    return points


def build() -> dict[str, list[tuple[str, str, float, float]]]:
    rng = np.random.default_rng(SEED)
    maps: dict[str, list] = {}

    def add(file, genus, species, mask, ellipses, n):
        rows = maps.setdefault(file, [])
        for lat, lon in sample(rng, mask, ellipses, n):
            rows.append((genus, species, lat, lon))

    world_land = land()
    add("gallery_monarchs", "Danaus", "plexippus", world_land, [
        (-98, 40, 17, 9), (-80, 33, 5, 6), (-100, 20, 8, 5),
        (-62, -15, 12, 14, 20), (-60, -34, 6, 6)], 22)
    add("gallery_monarchs", "Danaus", "plexippus", world_land, [
        (-16, 28.2, 1.2, 0.5), (-6, 37, 2, 1), (147, -35, 5, 3),
        (174.8, -37, 1, 1)], 6)
    add("gallery_monarchs", "Danaus", "chrysippus", world_land, [
        (15, 10, 25, 8), (30, -5, 8, 14), (25, -28, 6, 5),
        (72, 24, 10, 8), (110, 22, 10, 5), (140, -25, 8, 6)], 26)
    add("gallery_monarchs", "Danaus", "genutia", world_land, [
        (79, 21, 8, 8), (97, 20, 6, 8), (108, 14, 8, 10),
        (118, 5, 12, 6), (132, -13, 6, 3), (145, -17, 3, 5)], 24)

    ocean = coastal_water(2.0)
    add("gallery_sea_turtles", "Chelonia", "mydas", ocean, [
        (-80, 20, 15, 8), (-40, -15, 6, 10), (50, 10, 12, 12),
        (110, 5, 15, 8), (150, -15, 12, 6), (-150, 18, 8, 4),
        (-110, 5, 8, 5)], 28)
    add("gallery_sea_turtles", "Caretta", "caretta", ocean, [
        (-78, 32, 6, 8), (-12, 34, 12, 6), (20, 36, 12, 3),
        (-45, -25, 7, 8), (35, -25, 8, 10), (150, -27, 8, 8),
        (136, 35, 6, 5), (-118, 28, 6, 8)], 26)
    add("gallery_sea_turtles", "Dermochelys", "coriacea", ocean, [
        (-60, 15, 20, 18), (-10, 10, 14, 15), (-90, 7, 10, 10),
        (100, -5, 20, 10), (172, -40, 6, 5), (-78, -8, 5, 10)], 24)

    africa_forest = countries(
        "Guinea", "Sierra Leone", "Liberia", "Côte d'Ivoire", "Ghana", "Nigeria",
        "Cameroon", "Gabon", "Eq. Guinea", "Congo",
        "Dem. Rep. Congo", "Central African Rep.",
        "Uganda", "Tanzania", "Rwanda", "Burundi", "Mali", "Senegal")
    add("gallery_great_apes", "Pan", "troglodytes", africa_forest, [
        (-11.5, 9.5, 2.5, 2.5), (-8.5, 6, 2, 2), (7, 6.5, 3, 2),
        (14, 3.5, 3.5, 2.5), (24, 2, 4, 2.5), (30, -4.5, 1, 1.5)], 28)
    drc = countries("Dem. Rep. Congo")
    add("gallery_great_apes", "Pan", "paniscus", drc, [
        (22.5, -2.5, 3.5, 2.2), (19, -2.5, 1.5, 1.5)], 22)
    add("gallery_great_apes", "Gorilla", "gorilla",
        countries("Gabon", "Cameroon", "Congo",
                  "Central African Rep.", "Eq. Guinea"), [
        (11.5, -1, 2, 2.2), (14.5, 1.5, 2.2, 2.2), (13, 3.5, 2, 1.5)], 26)

    aus = countries("Australia")
    add("gallery_kangaroos", "Macropus", "giganteus", aus, [
        (150, -30, 3, 7, -15), (147, -37.5, 3, 1.5), (146, -23, 3, 4),
        (146.5, -42, 1, 1)], 26)
    add("gallery_kangaroos", "Macropus", "fuliginosus", aus, [
        (117, -33, 3, 2), (136, -34, 5, 2), (141, -33.5, 3, 2),
        (125, -32, 4, 1)], 24)
    add("gallery_kangaroos", "Osphranter", "rufus", aus, [
        (133, -25, 10, 7), (143, -28, 4, 5), (120, -26, 5, 5)], 28)

    nz = countries("New Zealand").intersection(box(166, -48, 179, -34))
    add("gallery_kiwi", "Apteryx", "mantelli", nz, [
        (175, -38.5, 2.2, 3.5, 20), (173.5, -35.5, 1, 1)], 26)
    add("gallery_kiwi", "Apteryx", "haastii", nz, [
        (172, -41.5, 1.3, 0.8, 30), (171.5, -42.5, 1, 0.8)], 22)
    islets = nz.buffer(0.03)
    add("gallery_kiwi", "Apteryx", "owenii", islets, [
        (175.0, -40.85, 0.1, 0.1), (175.07, -36.2, 0.1, 0.1),
        (174.75, -41.3, 0.08, 0.08)], 8)

    mad = countries("Madagascar")
    add("gallery_lemurs", "Lemur", "catta", mad, [
        (45, -24, 1.4, 1.6), (46.5, -22.5, 0.8, 0.8)], 18)
    add("gallery_lemurs", "Eulemur", "fulvus", mad, [
        (49.2, -15, 1.3, 2.2), (48.5, -18, 1, 1.3), (47.5, -13.5, 1, 1)], 24)
    add("gallery_lemurs", "Propithecus", "verreauxi", mad, [
        (44.5, -23, 1.2, 1.6), (45, -20, 1, 1.5), (46.5, -25, 1, 0.6),
        (44, -17, 1.2, 1.2)], 22)

    fl = state("Florida")
    add("gallery_florida_herps", "Alligator", "mississippiensis", fl, [
        (-82, 29, 1.8, 2.5), (-81, 27.5, 1.2, 1.2), (-81, 26, 1.2, 1.2),
        (-84, 30.5, 1.8, 0.5)], 28)
    add("gallery_florida_herps", "Crocodylus", "acutus", fl, [
        (-80.4, 25.2, 0.45, 0.35), (-81.0, 24.9, 0.6, 0.3),
        (-80.9, 25.6, 0.3, 0.3)], 16)
    add("gallery_florida_herps", "Gopherus", "polyphemus", fl, [
        (-82.3, 29.8, 1.4, 1.2), (-81.2, 28.2, 1.0, 1.1),
        (-85, 30.7, 2.0, 0.4), (-81.8, 26.8, 0.7, 0.7)], 28)

    ca = state("California")
    add("gallery_california_oaks", "Quercus", "lobata", ca, [
        (-121.2, 37.5, 1.0, 2.5, 35), (-121.5, 35.5, 0.8, 1.5),
        (-120.4, 34.7, 0.7, 0.4)], 26)
    add("gallery_california_oaks", "Quercus", "douglasii", ca, [
        (-120.2, 38.5, 0.6, 1.8, 40), (-119.5, 36.8, 0.7, 1.5, 40),
        (-121.5, 40.3, 0.9, 0.5), (-119, 35.2, 0.7, 0.5)], 26)
    add("gallery_california_oaks", "Quercus", "agrifolia", ca, [
        (-122.4, 37.8, 0.6, 1.8, 20), (-121.8, 36.4, 0.5, 1),
        (-120.5, 35.2, 0.5, 1), (-119.2, 34.4, 0.8, 0.4),
        (-117.5, 33.3, 0.8, 0.8), (-123, 39.2, 0.7, 1.5)], 28)

    # Last, so adding it left the RNG sequence of every file above alone.
    sumatra = (101.5, -1, 1.8, 3.5, -40)
    borneo = (114, 1, 3.5, 2.8)
    add("asia_hornbills", "Buceros", "bicornis", world_land, [
        (75.5, 12, 0.8, 3), (94, 24, 3, 3), (100, 16, 3, 4),
        (101.5, 6, 0.8, 1.2), sumatra], 13)
    add("asia_hornbills", "Buceros", "rhinoceros", world_land, [
        (102, 4, 1, 1.8), sumatra, borneo, (107, -6.9, 1.5, 0.5)], 12)
    add("asia_hornbills", "Anthracoceros", "albirostris", world_land, [
        (91, 26, 3, 1.2), (98, 18, 3, 5), (106, 14, 3, 5), borneo], 14)
    add("asia_hornbills", "Anthracoceros", "malayanus", world_land, [
        (102, 3, 1, 1.8), sumatra, (114, 0, 3.5, 2.5)], 12)
    add("asia_hornbills", "Anthracoceros", "coronatus", world_land, [
        (76, 13, 1.2, 4), (80.7, 7.5, 0.7, 1.1), (82, 20, 3, 2)], 12)
    add("asia_hornbills", "Rhyticeros", "undulatus", world_land, [
        (92, 27, 2, 0.8), (97, 19, 2, 4), (99, 12, 1.2, 3), borneo,
        (110, -7.3, 2.5, 0.5), sumatra], 13)
    add("asia_hornbills", "Rhyticeros", "subruficollis", world_land, [
        (98, 14, 1, 3), (101, 6, 0.8, 1)], 9)
    return maps


def with_holotypes(rows):
    """Rows plus a Type status: the middle record of each species is its
    holotype, the rest are blank. Chosen from the finished rows, so the RNG
    sequence (and every other file) is untouched."""
    by_species: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        by_species.setdefault(row[1], []).append(i)
    holotypes = {ids[len(ids) // 2] for ids in by_species.values()}
    return [(*row, "Holotype" if i in holotypes else "")
            for i, row in enumerate(rows)]


# Maps whose CSV carries a Type status column as well.
TYPE_STATUS = {"gallery_lemurs", "asia_hornbills"}
# Files that sit in sample_data/ itself rather than in the gallery folder.
NOT_GALLERY = {"asia_hornbills"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in build().items():
        path = (SAMPLES if name in NOT_GALLERY else OUT) / f"{name}.csv"
        header = "Genus,Species,Latitude,Longitude"
        if name in TYPE_STATUS:
            rows = with_holotypes(rows)
            header += ",Type status"
        with open(path, "w", newline="") as fh:
            fh.write(header + "\n")
            for row in rows:
                fh.write(",".join(str(v) for v in row) + "\n")
        print("wrote", path, len(rows), "rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
