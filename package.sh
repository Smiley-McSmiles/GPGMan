#!/usr/bin/env bash
# ==============================================================================
# GPGMan Multi-Platform Packaging & Compilation Script
# Builds packages for Fedora (.rpm), Ubuntu/Debian (.deb), Arch Linux (.pkg.tar.zst),
# OpenBSD (.pkg.tar.gz), Void Linux (.xbps / .tar.gz), Portable Tarballs (.tar.gz),
# AppImage, and Flatpak.
#
# Developers: WOOSAH & GPGMan Core Team
# Repository: https://github.com/Smiley-McSmiles/GPGMan
# License: MIT
# ==============================================================================

set -euo pipefail

VERSION="1.3.4"
APP_NAME="gpgman"
PKG_NAME="gpgman"
SUMMARY="Dual-style GTK4/Libadwaita GUI and CLI OpenPGP & GnuPG Suite"
DESCRIPTION="GPGMan is a modern, native OpenPGP and GnuPG key management, encrypted messaging, file cryptography, digital signature, and verification suite providing 1:1 feature parity between a polished GTK4/Libadwaita GUI and a full-featured terminal CLI."
AUTHOR="WOOSAH & Gemini 3.8 <https://github.com/Smiley-McSmiles/GPGMan>"
HOMEPAGE="https://github.com/Smiley-McSmiles/GPGMan"
LICENSE="MIT"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"
BUILD_DIR="${SCRIPT_DIR}/build"

# ANSI Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}${BOLD}[*] $1${NC}"
}

log_success() {
    echo -e "${GREEN}${BOLD}[✓] $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}[!] $1${NC}"
}

log_error() {
    echo -e "${RED}${BOLD}[✗] $1${NC}"
}

init_dirs() {
    mkdir -p "${DIST_DIR}"
    mkdir -p "${BUILD_DIR}"
}

clean_build() {
    log_info "Cleaning previous build and distribution directories..."
    rm -rf "${BUILD_DIR}"
    rm -rf "${DIST_DIR:?}"/*
    mkdir -p "${BUILD_DIR}" "${DIST_DIR}"
}

# ------------------------------------------------------------------------------
# 1. DEB Package (Ubuntu / Debian / Linux Mint / Pop!_OS)
# ------------------------------------------------------------------------------
build_deb() {
    log_info "Building Debian / Ubuntu package (.deb)..."
    local DEB_ROOT="${BUILD_DIR}/deb/gpgman_${VERSION}_all"
    rm -rf "${DEB_ROOT}"
    mkdir -p "${DEB_ROOT}/DEBIAN"
    mkdir -p "${DEB_ROOT}/opt/gpgman"
    mkdir -p "${DEB_ROOT}/usr/bin"
    mkdir -p "${DEB_ROOT}/usr/share/applications"
    mkdir -p "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps"
    mkdir -p "${DEB_ROOT}/usr/share/doc/gpgman"
    mkdir -p "${DEB_ROOT}/usr/share/man/man1"

    # Copy application code
    cp -r "${SCRIPT_DIR}/gpgman" "${DEB_ROOT}/opt/gpgman/"
    cp "${SCRIPT_DIR}/main.py" "${DEB_ROOT}/opt/gpgman/"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${DEB_ROOT}/opt/gpgman/"
    [ -f "${SCRIPT_DIR}/gpgman-icon.png" ] && cp "${SCRIPT_DIR}/gpgman-icon.png" "${DEB_ROOT}/opt/gpgman/"
    cp "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" "${DEB_ROOT}/opt/gpgman/"
    [ -f "${SCRIPT_DIR}/gpgman.1" ] && cp "${SCRIPT_DIR}/gpgman.1" "${DEB_ROOT}/opt/gpgman/"
    [ -d "${SCRIPT_DIR}/icons" ] && cp -r "${SCRIPT_DIR}/icons" "${DEB_ROOT}/opt/gpgman/"
    [ -f "${SCRIPT_DIR}/LICENSE" ] && cp "${SCRIPT_DIR}/LICENSE" "${DEB_ROOT}/usr/share/doc/gpgman/"
    [ -f "${SCRIPT_DIR}/README.md" ] && cp "${SCRIPT_DIR}/README.md" "${DEB_ROOT}/usr/share/doc/gpgman/"

    chmod +x "${DEB_ROOT}/opt/gpgman/main.py"

    # Symlinks in /usr/bin
    ln -sf "/opt/gpgman/main.py" "${DEB_ROOT}/usr/bin/gpgman"
    ln -sf "/opt/gpgman/main.py" "${DEB_ROOT}/usr/bin/gpgman-cli"

    # Desktop entry & Icon
    sed -e "s|/opt/gpgman|/opt/gpgman|g" "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" > "${DEB_ROOT}/usr/share/applications/io.github.smiley_mcsmiles.GPGMan.desktop"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg"

    # Manual page
    if [ -f "${SCRIPT_DIR}/gpgman.1" ]; then
        gzip -c -9 "${SCRIPT_DIR}/gpgman.1" > "${DEB_ROOT}/usr/share/man/man1/gpgman.1.gz"
        ln -sf "gpgman.1.gz" "${DEB_ROOT}/usr/share/man/man1/gpgman-cli.1.gz"
    fi

    # Control File
    cat <<EOF > "${DEB_ROOT}/DEBIAN/control"
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gnupg
Recommends: pinentry-gnome3 | pinentry-curses
Maintainer: ${AUTHOR}
Homepage: ${HOMEPAGE}
Description: ${SUMMARY}
 ${DESCRIPTION}
EOF

    # Post-install & Post-removal hooks
    cat <<'EOF' > "${DEB_ROOT}/DEBIAN/postinst"
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
    chmod 755 "${DEB_ROOT}/DEBIAN/postinst"

    cat <<'EOF' > "${DEB_ROOT}/DEBIAN/postrm"
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
    chmod 755 "${DEB_ROOT}/DEBIAN/postrm"

    local DEB_FILE="${DIST_DIR}/gpgman_${VERSION}_all.deb"
    if command -v dpkg-deb >/dev/null 2>&1; then
        dpkg-deb --build --root-owner-group "${DEB_ROOT}" "${DEB_FILE}"
        log_success "Built Debian package: ${DEB_FILE}"
    else
        log_warn "dpkg-deb not found. Packaging archive as tarball..."
        tar -czf "${DEB_FILE}.tar.gz" -C "${DEB_ROOT}" .
        log_success "Created staged deb directory archive: ${DEB_FILE}.tar.gz"
    fi
}

# ------------------------------------------------------------------------------
# 2. RPM Package (Fedora / RHEL / openSUSE)
# ------------------------------------------------------------------------------
build_rpm() {
    log_info "Building Fedora / RHEL package (.rpm)..."
    local RPM_TOP="${BUILD_DIR}/rpm"
    mkdir -p "${RPM_TOP}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS,BUILDROOT}

    # Create source tarball
    local SRC_TAR="${RPM_TOP}/SOURCES/gpgman-${VERSION}.tar.gz"
    tar --transform "s|^.|gpgman-${VERSION}|" \
        --exclude="./build" --exclude="./dist" --exclude="./.git" --exclude="./__pycache__" \
        -czf "${SRC_TAR}" -C "${SCRIPT_DIR}" .

    # Write RPM SPEC file
    cat <<EOF > "${RPM_TOP}/SPECS/gpgman.spec"
Name:           ${PKG_NAME}
Version:        ${VERSION}
Release:        1%{?dist}
Summary:        ${SUMMARY}
License:        ${LICENSE}
URL:            ${HOMEPAGE}
Source0:        gpgman-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       gnupg2

%description
${DESCRIPTION}

%prep
%setup -q

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/opt/gpgman
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
mkdir -p %{buildroot}%{_datadir}/doc/gpgman
mkdir -p %{buildroot}%{_mandir}/man1

cp -r gpgman %{buildroot}/opt/gpgman/
cp main.py %{buildroot}/opt/gpgman/
cp gpgman-icon.svg %{buildroot}/opt/gpgman/
[ -f gpgman-icon.png ] && cp gpgman-icon.png %{buildroot}/opt/gpgman/
cp io.github.smiley_mcsmiles.GPGMan.desktop %{buildroot}/opt/gpgman/
[ -f gpgman.1 ] && cp gpgman.1 %{buildroot}/opt/gpgman/
[ -d icons ] && cp -r icons %{buildroot}/opt/gpgman/
[ -f LICENSE ] && cp LICENSE %{buildroot}%{_datadir}/doc/gpgman/
[ -f README.md ] && cp README.md %{buildroot}%{_datadir}/doc/gpgman/

chmod +x %{buildroot}/opt/gpgman/main.py

ln -sf /opt/gpgman/main.py %{buildroot}%{_bindir}/gpgman
ln -sf /opt/gpgman/main.py %{buildroot}%{_bindir}/gpgman-cli

cp io.github.smiley_mcsmiles.GPGMan.desktop %{buildroot}%{_datadir}/applications/io.github.smiley_mcsmiles.GPGMan.desktop
cp gpgman-icon.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg
if [ -f gpgman.1 ]; then
    gzip -c -9 gpgman.1 > %{buildroot}%{_mandir}/man1/gpgman.1.gz
    ln -sf gpgman.1.gz %{buildroot}%{_mandir}/man1/gpgman-cli.1.gz
fi

%files
/opt/gpgman
%{_bindir}/gpgman
%{_bindir}/gpgman-cli
%{_datadir}/applications/io.github.smiley_mcsmiles.GPGMan.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg
%{_mandir}/man1/gpgman*.1*
%doc %{_datadir}/doc/gpgman/*

%changelog
* Mon Sep 28 2026 ${AUTHOR} - 1.3.0-1
- Release 1.3.0 featuring dual GTK4/Libadwaita GUI and full CLI suite.
- Release 1.3.1 added ability to press ENTER to encrypt/decrpt with passphrase (GTK)
- Release 1.3.2 adds a desktop-agnostic passphrase prompt for secret key export and fixes the app icon/name in the dock.
- Release 1.3.3 adds drag-and-drop key import, .asc file association, and a donation menu in the About dialog.
- Release 1.3.4 uses the file chooser portal in the Flatpak (no broad filesystem access), renames the app ID to io.github.smiley_mcsmiles.GPGMan, and prepares Flathub submission. Passphrases are now passed to gpg over a private pipe instead of the command line, exported secret keys are saved owner-only, key downloads are size-capped, and cached passphrases are cleared from gpg-agent when the app quits (or from the System tab).
EOF

    if command -v rpmbuild >/dev/null 2>&1; then
        rpmbuild --define "_topdir ${RPM_TOP}" -bb "${RPM_TOP}/SPECS/gpgman.spec"
        find "${RPM_TOP}/RPMS" -type f -name "*.rpm" -exec cp {} "${DIST_DIR}/" \;
        log_success "Built RPM package: $(find "${DIST_DIR}" -name "*.rpm" | head -n 1)"
    else
        log_warn "rpmbuild not available. Saved RPM SPEC and source tarball to: ${RPM_TOP}/SPECS/gpgman.spec"
    fi
}

# ------------------------------------------------------------------------------
# 3. Arch Linux Package (.pkg.tar.zst) and PKGBUILD
# ------------------------------------------------------------------------------
build_arch() {
    log_info "Building Arch Linux package (.pkg.tar.zst) & PKGBUILD..."
    local ARCH_DIR="${BUILD_DIR}/arch"
    mkdir -p "${ARCH_DIR}/pkg"

    cat <<EOF > "${ARCH_DIR}/PKGBUILD"
# Maintainer: ${AUTHOR}
pkgname=gpgman
pkgver=${VERSION}
pkgrel=1
pkgdesc="${SUMMARY}"
arch=('any')
url="${HOMEPAGE}"
license=('${LICENSE}')
depends=('python' 'python-gobject' 'gtk4' 'libadwaita' 'gnupg')
optdepends=('pinentry: for graphical or ncurses password prompts')
source=("\${pkgname}-\${pkgver}.tar.gz::${HOMEPAGE}/archive/refs/tags/v\${pkgver}.tar.gz")
sha256sums=('SKIP')

package() {
    install -d "\${pkgdir}/opt/gpgman"
    install -d "\${pkgdir}/usr/bin"
    install -d "\${pkgdir}/usr/share/applications"
    install -d "\${pkgdir}/usr/share/icons/hicolor/scalable/apps"
    install -d "\${pkgdir}/usr/share/licenses/\${pkgname}"
    install -d "\${pkgdir}/usr/share/man/man1"

    cp -r "\${srcdir}"/gpgman*/* "\${pkgdir}/opt/gpgman/" 2>/dev/null || true
    chmod +x "\${pkgdir}/opt/gpgman/main.py"

    ln -s /opt/gpgman/main.py "\${pkgdir}/usr/bin/gpgman"
    ln -s /opt/gpgman/main.py "\${pkgdir}/usr/bin/gpgman-cli"

    install -m644 "\${pkgdir}/opt/gpgman/io.github.smiley_mcsmiles.GPGMan.desktop" "\${pkgdir}/usr/share/applications/io.github.smiley_mcsmiles.GPGMan.desktop"
    install -m644 "\${pkgdir}/opt/gpgman/gpgman-icon.svg" "\${pkgdir}/usr/share/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg"
    [ -f "\${pkgdir}/opt/gpgman/gpgman.1" ] && install -m644 "\${pkgdir}/opt/gpgman/gpgman.1" "\${pkgdir}/usr/share/man/man1/gpgman.1" && ln -sf gpgman.1 "\${pkgdir}/usr/share/man/man1/gpgman-cli.1"
    [ -f "\${pkgdir}/opt/gpgman/LICENSE" ] && install -m644 "\${pkgdir}/opt/gpgman/LICENSE" "\${pkgdir}/usr/share/licenses/\${pkgname}/LICENSE"
}
EOF

    # Copy PKGBUILD to dist
    cp "${ARCH_DIR}/PKGBUILD" "${DIST_DIR}/PKGBUILD"

    # Assemble binary structure directly into .pkg format
    local PKG_ROOT="${ARCH_DIR}/root"
    mkdir -p "${PKG_ROOT}/opt/gpgman"
    mkdir -p "${PKG_ROOT}/usr/bin"
    mkdir -p "${PKG_ROOT}/usr/share/applications"
    mkdir -p "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps"
    mkdir -p "${PKG_ROOT}/usr/share/licenses/gpgman"
    mkdir -p "${PKG_ROOT}/usr/share/man/man1"

    cp -r "${SCRIPT_DIR}/gpgman" "${PKG_ROOT}/opt/gpgman/"
    cp "${SCRIPT_DIR}/main.py" "${PKG_ROOT}/opt/gpgman/"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${PKG_ROOT}/opt/gpgman/"
    [ -f "${SCRIPT_DIR}/gpgman-icon.png" ] && cp "${SCRIPT_DIR}/gpgman-icon.png" "${PKG_ROOT}/opt/gpgman/"
    cp "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" "${PKG_ROOT}/opt/gpgman/"
    [ -f "${SCRIPT_DIR}/gpgman.1" ] && cp "${SCRIPT_DIR}/gpgman.1" "${PKG_ROOT}/opt/gpgman/"
    [ -d "${SCRIPT_DIR}/icons" ] && cp -r "${SCRIPT_DIR}/icons" "${PKG_ROOT}/opt/gpgman/"
    [ -f "${SCRIPT_DIR}/LICENSE" ] && cp "${SCRIPT_DIR}/LICENSE" "${PKG_ROOT}/usr/share/licenses/gpgman/LICENSE"

    chmod +x "${PKG_ROOT}/opt/gpgman/main.py"
    ln -sf /opt/gpgman/main.py "${PKG_ROOT}/usr/bin/gpgman"
    ln -sf /opt/gpgman/main.py "${PKG_ROOT}/usr/bin/gpgman-cli"
    cp "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" "${PKG_ROOT}/usr/share/applications/io.github.smiley_mcsmiles.GPGMan.desktop"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg"
    if [ -f "${SCRIPT_DIR}/gpgman.1" ]; then
        cp "${SCRIPT_DIR}/gpgman.1" "${PKG_ROOT}/usr/share/man/man1/gpgman.1"
        ln -sf gpgman.1 "${PKG_ROOT}/usr/share/man/man1/gpgman-cli.1"
    fi

    # .PKGINFO for pacman
    cat <<EOF > "${PKG_ROOT}/.PKGINFO"
pkgname = ${PKG_NAME}
pkgver = ${VERSION}-1
pkgdesc = ${SUMMARY}
url = ${HOMEPAGE}
builddate = $(date +%s)
packager = ${AUTHOR}
size = $(du -sb "${PKG_ROOT}" | awk '{print $1}')
arch = any
license = ${LICENSE}
depend = python
depend = python-gobject
depend = gtk4
depend = libadwaita
depend = gnupg
optdepend = pinentry: for password entry
EOF

    local ARCH_PKG="${DIST_DIR}/gpgman-${VERSION}-1-any.pkg.tar.zst"
    if command -v zstd >/dev/null 2>&1; then
        (cd "${PKG_ROOT}" && tar -c .PKGINFO opt usr | zstd -T0 -19 -o "${ARCH_PKG}")
        log_success "Built Arch Linux package: ${ARCH_PKG}"
    else
        local ARCH_PKG_GZ="${DIST_DIR}/gpgman-${VERSION}-1-any.pkg.tar.gz"
        (cd "${PKG_ROOT}" && tar -czf "${ARCH_PKG_GZ}" .PKGINFO opt usr)
        log_success "Built Arch Linux package: ${ARCH_PKG_GZ}"
    fi
}

# ------------------------------------------------------------------------------
# 4. OpenBSD Package (.pkg.tar.gz) and Port Recipe
# ------------------------------------------------------------------------------
build_openbsd() {
    log_info "Building OpenBSD package (.pkg.tar.gz) & ports recipe..."
    local OBSD_DIR="${BUILD_DIR}/openbsd"
    local OBSD_ROOT="${OBSD_DIR}/root"
    mkdir -p "${OBSD_ROOT}/usr/local/share/gpgman"
    mkdir -p "${OBSD_ROOT}/usr/local/bin"
    mkdir -p "${OBSD_ROOT}/usr/local/share/applications"
    mkdir -p "${OBSD_ROOT}/usr/local/share/icons/hicolor/scalable/apps"
    mkdir -p "${OBSD_ROOT}/usr/local/share/doc/gpgman"
    mkdir -p "${OBSD_ROOT}/usr/local/man/man1"

    # Copy files
    cp -r "${SCRIPT_DIR}/gpgman" "${OBSD_ROOT}/usr/local/share/gpgman/"
    cp "${SCRIPT_DIR}/main.py" "${OBSD_ROOT}/usr/local/share/gpgman/"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${OBSD_ROOT}/usr/local/share/gpgman/"
    [ -f "${SCRIPT_DIR}/gpgman-icon.png" ] && cp "${SCRIPT_DIR}/gpgman-icon.png" "${OBSD_ROOT}/usr/local/share/gpgman/"
    cp "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" "${OBSD_ROOT}/usr/local/share/gpgman/"
    [ -f "${SCRIPT_DIR}/gpgman.1" ] && cp "${SCRIPT_DIR}/gpgman.1" "${OBSD_ROOT}/usr/local/share/gpgman/"
    [ -d "${SCRIPT_DIR}/icons" ] && cp -r "${SCRIPT_DIR}/icons" "${OBSD_ROOT}/usr/local/share/gpgman/"
    [ -f "${SCRIPT_DIR}/LICENSE" ] && cp "${SCRIPT_DIR}/LICENSE" "${OBSD_ROOT}/usr/local/share/doc/gpgman/"
    [ -f "${SCRIPT_DIR}/README.md" ] && cp "${SCRIPT_DIR}/README.md" "${OBSD_ROOT}/usr/local/share/doc/gpgman/"

    chmod +x "${OBSD_ROOT}/usr/local/share/gpgman/main.py"
    ln -sf /usr/local/share/gpgman/main.py "${OBSD_ROOT}/usr/local/bin/gpgman"
    ln -sf /usr/local/share/gpgman/main.py "${OBSD_ROOT}/usr/local/bin/gpgman-cli"
    sed -e "s|/opt/gpgman|/usr/local/share/gpgman|g" "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" > "${OBSD_ROOT}/usr/local/share/applications/io.github.smiley_mcsmiles.GPGMan.desktop"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${OBSD_ROOT}/usr/local/share/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg"
    if [ -f "${SCRIPT_DIR}/gpgman.1" ]; then
        cp "${SCRIPT_DIR}/gpgman.1" "${OBSD_ROOT}/usr/local/man/man1/gpgman.1"
        ln -sf gpgman.1 "${OBSD_ROOT}/usr/local/man/man1/gpgman-cli.1"
    fi

    # Packing list for OpenBSD (+CONTENTS)
    cat <<EOF > "${OBSD_ROOT}/+CONTENTS"
@name ${PKG_NAME}-${VERSION}
@comment ${SUMMARY}
@depend security/gnupg:gnupg-*:security/gnupg
@depend x11/gtk+4:gtk+4-*:x11/gtk+4
@depend x11/libadwaita:libadwaita-*:x11/libadwaita
@depend devel/py-gobject3:py3-gobject3-*:devel/py-gobject3
@cwd /usr/local
EOF
    (cd "${OBSD_ROOT}/usr/local" && find . -type f -o -type l | sed 's|^\./||' >> "${OBSD_ROOT}/+CONTENTS")

    # OpenBSD Port Makefile
    mkdir -p "${DIST_DIR}/openbsd-port"
    cat <<EOF > "${DIST_DIR}/openbsd-port/Makefile"
COMMENT =       ${SUMMARY}
V =             ${VERSION}
DISTNAME =      gpgman-\${V}
CATEGORIES =    security x11

HOMEPAGE =      ${HOMEPAGE}
MAINTAINER =    ${AUTHOR}
PERMIT_PACKAGE = Yes

MODULES =       lang/python
RUN_DEPENDS =   security/gnupg \\
                x11/gtk+4 \\
                x11/libadwaita \\
                devel/py-gobject3

NO_BUILD =      Yes
PKG_ARCH =      *

do-install:
	\${INSTALL_DATA_DIR} \${PREFIX}/share/gpgman
	cp -Rp \${WRKSRC}/gpgman \${PREFIX}/share/gpgman/
	\${INSTALL_SCRIPT} \${WRKSRC}/main.py \${PREFIX}/share/gpgman/
	ln -sf \${PREFIX}/share/gpgman/main.py \${PREFIX}/bin/gpgman
	ln -sf \${PREFIX}/share/gpgman/main.py \${PREFIX}/bin/gpgman-cli
	\${INSTALL_DATA_DIR} \${PREFIX}/share/applications
	\${INSTALL_DATA} \${WRKSRC}/io.github.smiley_mcsmiles.GPGMan.desktop \${PREFIX}/share/applications/
	\${INSTALL_DATA_DIR} \${PREFIX}/share/icons/hicolor/scalable/apps
	\${INSTALL_DATA} \${WRKSRC}/gpgman-icon.svg \${PREFIX}/share/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg

.include <bsd.port.mk>
EOF

    local OBSD_PKG="${DIST_DIR}/gpgman-${VERSION}-openbsd.pkg.tar.gz"
    tar -czf "${OBSD_PKG}" -C "${OBSD_ROOT}" .
    log_success "Built OpenBSD package archive: ${OBSD_PKG}"
    log_success "Generated OpenBSD Port: ${DIST_DIR}/openbsd-port/Makefile"
}

# ------------------------------------------------------------------------------
# 5. Void Linux Packaging (xbps template & package archive)
# ------------------------------------------------------------------------------
build_void() {
    log_info "Building Void Linux xbps template & distribution..."
    local VOID_DIR="${DIST_DIR}/void-linux"
    mkdir -p "${VOID_DIR}"

    cat <<EOF > "${VOID_DIR}/template"
# Template file for 'gpgman'
pkgname=gpgman
version=${VERSION}
revision=1
archs=noarch
build_style=meta
depends="python3 python3-gobject gtk4 libadwaita gnupg2"
short_desc="${SUMMARY}"
maintainer="${AUTHOR}"
license="${LICENSE}"
homepage="${HOMEPAGE}"
distfiles="${HOMEPAGE}/archive/refs/tags/v\${version}.tar.gz"
checksum=SKIP

do_install() {
    vmkdir opt/gpgman
    vmkdir usr/bin
    vmkdir usr/share/applications
    vmkdir usr/share/icons/hicolor/scalable/apps

    vcopy gpgman opt/gpgman/
    vinstall main.py 755 opt/gpgman/
    vinstall gpgman-icon.svg 644 opt/gpgman/
    vinstall io.github.smiley_mcsmiles.GPGMan.desktop 644 opt/gpgman/
    [ -d icons ] && vcopy icons opt/gpgman/

    ln -sf /opt/gpgman/main.py \${DESTDIR}/usr/bin/gpgman
    ln -sf /opt/gpgman/main.py \${DESTDIR}/usr/bin/gpgman-cli

    vinstall io.github.smiley_mcsmiles.GPGMan.desktop 644 usr/share/applications/
    vinstall gpgman-icon.svg 644 usr/share/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg
    [ -f gpgman.1 ] && vman gpgman.1
    vlicense LICENSE
}
EOF

    local VOID_PKG="${DIST_DIR}/gpgman-${VERSION}_1.void.tar.gz"
    tar -czf "${VOID_PKG}" -C "${SCRIPT_DIR}" --exclude="./build" --exclude="./dist" --exclude="./.git" .
    log_success "Generated Void Linux template: ${VOID_DIR}/template"
    log_success "Created Void source package: ${VOID_PKG}"
}

# ------------------------------------------------------------------------------
# 6. Standalone Portable Tarball (.tar.gz)
# ------------------------------------------------------------------------------
build_tar() {
    log_info "Building Portable Standalone Tarball (.tar.gz)..."
    local TAR_ROOT="${BUILD_DIR}/tar/gpgman-${VERSION}"
    rm -rf "${TAR_ROOT}"
    mkdir -p "${TAR_ROOT}"

    cp -r "${SCRIPT_DIR}/gpgman" "${TAR_ROOT}/"
    cp "${SCRIPT_DIR}/main.py" "${TAR_ROOT}/"
    cp "${SCRIPT_DIR}/install.sh" "${TAR_ROOT}/"
    cp "${SCRIPT_DIR}/package.sh" "${TAR_ROOT}/"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${TAR_ROOT}/"
    [ -f "${SCRIPT_DIR}/gpgman-icon.png" ] && cp "${SCRIPT_DIR}/gpgman-icon.png" "${TAR_ROOT}/"
    cp "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" "${TAR_ROOT}/"
    [ -f "${SCRIPT_DIR}/gpgman.1" ] && cp "${SCRIPT_DIR}/gpgman.1" "${TAR_ROOT}/"
    [ -d "${SCRIPT_DIR}/icons" ] && cp -r "${SCRIPT_DIR}/icons" "${TAR_ROOT}/"
    [ -f "${SCRIPT_DIR}/LICENSE" ] && cp "${SCRIPT_DIR}/LICENSE" "${TAR_ROOT}/"
    [ -f "${SCRIPT_DIR}/README.md" ] && cp "${SCRIPT_DIR}/README.md" "${TAR_ROOT}/"

    chmod +x "${TAR_ROOT}/main.py" "${TAR_ROOT}/install.sh" "${TAR_ROOT}/package.sh"

    local TAR_FILE="${DIST_DIR}/gpgman-${VERSION}-linux-portable.tar.gz"
    tar -czf "${TAR_FILE}" -C "${BUILD_DIR}/tar" "gpgman-${VERSION}"
    log_success "Built Portable Tarball: ${TAR_FILE}"
}

# ------------------------------------------------------------------------------
# 7. AppImage Compilation
# ------------------------------------------------------------------------------
build_appimage() {
    log_info "Building AppImage package..."
    local APPDIR="${BUILD_DIR}/appimage/GPGMan.AppDir"
    rm -rf "${APPDIR}"
    mkdir -p "${APPDIR}/usr/bin"
    mkdir -p "${APPDIR}/usr/share/gpgman"
    mkdir -p "${APPDIR}/usr/share/icons/hicolor/scalable/apps"
    mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"
    mkdir -p "${APPDIR}/usr/share/pixmaps"
    mkdir -p "${APPDIR}/usr/share/applications"
    mkdir -p "${APPDIR}/usr/share/man/man1"
    mkdir -p "${APPDIR}/opt/gpgman"

    cp -r "${SCRIPT_DIR}/gpgman" "${APPDIR}/usr/share/gpgman/"
    cp "${SCRIPT_DIR}/main.py" "${APPDIR}/usr/share/gpgman/"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${APPDIR}/usr/share/gpgman/"
    [ -f "${SCRIPT_DIR}/gpgman-icon.png" ] && cp "${SCRIPT_DIR}/gpgman-icon.png" "${APPDIR}/usr/share/gpgman/"
    cp "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" "${APPDIR}/usr/share/gpgman/"
    [ -f "${SCRIPT_DIR}/gpgman.1" ] && cp "${SCRIPT_DIR}/gpgman.1" "${APPDIR}/usr/share/man/man1/gpgman.1" && ln -sf gpgman.1 "${APPDIR}/usr/share/man/man1/gpgman-cli.1"
    [ -d "${SCRIPT_DIR}/icons" ] && cp -r "${SCRIPT_DIR}/icons" "${APPDIR}/usr/share/gpgman/"

    chmod +x "${APPDIR}/usr/share/gpgman/main.py"
    ln -sf ../share/gpgman/main.py "${APPDIR}/usr/bin/gpgman"
    ln -sf ../share/gpgman/main.py "${APPDIR}/usr/bin/gpgman-cli"

    # Mirror to /opt/gpgman in AppDir for backwards compatibility with any absolute paths
    ln -sf ../../usr/share/gpgman/main.py "${APPDIR}/opt/gpgman/main.py"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${APPDIR}/opt/gpgman/gpgman-icon.svg"
    [ -f "${SCRIPT_DIR}/gpgman-icon.png" ] && cp "${SCRIPT_DIR}/gpgman-icon.png" "${APPDIR}/opt/gpgman/gpgman-icon.png"

    # Generate 256x256 PNG icon if needed
    if [ ! -f "${SCRIPT_DIR}/gpgman-icon.png" ]; then
        if command -v rsvg-convert >/dev/null 2>&1; then
            rsvg-convert -w 256 -h 256 "${SCRIPT_DIR}/gpgman-icon.svg" -o "${SCRIPT_DIR}/gpgman-icon.png"
        fi
    fi

    # Root desktop & icon files required by AppImage spec:
    # appimagetool expects:
    # 1. Desktop file with 'Icon=io.github.smiley_mcsmiles.GPGMan' at root
    # 2. Icon file '<Icon>.png' or '<Icon>.svg' at root matching desktop file
    # 3. .DirIcon pointing to the icon
    # 4. Standard AppStream metadata in usr/share/metainfo/
    sed -e "s|^Icon=.*|Icon=io.github.smiley_mcsmiles.GPGMan|" \
        -e "s|^Exec=.*|Exec=gpgman %F|" \
        -e "s|^Categories=.*|Categories=System;Security;GTK;|" \
        "${SCRIPT_DIR}/io.github.smiley_mcsmiles.GPGMan.desktop" > "${APPDIR}/io.github.smiley_mcsmiles.GPGMan.desktop"
    cp "${APPDIR}/io.github.smiley_mcsmiles.GPGMan.desktop" "${APPDIR}/usr/share/applications/io.github.smiley_mcsmiles.GPGMan.desktop"

    # Copy icons to root and icon themes
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${APPDIR}/io.github.smiley_mcsmiles.GPGMan.svg"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${APPDIR}/gpgman.svg"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg"
    cp "${SCRIPT_DIR}/gpgman-icon.svg" "${APPDIR}/usr/share/pixmaps/io.github.smiley_mcsmiles.GPGMan.svg"

    if [ -f "${SCRIPT_DIR}/gpgman-icon.png" ]; then
        cp "${SCRIPT_DIR}/gpgman-icon.png" "${APPDIR}/io.github.smiley_mcsmiles.GPGMan.png"
        cp "${SCRIPT_DIR}/gpgman-icon.png" "${APPDIR}/gpgman.png"
        cp "${SCRIPT_DIR}/gpgman-icon.png" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/io.github.smiley_mcsmiles.GPGMan.png"
        cp "${SCRIPT_DIR}/gpgman-icon.png" "${APPDIR}/usr/share/pixmaps/io.github.smiley_mcsmiles.GPGMan.png"
        ln -sf io.github.smiley_mcsmiles.GPGMan.png "${APPDIR}/.DirIcon"
    else
        ln -sf io.github.smiley_mcsmiles.GPGMan.svg "${APPDIR}/.DirIcon"
    fi

    # Avoid appstreamcli validation aborts across varying host distro versions
    rm -rf "${APPDIR}/usr/share/metainfo"

    # Create AppRun bootstrap script
    cat <<'EOF' > "${APPDIR}/AppRun"
#!/bin/sh
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export PYTHONPATH="${HERE}/usr/share/gpgman:${PYTHONPATH}"
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

if [ "$1" = "--cli" ] || [ "$1" = "-c" ] || [ -z "$DISPLAY" -a -z "$WAYLAND_DISPLAY" ]; then
    exec python3 "${HERE}/usr/share/gpgman/main.py" "$@"
else
    exec python3 "${HERE}/usr/share/gpgman/main.py" "$@"
fi
EOF
    chmod +x "${APPDIR}/AppRun"

    local APPIMAGE_OUT="${DIST_DIR}/GPGMan-${VERSION}-x86_64.AppImage"
    if command -v appimagetool >/dev/null 2>&1; then
        ARCH=x86_64 appimagetool --appimage-extract-and-run "${APPDIR}" "${APPIMAGE_OUT}" 2>/dev/null || \
        ARCH=x86_64 appimagetool "${APPDIR}" "${APPIMAGE_OUT}"
        log_success "Built AppImage: ${APPIMAGE_OUT}"
    else
        log_warn "appimagetool not in PATH. Packing AppDir archive as ${APPIMAGE_OUT}.tar.gz"
        tar -czf "${APPIMAGE_OUT}.tar.gz" -C "${BUILD_DIR}/appimage" GPGMan.AppDir
        log_success "Created AppDir bundle: ${APPIMAGE_OUT}.tar.gz"
    fi
}

# ------------------------------------------------------------------------------
# 8. Flatpak Manifest & Build
# ------------------------------------------------------------------------------
# GNOME runtime used for the Flatpak. Override with: GNOME_RUNTIME=51 ./package.sh --flatpak
GNOME_RUNTIME="${GNOME_RUNTIME:-50}"

build_flatpak() {
    log_info "Building Flatpak (GNOME runtime ${GNOME_RUNTIME})..."
    local FLATPAK_DIR="${DIST_DIR}/flatpak"
    mkdir -p "${FLATPAK_DIR}"

    cat <<EOF > "${FLATPAK_DIR}/io.github.smiley_mcsmiles.GPGMan.yaml"
app-id: io.github.smiley_mcsmiles.GPGMan
runtime: org.gnome.Platform
runtime-version: '${GNOME_RUNTIME}'
sdk: org.gnome.Sdk
command: gpgman
finish-args:
  - --share=ipc
  - --socket=fallback-x11
  - --socket=wayland
  - --device=dri
  - --filesystem=~/.gnupg
  - --share=network

modules:
  - name: gpgman
    buildsystem: simple
    build-commands:
      - mkdir -p /app/share/gpgman /app/bin /app/share/applications /app/share/metainfo /app/share/icons/hicolor/scalable/apps
      - cp -r gpgman /app/share/gpgman/
      - install -m755 main.py /app/share/gpgman/
      - ln -sf /app/share/gpgman/main.py /app/bin/gpgman
      - ln -sf /app/share/gpgman/main.py /app/bin/gpgman-cli
      - install -m644 io.github.smiley_mcsmiles.GPGMan.desktop /app/share/applications/io.github.smiley_mcsmiles.GPGMan.desktop
      - install -m644 io.github.smiley_mcsmiles.GPGMan.metainfo.xml /app/share/metainfo/io.github.smiley_mcsmiles.GPGMan.metainfo.xml
      - install -m644 gpgman-icon.svg /app/share/icons/hicolor/scalable/apps/io.github.smiley_mcsmiles.GPGMan.svg
    sources:
      - type: dir
        path: ../../
        skip:
          - .git
          - dist
          - .flatpak-builder
EOF

    log_success "Generated Flatpak manifest: ${FLATPAK_DIR}/io.github.smiley_mcsmiles.GPGMan.yaml"

    if ! command -v flatpak-builder >/dev/null 2>&1; then
        log_warn "flatpak-builder not found; install it to build the Flatpak. Manifest generated only."
        return 0
    fi

    # --user builds need a user-level flathub remote (a system-wide one is not visible to them).
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo \
        || log_warn "Could not add the user flathub remote."

    (
        cd "${FLATPAK_DIR}" &&
        flatpak-builder --user --force-clean --install-deps-from=flathub \
            --repo=repo build-dir io.github.smiley_mcsmiles.GPGMan.yaml &&
        flatpak build-bundle repo "${DIST_DIR}/gpgman-${VERSION}.flatpak" io.github.smiley_mcsmiles.GPGMan
    ) && log_success "Built Flatpak bundle: ${DIST_DIR}/gpgman-${VERSION}.flatpak" \
      || log_error "Flatpak build failed."
}

# ------------------------------------------------------------------------------
# Checksums for all artifacts
# ------------------------------------------------------------------------------
generate_checksums() {
    log_info "Generating SHA-256 checksums for all release artifacts..."
    if [ -d "${DIST_DIR}" ]; then
        (
            cd "${DIST_DIR}"
            find . -maxdepth 1 -type f ! -name "SHA256SUMS" -exec sha256sum {} + > SHA256SUMS
        )
        log_success "Checksum file updated: ${DIST_DIR}/SHA256SUMS"
    fi
}

# ------------------------------------------------------------------------------
# Help & Entrypoint
# ------------------------------------------------------------------------------
show_help() {
    echo -e "${BOLD}GPGMan Multi-Platform Packaging Tool${NC}"
    echo "Usage: ./package.sh [options]"
    echo ""
    echo "Options:"
    echo "  --all         Build all package formats (DEB, RPM, Arch, OpenBSD, Void, Tar, AppImage, Flatpak)"
    echo "  --deb         Build Debian / Ubuntu package (.deb)"
    echo "  --rpm         Build Fedora / RHEL package (.rpm)"
    echo "  --arch        Build Arch Linux package (.pkg.tar.zst) and PKGBUILD"
    echo "  --openbsd     Build OpenBSD package (.pkg.tar.gz) and Port Makefile"
    echo "  --void        Build Void Linux template and source archive"
    echo "  --tar         Build portable standalone tarball (.tar.gz)"
    echo "  --appimage    Build standalone AppImage bundle"
    echo "  --flatpak     Build Flatpak bundle (GNOME_RUNTIME=${GNOME_RUNTIME})"
    echo "  --clean       Clean build directories"
    echo "  --help, -h    Display this message"
    echo ""
    echo "Output packages will be stored in: ${DIST_DIR}/"
}

main() {
    init_dirs

    if [ "$#" -eq 0 ]; then
        show_help
        exit 0
    fi

    for arg in "$@"; do
        case "$arg" in
            --clean)
                clean_build
                ;;
            --deb)
                build_deb
                ;;
            --rpm)
                build_rpm
                ;;
            --arch)
                build_arch
                ;;
            --openbsd)
                build_openbsd
                ;;
            --void)
                build_void
                ;;
            --tar)
                build_tar
                ;;
            --appimage)
                build_appimage
                ;;
            --flatpak)
                build_flatpak
                ;;
            --all)
                clean_build
                build_deb
                build_rpm
                build_arch
                build_openbsd
                build_void
                build_tar
                build_appimage
                build_flatpak
                generate_checksums
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $arg"
                show_help
                exit 1
                ;;
        esac
    done

    echo ""
    log_success "Packaging complete! All artifacts are in: ${DIST_DIR}/"
    ls -lh "${DIST_DIR}"
}

main "$@"
