"""Renderer tests: features outside a Lambert region and exporting the map."""

from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pymappr.geo.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.renderer.geometry import export_geometry  # noqa: E402
from renderer_helpers import _renderer  # noqa: E402


# ------------------------------------------- features outside a Lambert region


def test_natural_earth_features_outside_a_lambert_region_are_dropped():
    # Lagos (3E, 6N) is south of Lambert: Europe's 30N edge: its label and
    # marker are dropped, not stacked along the edge with every other
    # out-of-region feature. Paris stays.
    import pandas as pd

    r = _renderer(9.0, 6.5)
    r.set_projection("Lambert: Europe")
    frame = pd.DataFrame({"x": [3.4, 2.35], "y": [6.45, 48.86],
                          "text": ["Lagos", "Paris"], "min_label": [1, 1],
                          "min_zoom": [1, 1]})
    r.store.label_points = lambda _key, region=None: frame
    r.store.point_features = lambda _key: frame
    for xs, ys in (r._label_xy("cities"), r._point_xy("cities")[:2]):
        assert np.isnan(xs[0]) and np.isnan(ys[0])
        assert np.isfinite(xs[1]) and np.isfinite(ys[1])


def test_the_lambert_graticule_draws_no_chords_across_the_region():
    # Parallels must run west to east around the centre: wrapping longitudes
    # into lon_0 +/- 180 must not send part of one back to the far edge.
    r = _renderer(9.0, 6.5)
    for name in ("Lambert: Europe", "Lambert: N. America"):
        r.set_projection(name)
        r.set_graticule(10)
        # Meridians every 10 degrees from -180 to 180 come first.
        parallels = r._artists["graticule"][0].get_segments()[37:]
        assert parallels
        for seg in parallels:
            assert (np.diff(seg[:, 0]) >= -1e-6).all(), name


def test_lambert_labels_sit_on_the_part_of_a_feature_on_the_map():
    # Norway's whole-country anchor is on Svalbard (79.8N), Russia's and
    # Kazakhstan's east of 65E: all off Lambert: Europe, yet most of each
    # country is on it. Their labels anchor on the part that is drawn.
    store = LayerStore()
    if store.check_data():
        pytest.skip("map data not downloaded")
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, store)
    world = store.label_points("countries")
    norway = world[world["text"] == "Norway"].iloc[0]
    assert norway["y"] > 72.0   # the unclipped anchor, unchanged
    r.set_projection("Lambert: Europe")
    points = r._label_points("countries")
    xs, ys = r._label_xy("countries")
    x0, x1, y0, y1 = r.proj.bounds
    names = list(points["text"])
    for name in ("Norway", "Russia", "Kazakhstan"):
        i = names.index(name)
        assert np.isfinite([xs[i], ys[i]]).all(), name
        assert x0 <= xs[i] <= x1 and y0 <= ys[i] <= y1, name
    assert points["y"].to_numpy()[names.index("Norway")] < 72.0
    assert "Nigeria" not in names
    # World projections keep the whole-feature anchors.
    r.set_projection("Robinson")
    assert r._label_points("countries") is world


def test_label_and_marker_caches_follow_the_region_not_just_the_crs():
    # Lambert: Africa and Lambert Azimuthal (custom) centred on (20, 5)
    # share a CRS but not a region: switching between them must not reuse
    # the other's anchors or out-of-region mask.
    store = LayerStore()
    if store.check_data():
        pytest.skip("map data not downloaded")
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, store)
    r.set_projection("Lambert: Africa")
    africa = r.proj
    r._label_xy("countries")
    r._point_xy("cities")
    r.set_projection("Lambert Azimuthal (custom)", 20.0, 5.0)
    assert r.proj.crs == africa.crs and r.proj != africa
    points = r._label_points("countries")
    xs, ys = r._label_xy("countries")
    assert len(xs) == len(points)
    ex, ey = r.proj.forward(points["x"].to_numpy(), points["y"].to_numpy(),
                            clamp=False)
    np.testing.assert_array_equal(xs, ex)
    np.testing.assert_array_equal(ys, ey)
    features = store.point_features("cities")
    px, _py, _zoom = r._point_xy("cities")
    fx, _fy = r.proj.forward(features["x"].to_numpy(),
                             features["y"].to_numpy(), clamp=False)
    np.testing.assert_array_equal(px, fx)


def _black_marker_renderer():
    r = _renderer(4.0, 3.0)
    r.set_extent("World")
    r.ax.plot([-60.0], [20.0], marker="s", markersize=8, color="black")
    return r


def test_a_tiff_is_lzw_compressed_greyscale_without_alpha(tmp_path):
    from PIL import Image

    r = _black_marker_renderer()
    path = tmp_path / "map.tif"
    r.save_image(str(path), "tiff", dpi=150)
    with Image.open(path) as img:
        assert img.mode == "L"
        assert img.info["compression"] == "tiff_lzw"
        assert img.info["dpi"] == (150, 150)
        assert img.size == (600, 450)


def test_a_tiff_with_colour_stays_rgb(tmp_path):
    from PIL import Image

    r = _black_marker_renderer()
    r.ax.plot([0.0], [0.0], marker="o", markersize=8, color="red")
    path = tmp_path / "map.tif"
    r.save_image(str(path), "tiff", dpi=100)
    with Image.open(path) as img:
        assert img.mode == "RGB"
        assert img.info["compression"] == "tiff_lzw"


def test_vector_exports_keep_text_editable(tmp_path):
    r = _black_marker_renderer()
    r.ax.set_title("Nebulobunus")
    r.save_image(str(tmp_path / "map.pdf"), "pdf")
    r.save_image(str(tmp_path / "map.svg"), "svg")
    pdf = (tmp_path / "map.pdf").read_bytes()
    assert b"/FontFile2" in pdf and b"/Subtype /Type3" not in pdf  # TrueType
    svg = (tmp_path / "map.svg").read_text(encoding="utf-8")
    assert "<text" in svg and "Nebulobunus" in svg
    # The setting is scoped to the export, not left on for the session.
    assert matplotlib.rcParams["pdf.fonttype"] == 3


def test_export_geometry_scales_the_map_to_a_print_width():
    # A 9 x 6.5 in landscape canvas, axes filling it inside fixed margins.
    margins = (0.05, 0.05, 0.95, 0.95)
    bounds = (0.05, 0.05, 0.9, 0.9)
    (w, h), rect = export_geometry(bounds, 9.0, 6.5, margins,
                                   width_in=17 / 2.54)
    assert w == pytest.approx(17 / 2.54)
    # The tick-label gutters keep their inches; the map box keeps its shape.
    assert rect[0] * w == pytest.approx(0.05 * 9.0)
    box_w, box_h = rect[2] * w, rect[3] * h
    assert box_w / box_h == pytest.approx((0.9 * 9.0) / (0.9 * 6.5))


def test_export_geometry_keeps_a_tall_map_within_the_page_height():
    margins = (0.05, 0.05, 0.95, 0.95)
    bounds = (0.05, 0.05, 0.9, 0.9)
    (w, h), _rect = export_geometry(bounds, 4.0, 12.0, margins,
                                    width_in=17 / 2.54,
                                    max_height_in=25 / 2.54)
    assert h == pytest.approx(25 / 2.54)
    assert w < 17 / 2.54


def test_a_tiff_saved_at_a_print_width_is_that_wide(tmp_path):
    from PIL import Image

    r = _black_marker_renderer()   # a 4 x 3 in canvas
    path = tmp_path / "map.tif"
    r.save_image(str(path), "tiff", dpi=300, width_cm=17.0)
    with Image.open(path) as img:
        assert abs(img.size[0] - 17 / 2.54 * 300) <= 1  # whole pixels
    # The on-screen figure is put back.
    assert tuple(r.fig.get_size_inches()) == pytest.approx((4.0, 3.0))
    assert r.export_size_inches(17.0)[0] == pytest.approx(17 / 2.54)


def test_a_sharp_export_draws_finer_coastlines(monkeypatch):
    r = _renderer(9.0, 6.5)
    seen = []
    monkeypatch.setattr(r, "_sync_resolutions",
                        lambda: seen.append(r._detail_boost))
    with r._vector_detail_for(600, 17.0):
        pass
    # 17 cm at 600 dpi is ~4000 px against 900 on screen: two zoom levels.
    assert seen[0] == pytest.approx(np.log2(17 / 2.54 * 600 / 900), abs=1e-6)
    assert seen[-1] == 0.0 and r._detail_boost == 0.0
    seen.clear()
    with r._vector_detail_for(100):  # screen resolution: nothing to do
        pass
    assert seen == []
