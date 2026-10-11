r"""Reference outputs from PyMappr itself, for RustyMappr's tests.

Run with PyMappr's environment:

    C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/pymappr_reference.py <PyMappr dir> <command> [args]

Commands:
    default-state OUT.json                 the state a fresh PyMappr starts with
    project OUT.pymappr STANDARD CSV...    a project holding the CSVs, as PyMappr
                                           saves it; STANDARD is 1 to apply the
                                           Standard preset, else 0
"""

import json
import sys
from pathlib import Path

PYMAPPR = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(PYMAPPR))


def make_app():
    import tkinter as tk

    import matplotlib
    from pymappr.app import PyMapprApp
    from pymappr.geo.layers import LayerStore

    matplotlib.use("TkAgg")
    root = tk.Tk()
    root.withdraw()
    store = LayerStore(PYMAPPR / "data")
    return root, PyMapprApp(root, store, restore_session=False)


def default_state(out):
    root, app = make_app()
    state = app._collect_state()
    Path(out).write_text(json.dumps(state, indent=1), encoding="utf-8")
    root.destroy()


def project(out, standard, *csvs):
    from pymappr.files import projects
    from pymappr.files.data_loader import (build_dataset, guess_mapping,
                                           read_table)
    from pymappr.files.projects import DatasetEntry

    root, app = make_app()
    for csv in csvs:
        frame = read_table(csv, headers=True)
        dataset = build_dataset(frame, guess_mapping(frame), source_path=csv)
        labels = dataset.name_labels
        app._add_entry(DatasetEntry(dataset=dataset, name=Path(csv).name,
                                    group_by=labels[0] if labels else ""))
    if standard == "1":
        app.on_publication_style()
    projects.save_project(out, Path(out).stem, app._collect_state())
    root.destroy()


COMMANDS = {"default-state": default_state, "project": project}

if __name__ == "__main__":
    COMMANDS[sys.argv[2]](*sys.argv[3:])
