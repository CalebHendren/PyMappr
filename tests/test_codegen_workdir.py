"""Code export: exporting a ready-to-run working directory."""

import pytest

from pymappr.export import codegen

from codegen_helpers import (make_state, manual_entry, file_entry,
                             assert_parses_as_r)


# --------------------------------------------- export as working directory

def test_working_directory_python_layout():
    files = codegen.generate_working_directory(
        make_state(), [file_entry()], "Python", "My Project")
    assert set(files) >= {"recreate_map.py", "requirements.txt",
                          "README.md", ".gitignore"}
    # Point data lives in data/ as CSV, referenced by a relative path.
    data = [name for name in files if name.startswith("data/")]
    assert data == ["data/us_cities.csv"]
    assert "State,Longitude,Latitude" in files["data/us_cities.csv"]
    script = files["recreate_map.py"]
    compile(script, "recreate_map.py", "exec")
    assert "'path': 'data/us_cities.csv'" in script
    assert "'inline_data': None" in script
    assert "geopandas" in files["requirements.txt"]
    assert "pip install -r requirements.txt" in files["README.md"]


def test_working_directory_r_layout():
    files = codegen.generate_working_directory(
        make_state(), [file_entry()], "R", "My Project")
    # The RStudio project is named after the project, spaces and all.
    assert set(files) >= {"recreate_map.R", "install.R", "README.md",
                          ".gitignore", "My Project.Rproj"}
    assert "data/us_cities.csv" in files
    script = files["recreate_map.R"]
    assert_parses_as_r(script)
    assert '"path" = "data/us_cities.csv"' in script
    assert 'install.packages(c("sf", "ggplot2")' in files["install.R"]
    assert "Version: 1.0" in files["My Project.Rproj"]
    assert "Open `My Project.Rproj` in RStudio" in files["README.md"]


def test_working_directory_dedupes_data_filenames():
    # Two datasets exporting to the same slug get distinct CSV files.
    a = manual_entry("Sites")
    b = manual_entry("Sites")
    files = codegen.generate_working_directory(make_state(), [a, b],
                                               "Python", "P")
    data = sorted(name for name in files if name.startswith("data/"))
    assert data == ["data/Sites.csv", "data/Sites_2.csv"]
    script = files["recreate_map.py"]
    assert "'path': 'data/Sites.csv'" in script
    assert "'path': 'data/Sites_2.csv'" in script


def test_working_directory_manual_data_is_written_as_csv():
    files = codegen.generate_working_directory(
        make_state(), [manual_entry()], "Python", "P")
    data = [name for name in files if name.startswith("data/")]
    assert len(data) == 1
    assert "Legend,Label,Longitude,Latitude" in files[data[0]]


def test_working_directory_unknown_language_rejected():
    with pytest.raises(ValueError):
        codegen.generate_working_directory(make_state(), [], "Julia")
