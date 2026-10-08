"""Code export: the 1.31.3 export and review fixes for awkward names,
non-finite numbers, interrupted downloads and R-specific options."""

import ast
import io
import math
import types
import zipfile
from pathlib import Path

import pytest

from pymappr.export import codegen, literals
from pymappr.export.config import _export_filename
from pymappr.styling.legend import row_key

from codegen_helpers import (make_state, manual_entry, file_entry,
                             assert_parses_as_r, exec_python, run_r_harness,
                             coded_entry, ungrouped_entry, app_labels)


# ------------------------------------------------- export fixes (1.31.3)

def test_names_with_escapes_and_quotes_compile(tmp_path):
    names = ["Field\\Notes 2024", "C:\\path\\x41", 'say "hi"',
             "two\nlines", "caf\u00e9 \u00e5\u00df \u6f22", "\\N{oops}"]
    for name in names:
        entries = [manual_entry(name), ungrouped_entry(name, "#123456")]
        code = codegen.generate_code(make_state(), entries, "Python", name)
        compile(code, "recreate_map.py", "exec")
        ns = exec_python(code)
        assert [spec["name"] for spec in ns["DATASETS"]] == [name, name]
        files = codegen.generate_working_directory(make_state(), entries,
                                                   "Python", name)
        compile(files["recreate_map.py"], "recreate_map.py", "exec")
    expected = tmp_path / "expected.txt"
    for name in names:
        code = codegen.generate_code(make_state(), [manual_entry(name)], "R",
                                     name)
        expected.write_text(name, encoding="utf-8")
        run_r_harness(tmp_path, code, """
wanted <- paste(readLines("expected.txt", encoding = "UTF-8", warn = FALSE),
                collapse = "\\n")
stopifnot(identical(enc2utf8(DATASETS[[1]]$name), wanted))
""")


def test_backslash_project_name_compiles():
    # "\N" in a normal docstring starts a named-character escape.
    code = codegen.generate_code(make_state(), [file_entry()], "Python",
                                 "Field\\Notes 2024")
    docstring = ast.get_docstring(ast.parse(code))
    assert docstring.startswith(
        'Recreate the PyMappr map "Field\\Notes 2024" outside')


def test_source_path_cannot_inject_code(tmp_path):
    attack = "C:/data/x.csv\nINJECTED = 1\r\nINJECTED <- 1"
    entry = ungrouped_entry("Sites", "#123456", source_path=attack)
    py = codegen.generate_code(make_state(), [entry], "Python")
    assert "# originally imported from: C:/data/x.csv INJECTED = 1" in py
    assert "INJECTED" not in exec_python(py)
    r = codegen.generate_code(make_state(), [entry], "R")
    run_r_harness(tmp_path, r, 'stopifnot(!exists("INJECTED"))')


def test_non_finite_numbers_are_valid_literals(tmp_path):
    assert literals._py(float("nan")) == 'float("nan")'
    assert literals._py(float("inf")) == 'float("inf")'
    assert literals._py(-float("inf")) == '-float("inf")'
    assert literals._py({"a": (float("nan"),)}) == "{'a': (float(\"nan\"),)}"
    assert literals._r(float("nan")) == "NA_real_"
    assert literals._r(float("inf")) == "Inf"
    assert literals._r(-float("inf")) == "-Inf"
    # Typing "nan" as the scale bar's fixed length.
    state = make_state(map={"scale_bar": {"show": True,
                                          "length_mode": "fixed",
                                          "fixed_length": float("nan")}})
    ns = exec_python(codegen.generate_code(state, [], "Python"))
    assert math.isnan(ns["SCALE_BAR"]["fixed_length"])
    r = codegen.generate_code(state, [], "R")
    run_r_harness(tmp_path, r, "stopifnot(is.na(SCALE_BAR$fixed_length))")


def test_stale_color_by_is_ignored_like_the_app():
    entry = manual_entry(symbol_by="Label", group_by="",
                         color_by="Gone")  # names no column any more
    ns = exec_python(codegen.generate_code(make_state(), [entry], "Python"))
    spec = ns["DATASETS"][0]
    assert spec["color_col"] is None and spec["symbol_col"] == "Label"
    labels = ns["point_labels"](ns["load_points"](spec), spec)
    assert list(labels) == ["Site A", "Site B"]


def test_dataset_files_survive_case_and_reserved_names():
    entries = [manual_entry(name) for name in
               ("Sites", "sites", "CON", "nul.csv", "My Sites")]
    files = codegen.generate_working_directory(make_state(), entries,
                                               "Python", "P")
    data = [name for name in files if name.startswith("data/")]
    assert data == ["data/Sites.csv", "data/sites_2.csv", "data/CON_.csv",
                    "data/nul_.csv", "data/My Sites.csv"]
    assert len({name.casefold() for name in data}) == len(data)
    rproj = codegen.generate_working_directory(make_state(), [], "R", "AUX")
    assert "AUX_.Rproj" in rproj


def test_projection_helpers_are_built_once():
    ns = exec_python(codegen.generate_code(make_state(), [], "Python"))
    assert ns["_transformer"]() is ns["_transformer"]()
    assert ns["_geod"]() is ns["_geod"]()


def _zip_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ne_110m_land/ne_110m_land.shp", b"shape")
        archive.writestr("ne_110m_land/ne_110m_land.dbf", b"table")
    return buffer.getvalue()


def test_python_recovers_from_an_interrupted_download(tmp_path):
    ns = exec_python(codegen.generate_code(make_state(), [], "Python"))
    ns["SCRIPT_DIR"] = tmp_path
    cache = tmp_path / "naturalearth_cache"
    cache.mkdir()
    good = _zip_bytes()
    zip_path = cache / "ne_110m_land.zip"
    zip_path.write_bytes(good[: len(good) // 2])  # cut off mid-download
    fetched = []

    def fake_urlretrieve(url, target):
        fetched.append(url)
        Path(target).write_bytes(good)

    ns["urlretrieve"] = fake_urlretrieve
    assert ns["download_archive"]("110m", "physical", "land") == zip_path
    assert fetched and zip_path.read_bytes() == good

    # A download that dies part-way leaves no zip that looks finished.
    zip_path.unlink()

    def dying_urlretrieve(url, target):
        Path(target).write_bytes(good[:10])
        raise KeyboardInterrupt

    ns["urlretrieve"] = dying_urlretrieve
    with pytest.raises(KeyboardInterrupt):
        ns["download_archive"]("110m", "physical", "land")
    assert not zip_path.exists()


def test_python_recovers_from_a_failed_extraction(tmp_path):
    ns = exec_python(codegen.generate_code(make_state(), [], "Python"))
    zip_path = tmp_path / "ne_110m_land.zip"
    zip_path.write_bytes(_zip_bytes())
    folder = tmp_path / "ne_110m_land"
    folder.mkdir()  # what an extraction that failed used to leave behind
    ns["extract_archive"](zip_path, folder, "ne_110m_land.shp")
    assert (folder / "ne_110m_land.shp").read_bytes() == b"shape"
    assert not (tmp_path / "ne_110m_land.part").exists()


# ------------------------------------------------ review fixes (1.31.3)

def test_r_recovers_from_a_failed_extraction(tmp_path):
    # R's unzip only warns about a member it cannot decode (here LZMA), so
    # the folder used to be moved into place holding just the .shp, and
    # every later run skipped extraction and failed to read it.
    with zipfile.ZipFile(tmp_path / "bad.zip", "w") as archive:
        archive.writestr("ne/ne_110m_land.shp", b"shape",
                         compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("ne/ne_110m_land.dbf", b"table" * 100,
                         compress_type=zipfile.ZIP_LZMA)
    (tmp_path / "good.zip").write_bytes(_zip_bytes())
    code = codegen.generate_code(make_state(), [], "R")
    run_r_harness(tmp_path, code, """
failed <- tryCatch({
  extract_archive("bad.zip", "bad", "ne_110m_land.shp")
  FALSE
}, error = function(e) TRUE)
stopifnot(failed)
# Nothing that looks finished is left, and the zip goes so the next run
# downloads it again.
stopifnot(!dir.exists("bad"), !dir.exists("bad.part"),
          !file.exists("bad.zip"))
folder <- extract_archive("good.zip", "good", "ne_110m_land.shp")
stopifnot(identical(sort(list.files(folder)),
                    c("ne_110m_land.dbf", "ne_110m_land.shp")))
stopifnot(file.exists("good.zip"))
""")


@pytest.mark.parametrize("family, r_family", [
    ("monospace", "mono"), ("sans-serif", "sans"), ("serif", "serif"),
    ("DejaVu Sans", "DejaVu Sans")])
def test_r_legend_font_family_uses_r_names(tmp_path, family, r_family):
    # matplotlib's generic families have other names in R: "monospace" is
    # not one, and quietly fell back to Arial.
    state = make_state(legend={"font_family": family, "title": "T"})
    code = codegen.generate_code(state, [manual_entry()], "R")
    run_r_harness(tmp_path, code, f"""
stopifnot(identical(legend_text(9, FALSE, FALSE, "#000000")$family,
                    "{r_family}"))
""")


def west_entry():
    """Wyoming and Colorado both renamed "West", in different colours."""
    entry = file_entry()
    entry.legend_overrides = {
        row_key("group", "Wyoming"): {"label": "West", "color": "#111111"},
        row_key("group", "Colorado"): {"label": "West", "color": "#222222"}}
    return entry


def test_python_keeps_groups_renamed_to_the_same_label_apart():
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    entry = west_entry()
    assert app_labels([entry]) == [["West", "West"]]
    state = make_state(map={"projection": "Equirectangular"})
    ns = exec_python(codegen.generate_code(state, [entry], "Python"))
    calls = []
    ax = types.SimpleNamespace(
        scatter=lambda xs, ys, **kw: calls.append((list(ys), kw["c"])))
    ns["plot_dataset"](ax, ns["DATASETS"][0])
    # Wyoming's points (lat 43.0 and 41.1) keep Wyoming's colour.
    assert sorted(calls) == [([39.0], "#222222"), ([43.0, 41.1], "#111111")]
    fig = matplotlib.figure.Figure()
    axes = fig.add_subplot(111)
    ns["add_legend"](axes)
    legend = axes.get_legend()
    assert [t.get_text() for t in legend.get_texts()] == ["West", "West"]
    assert [h.get_markerfacecolor() for h in legend.legend_handles] == [
        "#111111", "#222222"]


def test_r_keeps_groups_renamed_to_the_same_label_apart(tmp_path):
    code = codegen.generate_code(make_state(), [west_entry()], "R")
    run_r_harness(tmp_path, code, """
points <- load_all_points()
fills <- unname(STYLE_FILLS[points$key])
stopifnot(identical(fills, c("#111111", "#222222", "#111111")))
guide <- get_guide_data(ggplot() + point_layers(), "fill")
stopifnot(identical(guide$.label, c("West", "West")))
stopifnot(identical(guide$fill, c("#111111", "#222222")))
""")


def test_nul_characters_never_reach_the_scripts(tmp_path):
    entry = coded_entry(name="nul\x00name", labels=["a\x00b", "c"])
    entry.dataset.source_path = "C:/data/x\x00.csv"
    py = codegen.generate_code(make_state(), [entry], "Python", "P\x00Q")
    compile(py, "recreate_map.py", "exec")
    assert "\x00" not in py
    ns = exec_python(py)
    spec = ns["DATASETS"][0]
    assert spec["name"] == "nulname"
    labels = ns["point_labels"](ns["load_points"](spec), spec)
    # The NUL is dropped from the data and the styles alike, so they match.
    assert list(labels) == ["ab", "c"] == list(spec["styles"])
    r = codegen.generate_code(make_state(), [entry], "R", "P\x00Q")
    assert "\x00" not in r
    assert_parses_as_r(r)
    run_r_harness(tmp_path, r, """
spec <- DATASETS[[1]]
stopifnot(identical(spec$name, "nulname"))
stopifnot(all(load_all_points()$key %in% names(STYLE_COLORS)))
""")


def test_reserved_names_with_a_second_dot_are_guarded():
    used: set[str] = set()
    assert _export_filename("NUL.tar", ".csv", used,
                            "dataset") == "NUL_.tar.csv"
    assert _export_filename("con", ".csv", used,
                            "dataset") == "con_.csv"
    assert _export_filename("Console", ".csv", used,
                            "dataset") == "Console.csv"


def test_templates_are_plain_ascii():
    # Non-ASCII characters are written as escapes, so the scripts read the
    # same in any editor encoding.
    for name in ("recreate_map.py", "recreate_map.R"):
        text = literals._template(name)
        assert text.isascii(), name
