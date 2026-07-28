"""Tests for point styling: markers, palette assignment, color-by grouping."""

import matplotlib.markers
import pandas as pd

from pymappr.styles import (DEFAULT_PALETTE, MARKER_CYCLE, MARKERS,
                            OPEN_SUFFIX, PointStyle, attribute_style_maps,
                            default_styles, group_points, marker_load,
                            nests_within, resolve_nesting,
                            style_by_attributes)


def test_markers_are_valid_matplotlib_markers():
    valid = matplotlib.markers.MarkerStyle.markers
    for name, marker in MARKERS.items():
        assert marker in valid, name
    for name in MARKER_CYCLE:
        assert name in MARKERS


def test_every_marker_has_solid_and_open_versions():
    solid = [name for name in MARKERS if not name.endswith(OPEN_SUFFIX)]
    for name in solid:
        open_name = name + OPEN_SUFFIX
        assert open_name in MARKERS
        # Openness is a fill style: both names share the marker shape.
        assert MARKERS[open_name] == MARKERS[name]
        assert not PointStyle(marker=name).is_open
        assert PointStyle(marker=open_name).is_open
        assert (PointStyle(marker=open_name).mpl_marker
                == PointStyle(marker=name).mpl_marker)


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


def _insect_frame():
    # Two orders, three families (nested), a few points each.
    return pd.DataFrame({
        "name1": ["Hemiptera", "Hemiptera", "Lepidoptera", "Lepidoptera",
                  "Hemiptera"],
        "name2": ["Pentatomidae", "Reduviidae", "Nymphalidae",
                  "Nymphalidae", "Pentatomidae"],
        "lon": [1.0, 2.0, 3.0, 4.0, 5.0],
        "lat": [1.0, 2.0, 3.0, 4.0, 5.0],
    })


def test_attribute_style_maps_assign_color_and_symbol_per_value():
    frame = _insect_frame()
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2")
    # One color per order, one marker per family, ordered by first appearance.
    assert list(color_map) == ["Hemiptera", "Lepidoptera"]
    assert list(color_map.values()) == DEFAULT_PALETTE[:2]
    assert list(symbol_map) == ["Pentatomidae", "Reduviidae", "Nymphalidae"]
    # Families nest inside orders, so the marker cycle restarts per order:
    # the colour keeps the two circles apart. Two shapes, not three.
    assert symbol_map == {"Pentatomidae": MARKER_CYCLE[0],
                          "Reduviidae": MARKER_CYCLE[1],
                          "Nymphalidae": MARKER_CYCLE[0]}


def test_crossed_columns_keep_globally_unique_markers():
    # Every habitat/sex combination occurs, so a repeated shape would make
    # (colour, shape) pairs ambiguous - the cycle must not restart.
    frame = pd.DataFrame({
        "name1": ["forest", "forest", "scrub", "scrub"],
        "name2": ["male", "female", "male", "female"],
        "lon": [1.0, 2.0, 3.0, 4.0], "lat": [1.0, 2.0, 3.0, 4.0],
    })
    _colors, symbol_map = attribute_style_maps(frame, "name1", "name2")
    assert list(symbol_map.values()) == MARKER_CYCLE[:2]
    assert len(set(symbol_map.values())) == 2


def test_nests_within_detects_hierarchy_and_cross_product():
    frame = _insect_frame()
    assert nests_within(frame, "name1", "name2") is True
    # Reversed, an order spans several families, so it does not nest.
    assert nests_within(frame, "name2", "name1") is False
    crossed = pd.DataFrame({
        "name1": ["forest", "forest", "scrub", "scrub"],
        "name2": ["male", "female", "male", "female"],
        "lon": [1.0, 2.0, 3.0, 4.0], "lat": [1.0, 2.0, 3.0, 4.0],
    })
    assert nests_within(crossed, "name1", "name2") is False
    # Missing keys and empty frames are not hierarchies.
    assert nests_within(frame, "name1", "nope") is False
    assert nests_within(frame, None, "name2") is False
    assert nests_within(frame.iloc[:0], "name1", "name2") is False


def test_resolve_nesting_honours_the_users_choice():
    frame = _insect_frame()
    crossed = pd.DataFrame({
        "name1": ["forest", "forest", "scrub", "scrub"],
        "name2": ["male", "female", "male", "female"],
        "lon": [1.0, 2.0, 3.0, 4.0], "lat": [1.0, 2.0, 3.0, 4.0],
    })
    # "auto" is what nests_within says.
    assert resolve_nesting(frame, "name1", "name2", "auto") is True
    assert resolve_nesting(crossed, "name1", "name2", "auto") is False
    # The other two override it in either direction.
    assert resolve_nesting(crossed, "name1", "name2", "always") is True
    assert resolve_nesting(frame, "name1", "name2", "never") is False
    # It still takes two real columns to nest, whatever the mode.
    assert resolve_nesting(frame, "name1", None, "always") is False
    assert resolve_nesting(frame, "name1", "nope", "always") is False
    assert resolve_nesting(frame.iloc[:0], "name1", "name2", "always") is False


def test_marker_load_counts_shapes_the_reader_must_tell_apart():
    frame = _insect_frame()
    # Nested: the biggest order holds two families, so two shapes suffice.
    assert marker_load(frame, "name1", "name2") == 2
    # Without a colour column to group them, all three need their own shape.
    assert marker_load(frame, None, "name2") == 3
    assert marker_load(frame, "name1", None) == 0
    # Refusing to nest means shapes may no longer repeat across colours, so
    # every family needs its own again - this is what keeps the map and the
    # legend agreeing about how many shapes are in play.
    assert marker_load(frame, "name1", "name2", "never") == 3


def test_markers_stay_put_when_rows_are_filtered_out():
    # Style maps come from the full frame, so hiding rows must not reshuffle
    # the shapes of the groups that remain.
    frame = _insect_frame()
    _colors, full = attribute_style_maps(frame, "name1", "name2")
    kept = frame[frame["name2"] != "Reduviidae"]
    _colors2, partial = attribute_style_maps(kept, "name1", "name2")
    assert full["Pentatomidae"] == partial["Pentatomidae"]
    assert full["Nymphalidae"] == partial["Nymphalidae"]


def test_style_by_attributes_groups_by_color_symbol_combo():
    frame = _insect_frame()
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2")
    groups = style_by_attributes(frame, "name1", "name2",
                                 color_map, symbol_map)
    # Distinct (order, family) combinations present, in first-seen order.
    labels = [label for label, _style, _sub in groups]
    assert labels == ["Hemiptera / Pentatomidae",
                      "Hemiptera / Reduviidae",
                      "Lepidoptera / Nymphalidae"]
    # Color follows the order; marker follows the family.
    by_label = {label: style for label, style, _ in groups}
    assert (by_label["Hemiptera / Pentatomidae"].color
            == by_label["Hemiptera / Reduviidae"].color)
    assert (by_label["Hemiptera / Pentatomidae"].color
            != by_label["Lepidoptera / Nymphalidae"].color)
    assert (by_label["Hemiptera / Pentatomidae"].marker
            != by_label["Hemiptera / Reduviidae"].marker)
    # Both Pentatomidae rows land in one group.
    sizes = {label: len(sub) for label, _s, sub in groups}
    assert sizes["Hemiptera / Pentatomidae"] == 2


def test_attribute_maps_stable_when_a_value_is_filtered_out():
    frame = _insect_frame()
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2")
    # Filtering the frame must not change colors derived from the full data.
    filtered = frame[frame["name1"] != "Lepidoptera"]
    groups = style_by_attributes(filtered, "name1", "name2",
                                 color_map, symbol_map)
    assert all("Lepidoptera" not in label for label, _s, _sub in groups)
    hemiptera = next(style for label, style, _ in groups
                     if label.startswith("Hemiptera"))
    assert hemiptera.color == color_map["Hemiptera"]
