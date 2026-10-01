"""Scale bar and compass: the maths, the drawing, and the round trip.

The scale bar is the one decoration whose correctness is not obvious by
eye - a bar drawn 20% short still looks like a scale bar - so most of what
is here measures the bar that was actually drawn and compares it with the
label it carries.
"""

from __future__ import annotations

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from pymappr.geo.layers import CONTINENT_EXTENTS, LayerStore
from pymappr.geo.projections import GLOBE, get_projection
from pymappr.renderer import MapRenderer
from pymappr.styling.decorations import (CompassOptions, ScaleBarOptions,
                                         corner_anchor, format_length,
                                         nice_length, unit_metres)

# Projections whose whole extent is drawable, so a corner of the axes is
# still on the map. Robinson, Mollweide and the globe are handled apart.
FLAT = ["Equirectangular", "Mercator", "Lambert: N. America"]


def _renderer(projection: str = "Equirectangular",
              extent: str = "Africa") -> MapRenderer:
    """A renderer on an Agg canvas, framed on a real continent. Touches no
    map-data layers, so it needs no Natural Earth download."""
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, LayerStore())
    r.set_projection(projection)
    r.set_extent(CONTINENT_EXTENTS[extent])
    return r


def _bars(renderer) -> list[tuple[float, float, float]]:
    """(x0, x1, y_middle) in axes fractions for each drawn bar, top first."""
    rects = [a for a in renderer._artists.get("scale_bar", [])
             if isinstance(a, Rectangle)]
    rows = sorted({round(a.get_y(), 6) for a in rects}, reverse=True)
    out = []
    for y in rows:
        row = [a for a in rects if round(a.get_y(), 6) == y]
        out.append((min(a.get_x() for a in row),
                    max(a.get_x() + a.get_width() for a in row),
                    y + row[0].get_height() / 2))
    return out


def _labels(renderer) -> list[str]:
    return [a.get_text() for a in renderer._artists.get("scale_bar", [])
            if hasattr(a, "get_text")]


# ------------------------------------------------------- ground distances

@pytest.mark.parametrize("projection", ["Equirectangular", "Mercator",
                                        "Robinson", "Mollweide", GLOBE])
def test_one_degree_of_longitude_at_the_equator(projection):
    """Every world projection measures the same ground distance, because the
    measurement is made on lon/lat rather than in axis units. (The regional
    Lambert presets clip to their own region, so they are measured inside
    it by :func:`test_distances_are_ellipsoidal_not_spherical`.)"""
    proj = get_projection(projection)
    x0, y0 = (float(v) for v in proj.forward(0.0, 0.0))
    x1, y1 = (float(v) for v in proj.forward(1.0, 0.0))
    km = proj.ground_distance(x0, y0, x1, y1) / 1000
    assert km == pytest.approx(111.319, abs=0.01)


def test_distances_are_ellipsoidal_not_spherical():
    """A degree of longitude shortens with latitude; a degree of latitude
    barely changes. Catches a transform that silently returns axis units."""
    proj = get_projection("Lambert: N. America")
    at = lambda lon, lat: tuple(float(v) for v in proj.forward(lon, lat))
    east = proj.ground_distance(*at(-100.0, 40.0), *at(-99.0, 40.0))
    north = proj.ground_distance(*at(-100.0, 40.0), *at(-100.0, 41.0))
    assert east / 1000 == pytest.approx(85.4, abs=0.5)
    assert north / 1000 == pytest.approx(111.0, abs=0.5)


def test_a_regional_projection_clips_outside_its_own_region():
    """Lambert: N. America projects only its own span, so two points off in
    Africa collapse onto the same clipped meridian - zero apart, not a
    distance measured through the projection's undefined part."""
    proj = get_projection("Lambert: N. America")
    at = lambda lon, lat: tuple(float(v) for v in proj.forward(lon, lat))
    assert proj.ground_distance(*at(0.0, 0.0), *at(1.0, 0.0)) == 0.0


def test_unmeasurable_points_come_back_as_nan():
    proj = get_projection(GLOBE, 0.0, 0.0)
    assert np.isnan(proj.ground_distance(float("nan"), 0.0, 1.0, 1.0))


# ------------------------------------------------------------ nice lengths

@pytest.mark.parametrize("metres", [55, 300, 1234, 137_000, 999_999,
                                    4.2e6, 3.0e7])
@pytest.mark.parametrize("units", ["km", "mi"])
def test_nice_length_is_round_and_never_longer_than_asked(metres, units):
    chosen = nice_length(metres, units)
    assert 0 < chosen <= metres
    mantissa = chosen / unit_metres(units)
    mantissa /= 10.0 ** np.floor(np.log10(mantissa))
    assert round(mantissa, 6) in (1.0, 2.0, 3.0, 5.0)


def test_a_metric_bar_under_a_kilometre_is_labelled_in_metres():
    assert format_length(500.0, "km") == "500 m"
    assert format_length(2_000_000.0, "km") == "2000 km"
    assert format_length(1609.344, "mi") == "1 mi"


def test_corner_anchor_maps_each_corner_to_its_own_quadrant():
    assert corner_anchor("lower left") == (0.03, 0.03)
    assert corner_anchor("upper right") == (0.97, 0.97)
    # An unknown corner falls back rather than raising.
    assert corner_anchor("nowhere") == corner_anchor("lower left")


# --------------------------------------------------- the bar that is drawn

@pytest.mark.parametrize("projection", FLAT)
@pytest.mark.parametrize("position", ["lower left", "upper right"])
def test_the_drawn_bar_is_the_length_its_label_claims(projection, position):
    r = _renderer(projection)
    r.set_scale_bar(ScaleBarOptions(show=True, position=position))
    r.fig.canvas.draw()
    (x0, x1, y), = _bars(r)
    label, = _labels(r)
    claimed = float(label.split()[0]) * (1000 if label.endswith("km") else 1)
    assert r._span_metres(x0, x1, y) == pytest.approx(claimed, rel=0.01)


def test_zooming_in_shortens_the_bar_monotonically():
    r = _renderer()
    r.set_scale_bar(ScaleBarOptions(show=True))
    r.fig.canvas.draw()
    lengths = []
    for _ in range(4):
        (x0, x1, y), = _bars(r)
        lengths.append(r._span_metres(x0, x1, y))
        r.zoom(4)
        r.fig.canvas.draw()
    assert lengths == sorted(lengths, reverse=True)
    assert lengths[0] > lengths[-1] * 10


def test_each_unit_of_a_both_bar_gets_its_own_round_length():
    """Two stacked bars, not one bar with an unreadable second label."""
    r = _renderer()
    r.set_scale_bar(ScaleBarOptions(show=True, units="both"))
    r.fig.canvas.draw()
    assert _labels(r) == ["2000 km", "1000 mi"]
    top, bottom = _bars(r)
    assert r._span_metres(*top) == pytest.approx(2_000_000, rel=0.01)
    assert r._span_metres(*bottom) == pytest.approx(1000 * 1609.344, rel=0.01)


def test_a_second_unit_stays_inside_the_axes():
    """The lower label is drawn below its bar, so the stack has to be
    lifted clear of the frame or the label falls off the map."""
    r = _renderer()
    r.set_scale_bar(ScaleBarOptions(show=True, units="both"))
    r.fig.canvas.draw()
    texts = [a for a in r._artists["scale_bar"] if hasattr(a, "get_text")]
    assert min(t.get_position()[1] for t in texts) > 0.0


def test_a_fixed_length_is_honoured():
    r = _renderer()
    r.set_scale_bar(ScaleBarOptions(show=True, length_mode="fixed",
                                    fixed_length=750))
    r.fig.canvas.draw()
    assert _labels(r) == ["750 km"]
    (x0, x1, y), = _bars(r)
    assert r._span_metres(x0, x1, y) == pytest.approx(750_000, rel=0.01)


def test_a_fixed_length_too_big_for_the_view_is_refused_with_a_reason():
    r = _renderer()
    r.set_scale_bar(ScaleBarOptions(show=True, length_mode="fixed",
                                    fixed_length=500_000))
    r.fig.canvas.draw()
    assert not r._artists.get("scale_bar")
    assert "scale varies" in r.scale_bar_note()


def test_a_plain_bar_is_one_box_and_a_segmented_bar_is_several():
    r = _renderer()
    r.set_scale_bar(ScaleBarOptions(show=True, style="plain"))
    r.fig.canvas.draw()
    plain = [a for a in r._artists["scale_bar"] if isinstance(a, Rectangle)]
    r.set_scale_bar(ScaleBarOptions(show=True, style="segmented", segments=4))
    r.fig.canvas.draw()
    segmented = [a for a in r._artists["scale_bar"]
                 if isinstance(a, Rectangle)]
    assert len(plain) == 1
    assert len(segmented) == 4


@pytest.mark.parametrize("projection", FLAT + ["Robinson", "Mollweide",
                                               "Winkel Tripel", GLOBE])
def test_a_bar_is_drawn_or_explained_on_every_projection(projection):
    """Silence is the one unacceptable outcome: either the bar appears, or
    the app can say why it did not."""
    r = _renderer(projection)
    r.set_scale_bar(ScaleBarOptions(show=True))
    r.fig.canvas.draw()
    assert r._artists.get("scale_bar") or r.scale_bar_note()


def test_a_world_view_at_the_poles_refuses_rather_than_lying():
    """Near a pole on a world map, widening the bar shortens it on the
    ground, so no honest bar of a round length exists there."""
    fig = Figure(figsize=(9, 6.5), dpi=100)
    FigureCanvasAgg(fig)
    r = MapRenderer(fig, LayerStore())
    r.set_projection("Winkel Tripel")
    r.set_scale_bar(ScaleBarOptions(show=True))
    fig.canvas.draw()
    assert not r._artists.get("scale_bar")
    assert "zoom in" in r.scale_bar_note()


def test_the_bar_survives_a_projection_change():
    r = _renderer()
    r.set_scale_bar(ScaleBarOptions(show=True))
    r.fig.canvas.draw()
    assert r._artists.get("scale_bar")
    r.set_projection("Mercator")
    r.fig.canvas.draw()
    assert r._artists.get("scale_bar")


def test_hiding_the_bar_removes_its_artists():
    r = _renderer()
    r.set_scale_bar(ScaleBarOptions(show=True))
    r.fig.canvas.draw()
    r.set_scale_bar(ScaleBarOptions(show=False))
    r.fig.canvas.draw()
    assert not r._artists.get("scale_bar")


# ------------------------------------------------------------------ compass

def test_the_compass_defaults_reproduce_the_original_arrow():
    r = _renderer()
    r.set_compass(CompassOptions(show=True))
    r.fig.canvas.draw()
    annotation, = r._artists["compass"]
    assert annotation.get_text() == "N"
    assert annotation.xy == (0.975, 0.975)


@pytest.mark.parametrize("position", ["lower left", "lower right",
                                      "upper left", "upper right"])
def test_the_compass_arrow_always_points_into_the_map(position):
    r = _renderer()
    r.set_compass(CompassOptions(show=True, position=position))
    r.fig.canvas.draw()
    annotation, = r._artists["compass"]
    tip_y = annotation.xy[1]
    tail_y = annotation.get_position()[1]
    assert 0.0 < tail_y < 1.0
    # The arrow runs from the tail towards the tip, away from the frame.
    assert (tip_y > tail_y) == (position.startswith("upper"))


def test_the_triangle_compass_draws_a_polygon_and_a_label():
    r = _renderer()
    r.set_compass(CompassOptions(show=True, style="triangle"))
    r.fig.canvas.draw()
    kinds = {type(a).__name__ for a in r._artists["compass"]}
    assert kinds == {"Polygon", "Text"}


# ------------------------------------------------------------- persistence

def test_options_round_trip_through_a_dict():
    bar = ScaleBarOptions(show=True, units="both", position="upper left",
                          style="plain", length_mode="fixed",
                          fixed_length=250.0, anchor_x=0.4, anchor_y=0.6)
    assert ScaleBarOptions.from_dict(bar.to_dict()) == bar
    compass = CompassOptions(show=True, position="lower right",
                             style="triangle", size=1.5)
    assert CompassOptions.from_dict(compass.to_dict()) == compass


def test_a_project_written_before_these_existed_still_loads():
    assert ScaleBarOptions.from_dict(None) == ScaleBarOptions()
    assert ScaleBarOptions.from_dict({}) == ScaleBarOptions()
    assert CompassOptions.from_dict(None) == CompassOptions()


def test_unknown_keys_are_ignored_and_strings_are_coerced():
    """Tk variables hand back strings, and a future version may drop a
    field; neither should stop an older project from opening."""
    bar = ScaleBarOptions.from_dict({"show": True, "fontsize": "9",
                                     "segments": "6", "gone": 1})
    assert (bar.show, bar.fontsize, bar.segments) == (True, 9.0, 6)


def test_a_dragged_anchor_overrides_the_chosen_corner():
    bar = ScaleBarOptions(show=True, position="upper right",
                          anchor_x=0.2, anchor_y=0.3)
    assert bar.anchor == (0.2, 0.3)
    assert ScaleBarOptions(show=True).anchor is None
