"""Point styling: per-group color / marker / size used for map and legend."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

__all__ = ["PointStyle", "MARKERS", "DEFAULT_PALETTE", "group_points",
           "default_styles"]

# Display name -> matplotlib marker.
MARKERS = {
    "Circle": "o",
    "Square": "s",
    "Triangle": "^",
    "Diamond": "D",
    "Star": "*",
    "Plus": "P",
    "X": "X",
    "Pentagon": "p",
}

DEFAULT_PALETTE = [
    "#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd",
    "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f",
]


@dataclass
class PointStyle:
    color: str = "#d62728"
    marker: str = "Circle"  # key into MARKERS
    size: float = 30.0      # matplotlib scatter area (points^2)

    @property
    def mpl_marker(self) -> str:
        return MARKERS.get(self.marker, "o")


def group_points(frame: pd.DataFrame, group_by: str | None):
    """Split a point frame into ordered (label, sub_frame) pairs.

    *group_by* is a name column key (``"name1"``, ``"name2"``, ``"name3"``,
    ...) or ``None`` (single group). Groups are ordered by first appearance
    in the file.
    """
    if frame.empty:
        return []
    if group_by is None or group_by not in frame.columns:
        return [("All points", frame)]
    values = frame[group_by].fillna("")
    labels = list(dict.fromkeys(values))
    groups = []
    for label in labels:
        sub = frame[values == label]
        groups.append((label if label else "(blank)", sub))
    return groups


def default_styles(labels: list[str]) -> dict[str, PointStyle]:
    """Assign palette colors round-robin to the given group labels."""
    return {
        label: PointStyle(color=DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)])
        for i, label in enumerate(labels)
    }
