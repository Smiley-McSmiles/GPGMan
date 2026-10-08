# GPGMan v1.3.6 - OpenPGP & GnuPG Suite (GUI & CLI)

<p align="center">
  <img src="gpgman-icon.svg" alt="GPGMan Logo" width="128" height="128">
</p>

<p align="center">
  <b>A native OpenPGP and GnuPG key manager for Linux &amp; OpenBSD</b><br>
  <i>A modern GTK4 / Libadwaita desktop app and a full terminal CLI, with the same features in both</i>
</p>

<p align="center">
  <a href="https://github.com/Smiley-McSmiles/GPGMan/releases"><img src="https://img.shields.io/badge/version-1.3.6-blue.svg?style=flat-square" alt="Version 1.3.6"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="MIT License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg?style=flat-square" alt="Python 3.10+"></a>
  <a href="https://gtk.org"><img src="https://img.shields.io/badge/toolkit-GTK4%20%7C%20Libadwaita-red.svg?style=flat-square" alt="GTK4 Libadwaita"></a>
  <a href="https://gnupg.org"><img src="https://img.shields.io/badge/engine-GnuPG%202.x-orange.svg?style=flat-square" alt="GnuPG"></a>
  <a href="https://github.com/Smiley-McSmiles/GPGMan"><img src="https://img.shields.io/badge/platform-Linux%20%7C%20OpenBSD-lightgrey.svg?style=flat-square" alt="Linux & OpenBSD"></a>
</p>

---

## 🌟 Overview

**GPGMan** is a complete, production-grade OpenPGP and GnuPG manager designed for modern Linux and BSD environments. It comes as a desktop app and a command-line tool, and every feature is available in both:

1. **🎨 Graphical User Interface (GUI)**: Built with **GTK4** and **Libadwaita**, adhering strictly to the GNOME Human Interface Guidelines with dark/light theme support, responsive adaptive cards, in-process file selection dialogs, and real-time status banners.
2. **💻 Command Line Interface (CLI)**: A rich, interactive ANSI-styled terminal application (`gpgman-cli` or `gpgman --cli`) and fully scriptable command suite (`gpgman keys`, `gpgman encrypt-text`, `gpgman encrypt-file`, `gpgman verify`, `gpgman checksum`, etc.) with zero external terminal library dependencies.

Both interfaces sit on top of the robust, hardened **`GPGBackend`** engine that directly interfaces with your system's native GnuPG (`gpg`) keyring and agent without brittle wrappers.

---

## 👥 Developers & Attribution

GPGMan is developed and maintained by:
- **WOOSAH** (Lead Architect & Maintainer)
- **Gemini 3.8 Flash** (Lead Engineer)
- **Claude Sonnett 5.5** (Engineer)

Project GitHub: [https://github.com/Smiley-McSmiles/GPGMan](https://github.com/Smiley-McSmiles/GPGMan)

---

## ✨ Feature Comparison: 1:1 Parity Matrix

| Feature | GTK4 / Libadwaita GUI | Interactive Terminal CLI | Direct Scriptable CLI |
| :--- | :---: | :---: | :---: |
| **List Public & Secret Keys** | ✅ | ✅ | `gpgman keys [--secret]` |
| **Generate Keys (Ed25519, RSA, ECDSA)** | ✅ Guided Dialog | ✅ Interactive Wizard | `gpgman key-generate` |
| **Import Keys (File, Text, Web URL)** | ✅ File / Paste / URL | ✅ File / Paste / URL | `gpgman key-import <src>` |
| **Export Keys (Public & Secret)** | ✅ Preview / Save / Copy | ✅ Terminal / File | `gpgman key-export <id>` |
| **Delete Key Pairs** | ✅ Confirmation Modal | ✅ Safety Confirmation | `gpgman key-delete <id>` |
| **Change Passphrase** | ✅ System Pinentry | ✅ Pinentry Loopback | ✅ Menu Option |
| **Encrypt Message (Asymmetric & Symmetric)** | ✅ Multi-recipient + Ciphers | ✅ Multi-recipient + Ciphers | `gpgman encrypt-text` |
| **Decrypt Message & Verify Signer** | ✅ Inline Banner | ✅ Status Color Diagnostics | `gpgman decrypt-text` |
| **Encrypt File (Binary `.gpg` or Armor `.asc`)** | ✅ In-process Picker | ✅ Path Prompt + Autocomplete | `gpgman encrypt-file` |
| **Decrypt File & Verify Signatures** | ✅ Output Auto-Stripping | ✅ Output Auto-Stripping | `gpgman decrypt-file` |
| **Clearsign Text Documents** | ✅ 1-Click Clearsign | ✅ Interactive Input Block | `gpgman clearsign` |
| **Detached & Embedded File Signing** | ✅ `.asc` / `.sig` selector | ✅ Detached / Armor options | `gpgman sign-file` |
| **Signature Verification (Text & File)** | ✅ Good / Bad / Expired Status | ✅ Good / Bad / Expired Status | `gpgman verify <file>` |
| **Cryptographic Checksums (SHA-256 / SHA-512)** | ✅ Dynamic Checksum Calculator | ✅ SHA-256 / SHA-512 Hashes | `gpgman checksum <file>` |
| **GPG System Diagnostics & Keyring Stats** | ✅ System View | ✅ System Info Menu | `gpgman system` |
| **Custom GPG Binary & GNUPGHOME** | ✅ Preferences Dialog | ✅ Interactive Config | ✅ Runtime Engine |

---

## 🚀 Quick Start & Installation

### Option 1: Universal Install Script (Recommended)

The provided `install.sh` script automatically detects your distribution or operating system (Ubuntu, Fedora, Arch, Void Linux, or OpenBSD) and sets up binaries, icons, and desktop entries:

```bash
# Clone the repository
git clone https://github.com/Smiley-McSmiles/GPGMan.git
cd GPGMan

# Install globally to /usr/local/bin and system application menus
sudo sh install.sh

# On OpenBSD (with doas):
doas sh install.sh
```

To uninstall at any time:
```bash
sudo sh install.sh --uninstall
```

---

## 📦 Multi-Platform Packaging

GPGMan includes a comprehensive compilation script `package.sh` to produce native packages for all major Linux distributions and OpenBSD.

### Build All Formats:
```bash
./package.sh --all
```
This produces all artifacts inside `dist/`:
- **Ubuntu / Debian**: `dist/gpgman_1.3.6_all.deb`
- **Fedora / RHEL / openSUSE**: `dist/gpgman-1.3.6-1.noarch.rpm`
- **Arch Linux**: `dist/gpgman-1.3.6-1-any.pkg.tar.zst` and `dist/PKGBUILD`
- **OpenBSD**: `dist/gpgman-1.3.6-openbsd.pkg.tar.gz` and `dist/openbsd-port/Makefile`
- **Void Linux**: `dist/void-linux/template` and `dist/gpgman-1.3.6_1.void.tar.gz`
- **Standalone Portable Tarball**: `dist/gpgman-1.3.6-linux-portable.tar.gz`
- **AppImage**: `dist/GPGMan-1.3.6-x86_64.AppImage` (or self-contained AppDir bundle)
- **Flatpak**: `dist/gpgman-1.3.6.flatpak` (and `dist/flatpak/io.github.smiley_mcsmiles.GPGMan.yaml`)
- **Checksums**: `dist/SHA256SUMS`

### Build Individual Package Formats:
```bash
./package.sh --deb       # Build .deb for Ubuntu/Debian/Mint
./package.sh --rpm       # Build .rpm for Fedora/RHEL
./package.sh --arch      # Build .pkg.tar.zst and PKGBUILD for Arch
./package.sh --openbsd   # Build OpenBSD package and Port Makefile
./package.sh --void      # Build Void Linux template & archive
./package.sh --tar       # Build portable tarball
./package.sh --appimage  # Build AppImage bundle
./package.sh --flatpak   # Build the Flatpak bundle (needs flatpak-builder; GNOME_RUNTIME=51 to override the runtime)
```

---

## 💻 CLI Usage Guide

GPGMan automatically selects the best mode:
- Run `gpgman` from desktop launcher or terminal with display: opens **GTK4 GUI**.
- Run `gpgman` in a headless environment / SSH: automatically launches **Interactive CLI**.
- Run `gpgman-cli` or `gpgman --cli`: launches **Interactive CLI**.
- Run `gpgman <subcommand>`: executes scriptable direct commands.

### 1. Interactive Menu CLI
```bash
gpgman-cli
# or
gpgman --cli
```
Displays an intuitive ANSI menu:
```text
================================================================
  🔒 GPGMan CLI v1.3.6 - OpenPGP & GnuPG Suite
  GUI & CLI OpenPGP Key Manager
================================================================

  [ MAIN MENU ]
  1) 🔑 Key Management (List, Generate, Import, Export, Delete)
  2) 💬 Message Cryptography (Encrypt & Decrypt Text)
  3) 📁 File Cryptography (Encrypt & Decrypt Files)
  4) ✍️ Digital Signatures (Clearsign, Detached Sign, Verify)
  5) 🛡️ Checksums & Integrity (SHA-256 / SHA-512 Verification)
  6) ⚙️ System & GPG Configuration
  0) 🚪 Exit GPGMan
```

### 2. Scriptable CLI Subcommands

#### Managing Keys:
```bash
# List all public keys
gpgman keys

# List secret / private keys only
gpgman keys --secret

# Generate modern Ed25519 keypair
gpgman key-generate --name "Alice Smith" --email "alice@example.com" --algo ed25519 --expire 1y

# Import key from file, ASCII text, or direct web URL
gpgman key-import /path/to/key.asc
gpgman key-import https://keys.openpgp.org/vks/v1/by-fingerprint/ABCD1234...

# Export public or secret key
gpgman key-export 0x12345678 -o alice_pub.asc
gpgman key-export 0x12345678 --secret -o alice_backup_private.asc

# Delete a key
gpgman key-delete 0x12345678
```

#### Encrypting & Decrypting Text:
```bash
# Asymmetric encryption for multiple recipients
gpgman encrypt-text -r alice@example.com -r bob@example.com -m "Confidential report text"

# Symmetric passphrase encryption (gpg -c equivalent)
gpgman encrypt-text -p "MyStrongPassword" -c AES256 -m "Secret vault payload"

# Sign and encrypt simultaneously
gpgman encrypt-text -r alice@example.com -s 0xMY_KEY_ID -m "Signed & encrypted text"

# Decrypt text from stdin or parameter
echo "-----BEGIN PGP MESSAGE-----..." | gpgman decrypt-text
gpgman decrypt-text -p "MyStrongPassword" -m "-----BEGIN PGP MESSAGE-----..."
```

#### Encrypting & Decrypting Files:
```bash
# Encrypt file to ASCII armor (.asc)
gpgman encrypt-file document.pdf -r alice@example.com --armor

# Encrypt file with password using TWOFISH cipher
gpgman encrypt-file backup.tar.gz -p "Password123" -c TWOFISH

# Decrypt file (auto-strips .gpg / .asc extension)
gpgman decrypt-file backup.tar.gz.gpg -o backup.tar.gz
```

#### Clearsigning & Verifying:
```bash
# Clearsign a message
gpgman clearsign -s 0xMY_KEY_ID -m "I endorse release v1.3.6"

# Verify detached signature
gpgman verify release.tar.gz --sig release.tar.gz.asc

# Calculate and verify SHA-256 / SHA-512 checksums
gpgman checksum installer.iso --expected e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

#### System Information:
```bash
gpgman system
```

---

## 🎨 GTK4 GUI Features

- **Modern Adaptive UI**: Built using `Adw.ToolbarView`, `Adw.PreferencesGroup`, `Adw.ActionRow`, and `Adw.EntryRow`.
- **Portal-Safe File Selection**: Uses GTK4 native in-process file dialogs (`Gtk.FileChooserDialog`) with fallbacks, ensuring zero crashes on desktop environments lacking desktop portals or Nautilus (e.g. Cinnamon, XFCE, MATE, OpenBSD).
- **Interactive Checksum Validator**: Built right into the Sign & Verify tab for instant comparison against `SHA256SUMS`.
- **Live Shell Command Generator**: Every GUI action generates the exact equivalent `gpg` command line string for educational copy-pasting.

---

## 🧪 Testing

Run the automated test suite:
```bash
# Headless with Xvfb
GTK_A11Y=none xvfb-run -a python3 -m unittest discover -s tests

# Direct CLI tests
python3 -c "from gpgman.cli import GPGManCLI; cli = GPGManCLI(); print('CLI initialized successfully')"
```

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

Copyright (c) 2026 **WOOSAH & Gemini 3.8**  
Repository: [https://github.com/Smiley-McSmiles/GPGMan](https://github.com/Smiley-McSmiles/GPGMan)
