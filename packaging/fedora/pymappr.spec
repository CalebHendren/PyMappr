# Packages the PyInstaller output (dist/PyMappr) as a Fedora RPM.
# Built by packaging/build_rpm.sh; the CI workflow runs pyinstaller first.
%global _enable_debug_package 0
%global debug_package %{nil}
%global __os_install_post %{nil}
%global __brp_check_rpaths %{nil}
%global __brp_mangle_shebangs %{nil}
%define _build_id_links none

Name:           pymappr
Version:        %{getenv:PYMAPPR_VERSION}
Release:        1%{?dist}
Summary:        Simple desktop mapping software
License:        MIT
URL:            https://github.com/CalebHendren/PyMappr
AutoReqProv:    no

%description
Simple desktop mapping software: plot CSV point data on offline Natural
Earth basemaps in multiple map projections, and export the result as a PNG.

%install
dist="%{getenv:PYMAPPR_DIST}"
mkdir -p %{buildroot}/opt/pymappr %{buildroot}%{_bindir} \
         %{buildroot}%{_datadir}/applications
cp -a "$dist/." %{buildroot}/opt/pymappr/
ln -s /opt/pymappr/PyMappr %{buildroot}%{_bindir}/pymappr
cat > %{buildroot}%{_datadir}/applications/pymappr.desktop <<EOF
[Desktop Entry]
Type=Application
Name=PyMappr
Comment=Simple desktop mapping software
Exec=/opt/pymappr/PyMappr
Terminal=false
Categories=Education;Geography;Science;
EOF

%files
/opt/pymappr
%{_bindir}/pymappr
%{_datadir}/applications/pymappr.desktop
