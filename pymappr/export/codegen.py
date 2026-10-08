"""Exporting the map as a ready-to-run Python or R script.

``build_config`` (config.py, layer sources in layers_config.py) turns the
app state into plain data; python_script.py and r_script.py write it out
as a configuration block above the pre-made functions in templates/, with
the literal helpers in literals.py.
"""

from __future__ import annotations

from pymappr.export.config import (BASEMAP_RASTERS, _export_filename,
                                   build_config)
from pymappr.export.literals import _safe_name
from pymappr.export.python_script import (_PY_GITIGNORE, _PY_REQUIREMENTS,
                                          _py_readme, _python_script)
from pymappr.export.r_script import (_R_GITIGNORE, _R_INSTALL, _RPROJ,
                                     _r_readme, _r_script)
from pymappr.renderer.tables import MARGINS_PLAIN, MARGINS_WITH_TICKS

__all__ = ["LANGUAGES", "CODE_EXTENSIONS", "BASEMAP_RASTERS",
           "MARGINS_PLAIN", "MARGINS_WITH_TICKS", "build_config",
           "generate_code", "generate_working_directory"]

LANGUAGES = ("Python", "R")
CODE_EXTENSIONS = {"Python": ".py", "R": ".R"}


# -------------------------------------------------- working directory export

def generate_working_directory(state: dict, entries, language: str,
                               project_name: str = "Untitled",
                               figure_size: tuple[float, float] | None = None
                               ) -> dict[str, str]:
    """A ready-to-run project folder recreating the map, as a mapping of
    relative path -> text content.

    Alongside the script it includes the point data as CSV under
    ``data/``, a dependency manifest (``requirements.txt`` or
    ``install.R``), a ``README.md``, a ``.gitignore``, and - for R - an
    RStudio ``.Rproj`` file. Point an IDE at the folder and run.
    """
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    config = build_config(state, entries, project_name, data_mode="files",
                          figure_size=figure_size)
    project = _safe_name(project_name)
    if language == "Python":
        files = {
            "recreate_map.py": _python_script(config),
            "requirements.txt": _PY_REQUIREMENTS,
            "README.md": _py_readme(project),
            ".gitignore": _PY_GITIGNORE,
        }
    else:
        rproj = _export_filename(project, ".Rproj", set(), "map")
        files = {
            "recreate_map.R": _r_script(config),
            "install.R": _R_INSTALL,
            rproj: _RPROJ,
            "README.md": _r_readme(project, rproj),
            ".gitignore": _R_GITIGNORE,
        }
    files.update(config["data_files"])  # data/<name>.csv -> CSV text
    return files


# ----------------------------------------------------------------- entry

def generate_code(state: dict, entries, language: str,
                  project_name: str = "Untitled",
                  figure_size: tuple[float, float] | None = None) -> str:
    """The complete Python or R script recreating the given map state.

    The script is self-contained: point data is embedded inline, and a
    missing package stops it with the command that installs it (or is
    installed for you with ``--install-deps``). The Python script replicates PyMappr's
    renderer; pass *figure_size* (the app canvas in inches) so the
    exported geometry matches the canvas exactly. Use
    :func:`generate_working_directory` for a folder-based export with the
    data kept as separate CSV files.
    """
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    config = build_config(state, entries, project_name,
                          figure_size=figure_size)
    if language == "Python":
        return _python_script(config)
    return _r_script(config)
