"""Which columns the Combine columns dialog starts with ticked."""

from pymappr.ui.combine_columns import default_columns


def test_genus_and_species_are_found_wherever_they_sit():
    labels = ["Genus", "Species", "Type status", "Country"]
    assert default_columns(labels) == ["Genus", "Species"]
    assert default_columns(["family", "GENUS", "specific epithet",
                            "Locality"]) == ["GENUS", "specific epithet"]


def test_without_those_names_the_last_two_are_ticked():
    assert default_columns(["Family", "Tribe", "Name"]) == ["Tribe", "Name"]
    assert default_columns(["Genus", "Locality"]) == ["Genus", "Locality"]
