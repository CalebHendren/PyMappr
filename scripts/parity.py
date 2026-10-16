r"""Render projects in PyMappr and in RustyMappr and compare them.

For each project: PyMappr draws it (pymappr_reference.py render), RustyMappr
draws it through its /parity page in headless Chrome, and parity_compare.py
checks geometry (0.01 pt) and pixels. Needs the dev bridge and the Vite dev
server running:

    npm run bridge        (or target\release\devbridge.exe)
    npm run dev

Run with PyMappr's environment:

    C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/parity.py OUT_DIR [PROJECT ...]

Without projects it uses every .pymappr fixture in src/lib/fixtures (and
scripts/parity-projects/ when it exists). Exits non-zero when any differs.
"""

import json
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYMAPPR = Path(r"C:\PyCharm\PyMappr")
PYTHON = PYMAPPR / ".venv" / "Scripts" / "python.exe"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
UI = "http://127.0.0.1:1420"


def projects(args):
    if args:
        return [Path(a).resolve() for a in args]
    found = sorted((ROOT / "src/lib/fixtures").glob("*.pymappr"))
    extra = ROOT / "scripts/parity-projects"
    if extra.is_dir():
        found += sorted(extra.glob("*.pymappr"))
    return found


def render_pymappr(project, out):
    subprocess.run([str(PYTHON), str(ROOT / "scripts/pymappr_reference.py"), str(PYMAPPR),
                    "render", str(project), str(out)], check=True, capture_output=True)


def render_rusty(project, out, tries=3):
    # Vite may still be reloading after an edit: try again.
    for _ in range(tries):
        if _render_rusty(project, out):
            return
    raise RuntimeError(f"RustyMappr did not render {project}")


def _render_rusty(project, out):
    marker = out / "geometry.json"
    for old in (marker, out / "screen.png"):
        if old.exists():
            old.unlink()
    query = urllib.parse.urlencode({"project": str(project), "out": str(out)})
    # The page writes its files through the bridge; stop Chrome as soon as
    # they are there (a page that Vite has just rebuilt can otherwise keep
    # headless Chrome waiting).
    chrome = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu",
                               "--window-size=1000,800", "--virtual-time-budget=60000",
                               "--dump-dom",
                               f"{UI}/parity?{query}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            if marker.exists():
                time.sleep(1.0)  # screen.png follows geometry.json
                return True
            time.sleep(0.5)
        return False
    finally:
        chrome.kill()


def main(out_dir, *args):
    out = Path(out_dir).resolve()
    results = {}
    for project in projects(args):
        name = project.stem
        print(f"== {name}")
        render_pymappr(project, out / name / "pymappr")
        render_rusty(project, out / name / "rusty")
        code = subprocess.run([str(PYTHON), str(ROOT / "scripts/parity_compare.py"),
                               str(out / name / "pymappr"), str(out / name / "rusty"),
                               str(out / name / "report")]).returncode
        results[name] = code == 0
    (out / "summary.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("\n".join(f"{'match' if ok else 'DIFFERS'}  {n}" for n, ok in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
