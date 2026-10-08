"""Shared helpers for the code export tests: map states, datasets, and
running the generated scripts."""

import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from pymappr.export import codegen
from pymappr.files.data_loader import build_manual_dataset
from pymappr.files.projects import DatasetEntry, entry_from_dict
from pymappr.styling.layout import layout_points
from pymappr.styling.legend import LegendOptions, row_key
from pymappr.styling.styles import DEFAULT_PALETTE


def make_state(**overrides):
    state = {
        "datasets": [],
        "active": 0,
        "map": {
            "projection": "Robinson", "proj_lon0": "", "proj_lat0": "",
            "basemap": "simple", "continent": "World",
            "compass": True, "graticule": "5\N{DEGREE SIGN}",
            "hide_grid_labels": False, "line_width": 1.0, "dpi": "300",
            "ocean": "blue", "lake_fill": "grey", "bathymetry": False,
            "capitals_only": False,
            "lines": {"countries": True, "rivers": True, "wadis": True,
                      "eez": False},
            "fills": {"land": True, "disputed": False},
            "points": {"cities": True},
            "labels": {"countries": False},
        },
        "legend": {"show": True, "frame": True, "location": "upper right",
                   "fontsize": "9", "title_fontsize": "12", "columns": "2",
                   "marker_scale": "1.5", "label_spacing": "0.8",
                   "title": ""},
        "point_alpha": 0.85,
        "view": {"xlim": [-180, 180], "ylim": [-90, 90]},
    }
    state["map"].update(overrides.pop("map", {}))
    state.update(overrides)
    return state


def manual_entry(name="spiders", **kwargs):
    dataset = build_manual_dataset(
        name, "38,-100, Site A\n-25,140, Site B\n")
    defaults = dict(dataset=dataset, name=name, group_by="Legend",
                    legend_overrides={row_key("group", name): {
                        "color": "#123456", "marker": "Star", "size": 45.0}})
    defaults.update(kwargs)
    return DatasetEntry(**defaults)


def file_entry():
    """A dataset as if imported from a CSV with a State name column."""
    return entry_from_dict({
        "name": "us_cities.csv",
        "source_path": "C:/data/us_cities.csv",
        "columns": ["name1", "lon", "lat"],
        "name_labels": ["State"],
        "rows": [["Wyoming", -107.5, 43.0], ["Colorado", -105.5, 39.0],
                 ["Wyoming", -104.8, 41.1]],
        "group_by": "State",
        "styles": {"Wyoming": {"color": "#123456", "marker": "Star",
                               "size": 45.0}},
    })


def find_rscript() -> str | None:
    """Rscript on PATH, else the newest one in a standard Windows install
    (R's installer does not put itself on PATH)."""
    found = shutil.which("Rscript")
    if found:
        return found
    candidates = sorted(Path("C:/Program Files/R").glob("R-*/bin/Rscript.exe"))
    return str(candidates[-1]) if candidates else None


def _rscript():
    path = find_rscript()
    if path is None:
        pytest.skip("Rscript is not installed (not on PATH or in "
                    "C:/Program Files/R)")
    return path


_R_PACKAGE_CACHE: dict[tuple[str, ...], list[str]] = {}


def _rscript_with(*packages):
    """Rscript, skipping visibly when any of *packages* is not installed."""
    rscript = _rscript()
    if packages not in _R_PACKAGE_CACHE:
        names = ", ".join(f"'{pkg}'" for pkg in packages)
        result = subprocess.run(
            [rscript, "-e",
             f"cat(Filter(function(p) !requireNamespace(p, quietly = TRUE), "
             f"c({names})), sep = ' ')"],
            capture_output=True, text=True)
        _R_PACKAGE_CACHE[packages] = (
            result.stdout.split() if result.returncode == 0 else
            list(packages))
    missing = _R_PACKAGE_CACHE[packages]
    if missing:
        pytest.skip("R package(s) not installed: " + ", ".join(missing))
    return rscript


def assert_parses_as_r(code):
    """Parse generated R with a real R interpreter; skip, visibly, when
    there is none."""
    rscript = _rscript()
    result = subprocess.run(
        [rscript, "-e", "invisible(parse(file('stdin'), encoding = 'UTF-8'))"],
        input=code.encode("utf-8"), capture_output=True)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")


def all_styles(ns):
    """Every dataset's label -> style, merged (for single-dataset maps)."""
    return {label: style for spec in ns["DATASETS"]
            for label, style in spec["styles"].items()}


def exec_python(code):
    """Run a generated script's definitions with geopandas stubbed out
    (main() stays unexecuted behind the __main__ guard)."""
    fake = types.ModuleType("geopandas")
    fake.read_file = lambda *a, **k: None
    fake.GeoDataFrame = object
    fake.GeoSeries = object
    fake.points_from_xy = lambda *a, **k: None
    saved = sys.modules.get("geopandas")
    sys.modules["geopandas"] = fake
    try:
        namespace = {"__name__": "recreate_map"}
        exec(compile(code, "recreate_map.py", "exec"), namespace)
    finally:
        if saved is None:
            del sys.modules["geopandas"]
        else:
            sys.modules["geopandas"] = saved
    return namespace


def run_r_harness(tmp_path, code, harness, name="harness.R"):
    """Run a generated R script's definitions (the package bootstrap and
    the final main() call dropped) followed by *harness*; return stdout."""
    rscript = _rscript_with("sf", "ggplot2")
    body = "\n".join(line for line in code.splitlines()
                     if not line.startswith("ensure_packages(")
                     and line != "main()")
    script = tmp_path / name
    script.write_text(body + "\n" + harness + '\ncat("HARNESS OK\\n")\n',
                      encoding="utf-8")
    result = subprocess.run([rscript, str(script)], cwd=tmp_path,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
    assert result.returncode == 0, result.stderr[-3000:]
    assert "HARNESS OK" in result.stdout, result.stdout[-2000:]
    return result.stdout


# ---------------------------------------------- datasets for the 1.31.3 fixes

TRICKY_LABELS = ["NA", "007", "T", "1.50", ""]


def coded_entry(name="codes", labels=TRICKY_LABELS, column="Code",
                **extra):
    """A grouped dataset whose group values pandas and R would retype."""
    rows = [[label, -100.0 + i * 10.0, 40.0 - i * 5.0]
            for i, label in enumerate(labels)]
    return entry_from_dict({"name": name, "columns": ["name1", "lon", "lat"],
                            "name_labels": [column], "rows": rows,
                            "group_by": column, **extra})


def ungrouped_entry(name, color, source_path=""):
    entry = manual_entry(name, group_by="",
                         legend_overrides={row_key("group", "All points"): {
                             "color": color}})
    entry.dataset.source_path = source_path
    return entry


def app_labels(entries, legend=None):
    """The labels the app draws each dataset's groups under."""
    layout = layout_points(entries, LegendOptions.from_dict(legend or {}),
                           DEFAULT_PALETTE)
    return [[label for label, _style, _rows in dataset.groups]
            for dataset in layout.datasets]


# ------------------------------- running whole exported R scripts (opt-in)

NE_DOWNLOADS = Path(__file__).resolve().parent.parent / "data" / "downloads"

run_r = pytest.mark.skipif(os.environ.get("PYMAPPR_RUN_R") != "1",
                           reason="set PYMAPPR_RUN_R=1 to run whole R "
                                  "scripts")


def r_run_state(projection, lon0="", lat0="", **map_overrides):
    """A small map: world-scale layers only, so the 110m zips do."""
    settings = {"projection": projection, "proj_lon0": lon0,
                "proj_lat0": lat0, "graticule": "10\N{DEGREE SIGN}",
                "ocean": "blue", "lake_fill": "grey",
                "lines": {"countries": True}, "fills": {"land": True},
                "points": {}, "labels": {},
                "scale_bar": {"show": True}}
    settings.update(map_overrides)
    return make_state(map=settings, view={})


def cities_entry():
    """Two groups far apart, so a regional map clips one of them."""
    dataset = build_manual_dataset(
        "cities", "48.86,2.35, Paris\n-33.92,18.42, Cape Town\n"
                  "51.5,-0.12, Paris\n")
    return DatasetEntry(dataset=dataset, name="cities", group_by="Label")


def run_exported_r(tmp_path, state, entries, files=None):
    """Write the exported script (plus any extra *files*) to *tmp_path* with
    a pre-filled Natural Earth cache, run it, and return the result."""
    rscript = _rscript_with("sf", "ggplot2")
    config = codegen.build_config(state, entries)
    cache = tmp_path / "naturalearth_cache"
    cache.mkdir()
    inset_layers = config["inset"]["layers"] if config["inset"] else []
    zip_names = [f"ne_{layer['scale']}_{layer['name']}.zip"
                 for layer in config["layers"] + inset_layers]
    if config["basemap"] in codegen.BASEMAP_RASTERS:
        (_scale, _category, name), _jpg = codegen.BASEMAP_RASTERS[
            config["basemap"]]
        zip_names.append(f"{name}.zip")
    for zip_name in zip_names:
        source = NE_DOWNLOADS / zip_name
        if not source.exists():
            pytest.skip(f"{zip_name} is not in {NE_DOWNLOADS}")
        shutil.copyfile(source, cache / zip_name)
    script = tmp_path / "recreate_map.R"
    script.write_text(codegen.generate_code(state, entries, "R"),
                      encoding="utf-8")
    for name, text in (files or {}).items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    result = subprocess.run([rscript, str(script)], cwd=tmp_path,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=600)
    return result


def assert_r_map_saved(tmp_path, result):
    assert result.returncode == 0, result.stderr[-3000:]
    assert (tmp_path / "map.png").stat().st_size > 10_000
    assert "Saved map.png" in result.stderr
