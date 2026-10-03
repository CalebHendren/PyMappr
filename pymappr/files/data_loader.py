from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from pymappr.files.coords import (CoordinateError, parse_latitude,
                                  parse_longitude)

__all__ = ["ColumnMapping", "PointDataset", "read_table", "far_points",
           "list_sheets", "headers_look_like_data", "guess_mapping",
           "build_dataset", "load_csv", "build_manual_dataset",
           "combine_name_columns", "SPREADSHEET_EXTENSIONS",
           "OPEN_FILETYPES"]

_LON_HINTS = ("lon", "lng", "long", "longitude", "x")
_LAT_HINTS = ("lat", "latitude", "y")

# Spreadsheet formats read through pandas' Excel/ODF readers; everything
# else is treated as delimited text.
SPREADSHEET_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls",
                          ".ods"}

# File-dialog filters for the data-import picker.
OPEN_FILETYPES = [
    ("All supported", "*.csv *.tsv *.txt *.xlsx *.xlsm *.xls *.ods"),
    ("CSV files", "*.csv"),
    ("Excel workbooks", "*.xlsx *.xlsm *.xls"),
    ("OpenDocument spreadsheets", "*.ods"),
    ("Tab-separated / text", "*.tsv *.txt"),
    ("All files", "*.*"),
]


@dataclass
class ColumnMapping:
    """Which CSV columns hold each field.

    *names* lists the CSV columns used as name/grouping fields, in order
    (Name 1, Name 2, ...). *use_headers* keeps the original CSV headers as
    the display labels instead of the generic "Name 1", "Name 2", ...
    *header_row* says the file's first line is a header row, which only
    affects how skipped rows are numbered.
    """

    longitude: str
    latitude: str
    names: list[str] = field(default_factory=list)
    use_headers: bool = True
    header_row: bool = True


@dataclass
class PointDataset:
    """Parsed points ready for plotting."""

    frame: pd.DataFrame  # columns: name1..nameN, lon, lat
    source_path: str
    skipped: list[str] = field(default_factory=list)  # per-row error messages
    # The file row each point came from, for messages about a point; empty
    # when the points did not come from a file read here.
    source_rows: list[int] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def name_labels(self) -> list[str]:
        """Display label for each name column, in order."""
        return list(self.frame.attrs.get("name_labels", []))

    @property
    def name_keys(self) -> list[str]:
        """Frame column key for each name column: name1, name2, ..."""
        return [f"name{i + 1}" for i in range(len(self.name_labels))]


def read_table(path: str, headers: bool = True,
               sheet: str | None = None) -> pd.DataFrame:
    """Read a delimited text file or spreadsheet as an all-text frame.

    *headers* says whether the first row holds column names; when False
    every row is data and the columns are named "Column 1", "Column 2",
    ... *sheet* picks a worksheet for spreadsheet formats (first sheet
    when None).
    """
    ext = Path(path).suffix.lower()
    header = 0 if headers else None
    if ext in SPREADSHEET_EXTENSIONS:
        try:
            frame = pd.read_excel(path, sheet_name=sheet if sheet else 0,
                                  header=header, dtype=str,
                                  keep_default_na=False)
        except ImportError as exc:
            raise ValueError(
                f"Reading {ext} files needs an extra library that is not "
                f"installed ({exc}).\nSaving the sheet as .xlsx or .csv "
                "and importing that will work.") from exc
    else:
        # .csv is comma separated and .tsv tab separated; for anything
        # else (e.g. .txt) sniff the delimiter from the file.
        sep = {".csv": ",", ".tsv": "\t"}.get(ext)
        frame = pd.read_csv(path, sep=sep, header=header,
                            engine=None if sep else "python",
                            dtype=str, keep_default_na=False,
                            skipinitialspace=True,
                            encoding_errors="replace")
    if not headers:
        frame.columns = [f"Column {i + 1}" for i in range(len(frame.columns))]
    else:
        frame.columns = [str(c) for c in frame.columns]
    # Spreadsheet cells may come back as NaN even with keep_default_na
    # (truly empty cells); normalize everything to text.
    frame = frame.fillna("").astype(str)
    if ext not in SPREADSHEET_EXTENSIONS:
        lines = _text_row_lines(path, sep, headers, len(frame))
        if lines is not None:
            frame.attrs["source_lines"] = lines
    return frame


def _text_row_lines(path: str, sep: str | None, headers: bool,
                    rows: int) -> list[int] | None:
    """The 1-based file line each data row of a delimited file starts on.

    read_csv drops blank lines and folds a quoted field that spans lines
    into one row, so a row's position alone misnumbers every row after
    either. None when this scan and pandas disagree on the row count (an
    unusual dialect); build_dataset then numbers rows by position.
    """
    try:
        with open(path, encoding="utf-8-sig", errors="replace",
                  newline="") as handle:
            if sep is None:
                sep = csv.Sniffer().sniff(handle.read(65536)).delimiter
                handle.seek(0)
            reader = csv.reader(handle, delimiter=sep)
            starts, line = [], 0
            for record in reader:
                # Like read_csv, skip empty and whitespace-only lines but
                # keep lines of bare delimiters (",,").
                if len(record) > 1 or (record and record[0].strip()):
                    starts.append(line + 1)
                line = reader.line_num
    except (OSError, csv.Error):
        return None
    if headers:
        starts = starts[1:]
    return starts if len(starts) == rows else None


def list_sheets(path: str) -> list[str]:
    """Worksheet names of a spreadsheet file ([] for text formats)."""
    if Path(path).suffix.lower() not in SPREADSHEET_EXTENSIONS:
        return []
    with pd.ExcelFile(path) as book:
        return [str(name) for name in book.sheet_names]


def headers_look_like_data(frame: pd.DataFrame) -> bool:
    """Guess whether the header row is really data (no header row).

    A file whose first row is coordinates to plot (e.g. "38,-100") reads
    into numeric-looking column names; real headers are words. Two or
    more numeric-looking headers means the row is probably data.
    """
    numeric = 0
    for column in frame.columns:
        try:
            float(str(column).strip())
            numeric += 1
        except ValueError:
            pass
    return numeric >= 2


def _match(columns: list[str], hints: tuple[str, ...]) -> str | None:
    """The column a coordinate header most likely names: an exact hint
    ("lng"), then one starting with a hint ("Long."), then one containing
    the whole word ("decimalLongitude"). Short hints never match inside
    other words - "x" and "y" sit in Taxon, Family and Locality, "lon" in
    Colony."""
    lowered = {c.lower().strip(): c for c in columns}
    rules = (lambda low, hint: low == hint,
             lambda low, hint: len(hint) > 1 and low.startswith(hint),
             lambda low, hint: len(hint) > 4 and hint in low)
    for rule in rules:
        for hint in hints:
            for low, original in lowered.items():
                if rule(low, hint):
                    return original
    return None


def guess_mapping(frame: pd.DataFrame) -> ColumnMapping:
    """Guess the column mapping from headers, falling back to position.

    Positional fallback follows the documented layout: the last two columns
    are Longitude and Latitude and everything before them is a name column.
    When the values disagree with that order (the presumed latitude column
    holds values beyond +/-90 while the other does not), the two are
    swapped - typed-in "lat, lon" files import correctly this way.
    """
    columns = list(frame.columns)
    lon = _match(columns, _LON_HINTS)
    lat = _match(columns, _LAT_HINTS)
    if lon is None or lat is None or lon == lat:
        if len(columns) >= 2:
            lon, lat = columns[-2], columns[-1]
            if _beyond_latitude(frame[lat]) and not _beyond_latitude(frame[lon]):
                lon, lat = lat, lon
        else:
            raise ValueError(
                "The file needs at least two columns (longitude, latitude)")

    names = [c for c in columns if c not in (lon, lat)]
    return ColumnMapping(longitude=lon, latitude=lat, names=names)


def _beyond_latitude(values: pd.Series) -> bool:
    """True if any numeric value in the column falls outside +/-90."""
    numeric = pd.to_numeric(values, errors="coerce")
    return bool((numeric.abs() > 90).any())


def _parse_column(values: pd.Series, parse, limit: float):
    """A coordinate column as degrees, plus the error for each row that has
    none. Plain decimals convert in one go; only what that misses (DMS,
    hemisphere letters, decimal commas, junk) goes through the row parser,
    which also words the errors - so the result is the parser's either way.
    """
    numbers = pd.to_numeric(values.astype(str).str.strip(),
                            errors="coerce").astype(float)
    fast = numbers.notna() & (numbers.abs() <= limit)
    degrees = numbers.where(fast)
    errors: dict = {}
    for idx in values.index[~fast]:
        try:
            degrees[idx] = parse(values[idx])
        except CoordinateError as exc:
            errors[idx] = exc
    return degrees, errors


def build_dataset(frame: pd.DataFrame, mapping: ColumnMapping,
                  source_path: str = "") -> PointDataset:
    """Parse the coordinates, skipping (and reporting) rows without a
    usable pair."""
    name_cols = list(mapping.names)
    lons, lon_errors = _parse_column(frame[mapping.longitude],
                                     parse_longitude, 180.0)
    lats, lat_errors = _parse_column(frame[mapping.latitude],
                                     parse_latitude, 90.0)
    bad = frame.index.isin(set(lon_errors) | set(lat_errors))
    # Rows are numbered by the file line they start on when read_table
    # recorded it. Otherwise by position, 1-based: data starts at row 2
    # under a header row and at row 1 without one. The longitude error
    # wins, as it is the one a person reading the row left to right meets
    # first.
    lines = frame.attrs.get("source_lines")
    if lines is None or len(lines) != len(frame):
        offset = 2 if mapping.header_row else 1
        lines = range(offset, len(frame) + offset)
    row_number = dict(zip(frame.index, lines))
    skipped = [f"row {row_number[idx]}: "
               f"{lon_errors.get(idx) or lat_errors[idx]}"
               for idx in frame.index[bad]]

    keys = [f"name{i + 1}" for i in range(len(name_cols))]
    result = pd.DataFrame(
        {**{key: frame.loc[~bad, col].astype(str).str.strip()
            for key, col in zip(keys, name_cols)},
         "lon": lons[~bad], "lat": lats[~bad]},
        columns=[*keys, "lon", "lat"]).reset_index(drop=True)
    if mapping.use_headers:
        labels = name_cols
    else:
        labels = [f"Name {i + 1}" for i in range(len(name_cols))]
    result.attrs["name_labels"] = list(labels)
    return PointDataset(frame=result, source_path=source_path, skipped=skipped,
                        source_rows=[int(row_number[idx])
                                     for idx in frame.index[~bad]])


# A point is "far from the rest" when the nearest other point is at least
# this far away, and this many times further than points usually are from
# their nearest neighbour. Checked only for datasets small enough to
# compare every pair quickly.
FAR_POINT_KM = 1000.0
FAR_POINT_FACTOR = 10.0
_FAR_POINT_MAX_ROWS = 5000
_EARTH_KM = 6371.0


def _unit_vectors(lons, lats) -> np.ndarray:
    lon, lat = np.radians(lons), np.radians(lats)
    return np.column_stack([np.cos(lat) * np.cos(lon),
                            np.cos(lat) * np.sin(lon), np.sin(lat)])


def _nearest_km(points: np.ndarray, others: np.ndarray,
                same: bool) -> np.ndarray:
    """Great-circle distance from each of *points* to the nearest of
    *others* (unit vectors), skipping a point's own entry when *same*."""
    nearest = np.empty(len(points))
    for start in range(0, len(points), 500):
        dots = np.clip(points[start:start + 500] @ others.T, -1.0, 1.0)
        if same:
            rows = np.arange(len(dots))
            dots[rows, start + rows] = -1.0
        nearest[start:start + 500] = np.arccos(dots.max(axis=1)) * _EARTH_KM
    return nearest


def far_points(dataset: PointDataset) -> list[str]:
    """Plain-language notes on points far from all the others.

    A lone point an ocean away from the rest is usually a coordinate typed
    without its minus sign or hemisphere letter (88.21 for 88.21 W). Each
    note names the row and, when flipping a sign puts the point among the
    others, which sign that is. Empty when nothing stands out."""
    frame = dataset.frame
    if not 5 <= len(frame) <= _FAR_POINT_MAX_ROWS:
        return []
    lons = frame["lon"].to_numpy(float)
    lats = frame["lat"].to_numpy(float)
    vectors = _unit_vectors(lons, lats)
    nearest = _nearest_km(vectors, vectors, same=True)
    typical = float(np.median(nearest))
    limit = max(FAR_POINT_KM, FAR_POINT_FACTOR * typical)
    far = np.flatnonzero(nearest > limit)
    if not len(far) or len(far) > len(frame) // 5:
        return []  # a widespread dataset, not a stray point
    keep = np.setdiff1d(np.arange(len(frame)), far)
    rest = vectors[keep]
    rows = dataset.source_rows
    notes = []
    for i in far:
        where = f"row {rows[i]}" if len(rows) == len(frame) else "a point"
        note = (f"{where} ({lats[i]:g}, {lons[i]:g}) is "
                f"{nearest[i]:,.0f} km from the nearest other point")
        for what, lon, lat in (("longitude", -lons[i], lats[i]),
                               ("latitude", lons[i], -lats[i]),
                               ("longitude and latitude", -lons[i],
                                -lats[i])):
            moved = _nearest_km(_unit_vectors([lon], [lat]), rest, False)
            if moved[0] <= limit:
                note += (f"; with the opposite sign on its {what} it "
                         "would sit with the rest")
                break
        notes.append(note + ".")
    return notes


def combine_name_columns(dataset: PointDataset, labels: list[str],
                         separator: str = " ") -> tuple[PointDataset, str]:
    """A copy of *dataset* with one more name column joining *labels*.

    Genus + Species becomes "Genus Species", valued "Eleusis chapadensis",
    so a legend can show the full name on one row. Blank parts are skipped
    rather than leaving a stray separator. The result is an ordinary name
    column, so grouping, filtering, saving and code export all see it.
    Returns the new dataset and the new column's label.
    """
    keys = dict(zip(dataset.name_labels, dataset.name_keys))
    missing = [label for label in labels if label not in keys]
    if missing:
        raise ValueError(f"No name column called {missing[0]!r}")
    frame = dataset.frame.copy()
    parts = frame[[keys[label] for label in labels]].fillna("").astype(str)
    values = [separator.join(p.strip() for p in row if p.strip())
              for row in parts.itertuples(index=False)]

    existing = dataset.name_labels
    base = separator.join(labels).strip() or "Combined"
    label, counter = base, 2
    while label in existing:
        label = f"{base} ({counter})"
        counter += 1
    # Name columns are name1..nameN in order, ahead of lon/lat.
    frame.insert(len(existing), f"name{len(existing) + 1}", values)
    frame.attrs["name_labels"] = [*existing, label]
    return (PointDataset(frame=frame, source_path=dataset.source_path,
                         skipped=list(dataset.skipped)), label)


def load_csv(path: str, mapping: ColumnMapping | None = None) -> PointDataset:
    """Convenience wrapper: read, guess mapping if not given, build dataset."""
    frame = read_table(path)
    if mapping is None:
        mapping = guess_mapping(frame)
    return build_dataset(frame, mapping, source_path=path)


def build_manual_dataset(legend: str, text: str,
                         order: str = "lat,lon") -> PointDataset:
    """Build a dataset from typed-in coordinate lines.

    Each non-empty line of *text* is one point: two coordinates separated
    by a comma, semicolon, or tab, in *order* ("lat,lon" like SimpleMappr,
    or "lon,lat"). An optional third field is a per-point label.
    Coordinates may be decimal degrees or DMS. Unparseable lines are
    collected in ``skipped``, matching file imports.
    """
    lat_first = order.replace(" ", "").lower().startswith("lat")
    rows: list[list] = []
    skipped: list[str] = []
    any_labels = False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace(";", ",")
                 .replace("\t", ",").split(",")]
        parts = [p for p in parts if p]
        if len(parts) < 2:
            skipped.append(f"line {number}: expected two coordinates, "
                           f"got {line!r}")
            continue
        first, second = parts[0], parts[1]
        label = ", ".join(parts[2:])
        try:
            if lat_first:
                lat = parse_latitude(first)
                lon = parse_longitude(second)
            else:
                lon = parse_longitude(first)
                lat = parse_latitude(second)
        except CoordinateError as exc:
            skipped.append(f"line {number}: {exc}")
            continue
        any_labels = any_labels or bool(label)
        rows.append([legend, label, lon, lat])

    labels = ["Legend"] + (["Label"] if any_labels else [])
    keys = [f"name{i + 1}" for i in range(len(labels))]
    if not any_labels:
        rows = [[row[0], row[2], row[3]] for row in rows]
    frame = pd.DataFrame(rows, columns=[*keys, "lon", "lat"])
    frame.attrs["name_labels"] = labels
    return PointDataset(frame=frame, source_path="", skipped=skipped)
