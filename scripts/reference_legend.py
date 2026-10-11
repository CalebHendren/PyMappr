r"""Reference legends from PyMappr itself, for RustyMappr's symbology tests.

Run with PyMappr's environment from the repository root:

    C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/reference_legend.py C:\PyCharm\PyMappr src/lib/fixtures/legend

Each case loads one of the fixture projects into a headless PyMappr, changes
a few settings, and writes `<case>.json` holding:

    state     the project state as PyMappr collected it after the change;
              a dataset whose rows match a fixture's has "rowsFrom":
              "<fixture>#<index>" in place of "rows"
    filter    the filter bar's selection ({dataset, key, allowed}) or null
    layout    pymappr.styling.layout.layout_points, flattened to JSON
    title     the legend title after with_default_title
    editor    editor_rows for the active dataset
    warning   the legend warning PyMappr put in the status bar, or ""
    legend    what matplotlib actually drew: title, entries, handles
    geometry  the drawn legend's boxes, in points from the axes' lower left,
              and the text metrics matplotlib measured them with
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pymappr_reference import make_app  # noqa: E402  (sets up sys.path)

OUT = Path(sys.argv[2])
FIXTURES = Path(__file__).resolve().parent.parent / "src" / "lib" / "fixtures"


def load(name):
    from pymappr.files import projects
    return projects.load_project(FIXTURES / f"{name}.pymappr")[1]


def style_json(style):
    if style is None:
        return None
    return {"color": style.color, "marker": style.marker,
            "size": float(style.size), "fill": style.fill}


def layout_json(layout):
    def groups(items):
        return [{"label": label, "style": style_json(style),
                 "rows": [int(i) for i in rows.index]}
                for label, style, rows in items]

    def sections(items):
        if items is None:
            return None
        return [{"title": title,
                 "rows": [{"label": e[0], "style": style_json(e[1]),
                           "depth": int(e[2]) if len(e) > 2 else 0}
                          for e in entries]}
                for title, entries in items]

    datasets = []
    for d in layout.datasets:
        datasets.append({
            "name": d.entry.name,
            "groups": groups(d.groups),
            "openGroups": groups(d.open_groups),
            "labelMap": d.label_map,
            "rows": [{"label": label, "style": style_json(style)}
                     for label, style in d.rows],
            "sections": sections(d.sections),
            "attribute": d.attribute,
            "paletteOffset": d.palette_offset,
        })
    note = layout.open_note
    return {"datasets": datasets, "sections": sections(layout.sections),
            "rowOrder": layout.row_order,
            "openNote": (None if note is None else
                         {"label": note[0], "style": style_json(note[1])})}


def pt_box(bbox, ax_bbox, dpi):
    k = 72.0 / dpi
    return [round((bbox.x0 - ax_bbox.x0) * k, 4),
            round((bbox.y0 - ax_bbox.y0) * k, 4),
            round(bbox.width * k, 4), round(bbox.height * k, 4)]


def legend_json(app):
    """What matplotlib drew, read back from the legend artist."""
    r = app.renderer
    r.fig.canvas.draw()
    leg = r.ax.get_legend()
    if leg is None:
        return None, None
    renderer = r.fig.canvas.get_renderer()
    dpi = r.fig.dpi
    ax_bbox = r.ax.bbox
    k = 72.0 / dpi
    underlined = {id(t) for t in r._legend_underline_texts}

    def text_json(t):
        return {"text": t.get_text(), "size": float(t.get_fontsize()),
                "weight": str(t.get_fontweight()),
                "style": t.get_fontstyle(), "color": t.get_color(),
                "family": list(t.get_fontfamily()),
                "underline": id(t) in underlined}

    def anchor_pt(t):
        x, y = t.get_transform().transform(t.get_position())
        return [round((x - ax_bbox.x0) * k, 4), round((y - ax_bbox.y0) * k, 4)]

    def metrics(t):
        prop = t.get_fontproperties()
        w, h, d = renderer.get_text_width_height_descent(
            t.get_text(), prop, ismath=False)
        _, lh, ld = renderer.get_text_width_height_descent(
            "lp", prop, ismath=False)
        return {"text": t.get_text(), "size": float(t.get_fontsize()),
                "weight": str(t.get_fontweight()),
                "style": t.get_fontstyle(),
                "w": w * k, "h": h * k, "d": d * k,
                "lpH": lh * k, "lpD": ld * k}

    entries = []
    handle_boxes = []
    for handle, text in zip(leg.legend_handles, leg.get_texts()):
        marker = handle.get_marker()
        entry = text_json(text)
        if marker in ("", "None", None):
            entry["handle"] = None
        else:
            entry["handle"] = {
                "marker": marker, "markersize": float(handle.get_markersize()),
                "face": handle.get_markerfacecolor(),
                "edge": handle.get_markeredgecolor(),
                "edgeWidth": float(handle.get_markeredgewidth())}
        entries.append(entry)
        xy = handle.get_xydata()
        point = handle.get_transform().transform(xy[len(xy) // 2])
        handle_boxes.append([round((point[0] - ax_bbox.x0) * k, 4),
                             round((point[1] - ax_bbox.y0) * k, 4)])
    title = leg.get_title()
    legend = {"title": text_json(title) if title.get_visible()
              and title.get_text() else None,
              "entries": entries}
    frame = leg.get_frame()
    geometry = {
        "axes": [round(ax_bbox.width * k, 4), round(ax_bbox.height * k, 4)],
        "box": pt_box(leg.get_window_extent(renderer), ax_bbox, dpi),
        "frame": pt_box(frame.get_window_extent(renderer), ax_bbox, dpi),
        "texts": [pt_box(t.get_window_extent(renderer), ax_bbox, dpi)
                  for t in leg.get_texts()],
        "title": (pt_box(title.get_window_extent(renderer), ax_bbox, dpi)
                  if legend["title"] else None),
        "markers": handle_boxes,
        # Where each text's baseline starts (its anchor point).
        "baselines": [anchor_pt(t) for t in leg.get_texts()],
        "titleBaseline": anchor_pt(title) if legend["title"] else None,
        "metrics": [metrics(t) for t in leg.get_texts()]
        + ([metrics(title)] if legend["title"] else []),
    }
    return legend, geometry


def strip_rows(state):
    """Replace each dataset's rows with a pointer to the fixture project
    holding the same rows ("rowsFrom": "<fixture>#<index>"), so the cases
    stay small."""
    sources = {name: load(name) for name in ("beetles-standard",
                                              "hornbills-orchids")}
    for entry in state["datasets"]:
        for name, source in sources.items():
            for index, other in enumerate(source["datasets"]):
                if (other["rows"] == entry["rows"]
                        and other["columns"] == entry["columns"]):
                    entry["rowsFrom"] = f"{name}#{index}"
                    del entry["rows"]
                    break
            if "rowsFrom" in entry:
                break
    return state


def set_filter(app, label, hidden_values):
    bar = app.filter_bar
    bar.column_var.set(label)
    bar._rebuild_values()
    for value in hidden_values:
        bar._value_vars[value].set(False)
    app.on_filter()


def run_case(app, name, state, filter_=None, after=None):
    from pymappr.styling.layout import editor_rows

    app._legend_warning = ""
    app.set_status("Ready.")
    app._apply_state(copy.deepcopy(state))
    if after is not None:
        after(app)
    if filter_ is not None:
        set_filter(app, *filter_)
    app._push_points()
    options = app._legend_options()
    layout = app._layout()
    entry = app._active_entry()
    drawn = next((d for d in layout.datasets if d.entry is entry), None)
    editor = [] if entry is None else [
        {"key": key, "value": value, "style": style_json(style),
         "depth": depth}
        for key, value, style, depth in editor_rows(
            entry, options, app._palette(),
            drawn.palette_offset if drawn else 0)]
    selection = app.filter_bar.selection()
    legend, geometry = legend_json(app)
    case = {
        "name": name,
        "state": strip_rows(app._collect_state()),
        "filter": (None if selection is None else
                   {"dataset": app.active, "key": selection[0],
                    "allowed": sorted(selection[1])}),
        "layout": layout_json(layout),
        "title": options.title,
        "editor": editor,
        "warning": app._legend_warning,
        "status": app.status.cget("text"),
        "legend": legend,
        "geometry": geometry,
    }
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(case, indent=1, ensure_ascii=False),
                    encoding="utf-8")
    print("wrote", path)


def legend(state, **values):
    state["legend"].update(values)
    return state


def dataset(state, index=0, **values):
    state["datasets"][index].update(values)
    return state


def cases():
    beetles = load("beetles-standard")
    birds = load("hornbills-orchids")
    k = "\x00"
    yield "beetles-standard", beetles, None, None
    yield "hornbills-orchids", birds, None, None
    yield "beetles-nested", dataset(copy.deepcopy(beetles), color_by="Genus",
                                    symbol_by="Species"), None, None
    yield "beetles-nested-counts", legend(dataset(
        copy.deepcopy(beetles), color_by="Genus", symbol_by="Species"),
        counts=True, count_format="(n, %)", order="count_desc",
        show_title=True), None, None
    yield "beetles-nested-za-options", legend(dataset(
        copy.deepcopy(beetles), color_by="Genus", symbol_by="Species"),
        order="za", group_swatch="child", bold_groups=False,
        group_spacer=False, indent=1, title_separator=" - ",
        location="upper left", columns=2), None, None
    yield "beetles-nested-noswatch", legend(dataset(
        copy.deepcopy(beetles), color_by="Genus", symbol_by="Species"),
        group_swatch="none", section_titles=False, counts=True,
        count_format="%", order="az", location="lower right"), None, None
    yield "beetles-nested-filtered", dataset(
        copy.deepcopy(beetles), color_by="Genus", symbol_by="Species"), \
        ("Genus", ["Eleusis"]), None
    yield "beetles-nested-filtered-empty", legend(dataset(
        copy.deepcopy(beetles), color_by="Genus", symbol_by="Species"),
        empty_groups=True), ("Species", ["chapadensis", "riograndensis"]), \
        None
    yield "beetles-nested-overrides", legend(dataset(
        copy.deepcopy(beetles), color_by="Genus", symbol_by="Species",
        legend_overrides={
            f"color{k}Eleusis": {"label": "Eleusis (group)",
                                 "color": "#123456"},
            f"pair{k}Eleusis{k}chapadensis": {"marker": "Star", "size": 80.0,
                                             "label": "E. chapadensis"},
            f"pair{k}Eleusis{k}riograndensis": {"hidden": True},
            f"color{k}Xanthopygus": {"hidden": True},
        }), counts=True), None, None
    yield "beetles-symbol-only", legend(dataset(
        copy.deepcopy(beetles), symbol_by="Species"), palette="Default",
        location="center left", title="Species key"), None, None
    yield "beetles-group-species", legend(dataset(
        copy.deepcopy(beetles), group_by="Species", vary_symbols=False),
        order="count_asc", counts=True, count_format="n",
        location="upper center", show_title=True), None, None
    yield "beetles-group-colorby", legend(dataset(
        copy.deepcopy(beetles), group_by="Species", color_by="Genus"),
        order="data", location="lower center", label_underline=True,
        title_underline=True, show_title=True, title_align="left",
        font_family="serif", label_bold=True), None, None
    yield "beetles-group-manual", legend(dataset(
        copy.deepcopy(beetles), group_by="Genus",
        legend_overrides={
            f"group{k}Xanthopygus": {"order": 0, "label": "Xanth."},
            f"group{k}Eleusis": {"order": 1, "color": "#ff00ff",
                                 "marker": "Hexagon (open)", "size": 60.0},
            f"group{k}Plociopterus": {"hidden": True},
        }), order="manual", location="center", shadow=True,
        rounded=True, frame_alpha=0.5, marker_scale=1.5,
        handle_length=3.0, handle_text_pad=1.0, border_pad=1.0,
        label_spacing=1.0, title="Genera", show_title=True,
        title_align="right"), None, None
    yield "beetles-group-filtered", legend(dataset(
        copy.deepcopy(beetles), group_by="Species"), counts=True,
        count_format="(n, %)", location="right"), \
        ("Genus", ["Plociopterus"]), None
    twice = copy.deepcopy(beetles)
    second = copy.deepcopy(twice["datasets"][0])
    second["name"] = "more_beetles.csv"
    twice["datasets"].append(second)
    yield "beetles-twice", legend(twice, location="upper right"), None, None
    whole = copy.deepcopy(birds)
    for d in whole["datasets"]:
        d["group_by"] = ""
    yield "birds-all-points", legend(whole, location="lower left"), None, None
    yield "birds-crossed", legend(dataset(
        copy.deepcopy(birds), 0, color_by="Genus", symbol_by="Type status",
        legend_overrides={f"symbol{k}Holotype": {"color": "#00aa00",
                                                  "label": "Holo"},
                          f"color{k}Buceros": {"marker": "Square"}}),
        counts=True, order="az", location="upper left"), None, None
    yield "birds-crossed-always", legend(dataset(
        copy.deepcopy(birds), 0, color_by="Species", symbol_by="Type status"),
        hierarchy="always", location="upper left"), None, None
    yield "birds-never-nest", legend(dataset(
        copy.deepcopy(birds), 0, color_by="Genus", symbol_by="Species"),
        hierarchy="never", dataset_prefix=False, location="upper left"), \
        None, None
    yield "birds-mixed-prefix", legend(dataset(
        copy.deepcopy(birds), 0, color_by="Genus", symbol_by="Species"),
        location="upper left"), None, None
    yield "birds-mixed-notitles", legend(dataset(
        copy.deepcopy(birds), 0, color_by="Genus", symbol_by="Species"),
        section_titles=False, location="upper left"), None, None
    yield "birds-open", dataset(
        copy.deepcopy(birds), 0, open_by="Type status",
        open_values=["Holotype"]), None, None
    yield "birds-open-symbol", legend(dataset(
        copy.deepcopy(birds), 0, color_by="Genus", symbol_by="Species",
        open_by="Type status", open_values=["Holotype"]),
        location="upper left"), None, None
    yield "birds-standard", birds, None, lambda app: app.on_publication_style()
    yield "beetles-many-shapes", dataset(
        copy.deepcopy(beetles), symbol_by="Species"), None, None
    bw = copy.deepcopy(birds)
    bw["map"]["palette"] = "Colourblind safe (Okabe-Ito)"
    yield "birds-okabe-vary", dataset(bw, 1, vary_symbols=True,
                                      group_by="Species"), None, None
    yield "beetles-layout-serif", legend(dataset(
        copy.deepcopy(beetles), color_by="Genus", symbol_by="Species"),
        font_family="serif", columns=3, column_spacing=1.0,
        label_spacing=0.2, border_pad=0.8, title="A rather long legend title",
        show_title=True, title_align="right", fontsize=7.0,
        title_fontsize=12.0, location="lower left", marker_scale=0.7,
        title_italic=True, label_bold=True), None, None
    yield "beetles-anchored", legend(copy.deepcopy(beetles), anchor=[0.3, 0.2],
                                     draggable=True, frame=False,
                                     border_pad=0.0, label_spacing=0.0),         None, None
    yield "birds-mono", legend(copy.deepcopy(birds), font_family="monospace",
                               title="Hornbills and orchids of the world",
                               show_title=True, title_align="left",
                               handle_length=1.0, handle_text_pad=0.2,
                               columns=2, location="center right",
                               counts=True), None, None
    hidden = copy.deepcopy(birds)
    hidden["datasets"][1]["visible"] = False
    yield "birds-one-hidden", legend(hidden, show_title=True), None, None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    root, app = make_app()
    for name, state, filter_, after in cases():
        run_case(app, name, state, filter_, after)
    root.destroy()


if __name__ == "__main__":
    main()
