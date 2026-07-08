#!/usr/bin/env bash
# Build a Fedora RPM from the PyInstaller output (dist/EzMaps).
#
#   packaging/build_rpm.sh
#
# Produces dist/ezmaps-<version>-1.<dist>.x86_64.rpm. Requires rpm-build.
# Run scripts/fetch_data.py and "pyinstaller packaging/ezmaps.spec" first.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

[ -d dist/EzMaps ] || { echo "dist/EzMaps missing - run pyinstaller first"; exit 1; }

export EZMAPS_VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' ezmaps/__init__.py)"
export EZMAPS_DIST="$REPO_ROOT/dist/EzMaps"

topdir="$REPO_ROOT/dist/rpmbuild"
rm -rf "$topdir"
mkdir -p "$topdir"

rpmbuild -bb packaging/fedora/ezmaps.spec \
    --define "_topdir $topdir" \
    --buildroot "$topdir/BUILDROOT"

cp "$topdir"/RPMS/*/ezmaps-*.rpm dist/
rm -rf "$topdir"
echo "built $(ls dist/ezmaps-*.rpm)"
