from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pymappr.coords import CoordinateError, parse_latitude, parse_longitude

__all__ = ["ColumnMapping", "PointDataset", "read_csv", "read_table",
           "list_sheets", "headers_look_like_data", "guess_mapping",
           "build_dataset", "load_csv", "build_manual_dataset",
           "SPREADSHEET_EXTENSIONS", "OPEN_FILETYPES"]

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
    """

    longitude: str
    latitude: str
    names: list[str] = field(default_factory=list)
    use_headers: bool = True

    @property
    def name1(self) -> str | None:
        return self.names[0] if len(self.names) > 0 else None

    @property
    def name2(self) -> str | None:
        return self.names[1] if len(self.names) > 1 else None


@dataclass
class PointDataset:
    """Parsed points ready for plotting."""

    frame: pd.DataFrame  # columns: name1..nameN, lon, lat
    source_path: str
    skipped: list[str] = field(default_factory=list)  # per-row error messages

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

    @property
    def name1_label(self) -> str:
        labels = self.name_labels
        return labels[0] if labels else "Name 1"

    @property
    def name2_label(self) -> str:
        labels = self.name_labels
        return labels[1] if len(labels) > 1 else "Name 2"


def read_csv(path: str) -> pd.DataFrame:
    """Read a CSV keeping every value as text (coordinates parsed later)."""
    return read_table(path, headers=True)


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
    return frame.fillna("").astype(str)


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
    lowered = {c.lower().strip(): c for c in columns}
    for hint in hints:
        if hint in lowered:
            return lowered[hint]
    for low, original in lowered.items():
        if any(low.startswith(hint) or hint in low for hint in hints):
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


def build_dataset(frame: pd.DataFrame, mapping: ColumnMapping,
                  source_path: str = "") -> PointDataset:
    """Parse coordinates row by row, collecting per-row errors."""
    name_cols = list(mapping.names)
    rows: list[list] = []
    skipped: list[str] = []
    for idx, row in frame.iterrows():
        line = idx + 2  # 1-based plus header row
        try:
            lon = parse_longitude(row[mapping.longitude])
            lat = parse_latitude(row[mapping.latitude])
        except CoordinateError as exc:
            skipped.append(f"row {line}: {exc}")
            continue
        names = [str(row[col]).strip() for col in name_cols]
        rows.append([*names, lon, lat])

    keys = [f"name{i + 1}" for i in range(len(name_cols))]
    result = pd.DataFrame(rows, columns=[*keys, "lon", "lat"])
    if mapping.use_headers:
        labels = name_cols
    else:
        labels = [f"Name {i + 1}" for i in range(len(name_cols))]
    result.attrs["name_labels"] = list(labels)
    # Backwards-compatible attrs used by older callers.
    result.attrs["name1_label"] = labels[0] if labels else "Name 1"
    result.attrs["name2_label"] = labels[1] if len(labels) > 1 else "Name 2"
    return PointDataset(frame=result, source_path=source_path, skipped=skipped)


def load_csv(path: str, mapping: ColumnMapping | None = None) -> PointDataset:
    """Convenience wrapper: read, guess mapping if not given, build dataset."""
    frame = read_csv(path)
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
    frame.attrs["name1_label"] = labels[0]
    frame.attrs["name2_label"] = labels[1] if len(labels) > 1 else "Name 2"
    return PointDataset(frame=frame, source_path="", skipped=skipped)
