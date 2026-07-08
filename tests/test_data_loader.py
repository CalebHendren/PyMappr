import textwrap

import pytest

from pymappr.data_loader import (ColumnMapping, build_dataset, guess_mapping,
                                load_csv, read_csv)


def write(tmp_path, text):
    path = tmp_path / "points.csv"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


def test_documented_layout(tmp_path):
    """Name 1, Name 2, Longitude, Latitude in order, mixed notations."""
    path = write(tmp_path, """\
        County,City,Longitude,Latitude
        Travis,Austin,-97.7431,30.2672
        King,Seattle,"122°19'59""W","47°36'35""N"
        Suffolk,Boston,71 3 37 W,42 21 33 N
    """)
    ds = load_csv(path)
    assert len(ds) == 3
    assert ds.skipped == []
    assert ds.name1_label == "County"
    assert ds.name2_label == "City"
    row = ds.frame.iloc[1]
    assert row["name1"] == "King"
    assert row["lon"] == pytest.approx(-(122 + 19 / 60 + 59 / 3600))
    assert row["lat"] == pytest.approx(47 + 36 / 60 + 35 / 3600)


def test_header_guessing_out_of_order(tmp_path):
    path = write(tmp_path, """\
        lat,lng,place
        30.5,-97.1,Somewhere
    """)
    frame = read_csv(path)
    mapping = guess_mapping(frame)
    assert mapping.longitude == "lng"
    assert mapping.latitude == "lat"
    assert mapping.name1 == "place"
    ds = build_dataset(frame, mapping)
    assert ds.frame.iloc[0]["lon"] == pytest.approx(-97.1)


def test_positional_fallback_without_hints(tmp_path):
    path = write(tmp_path, """\
        A,B,C,D
        Travis,Austin,-97.7431,30.2672
    """)
    mapping = guess_mapping(read_csv(path))
    assert mapping.names == ["A", "B"]
    assert (mapping.name1, mapping.name2) == ("A", "B")
    assert (mapping.longitude, mapping.latitude) == ("C", "D")


def test_many_name_columns(tmp_path):
    """More than two name columns are all kept, in order."""
    path = write(tmp_path, """\
        Country,State,County,City,Longitude,Latitude
        United States,Wyoming,Laramie,Cheyenne,-104.8202,41.1400
        United States,Wyoming,Natrona,Casper,-106.3131,42.8666
    """)
    ds = load_csv(path)
    assert len(ds) == 2
    assert ds.name_labels == ["Country", "State", "County", "City"]
    assert ds.name_keys == ["name1", "name2", "name3", "name4"]
    row = ds.frame.iloc[0]
    assert row["name1"] == "United States"
    assert row["name2"] == "Wyoming"
    assert row["name3"] == "Laramie"
    assert row["name4"] == "Cheyenne"


def test_generic_name_labels_option(tmp_path):
    """use_headers=False falls back to Name 1, Name 2, Name 3, ..."""
    path = write(tmp_path, """\
        Country,State,County,City,Longitude,Latitude
        United States,Wyoming,Campbell,Gillette,-105.5022,44.2911
    """)
    frame = read_csv(path)
    mapping = guess_mapping(frame)
    mapping.use_headers = False
    ds = build_dataset(frame, mapping)
    assert ds.name_labels == ["Name 1", "Name 2", "Name 3", "Name 4"]
    assert ds.name1_label == "Name 1"


def test_bad_rows_skipped_and_reported(tmp_path):
    path = write(tmp_path, """\
        County,City,Longitude,Latitude
        Travis,Austin,-97.7431,30.2672
        Bad,Row,not-a-number,30.0
        Alameda,Oakland,-122.2711,37.8044
        Off,Planet,-97.0,95.0
    """)
    ds = load_csv(path)
    assert len(ds) == 2
    assert len(ds.skipped) == 2
    assert "row 3" in ds.skipped[0]
    assert "row 5" in ds.skipped[1]


def test_explicit_mapping_overrides_guess(tmp_path):
    path = write(tmp_path, """\
        ignored,x,y
        junk,-97.1,30.5
    """)
    mapping = ColumnMapping(longitude="x", latitude="y", names=["ignored"])
    ds = build_dataset(read_csv(path), mapping)
    assert len(ds) == 1
    assert ds.frame.iloc[0]["name1"] == "junk"


def test_too_few_columns(tmp_path):
    path = write(tmp_path, """\
        only
        1.0
    """)
    with pytest.raises(ValueError):
        guess_mapping(read_csv(path))
