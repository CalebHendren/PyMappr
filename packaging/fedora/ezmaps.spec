# Packages the PyInstaller output (dist/EzMaps) as a Fedora RPM.
# Built by packaging/build_rpm.sh; the CI workflow runs pyinstaller first.
%global _enable_debug_package 0
%global debug_package %{nil}
%global __os_install_post %{nil}
%global __brp_check_rpaths %{nil}
%global __brp_mangle_shebangs %{nil}
%define _build_id_links none

Name:           ezmaps
Version:        %{getenv:EZMAPS_VERSION}
Release:        1%{?dist}
Summary:        Simple desktop mapping software
License:        MIT
URL:            https://github.com/CalebHendren/EzMaps
AutoReqProv:    no

%description
Simple desktop mapping software: plot CSV point data on offline Natural
Earth basemaps in multiple map projections, and export the result as a PNG.

%install
dist="%{getenv:EZMAPS_DIST}"
mkdir -p %{buildroot}/opt/ezmaps %{buildroot}%{_bindir} \
         %{buildroot}%{_datadir}/applications
cp -a "$dist/." %{buildroot}/opt/ezmaps/
ln -s /opt/ezmaps/EzMaps %{buildroot}%{_bindir}/ezmaps
cat > %{buildroot}%{_datadir}/applications/ezmaps.desktop <<EOF
[Desktop Entry]
Type=Application
Name=EzMaps
Comment=Simple desktop mapping software
Exec=/opt/ezmaps/EzMaps
Terminal=false
Categories=Education;Geography;Science;
EOF

%files
/opt/ezmaps
%{_bindir}/ezmaps
%{_datadir}/applications/ezmaps.desktop
