"""Degree labels on the graticule: thinning and frame crossings."""

from __future__ import annotations

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pymappr.geo.layers import LayerStore  # noqa: E402
from pymappr.renderer import MapRenderer  # noqa: E402
from pymappr.renderer.grid_labels import (edge_crossings,  # noqa: E402
                                          edge_ticks, label_stride)


def _renderer(projection="Equirectangular"):
    fig = Figure(figsize=(9.29, 6.59), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, LayerStore())
    r.set_projection(projection)
    return r


def _labels(r):
    r.fig.canvas.draw()
    return ([t.get_text() for t in r.ax.get_xticklabels() if t.get_text()],
            [t.get_text() for t in r.ax.get_yticklabels() if t.get_text()])


def test_edge_crossings_interpolate_and_skip_gaps():
    xs = np.array([0.0, 2.0, np.nan, 4.0, 6.0])
    ys = np.array([-1.0, 1.0, 0.0, -1.0, 1.0])
    assert edge_crossings(xs, ys, 0.0, "x") == pytest.approx([1.0, 5.0])


def test_a_short_straight_line_is_continued_to_the_edge():
    view = ((0.0, 10.0), (0.0, 10.0))
    # A horizontal line stopping at x = 0.2, just inside the left edge.
    xs = np.linspace(9.0, 0.2, 20)
    ys = np.full(20, 4.0)
    assert edge_ticks(xs, ys, view, "y") == pytest.approx([4.0])
    # A steep curve heading away gets no label rather than a wrong one.
    ys = 4.0 + (9.0 - xs) ** 2 / 4.0
    assert edge_ticks(xs, ys, view, "y") == []


@pytest.mark.parametrize("spacing, length, stride", [
    (40.0, 20.0, 1), (15.0, 20.0, 2), (5.0, 20.0, 4), (0.1, 20.0, 36)])
def test_label_stride(spacing, length, stride):
    assert label_stride(spacing, length) == stride


def test_a_dense_world_grid_is_thinned_to_readable_labels():
    r = _renderer()
    r.set_extent("World")
    r.set_graticule(5.0)
    xs, ys = _labels(r)
    assert xs and len(xs) < 72 / 2
    # Kept labels are a whole number of lines apart, at round degrees.
    assert all(int(t.rstrip("\N{DEGREE SIGN}EW").rstrip("\N{DEGREE SIGN}"))
               % 10 == 0 for t in xs)


def test_a_zoomed_grid_keeps_every_label():
    r = _renderer()
    r.set_extent((-100.0, -77.0, 6.0, 21.0))
    r.set_graticule(5.0)
    xs, ys = _labels(r)
    degrees = [int(t.rstrip("W").rstrip("\N{DEGREE SIGN}")) for t in xs]
    assert len(degrees) >= 5
    assert all(a - b == 5 for a, b in zip(degrees, degrees[1:]))


def test_a_lambert_map_is_labelled_where_the_grid_meets_the_frame():
    r = _renderer("Lambert Azimuthal (custom)")
    r.set_projection("Lambert Azimuthal (custom)", -178.0, -17.0)
    r.set_extent((175.0, 191.0, -23.5, -11.0))
    r.set_graticule(5.0)
    xs, ys = _labels(r)
    assert "180\N{DEGREE SIGN}" in xs and "175\N{DEGREE SIGN}W" in xs
    assert "15\N{DEGREE SIGN}S" in ys and "20\N{DEGREE SIGN}S" in ys


def test_a_pointed_pole_world_labels_its_meridians_at_the_equator():
    # Every Mollweide meridian meets the bottom edge at the pole, where
    # only one label (0°) used to survive.
    r = _renderer("Mollweide")
    r.set_extent("World")
    r.set_graticule(30.0)
    xs, _ys = _labels(r)
    assert {"120\N{DEGREE SIGN}W", "60\N{DEGREE SIGN}W", "0\N{DEGREE SIGN}",
            "60\N{DEGREE SIGN}E", "120\N{DEGREE SIGN}E"} <= set(xs)
    ticks = sorted(r.ax.get_xticks())
    equator = [float(r.proj.forward(np.array([lon]), np.array([0.0]))[0][0])
               for lon in (-60.0, 0.0, 60.0)]
    assert [min(ticks, key=lambda t: abs(t - x)) for x in equator] == \
        pytest.approx(equator)


def test_a_flat_pole_world_keeps_its_labels_on_the_edge():
    r = _renderer("Robinson")
    r.set_extent("World")
    r.set_graticule(30.0)
    xs, _ys = _labels(r)
    assert len(xs) >= 6
    # Where the 60°E meridian meets the bottom, not where it crosses the
    # equator: the pole line is narrower than the equator.
    loc = r.ax.xaxis.get_major_locator()
    at = next(x for x, lon in loc.degrees.items() if lon == 60.0)
    eq = float(r.proj.forward(np.array([60.0]), np.array([0.0]))[0][0])
    assert at < 0.9 * eq


def test_the_globe_and_hidden_labels_stay_unlabelled():
    r = _renderer("Globe (Orthographic)")
    r.set_graticule(10.0)
    assert _labels(r) == ([], [])
    r = _renderer("Robinson")
    r.set_graticule(10.0, show_labels=False)
    assert _labels(r) == ([], [])
