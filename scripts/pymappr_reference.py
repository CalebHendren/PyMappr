r"""Reference outputs from PyMappr itself, for RustyMappr's tests.

Run with PyMappr's environment:

    C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/pymappr_reference.py <PyMappr dir> <command> [args]

Commands:
    default-state OUT.json                 the state a fresh PyMappr starts with
    project OUT.pymappr STANDARD CSV...    a project holding the CSVs, as PyMappr
                                           saves it; STANDARD is 1 to apply the
                                           Standard preset, else 0
    variant PROJECT OUT.pymappr PATCH.json a copy of a project with PATCH (a JSON
                                           object) merged into its state and
                                           applied in PyMappr; "zoom": true in the
                                           patch frames the data afterwards (on
                                           the render's 900x650 px figure)
    render PROJECT OUT_DIR [WIDTH_CM DPI]  PyMappr's own rendering of a project on
                                           a 900x650 px (9 x 6.5 in at 100 dpi)
                                           figure: screen.png, export.png/.svg
                                           (at WIDTH_CM/DPI, default as on screen
                                           at 100 dpi) and geometry.json, every
                                           drawn text, marker, patch and axes in
                                           figure pixels (y down) for the
                                           parity check
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
    app = PyMapprApp(root, store, restore_session=False)
    # The portrait mat takes the Tk theme's background, which a withdrawn
    # root does not resolve; use PyMappr's own default.
    app.renderer.set_mat_color("#e6e6e6")
    return root, app


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


FIG_INCHES = (9.0, 6.5)


def _hex(color):
    from matplotlib.colors import to_hex
    try:
        return to_hex(color, keep_alpha=False)
    except (ValueError, TypeError):
        return None


def _geometry(fig):
    """Every visible artist that the parity check compares, in figure
    pixels with the origin at the top left."""
    from matplotlib.collections import PathCollection
    from matplotlib.patches import Patch
    from matplotlib.text import Text

    # Only texts that are really drawn: an axis keeps tick labels for
    # ticks outside the view, which it does not draw.
    drawn = set()
    text_draw = Text.draw

    def recording_draw(self, renderer):
        drawn.add(id(self))
        return text_draw(self, renderer)

    Text.draw = recording_draw
    try:
        fig.canvas.draw()
    finally:
        Text.draw = text_draw
    renderer = fig.canvas.get_renderer()
    height = fig.bbox.height

    def box(bb):
        return [bb.x0, height - bb.y1, bb.x1, height - bb.y0]

    out = {"size": [fig.bbox.width, height], "axes": [], "texts": [],
           "markers": [], "patches": []}
    # The map's axes and their child axes (the inset).
    every = [a for ax in fig.axes for a in (ax, *ax.child_axes)]
    for ax in every:
        if ax.get_visible():
            out["axes"].append({"box": box(ax.get_window_extent(renderer)),
                                "xlim": list(ax.get_xlim()),
                                "ylim": list(ax.get_ylim())})
    for artist in fig.findobj():
        if not artist.get_visible():
            continue
        if isinstance(artist, Text):
            text = artist.get_text()
            if not text.strip() or id(artist) not in drawn:
                continue
            x, y = artist.get_transform().transform(artist.get_unitless_position())
            bb = artist.get_window_extent(renderer)
            out["texts"].append({
                "text": text, "x": float(x), "y": float(height - y),
                "box": box(bb), "size": artist.get_fontsize(),
                "color": _hex(artist.get_color()),
                "weight": str(artist.get_fontweight()),
                "style": artist.get_fontstyle(),
                "ha": artist.get_horizontalalignment(),
                "va": artist.get_verticalalignment(),
                "zorder": artist.get_zorder()})
        elif isinstance(artist, PathCollection):
            offsets = artist.get_offsets()
            if len(offsets) == 0:
                continue
            pts = artist.get_offset_transform().transform(offsets)
            faces = artist.get_facecolors()
            edges = artist.get_edgecolors()
            sizes = artist.get_sizes()
            for i, (x, y) in enumerate(pts):
                out["markers"].append({
                    "x": float(x), "y": float(height - y),
                    "size": float(sizes[i % len(sizes)]) if len(sizes) else None,
                    "face": _hex(faces[i % len(faces)]) if len(faces) else None,
                    "edge": _hex(edges[i % len(edges)]) if len(edges) else None,
                    "zorder": artist.get_zorder()})
        elif isinstance(artist, Patch) and artist.axes is not None or                 isinstance(artist, Patch) and artist.figure is not None:
            try:
                bb = artist.get_window_extent(renderer)
            except Exception:  # noqa: BLE001 - some patches have no extent
                continue
            if bb.width <= 0 and bb.height <= 0:
                continue
            out["patches"].append({
                "kind": type(artist).__name__, "box": box(bb),
                "face": _hex(artist.get_facecolor()),
                "edge": _hex(artist.get_edgecolor()),
                "linewidth": artist.get_linewidth(),
                "zorder": artist.get_zorder()})
    return out


def render(project_path, out_dir, width_cm=None, dpi="100"):
    from pymappr.files import projects

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    root, app = make_app()
    app.renderer.fig.set_size_inches(*FIG_INCHES, forward=False)
    app.renderer.fig.set_dpi(100)
    _name, state = projects.load_project(project_path)
    app._apply_state(state)
    fig = app.renderer.fig
    fig.canvas.draw()
    # The figure's own face: white, or the mat around a portrait map.
    fig.savefig(out / "screen.png", dpi=100, facecolor=fig.get_facecolor())
    # Measured now: an export re-lays the figure out at its own size, and
    # "best" legend placement need not come back the same afterwards.
    geometry = _geometry(fig)
    width = None if width_cm in (None, "", "screen") else float(width_cm)
    app.renderer.save_image(str(out / "export.png"), "png", int(dpi), width)
    app.renderer.save_image(str(out / "export.svg"), "svg", int(dpi), width)
    geometry["project"] = str(project_path)
    (out / "geometry.json").write_text(json.dumps(geometry, indent=1),
                                       encoding="utf-8")
    root.destroy()


def _merge(base, patch):
    """Deep-merge *patch* into *base*; a list of objects merges by index."""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        elif (isinstance(value, list) and isinstance(base.get(key), list)
              and all(isinstance(v, dict) for v in value)):
            for old, new in zip(base[key], value):
                _merge(old, new)
        else:
            base[key] = value


def variant(project_path, out, patch_path):
    from pymappr.files import projects

    patch = json.loads(Path(patch_path).read_text(encoding="utf-8"))
    zoom = patch.pop("zoom", False)
    root, app = make_app()
    app.renderer.fig.set_size_inches(*FIG_INCHES, forward=False)
    app.renderer.fig.set_dpi(100)
    _name, state = projects.load_project(project_path)
    _merge(state, patch)
    app._apply_state(state)
    if zoom:
        app._zoom_to_data()
    app.renderer.fig.canvas.draw()
    projects.save_project(out, Path(out).stem, app._collect_state())
    root.destroy()


COMMANDS = {"default-state": default_state, "project": project,
            "variant": variant, "render": render}

if __name__ == "__main__":
    COMMANDS[sys.argv[2]](*sys.argv[3:])
