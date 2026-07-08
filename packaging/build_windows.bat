@echo off
rem Build the PyMappr Windows executable and installer locally.
rem Requirements: Python 3.11+, Inno Setup 6 (iscc on PATH).
setlocal
cd /d "%~dp0.."

echo === Installing Python dependencies ===
python -m pip install -r requirements.txt pyinstaller || goto :error

echo === Fetching map data ===
python scripts\fetch_data.py || goto :error

echo === Building executable with PyInstaller ===
python -m PyInstaller packaging\pymappr.spec --noconfirm || goto :error

echo === Building installer with Inno Setup ===
iscc packaging\installer.iss || goto :error

echo.
echo Done. Installer is in dist\installer\
exit /b 0

:error
echo Build failed.
exit /b 1
