"""Tests for the layer catalog: resolution switching and data wiring."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pymappr.layers import (BATHYMETRY_STEPS, DERIVED, LAYER_SPECS,
                            OPTIONAL_LAYERS)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _fetch_data_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_data", REPO_ROOT / "scripts" / "fetch_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolution_switching_picks_finer_data_when_zoomed():
    countries = LAYER_SPECS["countries"]
    assert countries.directory_for_zoom(0.0) == "ne_110m_admin_0_countries"
    assert countries.directory_for_zoom(2.0) == "ne_50m_admin_0_countries"
    assert countries.directory_for_zoom(6.0) == "ne_10m_admin_0_countries"
    # No zoom given: the default (mid) resolution, so label anchors and
    # non-interactive callers stay stable.
    assert countries.directory_for_zoom(None) == countries.directory


def test_single_resolution_layers_ignore_zoom():
    states = LAYER_SPECS["states"]
    for zoom in (None, 0.0, 5.0):
        assert states.directory_for_zoom(zoom) == states.directory


def test_every_spec_directory_is_downloaded_by_fetch_data():
    fetch_data = _fetch_data_module()
    ne_archives = {entry[2] for entry in fetch_data.VECTOR_LAYERS}
    extra_dirs = {entry[0] for entry in fetch_data.EXTRA_LAYERS}
    for key, spec in LAYER_SPECS.items():
        for directory in spec.directories():
            if key in OPTIONAL_LAYERS:
                assert directory in extra_dirs, (
                    f"{spec.key} needs {directory}, which fetch_data.py "
                    "does not download as an optional layer")
            else:
                assert directory in ne_archives, (
                    f"{spec.key} needs {directory}, which fetch_data.py "
                    "does not download")
    assert "ne_10m_bathymetry_all" in ne_archives


def test_optional_layers_have_specs_and_downloads():
    fetch_data = _fetch_data_module()
    extra_dirs = {entry[0] for entry in fetch_data.EXTRA_LAYERS}
    for key in OPTIONAL_LAYERS:
        assert key in LAYER_SPECS, f"optional layer {key} has no spec"
        assert LAYER_SPECS[key].directory in extra_dirs


def test_derived_layers_reference_real_sources():
    for key, (source, _filt) in DERIVED.items():
        assert source in LAYER_SPECS, f"{key} derives from unknown {source}"


def test_bathymetry_steps_are_sorted_shallow_to_deep():
    depths = [depth for _letter, depth in BATHYMETRY_STEPS]
    assert depths == sorted(depths)
    assert depths[0] == 0 and depths[-1] == 10000
