"""
CLI Interface for GPGMan - Terminal and Non-Interactive CLI.
Provides 1:1 feature parity with the GTK4 / Libadwaita GUI.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional

from gpgman import __version__
from gpgman.gpg_backend import GPGBackend, GPGKey, VerifyResult


class Colors:
    """ANSI color codes for terminal styling."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    MAGENTA = "\033[0;35m"
    CYAN = "\033[0;36m"
    WHITE = "\033[1;37m"
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_RED = "\033[41m"


def cprint(text: str, color: str = Colors.RESET, bold: bool = False, end: str = "\n"):
    style = Colors.BOLD if bold else ""
    sys.stdout.write(f"{style}{color}{text}{Colors.RESET}{end}")
    sys.stdout.flush()


def banner():
    cprint("=" * 64, Colors.CYAN, bold=True)
    cprint(f"  🔒 GPGMan CLI v{__version__} - OpenPGP & GnuPG Suite", Colors.WHITE, bold=True)
    cprint("  GUI & CLI OpenPGP Key Manager", Colors.CYAN)
    cprint("=" * 64, Colors.CYAN, bold=True)


def prompt_multiline(prompt_text: str) -> str:
    cprint(prompt_text, Colors.YELLOW, bold=True)
    cprint("(Paste/type text. Enter empty line followed by EOF [Ctrl+D] or '---END---' on new line to finish):", Colors.DIM)
    lines = []
    try:
        while True:
            line = input()
            if line.strip() == "---END---":
                break
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines)


class GPGManCLI:
    def __init__(self, backend: Optional[GPGBackend] = None):
        self.backend = backend or GPGBackend()

    # =========================================================================
    # Interactive CLI Menu Loop
    # =========================================================================
    def run_interactive(self):
        banner()
        while True:
            print()
            cprint("  [ MAIN MENU ]", Colors.BLUE, bold=True)
            print("  1) 🔑 Key Management (List, Generate, Import, Export, Delete)")
            print("  2) 💬 Message Cryptography (Encrypt & Decrypt Text)")
            print("  3) 📁 File Cryptography (Encrypt & Decrypt Files)")
            print("  4) ✍️ Digital Signatures (Clearsign, Detached Sign, Verify)")
            print("  5) 🛡️ Checksums & Integrity (SHA-256 / SHA-512 Verification)")
            print("  6) ⚙️ System & GPG Configuration")
            print("  0) 🚪 Exit GPGMan")
            print()

            try:
                choice = input(f"{Colors.BOLD}Select an option [0-6]: {Colors.RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                cprint("Goodbye!", Colors.CYAN)
                break

            if choice == "1":
                self._menu_keys()
            elif choice == "2":
                self._menu_messages()
            elif choice == "3":
                self._menu_files()
            elif choice == "4":
                self._menu_signatures()
            elif choice == "5":
                self._menu_checksums()
            elif choice == "6":
                self._menu_system()
            elif choice in ("0", "q", "quit", "exit"):
                cprint("Exiting GPGMan. Goodbye!", Colors.CYAN)
                break
            else:
                cprint("Invalid option. Please choose between 0 and 6.", Colors.RED)

    # =========================================================================
    # 1. Key Management Submenu
    # =========================================================================
    def _menu_keys(self):
        while True:
            print()
            cprint("  --- 🔑 Key Management ---", Colors.BLUE, bold=True)
            print("  1) List All Public Keys")
            print("  2) List Secret / Private Keys")
            print("  3) View Detailed Key Information")
            print("  4) Generate New Key Pair")
            print("  5) Import Key (File, Text Armor, or URL)")
            print("  6) Export Public Key")
            print("  7) Export Secret Key (Backup)")
            print("  8) Delete Key")
            print("  9) Change Key Passphrase")
            print("  0) Back to Main Menu")
            print()

            choice = input(f"{Colors.BOLD}Keys menu [0-9]: {Colors.RESET}").strip()
            if choice == "1":
                self.cmd_list_keys(secret_only=False)
            elif choice == "2":
                self.cmd_list_keys(secret_only=True)
            elif choice == "3":
                self._interactive_view_key()
            elif choice == "4":
                self._interactive_generate_key()
            elif choice == "5":
                self._interactive_import_key()
            elif choice == "6":
                self._interactive_export_key(secret=False)
            elif choice == "7":
                self._interactive_export_key(secret=True)
            elif choice == "8":
                self._interactive_delete_key()
            elif choice == "9":
                self._interactive_change_passphrase()
            elif choice in ("0", "b", "back"):
                break

    def cmd_list_keys(self, secret_only: bool = False):
        keys = self.backend.list_keys(secret_only=secret_only)
        title = "SECRET / PRIVATE KEYS" if secret_only else "PUBLIC KEYS"
        cprint(f"\n=== {title} ({len(keys)} found) ===", Colors.CYAN, bold=True)
        if not keys:
            cprint("  No keys found in keyring.", Colors.YELLOW)
            return

        for idx, k in enumerate(keys, 1):
            sec_badge = f"{Colors.YELLOW}[SEC]{Colors.RESET} " if k.is_secret else ""
            cprint(f"{idx:2d}. {sec_badge}{Colors.BOLD}{k.display_name}{Colors.RESET}")
            cprint(f"    Key ID : {Colors.GREEN}{k.key_id}{Colors.RESET}  ({k.algo} {k.length}b)")
            cprint(f"    Fingerprint : {Colors.DIM}{k.formatted_fingerprint}{Colors.RESET}")
            cprint(f"    Created: {k.created or 'Unknown'} | Expires: {k.expires or 'Never'}")
            if k.subkeys:
                sub_str = ", ".join(f"{s.algo} {s.key_id}" for s in k.subkeys)
                cprint(f"    Subkeys: {Colors.DIM}{sub_str}{Colors.RESET}")
            print()

    def _interactive_view_key(self):
        keys = self.backend.list_keys()
        if not keys:
            cprint("No keys available.", Colors.YELLOW)
            return
        key = self._prompt_select_key(keys, "Select key to view details:")
        if not key:
            return
        cprint(f"\n--- KEY DETAILS: {key.display_name} ---", Colors.CYAN, bold=True)
        print(f"  Name        : {key.name}")
        print(f"  Email       : {key.email}")
        print(f"  Comment     : {key.comment}")
        print(f"  Key ID      : {key.key_id}")
        print(f"  Algorithm   : {key.algo} ({key.length} bits)")
        print(f"  Fingerprint : {key.formatted_fingerprint}")
        print(f"  Created     : {key.created}")
        print(f"  Expires     : {key.expires or 'Never'}")
        print(f"  Has Secret  : {'Yes' if key.is_secret else 'No'}")
        print(f"  Capabilities: {', '.join(key.capabilities)}")
        if key.uids:
            print(f"  User IDs    : {len(key.uids)}")
            for u in key.uids:
                print(f"    - {u}")
        if key.subkeys:
            print(f"  Subkeys     :")
            for s in key.subkeys:
                print(f"    - {s.algo} {s.key_id} ({s.length}b) created {s.created or 'unknown'}")

    def _interactive_generate_key(self):
        cprint("\n--- Generate New GPG Key Pair ---", Colors.CYAN, bold=True)
        name = input("Full Name: ").strip()
        if not name:
            cprint("Name is required.", Colors.RED)
            return
        email = input("Email Address: ").strip()
        if not email or "@" not in email:
            cprint("Valid email address is required.", Colors.RED)
            return
        comment = input("Comment (optional): ").strip()

        print("\nAlgorithms:")
        print("  1) Ed25519 / Curve25519 (Modern, Fast, Recommended)")
        print("  2) RSA 4096-bit (High Security)")
        print("  3) RSA 3072-bit (Standard)")
        print("  4) RSA 2048-bit (Compatible)")
        print("  5) ECDSA (NIST P-256)")
        algo_choice = input("Select algorithm [1-5, default 1]: ").strip() or "1"
        algo_map = {
            "1": "ed25519",
            "2": "rsa4096",
            "3": "rsa3072",
            "4": "rsa2048",
            "5": "nistp256",
        }
        algo = algo_map.get(algo_choice, "ed25519")

        print("\nExpiration:")
        print("  1) 1 Year (Recommended)")
        print("  2) 2 Years")
        print("  3) 6 Months")
        print("  4) Never expire")
        print("  5) Custom days (e.g. 90d)")
        exp_choice = input("Select expiration [1-5, default 1]: ").strip() or "1"
        if exp_choice == "1":
            expire = "1y"
        elif exp_choice == "2":
            expire = "2y"
        elif exp_choice == "3":
            expire = "6m"
        elif exp_choice == "4":
            expire = "0"
        elif exp_choice == "5":
            expire = input("Enter custom expiration (e.g. 90, 60d, 2y): ").strip() or "1y"
        else:
            expire = "1y"

        passphrase = getpass.getpass("Passphrase for private key (leave empty for none): ")
        if passphrase:
            confirm = getpass.getpass("Confirm passphrase: ")
            if passphrase != confirm:
                cprint("Passphrases do not match. Aborting.", Colors.RED)
                return

        cprint("\nGenerating key pair... This may take a few moments.", Colors.YELLOW)
        ok, msg = self.backend.generate_key(
            name=name,
            email=email,
            comment=comment,
            algo=algo,
            expire=expire,
            passphrase=passphrase or None,
        )
        if ok:
            cprint(f"✓ Key generated successfully! {msg}", Colors.GREEN, bold=True)
        else:
            cprint(f"✗ Failed to generate key: {msg}", Colors.RED)

    def _interactive_import_key(self):
        cprint("\n--- Import GPG Key ---", Colors.CYAN, bold=True)
        print("  1) Import from File (.asc, .gpg, .key)")
        print("  2) Paste ASCII Armored Text")
        print("  3) Download from URL (keys.openpgp.org or HTTP/HTTPS)")
        print("  0) Cancel")
        ch = input("Choice [0-3]: ").strip()

        if ch == "1":
            path = input("Enter file path: ").strip().strip("'\"")
            if not os.path.isfile(path):
                cprint(f"File not found: {path}", Colors.RED)
                return
            ok, count, msg = self.backend.import_key_file(path)
            if ok:
                cprint(f"✓ Successfully imported {count} key(s) from {path}!", Colors.GREEN, bold=True)
            else:
                cprint(f"✗ Import failed: {msg}", Colors.RED)
        elif ch == "2":
            text = prompt_multiline("Paste ASCII Armor Key Block:")
            if not text.strip():
                cprint("Empty input. Cancelled.", Colors.YELLOW)
                return
            ok, count, msg = self.backend.import_key_text(text)
            if ok:
                cprint(f"✓ Successfully imported {count} key(s)!", Colors.GREEN, bold=True)
            else:
                cprint(f"✗ Import failed: {msg}", Colors.RED)
        elif ch == "3":
            url = input("Enter Key URL: ").strip()
            if not url.startswith(("http://", "https://")):
                cprint("Invalid URL format (must begin with http:// or https://)", Colors.RED)
                return
            cprint(f"Fetching key from {url}...", Colors.YELLOW)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": f"GPGMan-CLI/{__version__}"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw_data = resp.read().decode("utf-8", errors="replace")
                ok, count, msg = self.backend.import_key_text(raw_data)
                if ok:
                    cprint(f"✓ Successfully imported {count} key(s) from {url}!", Colors.GREEN, bold=True)
                else:
                    cprint(f"✗ Import failed: {msg}", Colors.RED)
            except Exception as e:
                cprint(f"✗ Network or download error: {e}", Colors.RED)

    def _interactive_export_key(self, secret: bool = False):
        keys = self.backend.list_keys(secret_only=secret)
        if not keys:
            cprint("No matching keys to export.", Colors.YELLOW)
            return

        title = "SECRET KEY" if secret else "PUBLIC KEY"
        if secret:
            cprint("⚠️  WARNING: You are about to export a PRIVATE / SECRET KEY.", Colors.RED, bold=True)
            cprint("Anyone with this key can decrypt your files and sign in your name!", Colors.YELLOW)
            confirm = input("Are you absolutely sure? [yes/N]: ").strip().lower()
            if confirm != "yes":
                cprint("Export cancelled.", Colors.YELLOW)
                return

        key = self._prompt_select_key(keys, f"Select {title} to export:")
        if not key:
            return

        if secret:
            ok, data = self.backend.export_secret_key(key.key_id, armor=True)
        else:
            ok, data = self.backend.export_public_key(key.key_id, armor=True)

        if not ok:
            cprint(f"Export failed: {data}", Colors.RED)
            return

        print("\nDestination:")
        print("  1) Save to File")
        print("  2) Print to Terminal")
        dest = input("Choice [1-2, default 1]: ").strip() or "1"
        if dest == "2":
            print("\n" + data)
        else:
            default_fn = f"{key.key_id}_{'secret' if secret else 'public'}.asc"
            out_path = input(f"Output filename [default: {default_fn}]: ").strip() or default_fn
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(data)
                cprint(f"✓ Key saved to {out_path}", Colors.GREEN, bold=True)
            except Exception as e:
                cprint(f"Failed to write file: {e}", Colors.RED)

    def _interactive_delete_key(self):
        keys = self.backend.list_keys()
        if not keys:
            cprint("No keys available.", Colors.YELLOW)
            return
        key = self._prompt_select_key(keys, "Select key to DELETE:")
        if not key:
            return
        cprint(f"⚠️  Are you sure you want to permanently delete key '{key.display_name}' ({key.key_id})?", Colors.RED, bold=True)
        confirm = input("Type 'DELETE' to confirm: ").strip()
        if confirm == "DELETE":
            ok, msg = self.backend.delete_key(key.key_id)
            if ok:
                cprint(f"✓ Key {key.key_id} deleted successfully.", Colors.GREEN)
            else:
                cprint(f"✗ Failed to delete key: {msg}", Colors.RED)
        else:
            cprint("Deletion aborted.", Colors.YELLOW)

    def _interactive_change_passphrase(self):
        keys = self.backend.list_keys(secret_only=True)
        if not keys:
            cprint("No secret keys found in keyring.", Colors.YELLOW)
            return
        key = self._prompt_select_key(keys, "Select secret key to change passphrase:")
        if not key:
            return
        cprint(f"Launching pinentry/GPG passphrase change for {key.display_name}...", Colors.YELLOW)
        ok, msg = self.backend.change_passphrase(key.key_id)
        if ok:
            cprint(f"✓ Passphrase updated successfully!", Colors.GREEN)
        else:
            cprint(f"✗ Failed to change passphrase: {msg}", Colors.RED)

    # =========================================================================
    # 2. Message Cryptography Submenu
    # =========================================================================
    def _menu_messages(self):
        while True:
            print()
            cprint("  --- 💬 Message Cryptography ---", Colors.BLUE, bold=True)
            print("  1) Encrypt Text Message")
            print("  2) Decrypt Text Message")
            print("  0) Back to Main Menu")
            print()

            choice = input(f"{Colors.BOLD}Messages menu [0-2]: {Colors.RESET}").strip()
            if choice == "1":
                self._interactive_encrypt_message()
            elif choice == "2":
                self._interactive_decrypt_message()
            elif choice in ("0", "b", "back"):
                break

    def _interactive_encrypt_message(self):
        cprint("\n--- Encrypt Text Message ---", Colors.CYAN, bold=True)
        plaintext = prompt_multiline("Enter message to encrypt:")
        if not plaintext.strip():
            cprint("Empty message. Cancelled.", Colors.YELLOW)
            return

        print("\nEncryption Mode:")
        print("  1) Public Key Recipients Only")
        print("  2) Password / Symmetric Only (gpg -c)")
        print("  3) Both (Recipients + Passphrase Fallback)")
        mode = input("Select mode [1-3, default 1]: ").strip() or "1"

        recipients = []
        if mode in ("1", "3"):
            recipients = self._prompt_select_multiple_recipients()
            if not recipients and mode == "1":
                cprint("At least one recipient is required for mode 1.", Colors.RED)
                return

        passphrase = None
        cipher = "AES256"
        if mode in ("2", "3"):
            passphrase = getpass.getpass("Enter symmetric encryption passphrase: ")
            confirm = getpass.getpass("Confirm passphrase: ")
            if passphrase != confirm:
                cprint("Passphrases do not match. Cancelled.", Colors.RED)
                return
            cipher = self._prompt_cipher_algorithm()

        sign_key_id = None
        sign_passphrase = None
        sec_keys = self.backend.list_keys(secret_only=True)
        if sec_keys:
            want_sign = input("\nDigitally sign this message? [y/N]: ").strip().lower()
            if want_sign == "y":
                sign_k = self._prompt_select_key(sec_keys, "Select signing key:")
                if sign_k:
                    sign_key_id = sign_k.key_id
                    sign_passphrase = getpass.getpass("Signing key passphrase (if required): ") or None

        cprint("\nEncrypting...", Colors.YELLOW)
        ok, ciphertext, err = self.backend.encrypt_text(
            plaintext=plaintext,
            recipient_ids=recipients if recipients else None,
            sign_key_id=sign_key_id,
            sign_passphrase=sign_passphrase,
            symmetric=bool(passphrase),
            symmetric_passphrase=passphrase,
            cipher_algo=cipher,
            armor=True,
        )
        if ok:
            cprint("✓ Message encrypted successfully!\n", Colors.GREEN, bold=True)
            print(ciphertext)
            print()
            save = input("Save ciphertext to file? [y/N]: ").strip().lower()
            if save == "y":
                fn = input("Filename [default: message.asc]: ").strip() or "message.asc"
                try:
                    with open(fn, "w", encoding="utf-8") as f:
                        f.write(ciphertext)
                    cprint(f"Saved to {fn}", Colors.GREEN)
                except Exception as e:
                    cprint(f"Failed to save file: {e}", Colors.RED)
        else:
            cprint(f"✗ Encryption failed: {err}", Colors.RED)

    def _interactive_decrypt_message(self):
        cprint("\n--- Decrypt Text Message ---", Colors.CYAN, bold=True)
        ciphertext = prompt_multiline("Paste PGP Armored Message Block:")
        if not ciphertext.strip():
            cprint("Empty input. Cancelled.", Colors.YELLOW)
            return

        passphrase = getpass.getpass("Decryption passphrase (optional, press Enter if using agent/secret key): ") or None
        cprint("\nDecrypting...", Colors.YELLOW)
        ok, plaintext, verify_result, err = self.backend.decrypt_text(ciphertext, passphrase=passphrase)
        if ok:
            cprint("✓ Message decrypted successfully!\n", Colors.GREEN, bold=True)
            cprint("--- DECRYPTED PLAINTEXT ---", Colors.CYAN, bold=True)
            print(plaintext)
            print("---------------------------")
            self._print_verify_result(verify_result)
        else:
            cprint(f"✗ Decryption failed: {err}", Colors.RED)

    # =========================================================================
    # 3. File Cryptography Submenu
    # =========================================================================
    def _menu_files(self):
        while True:
            print()
            cprint("  --- 📁 File Cryptography ---", Colors.BLUE, bold=True)
            print("  1) Encrypt File")
            print("  2) Decrypt File")
            print("  0) Back to Main Menu")
            print()

            choice = input(f"{Colors.BOLD}Files menu [0-2]: {Colors.RESET}").strip()
            if choice == "1":
                self._interactive_encrypt_file()
            elif choice == "2":
                self._interactive_decrypt_file()
            elif choice in ("0", "b", "back"):
                break

    def _interactive_encrypt_file(self):
        cprint("\n--- Encrypt File ---", Colors.CYAN, bold=True)
        in_path = input("Enter path to file to encrypt: ").strip().strip("'\"")
        if not os.path.isfile(in_path):
            cprint(f"File not found: {in_path}", Colors.RED)
            return

        armor_opt = input("Use ASCII Armor output (.asc instead of .gpg)? [y/N]: ").strip().lower() == "y"
        ext = ".asc" if armor_opt else ".gpg"
        default_out = in_path + ext
        out_path = input(f"Output file path [default: {default_out}]: ").strip().strip("'\"") or default_out

        print("\nEncryption Mode:")
        print("  1) Public Key Recipients Only")
        print("  2) Password / Symmetric Only")
        print("  3) Both (Recipients + Passphrase)")
        mode = input("Select mode [1-3, default 1]: ").strip() or "1"

        recipients = []
        if mode in ("1", "3"):
            recipients = self._prompt_select_multiple_recipients()
            if not recipients and mode == "1":
                cprint("At least one recipient is required.", Colors.RED)
                return

        passphrase = None
        cipher = "AES256"
        if mode in ("2", "3"):
            passphrase = getpass.getpass("Enter encryption passphrase: ")
            confirm = getpass.getpass("Confirm passphrase: ")
            if passphrase != confirm:
                cprint("Passphrases do not match.", Colors.RED)
                return
            cipher = self._prompt_cipher_algorithm()

        sign_key_id = None
        sign_passphrase = None
        sec_keys = self.backend.list_keys(secret_only=True)
        if sec_keys:
            want_sign = input("\nDigitally sign this file during encryption? [y/N]: ").strip().lower()
            if want_sign == "y":
                sign_k = self._prompt_select_key(sec_keys, "Select signing key:")
                if sign_k:
                    sign_key_id = sign_k.key_id
                    sign_passphrase = getpass.getpass("Signing key passphrase (if required): ") or None

        cprint("\nEncrypting file...", Colors.YELLOW)
        ok, msg = self.backend.encrypt_file(
            src_path=in_path,
            dest_path=out_path,
            recipient_ids=recipients if recipients else None,
            sign_key_id=sign_key_id,
            sign_passphrase=sign_passphrase,
            symmetric=bool(passphrase),
            symmetric_passphrase=passphrase,
            cipher_algo=cipher,
            armor=armor_opt,
        )
        if ok:
            cprint(f"✓ File successfully encrypted to {out_path}!", Colors.GREEN, bold=True)
        else:
            cprint(f"✗ File encryption failed: {msg}", Colors.RED)

    def _interactive_decrypt_file(self):
        cprint("\n--- Decrypt File ---", Colors.CYAN, bold=True)
        in_path = input("Enter path to encrypted file: ").strip().strip("'\"")
        if not os.path.isfile(in_path):
            cprint(f"File not found: {in_path}", Colors.RED)
            return

        base, ext = os.path.splitext(in_path)
        default_out = base if ext in (".gpg", ".asc", ".pgp") else in_path + ".decrypted"
        out_path = input(f"Output decrypted file path [default: {default_out}]: ").strip().strip("'\"") or default_out

        passphrase = getpass.getpass("Decryption passphrase (optional): ") or None
        cprint("\nDecrypting file...", Colors.YELLOW)
        ok, verify_result, msg = self.backend.decrypt_file(in_path, out_path, passphrase=passphrase)
        if ok:
            cprint(f"✓ File successfully decrypted to {out_path}!", Colors.GREEN, bold=True)
            self._print_verify_result(verify_result)
        else:
            cprint(f"✗ File decryption failed: {msg}", Colors.RED)

    # =========================================================================
    # 4. Signatures & Verification Submenu
    # =========================================================================
    def _menu_signatures(self):
        while True:
            print()
            cprint("  --- ✍️ Digital Signatures & Verification ---", Colors.BLUE, bold=True)
            print("  1) Clearsign Text Message (Inline Signature)")
            print("  2) Verify Signed Text Message")
            print("  3) Sign File (Detached or Embedded Signature)")
            print("  4) Verify Signed File")
            print("  0) Back to Main Menu")
            print()

            choice = input(f"{Colors.BOLD}Signatures menu [0-4]: {Colors.RESET}").strip()
            if choice == "1":
                self._interactive_clearsign_text()
            elif choice == "2":
                self._interactive_verify_text()
            elif choice == "3":
                self._interactive_sign_file()
            elif choice == "4":
                self._interactive_verify_file()
            elif choice in ("0", "b", "back"):
                break

    def _interactive_clearsign_text(self):
        sec_keys = self.backend.list_keys(secret_only=True)
        if not sec_keys:
            cprint("No secret keys found in keyring to sign with.", Colors.RED)
            return
        key = self._prompt_select_key(sec_keys, "Select signing key:")
        if not key:
            return
        passphrase = getpass.getpass("Passphrase for signing key (if protected): ") or None
        text = prompt_multiline("Enter text to sign:")
        if not text.strip():
            cprint("Empty text. Cancelled.", Colors.YELLOW)
            return

        cprint("\nSigning...", Colors.YELLOW)
        ok, signed_text, msg = self.backend.clearsign_text(text, key.key_id, passphrase=passphrase)
        if ok:
            cprint("✓ Clearsigned message generated!\n", Colors.GREEN, bold=True)
            print(signed_text)
            print()
        else:
            cprint(f"✗ Clearsign failed: {msg}", Colors.RED)

    def _interactive_verify_text(self):
        signed_text = prompt_multiline("Paste Signed Message (including PGP headers):")
        if not signed_text.strip():
            cprint("Empty input. Cancelled.", Colors.YELLOW)
            return
        cprint("\nVerifying signature...", Colors.YELLOW)
        ok, vr = self.backend.verify_text(signed_text)
        self._print_verify_result(vr)

    def _interactive_sign_file(self):
        sec_keys = self.backend.list_keys(secret_only=True)
        if not sec_keys:
            cprint("No secret keys found in keyring.", Colors.RED)
            return
        in_path = input("Enter path to file to sign: ").strip().strip("'\"")
        if not os.path.isfile(in_path):
            cprint(f"File not found: {in_path}", Colors.RED)
            return
        key = self._prompt_select_key(sec_keys, "Select signing key:")
        if not key:
            return
        passphrase = getpass.getpass("Signing passphrase: ") or None

        detached = input("Create detached signature (.asc / .sig)? [Y/n]: ").strip().lower() != "n"
        armor = input("Use ASCII armor (.asc)? [Y/n]: ").strip().lower() != "n"
        default_out = in_path + (".asc" if armor else ".sig")
        out_path = input(f"Output signature path [default: {default_out}]: ").strip().strip("'\"") or default_out

        cprint("\nSigning file...", Colors.YELLOW)
        ok, msg = self.backend.sign_file(
            src_path=in_path,
            dest_path=out_path,
            sign_key_id=key.key_id,
            passphrase=passphrase,
            detached=detached,
            armor=armor,
        )
        if ok:
            cprint(f"✓ Signature created at {out_path}!", Colors.GREEN, bold=True)
        else:
            cprint(f"✗ Signing failed: {msg}", Colors.RED)

    def _interactive_verify_file(self):
        f1 = input("Enter signed file (or data file): ").strip().strip("'\"")
        if not os.path.isfile(f1):
            cprint(f"File not found: {f1}", Colors.RED)
            return
        f2 = input("Enter signature file (leave empty if data file contains inline signature): ").strip().strip("'\"")
        if f2 and not os.path.isfile(f2):
            cprint(f"Signature file not found: {f2}", Colors.RED)
            return

        cprint("\nVerifying file...", Colors.YELLOW)
        ok, vr = self.backend.verify_file(f1, data_path=f2 or None)
        self._print_verify_result(vr)

    # =========================================================================
    # 5. Checksums & Integrity
    # =========================================================================
    def _menu_checksums(self):
        cprint("\n--- 🛡️ File Checksums (SHA-256 / SHA-512) ---", Colors.CYAN, bold=True)
        path = input("Enter path to file: ").strip().strip("'\"")
        if not os.path.isfile(path):
            cprint(f"File not found: {path}", Colors.RED)
            return

        expected = input("Expected hash (optional, for comparison): ").strip()
        self.cmd_checksum(path, expected=expected or None)

    def cmd_checksum(self, path: str, expected: Optional[str] = None):
        if not os.path.isfile(path):
            cprint(f"File not found: {path}", Colors.RED)
            return

        cprint(f"\nComputing cryptographic hashes for: {path}...", Colors.YELLOW)
        sha256 = hashlib.sha256()
        sha512 = hashlib.sha512()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
                sha512.update(chunk)

        h256 = sha256.hexdigest()
        h512 = sha512.hexdigest()

        cprint(f"\nSHA-256: {Colors.BOLD}{h256}{Colors.RESET}")
        cprint(f"SHA-512: {Colors.DIM}{h512}{Colors.RESET}\n")

        if expected:
            clean_exp = expected.strip().lower()
            if clean_exp in (h256.lower(), h512.lower()):
                cprint(f"✓ INTEGRITY VERIFIED: Hash matches expected value!", Colors.GREEN, bold=True)
            else:
                cprint(f"✗ HASH MISMATCH: File does NOT match expected hash!", Colors.RED, bold=True)

        print(f"Command line equivalent:")
        print(f"  sha256sum {path}")
        print(f"  sha512sum {path}")

    # =========================================================================
    # 6. System Information & Settings
    # =========================================================================
    def _menu_system(self):
        while True:
            print()
            cprint("  --- ⚙️ System & GPG Configuration ---", Colors.BLUE, bold=True)
            print("  1) View GPG Version & Supported Algorithms")
            print("  2) Change GPG Binary Path")
            print("  3) Change GNUPGHOME Directory")
            print("  0) Back to Main Menu")
            print()

            choice = input(f"{Colors.BOLD}System menu [0-3]: {Colors.RESET}").strip()
            if choice == "1":
                self.cmd_system_info()
            elif choice == "2":
                self._interactive_change_binary()
            elif choice == "3":
                self._interactive_change_homedir()
            elif choice in ("0", "b", "back"):
                break

    def cmd_system_info(self):
        info = self.backend.get_system_info()
        pub_keys = self.backend.list_keys(secret_only=False)
        sec_keys = self.backend.list_keys(secret_only=True)
        cprint(f"\n=== GnuPG System Information ===", Colors.CYAN, bold=True)
        print(f"  GPG Version      : {info.get('version', 'Unknown')}")
        print(f"  GPG Binary       : {info.get('binary', 'gpg')}")
        print(f"  GNUPGHOME        : {info.get('home', 'Default (~/.gnupg)')}")
        print(f"  Total Public Keys: {len(pub_keys)}")
        print(f"  Total Secret Keys: {len(sec_keys)}")
        print()
        print(f"  Supported Public Key Ciphers: {', '.join(info.get('pubkey_algos', []))}")
        print(f"  Supported Symmetric Ciphers : {', '.join(info.get('ciphers', []))}")
        print(f"  Supported Hash Algorithms   : {', '.join(info.get('hashes', []))}")

    def _interactive_change_binary(self):
        current = self.backend.gpg_binary
        cprint(f"Current GPG binary: {current}", Colors.CYAN)
        new_bin = input("Enter new GPG binary path (or 'default' to reset): ").strip()
        if not new_bin:
            return
        ok, msg = self.backend.set_gpg_binary(new_bin)
        if ok:
            cprint(f"✓ {msg}", Colors.GREEN)
        else:
            cprint(f"✗ Error: {msg}", Colors.RED)

    def _interactive_change_homedir(self):
        current = self.backend.gnupg_home or "Default (~/.gnupg)"
        cprint(f"Current GNUPGHOME: {current}", Colors.CYAN)
        new_home = input("Enter new GNUPGHOME directory path (or 'default' to reset): ").strip()
        if not new_home:
            return
        ok, msg = self.backend.set_gnupg_home(new_home)
        if ok:
            cprint(f"✓ {msg}", Colors.GREEN)
        else:
            cprint(f"✗ Error: {msg}", Colors.RED)

    # =========================================================================
    # Helpers
    # =========================================================================
    def _prompt_select_key(self, keys: List[GPGKey], prompt_title: str) -> Optional[GPGKey]:
        cprint(f"\n{prompt_title}", Colors.CYAN, bold=True)
        for i, k in enumerate(keys, 1):
            print(f"  {i}) {k.display_name} [{k.key_id}] ({k.algo})")
        print("  0) Cancel")
        ch = input("Select [0-{0}]: ".format(len(keys))).strip()
        try:
            val = int(ch)
            if 1 <= val <= len(keys):
                return keys[val - 1]
        except ValueError:
            pass
        return None

    def _prompt_select_multiple_recipients(self) -> List[str]:
        keys = self.backend.list_keys()
        if not keys:
            cprint("No public keys found to encrypt to!", Colors.RED)
            return []
        cprint("\nSelect Recipients (Enter comma-separated numbers, or 'all'):", Colors.CYAN, bold=True)
        for i, k in enumerate(keys, 1):
            print(f"  {i:2d}) {k.display_name} [{k.key_id}]")
        sel = input("Recipients: ").strip().lower()
        if sel == "all":
            return [k.key_id for k in keys]
        selected = []
        for part in sel.split(","):
            part = part.strip()
            try:
                idx = int(part)
                if 1 <= idx <= len(keys):
                    selected.append(keys[idx - 1].key_id)
            except ValueError:
                # Allow user to directly pass Key ID or email
                matched = [k.key_id for k in keys if part in k.key_id.lower() or part in k.email.lower()]
                selected.extend(matched)
        return list(dict.fromkeys(selected))

    def _prompt_cipher_algorithm(self) -> str:
        ciphers = ["AES256", "AES192", "AES128", "TWOFISH", "CAMELLIA256", "3DES"]
        print("\nSymmetric Cipher Algorithm:")
        for idx, c in enumerate(ciphers, 1):
            print(f"  {idx}) {c}{' (Recommended)' if c == 'AES256' else ''}")
        ch = input("Select cipher [1-6, default 1]: ").strip() or "1"
        try:
            val = int(ch)
            if 1 <= val <= len(ciphers):
                return ciphers[val - 1]
        except ValueError:
            pass
        return "AES256"

    def _print_verify_result(self, vr: VerifyResult):
        print()
        if vr.status == "NO_SIG":
            return
        if vr.status == "GOOD":
            cprint("✓ VALID DIGITAL SIGNATURE", Colors.GREEN, bold=True)
        elif vr.status == "BAD":
            cprint("✗ BAD DIGITAL SIGNATURE (Data may be corrupted or tampered!)", Colors.RED, bold=True)
        elif vr.status == "EXPIRED":
            cprint("⚠️  SIGNATURE IS VALID BUT KEY / SIGNATURE HAS EXPIRED", Colors.YELLOW, bold=True)
        elif vr.status == "NO_KEY":
            cprint("❓ SIGNED WITH UNKNOWN PUBLIC KEY (Public key not in keyring)", Colors.YELLOW, bold=True)
        else:
            cprint(f"Verification Status: {vr.status}", Colors.WHITE, bold=True)

        if vr.signer_uid:
            print(f"  Signer      : {vr.signer_uid}")
        if vr.key_id:
            print(f"  Key ID      : {vr.key_id}")
        if vr.fingerprint:
            print(f"  Fingerprint : {vr.fingerprint}")
        if vr.timestamp:
            print(f"  Signed Date : {vr.timestamp}")
        if vr.summary:
            cprint(f"  Summary     : {vr.summary}", Colors.DIM)


# =============================================================================
# CLI Subcommands Argument Parser
# =============================================================================
def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gpgman",
        description="GPGMan - Dual-Style OpenPGP Cryptographic Suite (GUI & CLI)",
    )
    parser.add_argument("-v", "--version", action="version", version=f"GPGMan v{__version__}")
    parser.add_argument("--gui", action="store_true", help="Launch the GTK4 / Libadwaita graphical interface")
    parser.add_argument("--cli", action="store_true", help="Launch the interactive terminal interface")

    subparsers = parser.add_subparsers(dest="subcommand", help="Available direct subcommands")

    # Interactive CLI command
    subparsers.add_parser("interactive", help="Start the interactive terminal menu")

    # keys
    p_keys = subparsers.add_parser("keys", help="Manage GPG keys")
    p_keys.add_argument("--secret", action="store_true", help="List secret keys only")
    p_keys.add_argument("--list", action="store_true", default=True, help="List keys (default)")

    # key-generate
    p_kgen = subparsers.add_parser("key-generate", help="Generate a new GPG key pair")
    p_kgen.add_argument("--name", required=True, help="Full name")
    p_kgen.add_argument("--email", required=True, help="Email address")
    p_kgen.add_argument("--comment", default="", help="Optional comment")
    p_kgen.add_argument("--algo", default="ed25519", choices=["ed25519", "rsa4096", "rsa3072", "rsa2048", "nistp256"], help="Key algorithm")
    p_kgen.add_argument("--expire", default="1y", help="Expiration (e.g. 1y, 2y, 6m, 0)")
    p_kgen.add_argument("--passphrase", default=None, help="Passphrase for secret key")

    # key-import
    p_kimp = subparsers.add_parser("key-import", help="Import a key from file, URL, or text")
    p_kimp.add_argument("source", help="File path, URL, or armored string")

    # key-export
    p_kexp = subparsers.add_parser("key-export", help="Export a public or secret key")
    p_kexp.add_argument("key_id", help="Key ID or fingerprint to export")
    p_kexp.add_argument("--secret", action="store_true", help="Export secret key instead of public")
    p_kexp.add_argument("-o", "--output", help="Output file path (default stdout)")

    # key-delete
    p_kdel = subparsers.add_parser("key-delete", help="Delete a key from keyring")
    p_kdel.add_argument("key_id", help="Key ID to delete")

    # encrypt-text
    p_et = subparsers.add_parser("encrypt-text", help="Encrypt a text message")
    p_et.add_argument("-r", "--recipient", action="append", default=[], help="Recipient Key ID(s)")
    p_et.add_argument("-p", "--passphrase", help="Symmetric encryption passphrase")
    p_et.add_argument("-c", "--cipher", default="AES256", help="Symmetric cipher algorithm")
    p_et.add_argument("-s", "--sign-key", help="Key ID to digitally sign message")
    p_et.add_argument("-m", "--message", help="Plaintext message string (or reads from stdin)")

    # decrypt-text
    p_dt = subparsers.add_parser("decrypt-text", help="Decrypt a text message")
    p_dt.add_argument("-p", "--passphrase", help="Decryption passphrase")
    p_dt.add_argument("-m", "--message", help="Ciphertext string (or reads from stdin)")

    # encrypt-file
    p_ef = subparsers.add_parser("encrypt-file", help="Encrypt a file")
    p_ef.add_argument("input_file", help="Path to input file")
    p_ef.add_argument("-o", "--output", help="Path to output file")
    p_ef.add_argument("-r", "--recipient", action="append", default=[], help="Recipient Key ID(s)")
    p_ef.add_argument("-p", "--passphrase", help="Symmetric passphrase")
    p_ef.add_argument("-c", "--cipher", default="AES256", help="Cipher algorithm")
    p_ef.add_argument("-s", "--sign-key", help="Key ID to sign file with")
    p_ef.add_argument("--armor", action="store_true", help="Produce ASCII armored output (.asc)")

    # decrypt-file
    p_df = subparsers.add_parser("decrypt-file", help="Decrypt a file")
    p_df.add_argument("input_file", help="Path to encrypted file")
    p_df.add_argument("-o", "--output", help="Path to output decrypted file")
    p_df.add_argument("-p", "--passphrase", help="Decryption passphrase")

    # clearsign
    p_cs = subparsers.add_parser("clearsign", help="Clearsign a message")
    p_cs.add_argument("-s", "--sign-key", required=True, help="Key ID to sign with")
    p_cs.add_argument("-p", "--passphrase", help="Signing key passphrase")
    p_cs.add_argument("-m", "--message", help="Message to sign (or stdin)")

    # verify
    p_vf = subparsers.add_parser("verify", help="Verify a signed file or text")
    p_vf.add_argument("file", help="Signed file or data file path")
    p_vf.add_argument("--sig", help="Detached signature file path")

    # checksum
    p_ck = subparsers.add_parser("checksum", help="Calculate and verify SHA-256 / SHA-512 hashes")
    p_ck.add_argument("file", help="Path to file")
    p_ck.add_argument("--expected", help="Expected hash to verify against")

    # system
    subparsers.add_parser("system", help="Show GnuPG system information")

    return parser


def run_cli_args(args: argparse.Namespace) -> int:
    cli = GPGManCLI()

    if args.subcommand in ("interactive", None) and (args.cli or args.subcommand == "interactive"):
        cli.run_interactive()
        return 0

    if args.subcommand == "keys":
        cli.cmd_list_keys(secret_only=args.secret)
        return 0

    if args.subcommand == "key-generate":
        ok, msg = cli.backend.generate_key(
            name=args.name,
            email=args.email,
            comment=args.comment,
            algo=args.algo,
            expire=args.expire,
            passphrase=args.passphrase,
        )
        if ok:
            cprint(f"✓ Key generated successfully! {msg}", Colors.GREEN, bold=True)
            return 0
        else:
            cprint(f"✗ Failed: {msg}", Colors.RED)
            return 1

    if args.subcommand == "key-import":
        source = args.source
        if os.path.isfile(source):
            ok, count, msg = cli.backend.import_key_file(source)
        elif source.startswith(("http://", "https://")):
            req = urllib.request.Request(source, headers={"User-Agent": f"GPGMan-CLI/{__version__}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8", errors="replace")
            ok, count, msg = cli.backend.import_key_text(raw_text)
        else:
            ok, count, msg = cli.backend.import_key_text(source)

        if ok:
            cprint(f"✓ Successfully imported {count} key(s)!", Colors.GREEN, bold=True)
            return 0
        else:
            cprint(f"✗ Import failed: {msg}", Colors.RED)
            return 1

    if args.subcommand == "key-export":
        if args.secret:
            ok, data = cli.backend.export_secret_key(args.key_id, armor=True)
        else:
            ok, data = cli.backend.export_public_key(args.key_id, armor=True)
        if not ok:
            cprint(f"Export failed: {data}", Colors.RED)
            return 1
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(data)
            cprint(f"✓ Key exported to {args.output}", Colors.GREEN)
        else:
            print(data)
        return 0

    if args.subcommand == "key-delete":
        ok, msg = cli.backend.delete_key(args.key_id)
        if ok:
            cprint(f"✓ Key {args.key_id} deleted successfully.", Colors.GREEN)
            return 0
        else:
            cprint(f"✗ Failed: {msg}", Colors.RED)
            return 1

    if args.subcommand == "encrypt-text":
        msg = args.message if args.message else sys.stdin.read()
        ok, cipher, err = cli.backend.encrypt_text(
            plaintext=msg,
            recipient_ids=args.recipient if args.recipient else None,
            sign_key_id=args.sign_key,
            symmetric=bool(args.passphrase),
            symmetric_passphrase=args.passphrase,
            cipher_algo=args.cipher,
            armor=True,
        )
        if ok:
            print(cipher)
            return 0
        else:
            cprint(f"✗ Encryption failed: {err}", Colors.RED)
            return 1

    if args.subcommand == "decrypt-text":
        msg = args.message if args.message else sys.stdin.read()
        ok, plain, vr, err = cli.backend.decrypt_text(msg, passphrase=args.passphrase)
        if ok:
            print(plain)
            cli._print_verify_result(vr)
            return 0
        else:
            cprint(f"✗ Decryption failed: {err}", Colors.RED)
            return 1

    if args.subcommand == "encrypt-file":
        out = args.output or (args.input_file + (".asc" if args.armor else ".gpg"))
        ok, msg = cli.backend.encrypt_file(
            src_path=args.input_file,
            dest_path=out,
            recipient_ids=args.recipient if args.recipient else None,
            sign_key_id=args.sign_key,
            symmetric=bool(args.passphrase),
            symmetric_passphrase=args.passphrase,
            cipher_algo=args.cipher,
            armor=args.armor,
        )
        if ok:
            cprint(f"✓ File encrypted to {out}", Colors.GREEN)
            return 0
        else:
            cprint(f"✗ Encryption failed: {msg}", Colors.RED)
            return 1

    if args.subcommand == "decrypt-file":
        base, ext = os.path.splitext(args.input_file)
        out = args.output or (base if ext in (".gpg", ".asc", ".pgp") else args.input_file + ".decrypted")
        ok, vr, msg = cli.backend.decrypt_file(args.input_file, out, passphrase=args.passphrase)
        if ok:
            cprint(f"✓ File decrypted to {out}", Colors.GREEN)
            cli._print_verify_result(vr)
            return 0
        else:
            cprint(f"✗ Decryption failed: {msg}", Colors.RED)
            return 1

    if args.subcommand == "clearsign":
        msg = args.message if args.message else sys.stdin.read()
        ok, signed, msg = cli.backend.clearsign_text(msg, args.sign_key, passphrase=args.passphrase)
        if ok:
            print(signed)
            return 0
        else:
            cprint(f"✗ Clearsign failed: {msg}", Colors.RED)
            return 1

    if args.subcommand == "verify":
        ok, vr = cli.backend.verify_file(args.file, data_path=args.sig)
        cli._print_verify_result(vr)
        return 0 if vr.status in ("GOOD", "EXPIRED") else 1

    if args.subcommand == "checksum":
        cli.cmd_checksum(args.file, expected=args.expected)
        return 0

    if args.subcommand == "system":
        cli.cmd_system_info()
        return 0

    # Default to interactive if no command specified
    cli.run_interactive()
    return 0
