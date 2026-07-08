# PyInstaller spec for PyMappr (Windows, macOS, and Linux).
#
#   pyinstaller packaging/pymappr.spec
#
# Expects data/ to be populated first (python scripts/fetch_data.py).
# Produces dist/PyMappr as a onedir bundle - fast startup and friendly to
# the platform packaging scripts in this directory. On macOS it also
# produces dist/PyMappr.app.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent
DATA_DIR = REPO_ROOT / "data"
ICON = DATA_DIR / "icon" / "pymappr.ico"

_init = (REPO_ROOT / "pymappr" / "__init__.py").read_text(encoding="utf-8")
VERSION = next(line.split('"')[1] for line in _init.splitlines()
               if line.startswith("__version__"))

datas = [
    (str(DATA_DIR / "shapes"), "data/shapes"),
    (str(DATA_DIR / "basemap"), "data/basemap"),
    (str(DATA_DIR / "icon"), "data/icon"),
]
binaries = []

# pyinstaller-hooks-contrib has no hook for pyogrio, so collect it by hand:
# geopandas imports it lazily and its GDAL/PROJ resource directories
# (pyogrio/gdal_data, pyogrio/proj_data) are plain data files.
datas += collect_data_files("pyogrio")

# The Windows wheels are delvewheel-repaired: GDAL and its dependent DLLs
# live in a "pyogrio.libs" directory next to the package, which PyInstaller
# does not pick up on its own. Without it the frozen app dies on startup
# with "GDAL DLL could not be found. It must be on the system PATH."
try:
    from PyInstaller.utils.hooks import collect_delvewheel_libs_directory

    datas, binaries = collect_delvewheel_libs_directory(
        "pyogrio", datas=datas, binaries=binaries
    )
except ImportError:
    # Older PyInstaller: bundle the .libs directory manually. pyogrio's
    # delvewheel patch calls os.add_dll_directory on it at import time.
    import pyogrio

    _libs = Path(pyogrio.__file__).resolve().parent.parent / "pyogrio.libs"
    if _libs.is_dir():
        binaries += [
            (str(f), "pyogrio.libs") for f in _libs.iterdir() if f.is_file()
        ]

a = Analysis(
    [str(REPO_ROOT / "pymappr" / "__main__.py")],
    pathex=[str(REPO_ROOT)],
    datas=datas,
    binaries=binaries,
    hiddenimports=[
        "pymappr.app",
        "matplotlib.backends.backend_tkagg",
        *collect_submodules("pyogrio", filter=lambda name: ".tests" not in name),
    ],
    excludes=[
        # Heavy optional deps pulled in by pandas/matplotlib that PyMappr
        # never uses - keeps the bundle smaller.
        "IPython", "jedi", "notebook", "pytest", "sphinx",
        "matplotlib.backends.backend_qt5agg", "PyQt5", "PyQt6", "PySide2",
        "PySide6",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="PyMappr",
    icon=str(ICON) if sys.platform == "win32" else None,
    console=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="PyMappr",
    upx=False,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="PyMappr.app",
        bundle_identifier="com.calebhendren.pymappr",
        version=VERSION,
    )
