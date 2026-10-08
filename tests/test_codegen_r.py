"""Code export: the generated R with a real R interpreter, and whole exported
R scripts (opt-in)."""

import subprocess

import pytest

from pymappr.export import codegen
from pymappr.export.config import _export_filename, _origin
from pymappr.files.data_loader import build_manual_dataset
from pymappr.files.projects import DatasetEntry

from codegen_helpers import (make_state, manual_entry, file_entry, _rscript,
                             exec_python, run_r_harness, run_r, r_run_state,
                             cities_entry, run_exported_r, assert_r_map_saved)


# ------------------------------------ with a real R interpreter, if any

def test_generated_r_parses_with_real_r(tmp_path):
    rscript = _rscript()
    for entries in ([file_entry()], [manual_entry(symbol_by="Label")], []):
        script = tmp_path / "recreate_map.R"
        script.write_text(codegen.generate_code(make_state(), entries, "R"),
                          encoding="utf-8")
        subprocess.run([rscript, "-e",
                        f"invisible(parse('{script.as_posix()}'))"],
                       check=True, capture_output=True)


def test_generated_r_functions_actually_run(tmp_path):
    """Run the R pre-made loaders on the embedded data (no sf/ggplot2
    needed: library lines and the main() call are stripped)."""
    rscript = _rscript()
    code = codegen.generate_code(make_state(), [manual_entry()], "R")
    # Drop the library() lines, the ensure_packages() bootstrap call (it
    # would try to install over the network), and the final main() call;
    # what remains are the loader functions this harness exercises.
    body = "\n".join(line for line in code.splitlines()
                     if not line.startswith("library(")
                     and not line.startswith("ensure_packages(")
                     and line != "main()")
    harness = body + """
spec <- DATASETS[[1]]
df <- load_points(spec)
stopifnot(nrow(df) == 2)
stopifnot(identical(df$`_lon`, c(-100, 140)))
stopifnot(identical(df$`_lat`, c(38, -25)))
labels <- point_labels(df, spec)
stopifnot(identical(labels, c("spiders", "spiders")))
stopifnot(STYLE_FILLS[["spiders"]] == "#123456")
gdf <- data.frame(FEATURECLA = c("Desert", "Plateau", "desert"),
                  adm0cap = c(1, 0, 1))
kept <- filter_layer(gdf, "featurecla", c("Desert"), TRUE)
stopifnot(identical(kept$FEATURECLA, c("Desert", "desert")))
caps <- filter_layer(gdf, "ADM0CAP", c("1"), TRUE)
stopifnot(nrow(caps) == 2)
dropped <- filter_layer(gdf, "featurecla", c("Desert"), FALSE)
stopifnot(identical(dropped$FEATURECLA, "Plateau"))
cat("R functions OK\\n")
"""
    script = tmp_path / "harness.R"
    script.write_text(harness, encoding="utf-8")
    result = subprocess.run([rscript, str(script)], capture_output=True,
                            text=True)
    assert result.returncode == 0, result.stderr
    assert "R functions OK" in result.stdout


# ------------------------------- running whole exported R scripts (opt-in)
#
# These run a generated script's main() end to end with real R, sf and
# ggplot2, against the Natural Earth zips the app already downloaded into
# data/downloads (copied into the script's naturalearth_cache/, so nothing
# is fetched). Slow, so opt in with PYMAPPR_RUN_R=1.

@run_r
@pytest.mark.parametrize("projection, lon0, lat0", [
    ("Mercator", "", ""),
    ("Lambert: Europe", "", ""),
    ("Globe (Orthographic)", "0", "0"),
    ("Globe (Orthographic)", "-100", "40"),
])
def test_exported_r_script_draws_the_map(tmp_path, projection, lon0, lat0):
    state = r_run_state(projection, lon0, lat0)
    result = run_exported_r(tmp_path, state, [cities_entry()])
    assert_r_map_saved(tmp_path, result)


@run_r
def test_exported_r_script_wraps_the_world_and_its_basemap(tmp_path):
    # Equirectangular from 100E to 260E: the right half is the next world
    # copy, basemap raster included, with Hawaii drawn at 203E.
    hawaii = DatasetEntry(dataset=build_manual_dataset(
        "islands", "19.9,-155.6, Hawaii"), name="islands",
        group_by="Label")
    state = r_run_state("Equirectangular", basemap="relief_grey")
    state["view"] = {"xlim": [100, 260], "ylim": [-40, 60]}
    result = run_exported_r(tmp_path, state, [hawaii])
    assert_r_map_saved(tmp_path, result)


def test_non_finite_origin_exports_the_default_centre():
    assert _origin({"proj_lon0": "inf", "proj_lat0": "nan"}) == (
        None, None)
    assert _origin({"proj_lon0": "1e400", "proj_lat0": "12.5"}) == (
        None, 12.5)


def test_export_filename_drops_the_extension_before_the_device_rule():
    used = set()
    assert _export_filename("CON.csv", ".csv", used, "data") == (
        "CON_.csv")
    assert _export_filename("sites.csv.", ".csv", used, "data") == (
        "sites.csv")
    assert _export_filename(".csv", ".csv", used, "data") == (
        "data.csv")


def test_exported_legend_clears_a_scale_bar_in_its_corner(tmp_path):
    state = make_state(map={"scale_bar": {"show": True,
                                          "position": "lower left"}})
    state["legend"]["location"] = "lower left"
    ns = exec_python(codegen.generate_code(state, [], "Python"))
    fig = ns["plt"].figure(figsize=(6, 4))
    ax = fig.add_axes([0.05, 0.05, 0.9, 0.9])
    ns["SCALE_BAR_CLEAR"] = ("lower left", 0.08, 11.2)
    placement = ns["legend_placement"](ax)
    assert placement["loc"] == "lower left"
    assert placement["bbox_to_anchor"] == (0.0, 0.08)
    ns["LEGEND"]["location"] = "upper right"
    assert ns["legend_placement"](ax) == {"loc": "upper right"}
    ns["plt"].close(fig)

    r = codegen.generate_code(state, [], "R")
    out = run_r_harness(tmp_path, r, """
clear <- scale_bar_clearance()
stopifnot(identical(clear$corner, "lower left"), clear$y > 0.05)
SCALE_BAR$show <- FALSE
stopifnot(is.null(scale_bar_clearance()))
""")
    assert "HARNESS OK" in out


@run_r
def test_exported_r_script_with_legend_and_bar_in_one_corner(tmp_path):
    state = r_run_state("Mercator")
    state["map"]["scale_bar"] = {"show": True, "position": "lower left"}
    state["legend"]["location"] = "lower left"
    result = run_exported_r(tmp_path, state, [cities_entry()])
    assert_r_map_saved(tmp_path, result)
