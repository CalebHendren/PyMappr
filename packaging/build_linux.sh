#!/usr/bin/env bash
# Package the PyInstaller output (dist/EzMaps) for Linux.
#
#   packaging/build_linux.sh <suffix> [--deb]
#
# <suffix> tags the tarball (e.g. "ubuntu" or "arch"):
#   dist/EzMaps-<version>-linux-<suffix>-x86_64.tar.gz
# --deb additionally builds dist/ezmaps_<version>_amd64.deb (Debian/Ubuntu).
#
# Run scripts/fetch_data.py and "pyinstaller packaging/ezmaps.spec" first.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SUFFIX="${1:?usage: build_linux.sh <suffix> [--deb]}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' ezmaps/__init__.py)"
ARCH="$(uname -m)"

[ -d dist/EzMaps ] || { echo "dist/EzMaps missing - run pyinstaller first"; exit 1; }

tarball="dist/EzMaps-${VERSION}-linux-${SUFFIX}-${ARCH}.tar.gz"
tar czf "$tarball" -C dist EzMaps
echo "built $tarball"

if [ "${2:-}" = "--deb" ]; then
    root="dist/debroot"
    rm -rf "$root"
    mkdir -p "$root/opt" "$root/usr/bin" "$root/usr/share/applications" \
             "$root/DEBIAN"
    cp -r dist/EzMaps "$root/opt/ezmaps"
    ln -s /opt/ezmaps/EzMaps "$root/usr/bin/ezmaps"

    cat > "$root/usr/share/applications/ezmaps.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=EzMaps
Comment=Simple desktop mapping software
Exec=/opt/ezmaps/EzMaps
Terminal=false
Categories=Education;Geography;Science;
EOF

    cat > "$root/DEBIAN/control" <<EOF
Package: ezmaps
Version: ${VERSION}
Section: science
Priority: optional
Architecture: amd64
Maintainer: Caleb Hendren <calebahendren@gmail.com>
Description: Simple desktop mapping software
 Plot CSV point data on offline Natural Earth basemaps, build heatmaps,
 and export the result as a PNG.
EOF

    deb="dist/ezmaps_${VERSION}_amd64.deb"
    dpkg-deb --build --root-owner-group "$root" "$deb"
    rm -rf "$root"
    echo "built $deb"
fi
