"""Tests for point styling: markers, palette assignment, color-by grouping."""

import matplotlib.markers
import pandas as pd

from ezmaps.styles import (DEFAULT_PALETTE, MARKER_CYCLE, MARKERS,
                           default_styles, group_points)


def test_markers_are_valid_matplotlib_markers():
    valid = matplotlib.markers.MarkerStyle.markers
    for name, marker in MARKERS.items():
        assert marker in valid, name
    for name in MARKER_CYCLE:
        assert name in MARKERS


def test_default_styles_cycles_colors_circle_markers():
    styles = default_styles(["a", "b", "c"])
    assert [s.color for s in styles.values()] == DEFAULT_PALETTE[:3]
    assert all(s.marker == "Circle" for s in styles.values())


def test_default_styles_vary_symbols():
    styles = default_styles(["a", "b", "c"], vary_symbols=True)
    markers = [s.marker for s in styles.values()]
    assert markers == MARKER_CYCLE[:3]


def test_color_by_shares_color_within_family_and_varies_shape():
    # Felines/canines scenario: color per family, shape per animal.
    labels = ["Domestic Cat", "Lion", "Cheetah", "Domestic Dog", "Gray Wolf"]
    families = ["Felines", "Felines", "Felines", "Canines", "Canines"]
    styles = default_styles(labels, color_keys=families)

    feline_colors = {styles[lb].color for lb, fam in zip(labels, families)
                     if fam == "Felines"}
    canine_colors = {styles[lb].color for lb, fam in zip(labels, families)
                     if fam == "Canines"}
    assert len(feline_colors) == 1
    assert len(canine_colors) == 1
    assert feline_colors != canine_colors

    feline_markers = [styles[lb].marker for lb, fam in zip(labels, families)
                      if fam == "Felines"]
    assert len(set(feline_markers)) == 3  # each cat its own shape


def test_group_points_orders_by_first_appearance():
    frame = pd.DataFrame({"name1": ["b", "a", "b"],
                          "lon": [1.0, 2.0, 3.0], "lat": [4.0, 5.0, 6.0]})
    groups = group_points(frame, "name1")
    assert [label for label, _ in groups] == ["b", "a"]
    assert len(groups[0][1]) == 2
