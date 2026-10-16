r"""Compare RustyMappr's rendering of a project with PyMappr's.

Both sides write the same files into their own folder (PyMappr through
`pymappr_reference.py render`, RustyMappr through its /parity page):

    screen.png      the 900x650 px figure
    geometry.json   every text, marker, patch and axes in figure pixels (y down)

Checks, in order of strictness:

    geometry  axes boxes, texts (content, anchor, box, size, colour, weight,
              style),
              markers (position, size, face, edge) and legend frames must match
              within TOL_PT points (default 0.01 pt);
    pixels    the bar is an eye check, not pixel identity: the two rasterisers
              anti-alias edges differently. A pixel counts as different only
              when nothing within one pixel of it in the other image is within
              MAX_CHANNEL_DIFF, and at most MAX_DIFFERENT of the pixels may be.
              A missing or misplaced line, marker or label fails this.

Writes report.json, diff.png (red = different pixels) and side.png (PyMappr
left, RustyMappr right, for the eye check) to OUT and exits non-zero when a
check fails.

    C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/parity_compare.py PYMAPPR_DIR RUSTY_DIR OUT
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

TOL_PT = 0.01
PX_PER_PT = 100 / 72  # both sides draw the screen figure at 100 dpi
TOL_PX = TOL_PT * PX_PER_PT
MAX_CHANNEL_DIFF = 128  # of 255
MAX_DIFFERENT = 1e-4   # share of all pixels


def load(folder):
    folder = Path(folder)
    return (json.loads((folder / "geometry.json").read_text(encoding="utf-8")),
            np.asarray(Image.open(folder / "screen.png").convert("RGB"), dtype=np.int16))


def on_canvas(markers, size):
    w, h = size
    return [m for m in markers if -1 <= m["x"] <= w + 1 and -1 <= m["y"] <= h + 1]


def compare_geometry(a, b):
    problems = []

    def close(x, y, tol=TOL_PX):
        return abs(x - y) <= tol

    if a["size"] != b["size"]:
        problems.append(f"figure size {a['size']} vs {b['size']}")
    for i, (pa, pb) in enumerate(zip(a["axes"], b["axes"])):
        if not all(close(x, y) for x, y in zip(pa["box"], pb["box"])):
            problems.append(f"axes {i} box {pa['box']} vs {pb['box']}")
    if len(a["axes"]) != len(b["axes"]):
        problems.append(f"{len(a['axes'])} axes vs {len(b['axes'])}")

    # Texts: matched by content, in order of appearance.
    rest = list(b["texts"])
    for t in a["texts"]:
        match = next((u for u in rest if u["text"] == t["text"]), None)
        if match is None:
            problems.append(f"text {t['text']!r} missing")
            continue
        rest.remove(match)
        for key in ("x", "y"):
            if not close(t[key], match[key]):
                problems.append(f"text {t['text']!r} {key} {t[key]:.3f} vs {match[key]:.3f}")
        if t.get("box") and match.get("box") and not all(
                close(p, q) for p, q in zip(t["box"], match["box"])):
            problems.append(f"text {t['text']!r} box "
                            f"{[round(v, 3) for v in t['box']]} vs "
                            f"{[round(v, 3) for v in match['box']]}")
        if not close(float(t.get("size") or 0), float(match.get("size") or 0), 0.001):
            problems.append(f"text {t['text']!r} size {t.get('size')} vs {match.get('size')}")
        for key in ("color", "weight", "style"):
            if str(t.get(key)) != str(match.get(key)):
                problems.append(f"text {t['text']!r} {key} {t.get(key)} vs {match.get(key)}")
    problems += [f"extra text {u['text']!r}" for u in rest]

    # Markers: on-canvas copies, matched to the nearest.
    ma = on_canvas(a["markers"], a["size"])
    mb = on_canvas(b["markers"], b["size"])
    if len(ma) != len(mb):
        problems.append(f"{len(ma)} markers vs {len(mb)}")
    left = list(mb)
    for m in ma:
        if not left:
            break
        near = min(left, key=lambda n: (n["x"] - m["x"]) ** 2 + (n["y"] - m["y"]) ** 2)
        left.remove(near)
        if not (close(m["x"], near["x"]) and close(m["y"], near["y"])):
            problems.append(f"marker at ({m['x']:.3f}, {m['y']:.3f}) vs ({near['x']:.3f}, {near['y']:.3f})")
        for key in ("size", "face", "edge"):
            if m.get(key) != near.get(key):
                problems.append(f"marker at ({m['x']:.1f}, {m['y']:.1f}) {key} {m.get(key)} vs {near.get(key)}")

    # Legend frames and other boxed patches (not spines or the background).
    def frames(g):
        return [p for p in g["patches"] if p["kind"] in ("FancyBboxPatch", "LegendFrame")]

    for pa, pb in zip(frames(a), frames(b)):
        if not all(close(x, y) for x, y in zip(pa["box"], pb["box"])):
            problems.append(f"legend frame {pa['box']} vs {pb['box']}")
    if len(frames(a)) != len(frames(b)):
        problems.append(f"{len(frames(a))} legend frames vs {len(frames(b))}")
    return problems


def compare_pixels(a, b, out):
    if a.shape != b.shape:
        return {"ok": False, "reason": f"image sizes differ: {a.shape} vs {b.shape}"}

    def nearest(x, y):
        # For each pixel of x, the smallest max-channel difference to y
        # within its 3x3 neighbourhood.
        h, w = x.shape[:2]
        pad = np.pad(y, ((1, 1), (1, 1), (0, 0)), mode="edge")
        best = np.full((h, w), 255, np.int16)
        for dy in range(3):
            for dx in range(3):
                best = np.minimum(best, np.abs(x - pad[dy:dy + h, dx:dx + w]).max(axis=2))
        return best

    near = np.maximum(nearest(a, b), nearest(b, a))
    different = near > MAX_CHANNEL_DIFF
    vis = (a // 2 + 127).astype(np.uint8)
    vis[different] = [220, 30, 30]
    Image.fromarray(vis).save(out / "diff.png")
    side = np.full((a.shape[0], a.shape[1] * 2 + 10, 3), 0, np.uint8)
    side[:, :a.shape[1]] = a
    side[:, a.shape[1] + 10:] = b
    Image.fromarray(side).save(out / "side.png")
    return {
        "ok": bool(different.mean() <= MAX_DIFFERENT),
        "identical": float(1 - (a != b).any(axis=2).mean()),
        "different": int(different.sum()),
        "allowed": int(MAX_DIFFERENT * different.size),
        "max_neighbourhood_diff": int(near.max()),
    }


def main(pymappr_dir, rusty_dir, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ga, ia = load(pymappr_dir)
    gb, ib = load(rusty_dir)
    geometry = compare_geometry(ga, gb)
    pixels = compare_pixels(ia, ib, out)
    report = {"geometry_ok": not geometry, "geometry_problems": geometry, "pixels": pixels}
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"geometry: {'match' if not geometry else f'{len(geometry)} differences'}")
    for p in geometry[:20]:
        print("  ", p)
    print(f"pixels: {pixels}")
    return 0 if not geometry and pixels.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
