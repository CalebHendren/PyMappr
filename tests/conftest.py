"""Skip the checks that compare MiniMappr with PyMappr when PyMappr's code is
not available (see tests/test_minimappr.py)."""

import importlib.util

import pytest


def pytest_collection_modifyitems(config, items):
    if importlib.util.find_spec("pymappr") is not None:
        return
    skip = pytest.mark.skip(reason="PyMappr not found; set PYMAPPR_DIR")
    for item in items:
        code = getattr(item.function, "__code__", None)
        names = code.co_names if code else ()
        if any(n == "PYMAPPR" or n.split(".")[0] == "pymappr" for n in names):
            item.add_marker(skip)
