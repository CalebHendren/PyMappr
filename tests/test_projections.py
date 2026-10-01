"""Tests for map projections, including the regional Lambert family."""

from __future__ import annotations

import numpy as np

from pymappr.geo.projections import (GLOBE, LAMBERT_PROJECTIONS, PROJECTIONS,
                                     default_origin, get_projection,
                                     has_custom_origin, is_globe, is_lambert)


def test_world_and_lambert_projections_listed():
    for name in ("Equirectangular", "Mercator", "Robinson"):
        assert name in PROJECTIONS
    for name in LAMBERT_PROJECTIONS:
        assert name in PROJECTIONS
        assert is_lambert(name)
    assert not is_lambert("Mercator")


def test_every_projection_builds_finite_bounds():
    for name in PROJECTIONS:
        proj = get_projection(name)
        x0, x1, y0, y1 = proj.bounds
        assert np.isfinite([x0, x1, y0, y1]).all()
        assert x0 < x1 and y0 < y1


def test_equirectangular_is_identity():
    proj = get_projection("Equirectangular")
    assert proj.is_geographic and not proj.is_regional
    xs, ys = proj.forward([10.0, -30.0], [45.0, -12.0])
    assert list(xs) == [10.0, -30.0]
    assert list(ys) == [45.0, -12.0]


def test_lambert_projections_are_regional_and_clip():
    for name in LAMBERT_PROJECTIONS:
        proj = get_projection(name)
        assert proj.is_regional
        clip = proj.clip_shape()
        assert clip is not None
        _lon0, lat0, _lon1, lat1 = clip.bounds
        assert (lat0, lat1) == (proj.min_lat, proj.max_lat)
        # Forward-projecting inside the region stays finite.
        lat_mid = (proj.min_lat + proj.max_lat) / 2
        xs, ys = proj.forward([proj.lon_0, proj.lon_0 + 5.0],
                              [lat_mid, lat_mid])
        assert np.isfinite(xs).all() and np.isfinite(ys).all()


def test_custom_origin_changes_crs_and_cache_key():
    name = "Lambert: N. America"
    default_lon, default_lat = default_origin(name)
    base = get_projection(name)
    assert base.lon_0 == default_lon
    shifted = get_projection(name, default_lon - 20.0, default_lat + 5.0)
    assert shifted.crs != base.crs
    assert shifted.key != base.key
    assert shifted.lon_0 == default_lon - 20.0


def test_world_projections_ignore_origin_overrides():
    # Non-Lambert projections ignore lon_0/lat_0 entirely.
    a = get_projection("Robinson")
    b = get_projection("Robinson", -50.0, 30.0)
    assert a == b


# --------------------------------------------------------------- the globe

def test_globe_is_listed_and_classified():
    assert GLOBE in PROJECTIONS
    assert is_globe(GLOBE)
    assert has_custom_origin(GLOBE)
    assert not is_lambert(GLOBE)
    assert not is_globe("Mercator")
    assert default_origin(GLOBE) == (0.0, 0.0)


def test_globe_shows_only_the_near_hemisphere():
    proj = get_projection(GLOBE)
    assert proj.hemisphere and not proj.is_geographic
    # The centre and near side project to finite coordinates; the exact
    # antipode has no orthographic image and comes back as NaN.
    xs, ys = proj.forward([0.0, 10.0, 180.0], [0.0, 0.0, 0.0])
    assert np.isfinite(xs[:2]).all() and np.isfinite(ys[:2]).all()
    assert np.isnan(xs[2]) and np.isnan(ys[2])


def test_globe_clip_shape_and_horizon():
    proj = get_projection(GLOBE, -100.0, 40.0)
    shape = proj.clip_shape()
    assert shape is not None and shape.area > 0.0
    # A near-side point falls inside the clip cap, the far side outside.
    from shapely.geometry import Point
    assert shape.intersects(Point(-100.0, 40.0))
    assert not shape.intersects(Point(80.0, -40.0))
    hx, hy = proj.horizon_xy()
    assert np.isfinite(hx).all() and np.isfinite(hy).all()
    # The horizon circle closes on itself.
    assert abs(hx[0] - hx[-1]) < 1e-6 and abs(hy[0] - hy[-1]) < 1e-6


def test_globe_custom_centre_changes_crs():
    base = get_projection(GLOBE)
    shifted = get_projection(GLOBE, -100.0, 40.0)
    assert shifted.crs != base.crs
    assert shifted.lon_0 == -100.0 and shifted.lat_0 == 40.0


def test_globe_project_extent_falls_back_to_the_disk():
    # A whole-world extent has its box edges (poles, antimeridian) on the
    # far side; the projected extent still bounds the visible disk.
    proj = get_projection(GLOBE)
    x0, x1, y0, y1 = proj.project_extent((-180.0, 180.0, -90.0, 90.0))
    assert np.isfinite([x0, x1, y0, y1]).all()
    assert x0 < x1 and y0 < y1


# ------------------------------------------------ outside a regional view

def test_lambert_drops_features_outside_the_region_when_not_clamping():
    # Natural Earth labels and markers outside the region are dropped
    # rather than piled onto its edge; the user's own points still clamp.
    proj = get_projection("Lambert: Europe")
    for lon, lat in ((8.0, 9.0),      # Nigeria, south of the 30N edge
                     (70.0, 50.0)):   # Kazakhstan, east of the 65E edge
        xs, ys = proj.forward([lon], [lat], clamp=False)
        assert np.isnan(xs[0]) and np.isnan(ys[0])
        xs, ys = proj.forward([lon], [lat])
        assert np.isfinite(xs[0]) and np.isfinite(ys[0])


def test_lambert_points_inside_the_region_ignore_clamp():
    for name in LAMBERT_PROJECTIONS:
        proj = get_projection(name)
        lat_mid = (proj.min_lat + proj.max_lat) / 2
        lons = [proj.lon_0 - 10.0, proj.lon_0, proj.lon_0 + 10.0]
        lats = [lat_mid, proj.min_lat + 1.0, proj.max_lat - 1.0]
        clamped = proj.forward(lons, lats)
        kept = proj.forward(lons, lats, clamp=False)
        assert np.isfinite(kept).all()
        np.testing.assert_array_equal(clamped, kept)


def test_lambert_wraps_longitudes_around_the_centre():
    # N. America keeps -186..-6: 175E is 185W, beside Alaska, not clamped
    # onto the eastern edge near Ireland.
    proj = get_projection("Lambert: N. America")
    xs, ys = proj.forward([175.0], [52.0])
    assert xs[0] < 0 and abs(xs[0] - -4.89e6) < 0.02e6
    np.testing.assert_array_equal((xs, ys), proj.forward([-185.0], [52.0]))
    # ... and a point that is only inside the region once wrapped is kept.
    xs, ys = proj.forward([178.0], [60.0], clamp=False)
    np.testing.assert_array_equal((xs, ys), proj.forward([-182.0], [60.0]))
    assert np.isfinite(xs).all()
    # Centred on the antimeridian, 170W is 10 degrees east of the centre.
    proj = get_projection("Lambert Azimuthal (custom)", 180.0, 0.0)
    xs, ys = proj.forward([-170.0], [0.0], clamp=False)
    assert xs[0] > 0 and np.isfinite(ys).all()
    np.testing.assert_array_equal((xs, ys), proj.forward([190.0], [0.0]))


def test_label_region_is_the_lambert_map_area():
    from shapely.geometry import Point

    for name in ("Robinson", "Equirectangular", GLOBE):
        assert get_projection(name).label_region() is None
    europe = get_projection("Lambert: Europe").label_region()
    assert europe.covers(Point(20.0, 60.0))
    assert not europe.covers(Point(8.0, 9.0))     # south of 30N
    assert not europe.covers(Point(70.0, 50.0))   # east of 65E
    # N. America's 186W..6W runs past the antimeridian to 174E.
    america = get_projection("Lambert: N. America").label_region()
    assert america.covers(Point(176.0, 60.0))
    assert america.covers(Point(-100.0, 40.0))
    assert not america.covers(Point(100.0, 60.0))
