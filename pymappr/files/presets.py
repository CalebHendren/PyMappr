from __future__ import annotations

import json
import time
from pathlib import Path

from pymappr import __version__
from pymappr.files.projects import DatasetEntry, config_dir, safe_filename

__all__ = ["PRESET_EXTENSION", "presets_dir", "preset_path", "list_presets",
           "save_preset", "load_preset", "delete_preset",
           "built_in_deleted", "delete_built_in",
           "settings_from_state", "apply_dataset_style"]

PRESET_EXTENSION = ".pymappr-preset"
_FORMAT = "pymappr-preset"
_FORMAT_VERSION = 1
# Present in the presets folder once the user has deleted the built-in
# preset, which has no file of its own to remove.
_BUILT_IN_DELETED = ".built-in-deleted"

# The parts of a project state that belong to this project alone: its data,
# which dataset is selected, and where the map is zoomed. A preset carries
# everything else.
_PROJECT_ONLY = ("datasets", "active", "view")

# Per-dataset choices that name a column; a preset applies each one only to
# a dataset that has that column.
_COLUMN_FIELDS = (("group_by", "Group by"), ("color_by", "Color by"),
                  ("symbol_by", "Symbol by"), ("open_by", "Open symbols for"))


def presets_dir() -> Path:
    """The folder presets are saved in, beside the session autosave."""
    folder = config_dir() / "Presets"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def preset_path(name: str) -> Path:
    return presets_dir() / (safe_filename(name) + PRESET_EXTENSION)


def list_presets(folder: str | Path | None = None) -> list[tuple[str, Path]]:
    """(name, path) for every readable preset, sorted by name."""
    folder = Path(folder) if folder else presets_dir()
    try:
        files = [p for p in folder.iterdir()
                 if p.suffix == PRESET_EXTENSION and p.is_file()]
    except OSError:
        return []
    found = []
    for path in files:
        try:
            name, _settings = load_preset(path)
        except (OSError, ValueError):
            continue
        found.append((name, path))
    return sorted(found, key=lambda item: item[0].casefold())


def save_preset(path: str | Path, name: str, settings: dict) -> None:
    document = {
        "format": _FORMAT,
        "format_version": _FORMAT_VERSION,
        "app_version": __version__,
        "name": name,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "settings": settings,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def load_preset(path: str | Path) -> tuple[str, dict]:
    """Read a preset file; returns (preset name, settings dict)."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"Not a PyMappr preset file: {exc}") from exc
    if (not isinstance(document, dict)
            or document.get("format") != _FORMAT
            or not isinstance(document.get("settings"), dict)):
        raise ValueError("Not a PyMappr preset file.")
    if int(document.get("format_version", 1)) > _FORMAT_VERSION:
        raise ValueError(
            "This preset was saved by a newer PyMappr "
            f"({document.get('app_version', '?')}). Update PyMappr to "
            "use it.")
    name = str(document.get("name") or Path(path).stem)
    return name, document["settings"]


def delete_preset(path: str | Path) -> None:
    Path(path).unlink()


def built_in_deleted() -> bool:
    return (presets_dir() / _BUILT_IN_DELETED).exists()


def delete_built_in() -> None:
    (presets_dir() / _BUILT_IN_DELETED).touch()


# ---------------------------------------------------------------- applying

def settings_from_state(state: dict, entry: DatasetEntry | None) -> dict:
    """A preset from a collected project *state*: every setting but the
    data and the zoom, plus the styling of the selected dataset *entry*."""
    settings = {key: value for key, value in state.items()
                if key not in _PROJECT_ONLY}
    settings["dataset"] = {} if entry is None else {
        "group_by": entry.group_by,
        "color_by": entry.color_by,
        "symbol_by": entry.symbol_by,
        "vary_symbols": entry.vary_symbols,
        "open_by": entry.open_by,
        "open_values": list(entry.open_values),
        "legend_overrides": {key: dict(value) for key, value
                             in entry.legend_overrides.items()},
    }
    return settings


def apply_dataset_style(entry: DatasetEntry, style: dict) -> list[str]:
    """Give *entry* a preset's dataset *style*.

    A choice naming a column the dataset lacks is left as it was, and its
    description (Group by “Genus Species”) is returned so the
    caller can say what did not carry over. Legend-row edits are merged in,
    the preset's winning where both edited the same row.
    """
    if not style:
        return []
    labels = set(entry.dataset.name_labels)
    skipped = []
    for field, title in _COLUMN_FIELDS:
        if field not in style:
            continue
        value = str(style.get(field) or "")
        if value and value not in labels:
            skipped.append(f"{title} \N{LEFT DOUBLE QUOTATION MARK}{value}"
                           "\N{RIGHT DOUBLE QUOTATION MARK}")
            continue
        setattr(entry, field, value)
        if field == "open_by":
            entry.open_values = ([str(v) for v in style.get("open_values")
                                  or []] if value else [])
    if "vary_symbols" in style:
        entry.vary_symbols = bool(style["vary_symbols"])
    for key, override in dict(style.get("legend_overrides") or {}).items():
        if isinstance(override, dict):
            entry.legend_overrides.setdefault(str(key), {}).update(override)
    return skipped
