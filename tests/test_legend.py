"""Tests for legend content: sections, nesting, counts, order, options."""

from pathlib import Path

import pandas as pd

from pymappr.legend import (NEUTRAL_MARKER_COLOR, LegendOptions, legend_counts,
                            legend_sections, order_labels, row_key)
from pymappr.styles import apply_override, attribute_style_maps


def _beetle_frame():
    """The shipped taxonomy sample: 3 genera x 3 species, perfectly nested."""
    path = Path(__file__).resolve().parent.parent / "sample_data"
    frame = pd.read_csv(path / "south_america_beetles.csv")
    return frame.rename(columns={"Genus": "name1", "Species": "name2"})


def _crossed_frame():
    """Habitat x sex: every shape really does appear in every colour."""
    return pd.DataFrame({
        "name1": ["forest", "forest", "scrub", "scrub"],
        "name2": ["male", "female", "male", "female"],
        "lon": [1.0, 2.0, 3.0, 4.0], "lat": [1.0, 2.0, 3.0, 4.0],
    })


def _sections(frame, options=None, **kwargs):
    options = options or LegendOptions()
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2",
                                                 options.hierarchy)
    return legend_sections(frame, "name1", "name2", color_map, symbol_map,
                           "Genus", "Species", options=options, **kwargs)


# ------------------------------------------------------------ nested key


def test_nested_legend_lists_species_under_their_genus():
    sections = _sections(_beetle_frame())
    # One key, not two independent ones.
    assert len(sections) == 1
    title, entries = sections[0]
    assert title == "Genus / Species"
    genera = [(label, style) for label, style, depth in entries if depth == 0]
    species = [(label, style) for label, style, depth in entries if depth == 1]
    assert [label for label, _ in genera] == ["Eleusis", "Xanthopygus",
                                              "Plociopterus"]
    assert len(species) == 9


def test_nested_legend_swatches_match_the_map():
    # Every species swatch carries its genus's colour and its own marker -
    # the exact marker drawn on the map. Nothing is the neutral grey.
    frame = _beetle_frame()
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2")
    owner = dict(zip(frame["name2"], frame["name1"]))
    _title, entries = _sections(frame)[0]
    genus = None
    for label, style, depth in entries:
        assert style.color != NEUTRAL_MARKER_COLOR
        if depth == 0:
            genus = label
            assert style.color == color_map[label]
        else:
            assert owner[label] == genus
            assert style.color == color_map[genus]
            assert style.marker == symbol_map[label]


def test_nested_legend_prunes_filtered_out_values():
    frame = _beetle_frame()
    kept = frame[frame["name1"] != "Xanthopygus"]
    sections = _sections(frame, shown_colors=set(kept["name1"]),
                         shown_symbols=set(kept["name2"]))
    _title, entries = sections[0]
    assert [label for label, _s, depth in entries if depth == 0] == [
        "Eleusis", "Plociopterus"]
    assert len([1 for *_x, depth in entries if depth == 1]) == 6


def test_crossed_columns_keep_two_independent_keys():
    frame = _crossed_frame()
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2")
    sections = legend_sections(frame, "name1", "name2", color_map, symbol_map,
                               "Habitat", "Sex")
    assert [title for title, _rows in sections] == ["Habitat", "Sex"]
    # A shape genuinely appears in every colour here, so neutral is honest.
    _title, symbols = sections[1]
    assert all(style.color == NEUTRAL_MARKER_COLOR
               for _label, style, _depth in symbols)
    assert all(depth == 0 for section in sections
               for *_x, depth in section[1])


# --------------------------------------------------------------- hierarchy


def test_hierarchy_never_splits_a_real_hierarchy_into_two_keys():
    sections = _sections(_beetle_frame(),
                         LegendOptions(hierarchy="never"))
    assert [title for title, _rows in sections] == ["Genus", "Species"]
    # Refusing to nest means shapes can no longer repeat across colours, so
    # all nine species need nine distinct markers.
    _title, symbols = sections[1]
    assert len({style.marker for _label, style, _d in symbols}) == 9


def test_hierarchy_always_nests_columns_that_actually_cross():
    sections = _sections(_crossed_frame(), LegendOptions(hierarchy="always"))
    assert len(sections) == 1
    _title, entries = sections[0]
    parents = [label for label, _s, depth in entries if depth == 0]
    children = [label for label, _s, depth in entries if depth == 1]
    assert parents == ["forest", "scrub"]
    # Each sex is listed once, under the first habitat it appears in.
    assert sorted(children) == ["female", "male"]


def test_forced_nesting_still_lists_every_colour_on_the_map():
    # Under forced nesting "scrub" loses both its sexes to "forest", which
    # saw them first. It still has points on the map, so dropping it would
    # leave a colour the legend never explains.
    sections = _sections(_crossed_frame(), LegendOptions(hierarchy="always"))
    _title, entries = sections[0]
    parents = [label for label, _s, depth in entries if depth == 0]
    assert parents == ["forest", "scrub"]


def test_forced_nesting_takes_the_first_owner_not_the_last():
    # "male" appears under forest first and scrub later. Last-wins would put
    # it under scrub and make the result depend on row order at the end of
    # the file rather than the start.
    sections = _sections(_crossed_frame(), LegendOptions(hierarchy="always"))
    _title, entries = sections[0]
    seen_parent = None
    owners = {}
    for label, _style, depth in entries:
        if depth == 0:
            seen_parent = label
        else:
            owners[label] = seen_parent
    assert owners["male"] == "forest"
    assert owners["female"] == "forest"


def test_auto_hierarchy_is_the_default_and_unchanged():
    assert LegendOptions().hierarchy == "auto"
    assert len(_sections(_beetle_frame())) == 1        # nests
    assert len(_sections(_crossed_frame())) == 2       # crosses


# ------------------------------------------------------------------ counts


def test_counts_are_appended_only_when_asked_for():
    frame = _beetle_frame()
    # Off by default: bare labels.
    _title, plain = _sections(frame)[0]
    assert [label for label, _s, _d in plain if label == "chapadensis"]

    counts = legend_counts(frame, "name1", "name2")
    _title, entries = _sections(frame, LegendOptions(counts=True),
                                counts=counts)[0]
    labels = [label for label, _s, _d in entries]
    assert "Eleusis (18)" in labels        # genus total
    assert "chapadensis (6)" in labels     # taxon total


def test_counts_follow_the_filtered_frame():
    frame = _beetle_frame()
    kept = frame[frame["name2"] != "chapadensis"]
    counts = legend_counts(kept, "name1", "name2")
    _title, entries = _sections(frame, LegendOptions(counts=True),
                                shown_colors=set(kept["name1"]),
                                shown_symbols=set(kept["name2"]),
                                counts=counts)[0]
    labels = [label for label, _s, _d in entries]
    assert "Eleusis (12)" in labels        # 18 minus the 6 hidden
    assert not any(label.startswith("chapadensis") for label in labels)


def test_every_count_format_renders():
    frame = _beetle_frame()
    counts = legend_counts(frame, "name1", "name2")
    # 18 of the sample's 50 rows are Eleusis.
    expected = {"(n)": "Eleusis (18)", "n": "Eleusis 18",
                "(n, %)": "Eleusis (18, 36%)", "%": "Eleusis 36%"}
    for fmt, want in expected.items():
        options = LegendOptions(counts=True, count_format=fmt)
        _title, entries = _sections(frame, options, counts=counts)[0]
        assert want in [label for label, _s, _d in entries], fmt


def test_counts_stay_off_when_only_the_order_needs_them():
    # Ordering by count needs the numbers, but must not put them in the text.
    frame = _beetle_frame()
    counts = legend_counts(frame, "name1", "name2")
    options = LegendOptions(order="count_desc", counts=False)
    _title, entries = _sections(frame, options, counts=counts)[0]
    assert all("(" not in label for label, _s, _d in entries)


# ------------------------------------------------------------------- order


def test_order_labels_sorts_alphabetically_both_ways():
    values = ["pear", "Apple", "fig"]
    assert order_labels(values, "az") == ["Apple", "fig", "pear"]
    assert order_labels(values, "za") == ["pear", "fig", "Apple"]
    assert order_labels(values, "data") == values


def test_order_labels_sorts_by_count_and_breaks_ties_by_label():
    counts = {"a": 5, "b": 5, "c": 9}
    of = counts.get
    assert order_labels(["a", "b", "c"], "count_desc", of) == ["c", "a", "b"]
    assert order_labels(["a", "b", "c"], "count_asc", of) == ["a", "b", "c"]


def test_nested_order_applies_to_parents_and_children():
    frame = _beetle_frame()
    _title, entries = _sections(frame, LegendOptions(order="az"))[0]
    parents = [label for label, _s, depth in entries if depth == 0]
    assert parents == sorted(parents, key=str.casefold)
    # Children are sorted inside each block, not across the whole list.
    block: list = []
    blocks = []
    for label, _style, depth in entries:
        if depth == 0:
            block = []
            blocks.append(block)
        else:
            block.append(label)
    assert blocks and all(b == sorted(b, key=str.casefold) for b in blocks)


def test_order_does_not_disturb_the_colour_map():
    # Sorting the legend must not repaint the map: colours stay keyed to
    # first appearance whatever the legend order is.
    frame = _beetle_frame()
    base, _ = attribute_style_maps(frame, "name1", "name2")
    for order in ("az", "za", "count_desc"):
        colours, _ = attribute_style_maps(frame, "name1", "name2")
        assert colours == base, order
        _sections(frame, LegendOptions(order=order))
        assert attribute_style_maps(frame, "name1", "name2")[0] == base


# ---------------------------------------------------------- row appearance


def test_blank_values_use_the_configured_stand_in():
    frame = pd.DataFrame({"name1": ["", "a"], "name2": ["x", "y"],
                          "lon": [1.0, 2.0], "lat": [1.0, 2.0]})
    options = LegendOptions(blank_label="(none)")
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2")
    sections = legend_sections(frame, "name1", "name2", color_map, symbol_map,
                               "A", "B", options=options)
    labels = [label for _t, rows in sections for label, _s, _d in rows]
    assert "(none)" in labels
    assert "(blank)" not in labels


def test_section_titles_can_be_turned_off():
    sections = _sections(_beetle_frame(),
                         LegendOptions(section_titles=False))
    assert [title for title, _rows in sections] == [""]


def test_turning_titles_off_drops_the_dataset_prefix_too():
    # The prefix rides on the heading. With headings off it has nothing to
    # attach to, and a section titled "beetles: " would be nonsense.
    sections = _sections(_beetle_frame(),
                         LegendOptions(section_titles=False),
                         prefix="beetles: ")
    assert [title for title, _rows in sections] == [""]
    crossed = legend_sections(
        _crossed_frame(), "name1", "name2",
        *attribute_style_maps(_crossed_frame(), "name1", "name2"),
        "Habitat", "Sex", prefix="sites: ",
        options=LegendOptions(section_titles=False))
    assert [title for title, _rows in crossed] == ["", ""]


def test_the_dataset_prefix_is_kept_when_titles_are_on():
    sections = _sections(_beetle_frame(), prefix="beetles: ")
    assert sections[0][0] == "beetles: Genus / Species"


def test_title_separator_is_configurable():
    sections = _sections(_beetle_frame(),
                         LegendOptions(title_separator=" > "))
    assert sections[0][0] == "Genus > Species"


def test_group_swatch_can_match_the_first_child_or_be_dropped():
    frame = _beetle_frame()
    _title, entries = _sections(frame,
                                LegendOptions(group_swatch="child"))[0]
    first_parent = next(e for e in entries if e[2] == 0)
    first_child = next(e for e in entries if e[2] == 1)
    assert first_parent[1].marker == first_child[1].marker

    _title, entries = _sections(frame, LegendOptions(group_swatch="none"))[0]
    assert all(style is None for _l, style, depth in entries if depth == 0)
    assert all(style is not None for _l, style, depth in entries if depth == 1)


def test_crossed_symbol_swatch_colour_is_configurable():
    options = LegendOptions(symbol_swatch_color="#123456")
    frame = _crossed_frame()
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2")
    sections = legend_sections(frame, "name1", "name2", color_map, symbol_map,
                               "Habitat", "Sex", options=options)
    _title, symbols = sections[1]
    assert all(style.color == "#123456" for _l, style, _d in symbols)


def test_empty_groups_are_dropped_unless_asked_for():
    frame = _beetle_frame()
    kept = frame[frame["name1"] != "Xanthopygus"]
    shown_symbols = set(kept["name2"])
    # The genus itself is still "shown", but none of its species are.
    hidden = _sections(frame, shown_symbols=shown_symbols)
    assert "Xanthopygus" not in [label for label, _s, d in hidden[0][1]
                                 if d == 0]
    kept_rows = _sections(frame, LegendOptions(empty_groups=True),
                          shown_symbols=shown_symbols)
    assert "Xanthopygus" in [label for label, _s, d in kept_rows[0][1]
                             if d == 0]


# ----------------------------------------------------------------- options


def test_options_round_trip_through_a_dict():
    options = LegendOptions(hierarchy="never", indent=5, counts=True,
                            frame_color="#101010", title="Key")
    assert LegendOptions.from_dict(options.to_dict()) == options


def test_from_dict_ignores_unknown_keys_and_defaults_missing_ones():
    options = LegendOptions.from_dict({"indent": 7, "removed_setting": 1})
    assert options.indent == 7
    assert options.hierarchy == "auto"      # a key an old project never wrote


def test_indent_and_pad_helpers():
    options = LegendOptions(indent=2)
    assert options.indent_for(0) == "  "
    assert options.indent_for(1) == "    "
    # Blank means "match the legend kind", which is what the two draw paths
    # did before the gap was settable.
    assert LegendOptions().pad_for(sectioned=True) == 0.4
    assert LegendOptions().pad_for(sectioned=False) == 0.8
    assert LegendOptions(handle_text_pad=1.5).pad_for(True) == 1.5


# --------------------------------------------------------- row overrides


def test_row_keys_are_tagged_so_channels_cannot_collide():
    # "unknown" can legitimately appear in both the colour and the symbol
    # column; their rows must stay separate customizations.
    assert row_key("color", "unknown") != row_key("symbol", "unknown")
    assert row_key("group", "a") != row_key("color", "a")


def test_row_keys_survive_values_containing_punctuation():
    # Separators people reach for first - "/" and ":" - turn up in real
    # values all the time, which is why the key uses NUL instead.
    assert row_key("pair", "a/b", "c") != row_key("pair", "a", "b/c")
    assert row_key("pair", "a:b", "c") != row_key("pair", "a", "b:c")
    assert row_key("pair", "a b", "c") != row_key("pair", "a", "b c")


def test_a_row_can_be_renamed():
    frame = _beetle_frame()
    overrides = {row_key("pair", "Eleusis", "chapadensis"):
                 {"label": "E. chapadensis"}}
    _title, entries = _sections(frame, overrides=overrides)[0]
    labels = [label for label, _s, _d in entries]
    assert "E. chapadensis" in labels
    assert "chapadensis" not in labels


def test_a_renamed_row_still_gets_its_count():
    # Renaming is about what the row is called, not about dropping numbers.
    frame = _beetle_frame()
    counts = legend_counts(frame, "name1", "name2")
    overrides = {row_key("color", "Eleusis"): {"label": "Genus E"}}
    _title, entries = _sections(frame, LegendOptions(counts=True),
                                counts=counts, overrides=overrides)[0]
    assert "Genus E (18)" in [label for label, _s, _d in entries]


def test_a_hidden_row_leaves_the_legend():
    frame = _beetle_frame()
    overrides = {row_key("pair", "Eleusis", "andina"): {"hidden": True}}
    _title, entries = _sections(frame, overrides=overrides)[0]
    assert "andina" not in [label for label, _s, _d in entries]
    # Its siblings and its genus stay.
    assert "chapadensis" in [label for label, _s, _d in entries]
    assert "Eleusis" in [label for label, _s, _d in entries]


def test_hiding_a_group_hides_the_block_it_heads():
    # The children are drawn in the group's colour, so leaving them behind
    # would orphan them under whatever row happened to precede them.
    frame = _beetle_frame()
    overrides = {row_key("color", "Eleusis"): {"hidden": True}}
    _title, entries = _sections(frame, overrides=overrides)[0]
    labels = [label for label, _s, _d in entries]
    assert "Eleusis" not in labels
    assert "chapadensis" not in labels
    assert "Xanthopygus" in labels


def test_a_row_can_be_restyled():
    frame = _beetle_frame()
    overrides = {row_key("pair", "Eleusis", "andina"):
                 {"color": "#123456", "marker": "Star", "size": 90.0}}
    _title, entries = _sections(frame, overrides=overrides)[0]
    style = next(s for label, s, _d in entries if label == "andina")
    assert (style.color, style.marker, style.size) == ("#123456", "Star", 90.0)


def test_an_override_only_replaces_what_it_sets():
    # A row that was only renamed keeps following the palette.
    frame = _beetle_frame()
    plain = _sections(frame)[0][1]
    base = next(s for label, s, _d in plain if label == "andina")
    overrides = {row_key("pair", "Eleusis", "andina"): {"label": "A."}}
    _title, entries = _sections(frame, overrides=overrides)[0]
    style = next(s for label, s, _d in entries if label == "A.")
    assert (style.color, style.marker, style.size) == (base.color, base.marker,
                                                       base.size)


def test_crossed_rows_take_their_own_overrides():
    frame = _crossed_frame()
    overrides = {row_key("color", "forest"): {"label": "Woodland"},
                 row_key("symbol", "male"): {"hidden": True}}
    color_map, symbol_map = attribute_style_maps(frame, "name1", "name2")
    sections = legend_sections(frame, "name1", "name2", color_map, symbol_map,
                               "Habitat", "Sex", overrides=overrides)
    colors = [label for label, _s, _d in sections[0][1]]
    symbols = [label for label, _s, _d in sections[1][1]]
    assert "Woodland" in colors and "forest" not in colors
    assert "male" not in symbols and "female" in symbols


def test_manual_order_places_rows_and_leaves_the_rest_in_data_order():
    frame = _beetle_frame()
    overrides = {row_key("color", "Plociopterus"): {"order": 0},
                 row_key("color", "Eleusis"): {"order": 1}}
    options = LegendOptions(order="manual")
    _title, entries = _sections(frame, options, overrides=overrides)[0]
    parents = [label for label, _s, depth in entries if depth == 0]
    # The two placed genera lead, and the one never placed falls to the end.
    assert parents == ["Plociopterus", "Eleusis", "Xanthopygus"]


def test_manual_order_sorts_children_inside_their_own_group():
    frame = _beetle_frame()
    overrides = {row_key("pair", "Eleusis", "andina"): {"order": 0}}
    options = LegendOptions(order="manual")
    _title, entries = _sections(frame, options, overrides=overrides)[0]
    block: list = []
    for label, _style, depth in entries:
        if depth == 0 and label == "Eleusis":
            block = []
            current = True
        elif depth == 0:
            current = False
        elif current:
            block.append(label)
    assert block[0] == "andina"


def test_apply_override_leaves_a_missing_style_alone():
    # group_swatch="none" emits None; an override must not conjure one up.
    assert apply_override(None, {"color": "#fff"}) is None
    assert apply_override(None, None) is None
