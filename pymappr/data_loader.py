"""CSV loading and column mapping for point datasets.

A CSV needs a longitude and a latitude column plus any number of name
columns (Name 1, Name 2, Name 3, ...). Column order does not matter:
headers are guessed and the user confirms or remaps them in the UI before
import - picking the latitude/longitude columns is always required.
Coordinates may be decimal degrees or DMS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from pymappr.coords import CoordinateError, parse_latitude, parse_longitude

__all__ = ["ColumnMapping", "PointDataset", "read_csv", "guess_mapping",
           "build_dataset", "load_csv"]

_LON_HINTS = ("lon", "lng", "long", "longitude", "x")
_LAT_HINTS = ("lat", "latitude", "y")


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
    return pd.read_csv(path, dtype=str, keep_default_na=False,
                       skipinitialspace=True, encoding_errors="replace")


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
    """
    columns = list(frame.columns)
    lon = _match(columns, _LON_HINTS)
    lat = _match(columns, _LAT_HINTS)
    if lon is None or lat is None or lon == lat:
        if len(columns) >= 2:
            lon, lat = columns[-2], columns[-1]
        else:
            raise ValueError("CSV needs at least two columns (longitude, latitude)")

    names = [c for c in columns if c not in (lon, lat)]
    return ColumnMapping(longitude=lon, latitude=lat, names=names)


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
