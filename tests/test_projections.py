"""Tests for map projections, including the regional Lambert family."""

from __future__ import annotations

import numpy as np

from pymappr.projections import (GLOBE, LAMBERT_PROJECTIONS, PROJECTIONS,
                                 default_origin, get_projection,
                                 has_custom_origin, is_globe, is_lambert,
                                 lambert_default_origin)


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
        clip = proj.clip_box()
        assert clip is not None
        _lon0, _lon1, lat0, lat1 = clip
        assert lat0 < lat1
        # Forward-projecting inside the region stays finite.
        lat_mid = (proj.min_lat + proj.max_lat) / 2
        xs, ys = proj.forward([proj.lon_0, proj.lon_0 + 5.0],
                              [lat_mid, lat_mid])
        assert np.isfinite(xs).all() and np.isfinite(ys).all()


def test_custom_origin_changes_crs_and_cache_key():
    name = "Lambert: N. America"
    default_lon, default_lat = lambert_default_origin(name)
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
