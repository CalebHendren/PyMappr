"""Project persistence: save/load named projects, settings, and sessions.

A *project* is everything needed to reproduce the current map: every
loaded dataset (data included, so a project file is self-contained and
can be shared with collaborators), per-dataset styling, the visible
layers, projection, view, legend, and export options.

Projects are JSON documents with a ``.pymappr`` extension, stored in a
user-selectable projects folder (Documents/PyMappr Projects by default).
Because they live in per-user directories - never inside the install
directory - they survive application updates. Import/export is the same
format: an exported file dropped in someone else's projects folder (or
imported through the File menu) opens identically for them.

The *session* is an automatic project saved to the per-user config
directory when the app closes and restored on the next launch, so users
pick up right where they left off.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pymappr import __version__
from pymappr.data_loader import PointDataset
from pymappr.styles import PointStyle

__all__ = ["PROJECT_EXTENSION", "DatasetEntry", "config_dir",
           "load_settings", "save_settings", "projects_dir",
           "set_projects_dir", "session_path", "entry_to_dict",
           "entry_from_dict", "save_project", "load_project",
           "list_projects", "delete_project", "rename_project",
           "safe_filename"]

PROJECT_EXTENSION = ".pymappr"
_FORMAT = "pymappr-project"
_FORMAT_VERSION = 1


# ------------------------------------------------------------- directories

def config_dir() -> Path:
    """Per-user configuration directory (settings, session autosave)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME",
                                   str(Path.home() / ".config")))
    return base / "PyMappr"


def _settings_path() -> Path:
    return config_dir() / "settings.json"


def session_path() -> Path:
    """Autosaved session, restored on the next launch."""
    return config_dir() / ("session" + PROJECT_EXTENSION)


def load_settings() -> dict:
    try:
        settings = json.loads(_settings_path().read_text(encoding="utf-8"))
        return settings if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass  # settings are conveniences; never block the app on them


def _default_projects_dir() -> Path:
    documents = Path.home() / "Documents"
    base = documents if documents.is_dir() else Path.home()
    return base / "PyMappr Projects"


def projects_dir() -> Path:
    """The folder projects are saved in (user-selectable, created lazily)."""
    stored = load_settings().get("projects_dir")
    folder = Path(stored) if stored else _default_projects_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        folder = _default_projects_dir()
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def set_projects_dir(folder: str | Path) -> None:
    settings = load_settings()
    settings["projects_dir"] = str(folder)
    save_settings(settings)


# ---------------------------------------------------------------- datasets

@dataclass
class DatasetEntry:
    """One loaded dataset plus everything the user set up around it."""

    dataset: PointDataset
    name: str
    visible: bool = True
    group_by: str = ""       # display labels ("" = None)
    color_by: str = ""
    symbol_by: str = ""
    vary_symbols: bool = False
    styles: dict[str, PointStyle] = field(default_factory=dict)
    # For typed-in datasets: {"text": ..., "order": ...} so they can be
    # re-opened in the manual entry dialog and edited.
    manual: dict | None = None


def entry_to_dict(entry: DatasetEntry) -> dict:
    """Serialize a dataset entry, data included, to JSON-safe values."""
    frame = entry.dataset.frame
    return {
        "name": entry.name,
        "visible": entry.visible,
        "source_path": entry.dataset.source_path,
        "columns": [str(c) for c in frame.columns],
        "name_labels": entry.dataset.name_labels,
        "rows": [[value if isinstance(value, (int, float)) else str(value)
                  for value in row] for row in frame.itertuples(index=False)],
        "group_by": entry.group_by,
        "color_by": entry.color_by,
        "symbol_by": entry.symbol_by,
        "vary_symbols": entry.vary_symbols,
        "styles": {label: {"color": style.color, "marker": style.marker,
                           "size": style.size}
                   for label, style in entry.styles.items()},
        "manual": entry.manual,
    }


def entry_from_dict(data: dict) -> DatasetEntry:
    columns = [str(c) for c in data.get("columns", [])]
    frame = pd.DataFrame(data.get("rows", []), columns=columns)
    for column in ("lon", "lat"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    labels = [str(v) for v in data.get("name_labels", [])]
    frame.attrs["name_labels"] = labels
    frame.attrs["name1_label"] = labels[0] if labels else "Name 1"
    frame.attrs["name2_label"] = labels[1] if len(labels) > 1 else "Name 2"
    dataset = PointDataset(frame=frame,
                           source_path=str(data.get("source_path", "")))
    styles = {}
    for label, raw in dict(data.get("styles", {})).items():
        try:
            styles[label] = PointStyle(color=str(raw.get("color", "#d62728")),
                                       marker=str(raw.get("marker", "Circle")),
                                       size=float(raw.get("size", 30.0)))
        except (TypeError, ValueError, AttributeError):
            continue
    manual = data.get("manual")
    return DatasetEntry(
        dataset=dataset,
        name=str(data.get("name", "Dataset")),
        visible=bool(data.get("visible", True)),
        group_by=str(data.get("group_by", "")),
        color_by=str(data.get("color_by", "")),
        symbol_by=str(data.get("symbol_by", "")),
        vary_symbols=bool(data.get("vary_symbols", False)),
        styles=styles,
        manual=dict(manual) if isinstance(manual, dict) else None,
    )


# ---------------------------------------------------------------- projects

def save_project(path: str | Path, name: str, state: dict) -> None:
    """Write *state* (the app's collected state dict) as a project file."""
    document = {
        "format": _FORMAT,
        "format_version": _FORMAT_VERSION,
        "app_version": __version__,
        "name": name,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "state": state,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def load_project(path: str | Path) -> tuple[str, dict]:
    """Read a project file; returns (project name, state dict)."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"Not a PyMappr project file: {exc}") from exc
    if (not isinstance(document, dict)
            or document.get("format") != _FORMAT
            or not isinstance(document.get("state"), dict)):
        raise ValueError("Not a PyMappr project file.")
    if int(document.get("format_version", 1)) > _FORMAT_VERSION:
        raise ValueError(
            "This project was saved by a newer PyMappr "
            f"({document.get('app_version', '?')}). Update PyMappr to "
            "open it.")
    name = str(document.get("name") or Path(path).stem)
    return name, document["state"]


def list_projects(folder: str | Path | None = None) -> list[Path]:
    """Project files in the projects folder, most recently saved first."""
    folder = Path(folder) if folder else projects_dir()
    try:
        files = [p for p in folder.iterdir()
                 if p.suffix == PROJECT_EXTENSION and p.is_file()]
    except OSError:
        return []
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def delete_project(path: str | Path) -> None:
    Path(path).unlink()


def rename_project(path: str | Path, new_name: str) -> Path:
    """Rename a project file; returns the new path."""
    path = Path(path)
    target = path.with_name(safe_filename(new_name) + PROJECT_EXTENSION)
    if target.exists() and target != path:
        raise FileExistsError(f"A project named {new_name!r} already exists.")
    path.rename(target)
    return target


def safe_filename(name: str) -> str:
    """A filesystem-safe version of a user-typed project name."""
    cleaned = "".join("_" if ch in '<>:"/\\|?*' or ord(ch) < 32 else ch
                      for ch in name.strip())
    return cleaned.strip(". ") or "Untitled"
