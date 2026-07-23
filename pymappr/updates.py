from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

from pymappr import __version__

GITHUB_REPO = "CalebHendren/PyMappr"
LATEST_RELEASE_API = ("https://api.github.com/repos/"
                      f"{GITHUB_REPO}/releases/latest")
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
CHECK_INTERVAL = 24 * 60 * 60  # at most one automatic check per day


def _state_path() -> Path:
    """Per-user file holding the time of the last automatic check."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME",
                                   str(Path.home() / ".config")))
    return base / "PyMappr" / "update_check.json"


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass  # a failed write only means we check again next launch


def parse_version(text: str) -> tuple[int, ...]:
    """``"v1.2.0"`` -> ``(1, 2, 0)``; parsing stops at non-numeric parts."""
    parts: list[int] = []
    for chunk in text.strip().lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def fetch_latest_version(timeout: float = 10.0) -> str:
    """Tag name of the newest GitHub release (raises on network errors)."""
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": f"PyMappr/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        payload = json.load(resp)
    return str(payload.get("tag_name", ""))


def check_now() -> str | None:
    """Query GitHub; return the newer version string, or None if current."""
    tag = fetch_latest_version()
    if parse_version(tag) > parse_version(__version__):
        return tag.lstrip("vV")
    return None


def check_daily_async(on_update) -> bool:
    """Run :func:`check_now` in a background thread, at most once per day.

    Returns False without checking when the last check was less than a
    day ago. Otherwise starts a daemon thread and returns True;
    *on_update* is called from that thread with the newer version string
    if one exists. Network failures are silently ignored (offline use
    must never bother the user).
    """
    state = _load_state()
    now = time.time()
    try:
        last = float(state.get("last_check", 0))
    except (TypeError, ValueError):
        last = 0.0
    if now - last < CHECK_INTERVAL:
        return False
    _save_state({"last_check": now})

    def worker() -> None:
        try:
            newer = check_now()
        except Exception:  # noqa: BLE001 - offline/rate-limited: retry tomorrow
            return
        if newer:
            on_update(newer)

    threading.Thread(target=worker, daemon=True).start()
    return True
