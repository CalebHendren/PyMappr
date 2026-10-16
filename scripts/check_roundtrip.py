r"""Open RustyMappr's re-saved fixture projects in PyMappr itself.

    set RUSTYMAPPR_ROUNDTRIP_DIR=%TEMP%\rustymappr-roundtrip
    npx vitest run src/lib/project.test.ts
    C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/check_roundtrip.py C:\PyCharm\PyMappr %TEMP%\rustymappr-roundtrip

Each file is loaded with pymappr.files.projects.load_project, applied to a
headless PyMappr, and collected again; the collected state must equal the
original fixture's.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pymappr_reference import make_app  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "src" / "lib" / "fixtures"


def main():
    from pymappr.files import projects

    folder = Path(sys.argv[2])
    root, app = make_app()
    failures = 0
    for path in sorted(folder.glob("*.pymappr")):
        name, state = projects.load_project(path)
        app._apply_state(state)
        collected = json.loads(json.dumps(app._collect_state()))
        original = json.loads((FIXTURES / path.name).read_text(encoding="utf-8"))["state"]
        same = collected == original
        failures += not same
        print(f"{path.name}: opened as {name!r}, "
              f"{len(app.entries)} datasets, "
              f"{'same state' if same else 'STATE DIFFERS'}")
    root.destroy()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
