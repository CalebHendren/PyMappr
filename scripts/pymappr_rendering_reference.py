r"""Write PyMappr rendering reference values for mappr-core's tests: view
framing, graticule ticks, place labels, point markers, scale bars and insets,
read off PyMappr's own renderer on a 9 x 6.5 in, 100 dpi Agg figure.

Run with PyMappr's environment and map data:

    C:\PyCharm\PyMappr\.venv\Scripts\python.exe scripts/pymappr_rendering_reference.py C:\PyCharm\PyMappr
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from pymappr.geo.layers import CONTINENT_EXTENTS, LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.styling.decorations import InsetOptions, ScaleBarOptions  # noqa: E402

OUT = (Path(__file__).resolve().parent.parent
       / "crates/mappr-core/tests/data/pymappr_rendering_reference.json")
STORE = LayerStore(Path(sys.argv[1]) / "data")

FIJI = (175.0, 191.0, -23.5, -11.0)
LANCASTER = (-97.3, -96.2, 40.5, 41.4)
ALPS = (5.0, 12.0, 44.0, 48.5)


def renderer(projection, origin=None, extent="World", graticule=None,
             labels=True):
    fig = Figure(figsize=(9.0, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, STORE)
    if origin:
        r.set_projection(projection, *origin)
    else:
        r.set_projection(projection)
    r.set_graticule(graticule, show_labels=labels)
    r.set_extent(extent if isinstance(extent, str) else tuple(extent))
    return r


def frame(r, projection, origin, extent):
    pos = r.ax.get_position()
    fig_w, fig_h = r.fig.get_size_inches()
    bbox = r.ax.bbox
    x0, x1 = r.ax.get_xlim()
    y0, y1 = r.ax.get_ylim()
    return {
        "projection": projection,
        "origin": list(origin) if origin else None,
        "extent": list(CONTINENT_EXTENTS[extent]) if isinstance(extent, str) else list(extent),
        # Height / width of the map box, as the frontend passes it.
        "aspect": (pos.height * fig_h) / (pos.width * fig_w),
        "px": [bbox.width, bbox.height],
        "px_per_pt": r.fig.dpi / 72.0,
        "xlim": [x0, x1],
        "ylim": [y0, y1],
    }


def extent_cases():
    cases = []
    for projection, origin in [("Equirectangular", None), ("Robinson", None),
                               ("Mercator", None), ("Mollweide", None),
                               ("Winkel Tripel", None), ("Natural Earth", None),
                               ("Lambert: Europe", None),
                               ("Lambert: N. America", None),
                               ("Lambert Azimuthal (custom)", (-178.0, -17.0)),
                               ("Globe (Orthographic)", (20.0, 10.0))]:
        for extent in ["World", "Africa", "Europe", "South America", FIJI,
                       LANCASTER]:
            for graticule in (None, 10.0):
                try:
                    r = renderer(projection, origin, extent, graticule)
                except ZeroDivisionError:
                    continue  # an extent wholly outside a regional map
                cases.append(frame(r, projection, origin, extent))
    return cases


def tick_cases():
    cases = []
    for projection, origin, extent, step in [
            ("Equirectangular", None, "World", 5.0),
            ("Equirectangular", None, (-100.0, -77.0, 6.0, 21.0), 5.0),
            ("Equirectangular", None, ALPS, 1.0),
            ("Robinson", None, "World", 30.0),
            ("Robinson", None, "Africa", 10.0),
            ("Mollweide", None, "World", 30.0),
            ("Winkel Tripel", None, "World", 10.0),
            ("Natural Earth", None, "Europe", 5.0),
            ("Mercator", None, "South America", 10.0),
            ("Mercator", None, FIJI, 5.0),
            ("Lambert Azimuthal (custom)", (-178.0, -17.0), FIJI, 5.0),
            ("Lambert: N. America", None, "World", 10.0),
            ("Lambert: Europe", None, "Europe", 5.0),
            ("Lambert: Asia", None, "Asia", 10.0)]:
        r = renderer(projection, origin, extent, step)
        r.fig.canvas.draw()
        case = frame(r, projection, origin, extent)
        case["step"] = step
        (vx0, vx1), (vy0, vy1) = sorted(r.ax.get_xlim()), sorted(r.ax.get_ylim())

        xs = r.ax.get_xticklabels()
        ys = r.ax.get_yticklabels()
        case["x_ticks"] = [[float(t.get_position()[0]), t.get_text()] for t in xs
                           if t.get_text() and vx0 <= t.get_position()[0] <= vx1]
        case["y_ticks"] = [[float(t.get_position()[1]), t.get_text()] for t in ys
                           if t.get_text() and vy0 <= t.get_position()[1] <= vy1]
        cases.append(case)
    return cases


def label_cases():
    cases = []
    for projection, origin, extent, keys, capitals, zoom in [
            ("Equirectangular", None, "World", ["countries", "cities"], False, None),
            ("Robinson", None, "Europe",
             ["countries", "states", "cities", "lakes", "rivers"], False, None),
            ("Lambert: Europe", None, "Europe", ["countries", "cities"], False, None),
            ("Equirectangular", None, ALPS,
             ["countries", "states", "cities", "airports", "ports", "lakes",
              "rivers", "regions"], False, None),
            ("Mercator", None, "South America",
             ["countries", "cities", "regions", "timezones"], True, None),
            ("Equirectangular", None, LANCASTER,
             ["states", "counties", "cities"], False, None),
            ("Mercator", None, FIJI, ["countries", "cities"], False, None),
            ("Globe (Orthographic)", (20.0, 45.0), "World",
             ["countries", "cities", "lakes"], False, 3.0),
            ("Lambert Azimuthal (custom)", (-178.0, -17.0), FIJI,
             ["countries", "states", "cities"], False, None),
            ("Natural Earth", None, "World",
             ["countries", "cities", "lakes", "rivers", "regions",
              "timezones"], False, None),
            ("Winkel Tripel", None, "Asia",
             ["countries", "states", "cities", "airports", "ports"], False, None),
            ("Lambert: S. America", None, "South America",
             ["countries", "states", "cities", "rivers"], True, None)]:
        r = renderer(projection, origin, extent)
        if zoom:
            r.zoom(zoom)
        r.set_capitals_only(capitals)
        for key in keys:
            r.set_labels(key, True)
        case = frame(r, projection, origin, extent)
        case["keys"] = keys
        case["capitals_only"] = capitals
        case["labels"] = [
            [key, t.get_text(), float(t.get_position()[0]),
             float(t.get_position()[1]), float(t.get_fontsize())]
            for key, texts in r._label_texts.items() for t in texts]
        cases.append(case)
    return cases


def marker_cases():
    cases = []
    for projection, extent, keys, capitals in [
            ("Equirectangular", "Europe", ["cities", "airports", "ports"], False),
            ("Robinson", "Africa", ["cities"], True),
            ("Lambert: Europe", "Europe", ["cities"], False),
            ("Mercator", FIJI, ["cities", "ports"], False),
            ("Lambert: Asia", "Asia", ["cities", "airports"], True),
            ("Globe (Orthographic)", "World", ["cities", "ports"], False)]:
        r = renderer(projection, (20.0, 45.0) if "Globe" in projection else None, extent)
        r.set_capitals_only(capitals)
        for key in keys:
            r.set_point_layer(key, True)
        case = frame(r, projection, (20.0, 45.0) if "Globe" in projection else None, extent)
        case["keys"] = keys
        case["capitals_only"] = capitals
        # Only the markers on screen (and a 2% margin): PyMappr draws all
        # the zoom allows on every world copy, the frontend needs these.
        (x0, x1), (y0, y1) = sorted(r.ax.get_xlim()), sorted(r.ax.get_ylim())
        m = max(x1 - x0, y1 - y0) * 0.02
        case["markers"] = {}
        for key, artists in r._point_layer_artists.items():
            xy = np.asarray(artists[0].get_offsets(), float)
            keep = (np.isfinite(xy).all(axis=1) & (xy[:, 0] >= x0 - m)
                    & (xy[:, 0] <= x1 + m) & (xy[:, 1] >= y0 - m)
                    & (xy[:, 1] <= y1 + m))
            case["markers"][key] = xy[keep].tolist()
        cases.append(case)
    return cases


def bars_of(r):
    rects = [a for a in r._artists.get("scale_bar", []) if isinstance(a, Rectangle)]
    rows = sorted({round(a.get_y(), 9) for a in rects}, reverse=True)
    out = []
    for y in rows:
        row = [a for a in rects if round(a.get_y(), 9) == y]
        x0 = min(a.get_x() for a in row)
        x1 = max(a.get_x() + a.get_width() for a in row)
        out.append([x0, row[0].get_y(), x1 - x0, len(row)])
    labels = [a.get_text() for a in r._artists.get("scale_bar", [])
              if hasattr(a, "get_text")]
    return out, labels


def scale_bar_cases():
    cases = []
    options = [dict(), dict(position="upper right"), dict(units="both"),
               dict(units="mi", position="lower right", style="plain"),
               dict(length_mode="fixed", fixed_length=750.0),
               dict(length_mode="fixed", fixed_length=500000.0),
               dict(anchor_x=0.4, anchor_y=0.6, units="both"),
               dict(width=0.35, segments=5, position="upper left")]
    for projection, origin, extent in [
            ("Equirectangular", None, "Africa"), ("Mercator", None, "Africa"),
            ("Lambert: N. America", None, "North America"),
            ("Robinson", None, "World"), ("Mollweide", None, "Europe"),
            ("Winkel Tripel", None, "World"),
            ("Globe (Orthographic)", (20.0, 10.0), "World"),
            ("Equirectangular", None, LANCASTER), ("Mercator", None, FIJI)]:
        for opts in options:
            r = renderer(projection, origin, extent)
            r.set_scale_bar(ScaleBarOptions(show=True, **opts))
            case = frame(r, projection, origin, extent)
            case["options"] = ScaleBarOptions(show=True, **opts).to_dict()
            case["bars"], case["labels"] = bars_of(r)
            case["note"] = r.scale_bar_note()
            cases.append(case)
    return cases


def inset_cases():
    cases = []
    hawaii = dict(region="custom", lon_min=-160.5, lon_max=-154.5,
                  lat_min=18.7, lat_max=22.4)
    for projection, origin, extent, opts, bar in [
            ("Equirectangular", None, LANCASTER,
             dict(region="state", states=True, counties=True), None),
            ("Equirectangular", None, "World", hawaii, None),
            ("Lambert: N. America", None, LANCASTER, dict(region="country"), None),
            ("Robinson", None, LANCASTER, dict(region="country"), None),
            ("Equirectangular", None, (41.0, 53.0, -27.0, -11.0),
             dict(region="state", projection="Globe"), None),
            ("Equirectangular", None, LANCASTER, dict(region="around"),
             dict(position="lower right")),
            ("Equirectangular", None, LANCASTER,
             dict(region="Europe", position="upper left", size=0.45),
             dict(position="upper left", units="both")),
            ("Mercator", None, "South America",
             dict(region="South America", size=0.6), None),
            ("Equirectangular", None, ALPS,
             dict(region="country", anchor_x=0.2, anchor_y=0.3), None),
            ("Globe (Orthographic)", (20.0, 10.0), "World",
             dict(region="Africa"), None)]:
        r = renderer(projection, origin, extent)
        if bar:
            r.set_scale_bar(ScaleBarOptions(show=True, **bar))
        r.set_layer("countries", True)
        r.set_inset(InsetOptions(show=True, **opts))
        case = frame(r, projection, origin, extent)
        case["options"] = InsetOptions(show=True, **opts).to_dict()
        case["scale_bar"] = ScaleBarOptions(show=True, **bar).to_dict() if bar else None
        case["rect"] = list(r._inset_rect)
        case["limits"] = [float(v) for v in r._inset_limits]
        case["region"] = [float(v) for v in r._inset_region]
        p = r._inset_proj
        case["inset_projection"] = [p.name, p.lon_0, p.lat_0]
        box = r.inset_box_xy()
        case["box"] = None if box is None else {
            "target": box[0],
            "x": [None if not np.isfinite(v) else float(v) for v in box[1]],
            "y": [None if not np.isfinite(v) else float(v) for v in box[2]]}
        cases.append(case)
    return cases


def main():
    data = {
        "extent": extent_cases(),
        "ticks": tick_cases(),
        "labels": label_cases(),
        "markers": marker_cases(),
        "scale_bar": scale_bar_cases(),
        "inset": inset_cases(),
    }
    OUT.write_text(json.dumps(data, indent=None, separators=(",", ":"), allow_nan=False),
                   encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
