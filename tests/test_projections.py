"""Tests for map projections, including the regional Lambert family."""

from __future__ import annotations

import numpy as np

from pymappr.projections import (LAMBERT_PROJECTIONS, PROJECTIONS,
                                 get_projection, is_lambert,
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
