"""CSV loading and column mapping for point datasets.

The expected layout is four columns - Name 1, Name 2, Longitude, Latitude -
but any column order works: headers are guessed and the user can remap them
in the UI before import. Coordinates may be decimal degrees or DMS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ezmaps.coords import CoordinateError, parse_latitude, parse_longitude

__all__ = ["ColumnMapping", "PointDataset", "read_csv", "guess_mapping", "build_dataset"]

_LON_HINTS = ("lon", "lng", "long", "longitude", "x")
_LAT_HINTS = ("lat", "latitude", "y")


@dataclass
class ColumnMapping:
    """Which CSV columns hold each field. Name columns are optional."""

    longitude: str
    latitude: str
    name1: str | None = None
    name2: str | None = None


@dataclass
class PointDataset:
    """Parsed points ready for plotting."""

    frame: pd.DataFrame  # columns: name1, name2, lon, lat
    source_path: str
    skipped: list[str] = field(default_factory=list)  # per-row error messages

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def name1_label(self) -> str:
        return self.frame.attrs.get("name1_label", "Name 1")

    @property
    def name2_label(self) -> str:
        return self.frame.attrs.get("name2_label", "Name 2")


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

    Positional fallback follows the documented layout: column 1 = Name 1,
    column 2 = Name 2, column 3 = Longitude, column 4 = Latitude.
    """
    columns = list(frame.columns)
    lon = _match(columns, _LON_HINTS)
    lat = _match(columns, _LAT_HINTS)
    if lon is None or lat is None or lon == lat:
        if len(columns) >= 4:
            lon, lat = columns[2], columns[3]
        elif len(columns) >= 2:
            lon, lat = columns[-2], columns[-1]
        else:
            raise ValueError("CSV needs at least two columns (longitude, latitude)")

    remaining = [c for c in columns if c not in (lon, lat)]
    name1 = remaining[0] if remaining else None
    name2 = remaining[1] if len(remaining) > 1 else None
    return ColumnMapping(longitude=lon, latitude=lat, name1=name1, name2=name2)


def build_dataset(frame: pd.DataFrame, mapping: ColumnMapping,
                  source_path: str = "") -> PointDataset:
    """Parse coordinates row by row, collecting per-row errors."""
    rows: list[tuple[str, str, float, float]] = []
    skipped: list[str] = []
    for idx, row in frame.iterrows():
        line = idx + 2  # 1-based plus header row
        try:
            lon = parse_longitude(row[mapping.longitude])
            lat = parse_latitude(row[mapping.latitude])
        except CoordinateError as exc:
            skipped.append(f"row {line}: {exc}")
            continue
        name1 = str(row[mapping.name1]).strip() if mapping.name1 else ""
        name2 = str(row[mapping.name2]).strip() if mapping.name2 else ""
        rows.append((name1, name2, lon, lat))

    result = pd.DataFrame(rows, columns=["name1", "name2", "lon", "lat"])
    result.attrs["name1_label"] = mapping.name1 or "Name 1"
    result.attrs["name2_label"] = mapping.name2 or "Name 2"
    return PointDataset(frame=result, source_path=source_path, skipped=skipped)


def load_csv(path: str, mapping: ColumnMapping | None = None) -> PointDataset:
    """Convenience wrapper: read, guess mapping if not given, build dataset."""
    frame = read_csv(path)
    if mapping is None:
        mapping = guess_mapping(frame)
    return build_dataset(frame, mapping, source_path=path)
