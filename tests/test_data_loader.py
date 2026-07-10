import textwrap

import pytest

from pymappr.data_loader import (ColumnMapping, build_dataset,
                                build_manual_dataset, guess_mapping,
                                headers_look_like_data, list_sheets,
                                load_csv, read_csv, read_table)


def write(tmp_path, text, name="points.csv"):
    path = tmp_path / name
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


# ------------------------------------------------- first row is data, not headers

def test_read_table_without_headers(tmp_path):
    """headers=False keeps the first row as data to plot."""
    path = write(tmp_path, """\
        38,-100
        -25,140
    """)
    frame = read_table(path, headers=False)
    assert list(frame.columns) == ["Column 1", "Column 2"]
    assert len(frame) == 2
    assert frame.iloc[0]["Column 1"] == "38"


def test_headers_look_like_data(tmp_path):
    numeric = read_table(write(tmp_path, "38,-100\n-25,140\n"))
    assert headers_look_like_data(numeric)
    named = read_table(write(tmp_path, "City,Longitude,Latitude\n"
                                       "Austin,-97.7,30.3\n"))
    assert not headers_look_like_data(named)


def test_positional_fallback_swaps_lat_lon_by_value(tmp_path):
    """A headerless lat,lon file imports correctly: values beyond +/-90 in
    the presumed latitude column flip the guess."""
    path = write(tmp_path, """\
        38,-100
        -25,140
    """)
    frame = read_table(path, headers=False)
    mapping = guess_mapping(frame)
    assert mapping.latitude == "Column 1"
    assert mapping.longitude == "Column 2"
    ds = build_dataset(frame, mapping)
    assert ds.frame.iloc[1]["lon"] == pytest.approx(140)
    assert ds.frame.iloc[1]["lat"] == pytest.approx(-25)


# --------------------------------------------------------------- other formats

def test_read_table_tsv(tmp_path):
    path = write(tmp_path, "City\tLongitude\tLatitude\n"
                           "Austin\t-97.7\t30.3\n", name="points.tsv")
    frame = read_table(path)
    assert list(frame.columns) == ["City", "Longitude", "Latitude"]
    assert frame.iloc[0]["Longitude"] == "-97.7"


def test_read_table_sniffs_txt_delimiter(tmp_path):
    path = write(tmp_path, "City;Longitude;Latitude\n"
                           "Austin;-97.7;30.3\n", name="points.txt")
    frame = read_table(path)
    assert list(frame.columns) == ["City", "Longitude", "Latitude"]


def test_read_table_excel(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    path = str(tmp_path / "points.xlsx")
    pd.DataFrame({"City": ["Austin"], "Longitude": [-97.7],
                  "Latitude": [30.3]}).to_excel(path, index=False,
                                                sheet_name="Sites")
    assert list_sheets(path) == ["Sites"]
    frame = read_table(path, sheet="Sites")
    assert list(frame.columns) == ["City", "Longitude", "Latitude"]
    ds = build_dataset(frame, guess_mapping(frame), source_path=path)
    assert len(ds) == 1
    assert ds.frame.iloc[0]["lon"] == pytest.approx(-97.7)


def test_read_table_excel_first_row_as_data(tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    path = str(tmp_path / "raw.xlsx")
    pd.DataFrame([[38, -100], [-25, 140]]).to_excel(path, index=False,
                                                    header=False)
    frame = read_table(path, headers=False)
    assert list(frame.columns) == ["Column 1", "Column 2"]
    assert len(frame) == 2


# ---------------------------------------------------------------- manual entry

def test_build_manual_dataset_lat_lon_lines():
    ds = build_manual_dataset("Pardosa distincta", "38,-100\n-25,140\n")
    assert len(ds) == 2
    assert ds.skipped == []
    assert ds.name_labels == ["Legend"]
    assert set(ds.frame["name1"]) == {"Pardosa distincta"}
    assert ds.frame.iloc[0]["lat"] == pytest.approx(38)
    assert ds.frame.iloc[0]["lon"] == pytest.approx(-100)


def test_build_manual_dataset_lon_lat_order_and_labels():
    ds = build_manual_dataset("Sites", "-100, 38, Site A\n140.0;-25;Site B\n",
                              order="lon,lat")
    assert len(ds) == 2
    assert ds.name_labels == ["Legend", "Label"]
    assert list(ds.frame["name2"]) == ["Site A", "Site B"]
    assert ds.frame.iloc[0]["lon"] == pytest.approx(-100)


def test_build_manual_dataset_dms_and_errors():
    text = "47°36'35\"N, 122°19'59\"W\nnot-a-coordinate\n95, 10\n"
    ds = build_manual_dataset("Mixed", text)
    assert len(ds) == 1
    assert len(ds.skipped) == 2
    assert "line 2" in ds.skipped[0]
    assert "line 3" in ds.skipped[1]
    assert ds.frame.iloc[0]["lat"] == pytest.approx(47 + 36 / 60 + 35 / 3600)
