#!/usr/bin/env sh
# ==============================================================================
# GPGMan Installer Script
# Installs GPGMan and integrates with Linux and OpenBSD desktop environments
# ==============================================================================

set -e

# ANSI Color codes for clean output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Detect Operating System
UNAME_S="$(uname -s)"

# Adjust paths based on OS
if [ "$UNAME_S" = "OpenBSD" ]; then
    INSTALL_DIR="/usr/local/share/gpgman"
    DESKTOP_DIR="/usr/local/share/applications"
    BIN_DIR="/usr/local/bin"
    ICON_DIR="/usr/local/share/icons/hicolor/scalable/apps"
    PIXMAPS_DIR="/usr/local/share/pixmaps"
    MAN_DIR="/usr/local/man/man1"
    LOCAL_MAN_DIR=""
else
    # Linux (Void, Arch, Ubuntu, Fedora, etc.)
    INSTALL_DIR="/opt/gpgman"
    DESKTOP_DIR="/usr/share/applications"
    BIN_DIR="/usr/local/bin"
    ICON_DIR="/usr/share/icons/hicolor/scalable/apps"
    PIXMAPS_DIR="/usr/share/pixmaps"
    MAN_DIR="/usr/share/man/man1"
    LOCAL_MAN_DIR="/usr/local/share/man/man1"
fi

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure root privileges (supports both doas and sudo)
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo -e "${YELLOW}[!] Root privileges required.${NC}"
        if command -v doas >/dev/null 2>&1; then
            echo -e "${YELLOW}Re-running with doas...${NC}"
            exec doas sh "$0" "$@"
        elif command -v sudo >/dev/null 2>&1; then
            echo -e "${YELLOW}Re-running with sudo...${NC}"
            exec sudo sh "$0" "$@"
        else
            echo -e "${RED}[X] Error: Neither 'doas' nor 'sudo' was found. Please run this script as root.${NC}"
            exit 1
        fi
    fi
}

uninstall_gpgman() {
    echo -e "${BLUE}${BOLD}==> Uninstalling GPGMan...${NC}"

    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        echo -e "  ${GREEN}✓${NC} Removed $INSTALL_DIR"
    fi

    if [ -f "$BIN_DIR/gpgman" ] || [ -L "$BIN_DIR/gpgman" ]; then
        rm -f "$BIN_DIR/gpgman"
        echo -e "  ${GREEN}✓${NC} Removed $BIN_DIR/gpgman"
    fi

    if [ -f "$BIN_DIR/gpgman-cli" ] || [ -L "$BIN_DIR/gpgman-cli" ]; then
        rm -f "$BIN_DIR/gpgman-cli"
        echo -e "  ${GREEN}✓${NC} Removed $BIN_DIR/gpgman-cli"
    fi

    if [ -f "$DESKTOP_DIR/gpgman.desktop" ]; then
        rm -f "$DESKTOP_DIR/gpgman.desktop"
        echo -e "  ${GREEN}✓${NC} Removed $DESKTOP_DIR/gpgman.desktop"
    fi

    if [ -f "$ICON_DIR/gpgman-icon.svg" ]; then
        rm -f "$ICON_DIR/gpgman-icon.svg"
        echo -e "  ${GREEN}✓${NC} Removed $ICON_DIR/gpgman-icon.svg"
    fi

    if [ -f "$PIXMAPS_DIR/gpgman-icon.svg" ]; then
        rm -f "$PIXMAPS_DIR/gpgman-icon.svg"
        echo -e "  ${GREEN}✓${NC} Removed $PIXMAPS_DIR/gpgman-icon.svg"
    fi

    # Remove manpages
    rm -f "$MAN_DIR/gpgman.1" "$MAN_DIR/gpgman-cli.1" "$MAN_DIR/gpgman.1.gz" "$MAN_DIR/gpgman-cli.1.gz" 2>/dev/null || true
    if [ -n "$LOCAL_MAN_DIR" ]; then
        rm -f "$LOCAL_MAN_DIR/gpgman.1" "$LOCAL_MAN_DIR/gpgman-cli.1" "$LOCAL_MAN_DIR/gpgman.1.gz" "$LOCAL_MAN_DIR/gpgman-cli.1.gz" 2>/dev/null || true
    fi
    echo -e "  ${GREEN}✓${NC} Removed manual pages"

    # Update caches
    if command -v mandb >/dev/null 2>&1; then
        mandb -q 2>/dev/null || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q "$DESKTOP_DIR" 2>/dev/null || true
    fi

    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f "${ICON_DIR%/*/*/*}" 2>/dev/null || true
    fi

    echo -e "${GREEN}${BOLD}✓ GPGMan successfully uninstalled.${NC}"
    exit 0
}

# Handle arguments
if [ "$1" = "--uninstall" ] || [ "$1" = "-u" ] || [ "$1" = "uninstall" ]; then
    check_root "$@"
    uninstall_gpgman
fi

check_root "$@"

echo -e "${BLUE}${BOLD}========================================${NC}"
echo -e "${BLUE}${BOLD}        GPGMan v1.3.1 Installer ($UNAME_S)      ${NC}"
echo -e "${BLUE}${BOLD}========================================${NC}"

# Check for required system packages
echo -e "${BLUE}==> Checking system dependencies...${NC}"
MISSING_DEPS=""

if ! command -v python3 >/dev/null 2>&1; then
    MISSING_DEPS="${MISSING_DEPS} python3"
fi

if ! command -v gpg >/dev/null 2>&1 && ! command -v gpg2 >/dev/null 2>&1; then
    MISSING_DEPS="${MISSING_DEPS} gpg"
fi

if ! python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); from gi.repository import Gtk, Adw" >/dev/null 2>&1; then
    MISSING_DEPS="${MISSING_DEPS} python3-gi/libadwaita-1/gtk4"
fi

if [ -n "$MISSING_DEPS" ]; then
    echo -e "${YELLOW}[!] Warning: Missing dependencies detected:${BOLD}$MISSING_DEPS${NC}"
    echo -e "${YELLOW}You can install them using your system package manager:${NC}"
    echo -e "  Void Linux:   ${BOLD}sudo xbps-install -S python3 python3-gobject gtk4 libadwaita gnupg2${NC}"
    echo -e "  OpenBSD:      ${BOLD}doas pkg_add python py3-gobject3 gtk+4 libadwaita gnupg${NC}"
    echo -e "  Arch Linux:   ${BOLD}sudo pacman -S python python-gobject gtk4 libadwaita gnupg${NC}"
    echo -e "  Ubuntu/Debian:${BOLD}sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gnupg${NC}"
    echo -e "  Fedora:       ${BOLD}sudo dnf install python3 python3-gobject gtk4 libadwaita gnupg2${NC}"
    echo ""
fi

# 1. Create target directories
echo -e "${BLUE}==> Creating destination directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$DESKTOP_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$ICON_DIR"
mkdir -p "$PIXMAPS_DIR"
mkdir -p "$MAN_DIR"
if [ -n "$LOCAL_MAN_DIR" ]; then
    mkdir -p "$LOCAL_MAN_DIR"
fi

# 2. Copy application files
echo -e "${BLUE}==> Installing application files to $INSTALL_DIR...${NC}"
rm -rf "${INSTALL_DIR:?}"/*

# Copy core package and launcher
cp -r "$SCRIPT_DIR/gpgman" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/main.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/gpgman-icon.svg" "$INSTALL_DIR/"
if [ -f "$SCRIPT_DIR/gpgman-icon.png" ]; then
    cp "$SCRIPT_DIR/gpgman-icon.png" "$INSTALL_DIR/"
fi
cp "$SCRIPT_DIR/gpgman.desktop" "$INSTALL_DIR/"
if [ -d "$SCRIPT_DIR/icons" ]; then
    cp -r "$SCRIPT_DIR/icons" "$INSTALL_DIR/"
fi

if [ -f "$SCRIPT_DIR/README.md" ]; then
    cp "$SCRIPT_DIR/README.md" "$INSTALL_DIR/"
fi

# Set proper execution and access permissions
chmod -R a+rX "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/main.py"

echo -e "  ${GREEN}✓${NC} Files copied to $INSTALL_DIR"

# 3. Create global binary symlinks
echo -e "${BLUE}==> Creating global executable symlinks...${NC}"
ln -sf "$INSTALL_DIR/main.py" "$BIN_DIR/gpgman"
ln -sf "$INSTALL_DIR/main.py" "$BIN_DIR/gpgman-cli"
chmod +x "$BIN_DIR/gpgman" "$BIN_DIR/gpgman-cli"
echo -e "  ${GREEN}✓${NC} Created symlinks $BIN_DIR/gpgman and $BIN_DIR/gpgman-cli -> $INSTALL_DIR/main.py"

# 4. Install desktop icon
echo -e "${BLUE}==> Installing application icons...${NC}"
cp "$SCRIPT_DIR/gpgman-icon.svg" "$ICON_DIR/gpgman-icon.svg"
cp "$SCRIPT_DIR/gpgman-icon.svg" "$PIXMAPS_DIR/gpgman-icon.svg"
chmod a+r "$ICON_DIR/gpgman-icon.svg" "$PIXMAPS_DIR/gpgman-icon.svg"
echo -e "  ${GREEN}✓${NC} Installed icons to system icon directories"

# 5. Move/install .desktop file
echo -e "${BLUE}==> Installing desktop entry to $DESKTOP_DIR...${NC}"
sed -e "s|/opt/gpgman|$INSTALL_DIR|g" "$SCRIPT_DIR/gpgman.desktop" > "$DESKTOP_DIR/gpgman.desktop"
chmod 644 "$DESKTOP_DIR/gpgman.desktop"
echo -e "  ${GREEN}✓${NC} Installed $DESKTOP_DIR/gpgman.desktop"

# 6. Install manual page
if [ -f "$SCRIPT_DIR/gpgman.1" ]; then
    echo -e "${BLUE}==> Installing manual pages (man gpgman)...${NC}"
    cp "$SCRIPT_DIR/gpgman.1" "$MAN_DIR/gpgman.1"
    chmod 644 "$MAN_DIR/gpgman.1"
    ln -sf "gpgman.1" "$MAN_DIR/gpgman-cli.1" 2>/dev/null || true

    if [ -n "$LOCAL_MAN_DIR" ] && [ "$LOCAL_MAN_DIR" != "$MAN_DIR" ]; then
        cp "$SCRIPT_DIR/gpgman.1" "$LOCAL_MAN_DIR/gpgman.1"
        chmod 644 "$LOCAL_MAN_DIR/gpgman.1"
        ln -sf "gpgman.1" "$LOCAL_MAN_DIR/gpgman-cli.1" 2>/dev/null || true
    fi

    if command -v mandb >/dev/null 2>&1; then
        mandb -q 2>/dev/null || true
    fi
    echo -e "  ${GREEN}✓${NC} Installed manual pages to $MAN_DIR/gpgman.1"
fi

# 7. Update system desktop and icon databases
echo -e "${BLUE}==> Updating system databases...${NC}"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q "$DESKTOP_DIR" 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Updated desktop database"
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "${ICON_DIR%/*/*/*}" 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Updated GTK icon cache"
fi

echo ""
echo -e "${GREEN}${BOLD}====================================================${NC}"
echo -e "${GREEN}${BOLD}        GPGMan successfully installed!              ${NC}"
echo -e "${GREEN}${BOLD}====================================================${NC}"
echo -e "You can launch GPGMan by:"
echo -e "  1. Searching for ${BOLD}GPGMan${NC} in your desktop launcher"
echo -e "  2. Running ${BOLD}gpgman${NC} in your terminal"
echo -e "  3. Running ${BOLD}man gpgman${NC} for full CLI & GUI documentation"
echo -e "  4. Running ${BOLD}$INSTALL_DIR/main.py${NC}"
echo ""
echo -e "To uninstall anytime, run:"
if command -v doas >/dev/null 2>&1; then
    echo -e "  ${BOLD}doas sh install.sh --uninstall${NC}"
else
    echo -e "  ${BOLD}sudo sh install.sh --uninstall${NC}"
fi
echo ""
