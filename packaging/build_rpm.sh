#!/usr/bin/env bash
# Build a Fedora RPM from the PyInstaller output (dist/PyMappr).
#
#   packaging/build_rpm.sh
#
# Produces dist/pymappr-<version>-1.<dist>.x86_64.rpm. Requires rpm-build.
# Run scripts/fetch_data.py and "pyinstaller packaging/pymappr.spec" first.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

[ -d dist/PyMappr ] || { echo "dist/PyMappr missing - run pyinstaller first"; exit 1; }

export PYMAPPR_VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pymappr/__init__.py)"
export PYMAPPR_DIST="$REPO_ROOT/dist/PyMappr"

topdir="$REPO_ROOT/dist/rpmbuild"
rm -rf "$topdir"
mkdir -p "$topdir"

rpmbuild -bb packaging/fedora/pymappr.spec \
    --define "_topdir $topdir" \
    --buildroot "$topdir/BUILDROOT"

cp "$topdir"/RPMS/*/pymappr-*.rpm dist/
rm -rf "$topdir"
echo "built $(ls dist/pymappr-*.rpm)"
