# PyInstaller spec for EzMaps (build on Windows).
#
#   pyinstaller packaging/ezmaps.spec
#
# Expects data/ to be populated first (python scripts/fetch_data.py).
# Produces dist/EzMaps/EzMaps.exe as a onedir bundle - fast startup and
# friendly to the Inno Setup installer in this directory.

from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent
DATA_DIR = REPO_ROOT / "data"
ICON = DATA_DIR / "icon" / "ezmaps.ico"

datas = [
    (str(DATA_DIR / "shapes"), "data/shapes"),
    (str(DATA_DIR / "basemap"), "data/basemap"),
    (str(DATA_DIR / "icon"), "data/icon"),
]

a = Analysis(
    [str(REPO_ROOT / "ezmaps" / "__main__.py")],
    pathex=[str(REPO_ROOT)],
    datas=datas,
    hiddenimports=[
        "ezmaps.app",
        "matplotlib.backends.backend_tkagg",
        "scipy.ndimage",
    ],
    excludes=[
        # Heavy optional deps pulled in by pandas/matplotlib that EzMaps
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
    name="EzMaps",
    icon=str(ICON),
    console=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="EzMaps",
    upx=False,
)
