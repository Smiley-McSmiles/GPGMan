"""
GPG Backend - Wrapper around system GPG binary.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

CONFIG_DIR = os.path.expanduser("~/.config/gpgman")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")


ALGO_MAP: Dict[str, str] = {
    "1": "RSA",
    "2": "RSA Encrypt-Only",
    "3": "RSA Sign-Only",
    "16": "ElGamal",
    "17": "DSA",
    "18": "ECDH",
    "19": "ECDSA",
    "22": "EdDSA (Ed25519)",
}

VALIDITY_MAP: Dict[str, str] = {
    "o": "Unknown",
    "i": "Invalid",
    "d": "Disabled",
    "r": "Revoked",
    "e": "Expired",
    "q": "Undefined",
    "n": "Never",
    "m": "Marginal",
    "f": "Full",
    "u": "Ultimate",
}


@dataclass
class GPGSubkey:
    key_id: str
    fingerprint: str
    algo: str
    length: int
    created: Optional[str]
    expires: Optional[str]
    capabilities: List[str]
    is_secret: bool = False


@dataclass
class GPGKey:
    key_id: str
    fingerprint: str
    uids: List[str] = field(default_factory=list)
    primary_uid: str = ""
    name: str = ""
    email: str = ""
    comment: str = ""
    length: int = 0
    algo: str = "Unknown"
    created: Optional[str] = None
    expires: Optional[str] = None
    is_expired: bool = False
    is_secret: bool = False
    validity: str = "Unknown"
    capabilities: List[str] = field(default_factory=list)
    subkeys: List[GPGSubkey] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if self.name and self.email:
            return f"{self.name} <{self.email}>"
        if self.name:
            return self.name
        if self.email:
            return self.email
        if self.primary_uid:
            return self.primary_uid
        return self.key_id

    @property
    def formatted_fingerprint(self) -> str:
        if not self.fingerprint:
            return ""
        fp = self.fingerprint.upper()
        # Group into 4-char chunks
        return " ".join(fp[i : i + 4] for i in range(0, len(fp), 4))


@dataclass
class VerifyResult:
    valid: bool
    status: str  # "GOOD", "BAD", "EXPIRED", "NO_KEY", "ERROR"
    signer_uid: str = ""
    key_id: str = ""
    fingerprint: str = ""
    timestamp: Optional[str] = None
    trust: str = "Unknown"
    raw_output: str = ""
    summary: str = ""


class GPGBackend:
    def __init__(self, gpg_binary: Optional[str] = None, gnupg_home: Optional[str] = None):
        saved_bin, saved_home = self._load_settings()
        self.gpg_binary = gpg_binary or saved_bin or shutil.which("gpg") or "/usr/bin/gpg"
        self.gnupg_home = gnupg_home or saved_home or None
        if not os.path.exists(self.gpg_binary):
            raise FileNotFoundError(f"GPG binary not found at '{self.gpg_binary}'")

    def _load_settings(self) -> Tuple[Optional[str], Optional[str]]:
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    b = data.get("gpg_binary")
                    h = data.get("gnupg_home")
                    if b and os.path.isfile(b) and os.access(b, os.X_OK):
                        return b, h
                    return None, h
        except Exception:
            pass
        return None, None

    def _save_settings(self):
        try:
            os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
            data = {
                "gpg_binary": self.gpg_binary,
                "gnupg_home": self.gnupg_home,
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def set_gpg_binary(self, path: str) -> Tuple[bool, str]:
        """Validate and set a custom GPG binary executable."""
        path = path.strip()
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            return False, f"File does not exist or is not executable: {path}"
        try:
            res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                return False, f"Binary failed verification (exit code {res.returncode}): {res.stderr}"
        except Exception as e:
            return False, f"Failed to execute binary: {e}"

        self.gpg_binary = path
        self._save_settings()
        return True, f"GPG binary updated to: {path}"

    def set_gnupg_home(self, path: str) -> Tuple[bool, str]:
        """Validate and set custom GnuPG home directory."""
        path = path.strip()
        if not path or path == "default":
            self.gnupg_home = None
            self._save_settings()
            return True, "Reset GnuPG home to default directory."

        resolved = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(resolved):
            try:
                os.makedirs(resolved, mode=0o700, exist_ok=True)
            except Exception as e:
                return False, f"Failed to create directory {resolved}: {e}"
        elif not os.path.isdir(resolved):
            return False, f"Path is not a directory: {resolved}"

        self.gnupg_home = resolved
        self._save_settings()
        return True, f"GnuPG home directory updated to: {resolved}"

    def _run(
        self,
        args: List[str],
        input_data: Optional[str | bytes] = None,
        check: bool = False,
        passphrase: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """Runs the gpg command with provided arguments.

        ``passphrase`` is handed to gpg through a private pipe (--passphrase-fd) in
        loopback pinentry mode, so it never appears in the process list.
        """
        cmd = [self.gpg_binary]
        if self.gnupg_home:
            cmd.extend(["--homedir", self.gnupg_home])
        cmd.extend(["--batch", "--no-tty"])
        pass_fds: Tuple[int, ...] = ()
        pass_read_fd = None
        if passphrase is not None:
            pass_read_fd, pass_write_fd = os.pipe()
            try:
                os.write(pass_write_fd, (passphrase + "\n").encode("utf-8"))
            finally:
                os.close(pass_write_fd)
            pass_fds = (pass_read_fd,)
            cmd.extend(["--pinentry-mode", "loopback", "--passphrase-fd", str(pass_read_fd)])
        cmd.extend(args)
        stdin = subprocess.PIPE if input_data is not None else subprocess.DEVNULL
        
        if isinstance(input_data, str):
            input_bytes = input_data.encode("utf-8")
        else:
            input_bytes = input_data

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=pass_fds,
            )
            stdout, stderr = proc.communicate(input=input_bytes)
            out_str = stdout.decode("utf-8", errors="replace")
            err_str = stderr.decode("utf-8", errors="replace")
            if check and proc.returncode != 0:
                raise RuntimeError(f"GPG error ({proc.returncode}): {err_str}")
            return proc.returncode, out_str, err_str
        except Exception as e:
            return -1, "", str(e)
        finally:
            if pass_read_fd is not None:
                os.close(pass_read_fd)

    def _parse_timestamp(self, ts_str: str) -> Optional[str]:
        if not ts_str:
            return None
        try:
            ts = int(ts_str)
            if ts <= 0:
                return None
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError):
            return ts_str

    def _parse_uid(self, uid_str: str) -> Tuple[str, str, str]:
        """Parses a UID like 'John Doe (work) <john@example.com>' into name, email, comment."""
        name = ""
        email = ""
        comment = ""

        # Match name (comment) <email>
        match = re.match(r"^(.*?)(?:\s*\((.*?)\))?(?:\s*<([^>]+)>)?$", uid_str.strip())
        if match:
            name = (match.group(1) or "").strip()
            comment = (match.group(2) or "").strip()
            email = (match.group(3) or "").strip()
        else:
            name = uid_str.strip()

        return name, email, comment

    def _parse_capabilities(self, cap_str: str) -> List[str]:
        caps = []
        c = cap_str.lower()
        if "e" in c:
            caps.append("Encrypt")
        if "s" in c:
            caps.append("Sign")
        if "c" in c:
            caps.append("Certify")
        if "a" in c:
            caps.append("Authenticate")
        return caps

    def list_keys(self, secret_only: bool = False) -> List[GPGKey]:
        """List public and/or secret keys from system keyring."""
        # First gather secret key IDs if we need secret flags
        secret_ids = set()
        code, sec_out, _ = self._run(
            ["--with-colons", "--fingerprint", "--list-secret-keys"]
        )
        if code == 0:
            for line in sec_out.splitlines():
                parts = line.split(":")
                if parts and parts[0] in ("sec", "ssb") and len(parts) > 4:
                    secret_ids.add(parts[4])

        list_cmd = (
            ["--with-colons", "--fingerprint", "--list-secret-keys"]
            if secret_only
            else ["--with-colons", "--fingerprint", "--list-keys"]
        )
        code, stdout, _ = self._run(list_cmd)
        if code != 0:
            return []

        keys: List[GPGKey] = []
        current_key: Optional[GPGKey] = None
        current_subkey: Optional[GPGSubkey] = None

        for line in stdout.splitlines():
            parts = line.split(":")
            if not parts:
                continue
            rec_type = parts[0]

            if rec_type in ("pub", "sec"):
                # Save previous key if present
                if current_key:
                    keys.append(current_key)
                
                key_id = parts[4] if len(parts) > 4 else ""
                val_code = parts[1] if len(parts) > 1 else ""
                length = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                algo_id = parts[3] if len(parts) > 3 else ""
                created = self._parse_timestamp(parts[5]) if len(parts) > 5 else None
                expires = self._parse_timestamp(parts[6]) if len(parts) > 6 else None
                cap_str = parts[11] if len(parts) > 11 else ""

                is_expired = False
                if len(parts) > 6 and parts[6].isdigit():
                    exp_ts = int(parts[6])
                    if 0 < exp_ts < datetime.now().timestamp():
                        is_expired = True

                is_sec = rec_type == "sec" or key_id in secret_ids

                current_key = GPGKey(
                    key_id=key_id,
                    fingerprint="",
                    length=length,
                    algo=ALGO_MAP.get(algo_id, f"Algo {algo_id}"),
                    created=created,
                    expires=expires,
                    is_expired=is_expired,
                    is_secret=is_sec,
                    validity=VALIDITY_MAP.get(val_code, "Unknown"),
                    capabilities=self._parse_capabilities(cap_str),
                )
                current_subkey = None

            elif rec_type in ("sub", "ssb") and current_key:
                key_id = parts[4] if len(parts) > 4 else ""
                length = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                algo_id = parts[3] if len(parts) > 3 else ""
                created = self._parse_timestamp(parts[5]) if len(parts) > 5 else None
                expires = self._parse_timestamp(parts[6]) if len(parts) > 6 else None
                cap_str = parts[11] if len(parts) > 11 else ""

                current_subkey = GPGSubkey(
                    key_id=key_id,
                    fingerprint="",
                    algo=ALGO_MAP.get(algo_id, f"Algo {algo_id}"),
                    length=length,
                    created=created,
                    expires=expires,
                    capabilities=self._parse_capabilities(cap_str),
                    is_secret=(rec_type == "ssb" or key_id in secret_ids),
                )
                current_key.subkeys.append(current_subkey)

            elif rec_type == "fpr":
                fpr_val = parts[9] if len(parts) > 9 else ""
                if current_subkey:
                    current_subkey.fingerprint = fpr_val
                elif current_key and not current_key.fingerprint:
                    current_key.fingerprint = fpr_val

            elif rec_type == "uid" and current_key:
                uid_str = parts[9] if len(parts) > 9 else ""
                if uid_str and uid_str not in current_key.uids:
                    current_key.uids.append(uid_str)
                    if not current_key.primary_uid:
                        current_key.primary_uid = uid_str
                        name, email, comment = self._parse_uid(uid_str)
                        current_key.name = name
                        current_key.email = email
                        current_key.comment = comment

        if current_key:
            keys.append(current_key)

        return keys

    def get_key(self, key_id: str) -> Optional[GPGKey]:
        all_keys = self.list_keys()
        for k in all_keys:
            if k.key_id == key_id or k.fingerprint == key_id:
                return k
        return None

    def generate_key(
        self,
        name: str,
        email: str = "",
        comment: str = "",
        algo: str = "ed25519",
        usage: str = "all",
        expire: str | int = 0,
        expire_days: Optional[int] = None,
        passphrase: str = "",
    ) -> Tuple[bool, str]:
        """Generate a new GPG key using quick-generate-key."""
        if not name.strip():
            return False, "Name cannot be empty."

        # Construct UserID
        uid_parts = [name.strip()]
        if comment.strip():
            uid_parts.append(f"({comment.strip()})")
        if email.strip():
            uid_parts.append(f"<{email.strip()}>")
        user_id = " ".join(uid_parts)

        # Map algorithm
        algo_lower = algo.lower()
        if "ed25519" in algo_lower or "eddsa" in algo_lower:
            key_algo = "ed25519"
            sub_algo = "cv25519" if usage in ("all", "encrypt") else None
        elif "4096" in algo_lower:
            key_algo = "rsa4096"
            sub_algo = "rsa4096" if usage in ("all", "encrypt") else None
        elif "3072" in algo_lower:
            key_algo = "rsa3072"
            sub_algo = "rsa3072" if usage in ("all", "encrypt") else None
        elif "2048" in algo_lower:
            key_algo = "rsa2048"
            sub_algo = "rsa2048" if usage in ("all", "encrypt") else None
        elif "521" in algo_lower:
            key_algo = "nistp521"
            sub_algo = "nistp521" if usage in ("all", "encrypt") else None
        elif "384" in algo_lower:
            key_algo = "nistp384"
            sub_algo = "nistp384" if usage in ("all", "encrypt") else None
        elif "256" in algo_lower or "ecdsa" in algo_lower:
            key_algo = "nistp256"
            sub_algo = "nistp256" if usage in ("all", "encrypt") else None
        else:
            key_algo = "default"
            sub_algo = "default" if usage in ("all", "encrypt") else None

        # Determine expiration string
        if expire_days is not None and expire == 0:
            expire_str = "0" if expire_days <= 0 else f"{expire_days}d"
        elif isinstance(expire, str):
            expire_str = expire.strip() or "0"
        elif isinstance(expire, int):
            expire_str = "0" if expire <= 0 else f"{expire}d"
        else:
            expire_str = "0"

        passphrase_val = passphrase or ""
        cmd_args = []
        primary_usage = "default"
        if usage == "sign":
            primary_usage = "sign"
        elif usage == "encrypt":
            primary_usage = "encr"

        cmd_args.extend(["--quick-generate-key", user_id, key_algo, primary_usage, expire_str])

        code, out, err = self._run(cmd_args, passphrase=passphrase_val)
        if code != 0:
            return False, err or out or "Failed to generate key."

        # Add encryption subkey if needed (e.g. ed25519 needs cv25519, rsa needs encr subkey)
        if sub_algo and usage == "all" and key_algo != "default":
            new_keys = self.list_keys()
            matching = [k for k in new_keys if user_id in k.uids or (email and email in k.email)]
            if matching:
                fpr = matching[-1].fingerprint
                sub_args = ["--quick-add-key", fpr, sub_algo, "encr", expire_str]
                self._run(sub_args, passphrase=passphrase_val)

        return True, f"Key created successfully for '{user_id}'."

    def import_key_text(self, key_text: str) -> Tuple[bool, int, str]:
        """Import key from ASCII armored text."""
        code, out, err = self._run(["--import"], input_data=key_text)
        total_imported = 0
        for line in (err + "\n" + out).splitlines():
            if "imported:" in line.lower() or "total number processed:" in line.lower():
                nums = re.findall(r"\d+", line)
                if nums:
                    total_imported = max(total_imported, int(nums[-1]))
        if code == 0:
            return True, total_imported, err or out or "Key(s) imported successfully."
        return False, 0, err or "Failed to import key."

    def import_key_file(self, file_path: str) -> Tuple[bool, int, str]:
        """Import key from a file (.asc, .gpg, .key)."""
        if not os.path.isfile(file_path):
            return False, 0, f"File not found: {file_path}"
        code, out, err = self._run(["--import", file_path])
        total_imported = 0
        for line in (err + "\n" + out).splitlines():
            if "imported:" in line.lower() or "total number processed:" in line.lower():
                nums = re.findall(r"\d+", line)
                if nums:
                    total_imported = max(total_imported, int(nums[-1]))
        if code == 0:
            return True, total_imported, err or out or "Key(s) imported successfully."
        return False, 0, err or "Failed to import key."

    def export_public_key(self, key_id: str, armor: bool = True) -> Tuple[bool, str]:
        """Export public key."""
        args = ["--export"]
        if armor:
            args.insert(0, "--armor")
        args.append(key_id)
        code, out, err = self._run(args)
        if code == 0 and out.strip():
            return True, out
        return False, err or "Export failed."

    def export_secret_key(
        self, key_id: str, armor: bool = True, passphrase: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Export secret key.

        With ``passphrase`` set, gpg is run in loopback pinentry mode and the
        passphrase is fed over stdin, so no system pinentry is required.
        """
        args = ["--export-secret-keys"]
        if armor:
            args.insert(0, "--armor")
        args.append(key_id)
        code, out, err = self._run(args, passphrase=passphrase)
        if code == 0 and out.strip():
            return True, out
        return False, err or "Export secret key failed."

    def delete_key(self, key_id: str) -> Tuple[bool, str]:
        """Delete secret key and/or public key."""
        target_key = self.get_key(key_id)
        fpr = target_key.fingerprint if target_key and target_key.fingerprint else key_id
        # Try deleting secret key first (if exists)
        self._run(["--yes", "--delete-secret-key", fpr])
        # Then delete public key
        code, out, err = self._run(["--yes", "--delete-key", fpr])
        if code == 0:
            return True, "Key deleted successfully."
        return False, err or "Failed to delete key."

    def change_passphrase(self, key_id: str) -> Tuple[bool, str]:
        """Runs gpg --passwd."""
        code, out, err = self._run(["--passwd", key_id])
        if code == 0:
            return True, "Passphrase updated."
        return False, err or "Failed to change passphrase."

    def encrypt_text(
        self,
        plaintext: str,
        recipient_ids: Optional[List[str]] = None,
        sign_key_id: Optional[str] = None,
        sign_passphrase: Optional[str] = None,
        symmetric: bool = False,
        symmetric_passphrase: Optional[str] = None,
        cipher_algo: Optional[str] = None,
        armor: bool = True,
    ) -> Tuple[bool, str, str]:
        """Encrypt text for recipients and/or symmetric passphrase, optionally signing."""
        if not recipient_ids and not symmetric:
            return False, "", "No recipients selected and symmetric encryption not chosen."

        run_passphrase: Optional[str] = None
        args = ["--yes"]
        if armor:
            args.append("--armor")
        if cipher_algo:
            args.extend(["--cipher-algo", cipher_algo])

        # If symmetric passphrase is used
        if symmetric:
            args.append("--symmetric")
            if symmetric_passphrase:
                run_passphrase = symmetric_passphrase

        # If public key recipients are used
        if recipient_ids:
            args.extend(["--encrypt", "--trust-model", "always"])
            for r in recipient_ids:
                args.extend(["-r", r])

        # If signing with secret key
        if sign_key_id:
            args.extend(["--sign", "--local-user", sign_key_id])
            if sign_passphrase and not (symmetric and symmetric_passphrase):
                run_passphrase = sign_passphrase

        code, out, err = self._run(args, input_data=plaintext, passphrase=run_passphrase)
        if code == 0:
            return True, out, ""
        return False, "", err or "Encryption failed."

    def decrypt_text(
        self,
        ciphertext: str,
        passphrase: Optional[str] = None,
    ) -> Tuple[bool, str, VerifyResult, str]:
        """Decrypt text and extract signature status if present."""
        args = ["--status-fd", "2", "--decrypt", "--yes"]
        code, out, err = self._run(args, input_data=ciphertext, passphrase=passphrase or None)
        verify_res = self._parse_verify_output(err)
        if code == 0:
            return True, out, verify_res, ""
        return False, "", verify_res, err or "Decryption failed."

    def encrypt_file(
        self,
        src_path: str,
        dest_path: str,
        recipient_ids: Optional[List[str]] = None,
        sign_key_id: Optional[str] = None,
        sign_passphrase: Optional[str] = None,
        symmetric: bool = False,
        symmetric_passphrase: Optional[str] = None,
        cipher_algo: Optional[str] = None,
        armor: bool = True,
    ) -> Tuple[bool, str]:
        """Encrypt a file."""
        if not os.path.isfile(src_path):
            return False, f"Source file does not exist: {src_path}"
        if not recipient_ids and not symmetric:
            return False, "No recipients selected and symmetric encryption not chosen."

        run_passphrase: Optional[str] = None
        args = ["--yes", "-o", dest_path]
        if armor:
            args.append("--armor")
        if cipher_algo:
            args.extend(["--cipher-algo", cipher_algo])

        if symmetric:
            args.append("--symmetric")
            if symmetric_passphrase:
                run_passphrase = symmetric_passphrase

        if recipient_ids:
            args.extend(["--encrypt", "--trust-model", "always"])
            for r in recipient_ids:
                args.extend(["-r", r])

        if sign_key_id:
            args.extend(["--sign", "--local-user", sign_key_id])
            if sign_passphrase and not (symmetric and symmetric_passphrase):
                run_passphrase = sign_passphrase

        args.append(src_path)
        code, _, err = self._run(args, passphrase=run_passphrase)
        if code == 0:
            return True, f"File encrypted successfully to {dest_path}"
        return False, err or "File encryption failed."

    def decrypt_file(
        self,
        src_path: str,
        dest_path: str,
        passphrase: Optional[str] = None,
    ) -> Tuple[bool, VerifyResult, str]:
        """Decrypt a file."""
        if not os.path.isfile(src_path):
            return False, VerifyResult(valid=False, status="ERROR"), f"Source file does not exist: {src_path}"

        args = ["--status-fd", "2", "--decrypt", "--yes", "-o", dest_path]
        args.append(src_path)

        code, _, err = self._run(args, passphrase=passphrase or None)
        verify_res = self._parse_verify_output(err)
        if code == 0:
            return True, verify_res, f"File decrypted successfully to {dest_path}"
        return False, verify_res, err or "File decryption failed."

    def clearsign_text(
        self,
        plaintext: str,
        sign_key_id: str,
        passphrase: Optional[str] = None,
    ) -> Tuple[bool, str, str]:
        """Clearsign text message."""
        args = ["--armor", "--local-user", sign_key_id, "--clear-sign", "--yes"]
        code, out, err = self._run(args, input_data=plaintext, passphrase=passphrase or None)
        if code == 0:
            return True, out, ""
        return False, "", err or "Clearsigning failed."

    def sign_file(
        self,
        src_path: str,
        dest_path: str,
        sign_key_id: str,
        passphrase: Optional[str] = None,
        detached: bool = True,
        armor: bool = True,
    ) -> Tuple[bool, str]:
        """Sign a file."""
        if not os.path.isfile(src_path):
            return False, f"Source file not found: {src_path}"

        args = ["--yes", "--local-user", sign_key_id, "-o", dest_path]
        if armor:
            args.append("--armor")
        if detached:
            args.append("--detach-sign")
        else:
            args.append("--clear-sign")
        args.append(src_path)

        code, _, err = self._run(args, passphrase=passphrase or None)
        if code == 0:
            return True, f"File signed successfully: {dest_path}"
        return False, err or "File signing failed."

    def verify_text(self, signed_text: str) -> Tuple[bool, VerifyResult]:
        """Verify signature in text."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write(signed_text)
            temp_path = f.name

        try:
            code, out, err = self._run(["--status-fd", "2", "--verify", temp_path])
            res = self._parse_verify_output(err)
            res.raw_output = err + "\n" + out
            return (code == 0 and res.valid), res
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def verify_file(self, data_or_sig_path: str, data_path: Optional[str] = None) -> Tuple[bool, VerifyResult]:
        """Verify signature for file(s)."""
        args = ["--status-fd", "2", "--verify", data_or_sig_path]
        if data_path:
            args.append(data_path)

        code, out, err = self._run(args)
        res = self._parse_verify_output(err)
        res.raw_output = err + "\n" + out
        return (code == 0 and res.valid), res

    def _parse_verify_output(self, stderr_text: str) -> VerifyResult:
        """Parses machine-readable GPG status tokens."""
        valid = False
        status = "NO_SIG"
        signer_uid = ""
        key_id = ""
        fingerprint = ""
        timestamp = None
        trust = "Unknown"
        summary = ""

        for line in stderr_text.splitlines():
            if line.startswith("[GNUPG:] GOODSIG"):
                parts = line.split(maxsplit=3)
                if len(parts) >= 3:
                    key_id = parts[2]
                if len(parts) >= 4:
                    signer_uid = parts[3]
                valid = True
                status = "GOOD"
            elif line.startswith("[GNUPG:] VALIDSIG"):
                parts = line.split()
                if len(parts) >= 3:
                    fingerprint = parts[2]
                if len(parts) >= 4 and parts[3].isdigit():
                    timestamp = self._parse_timestamp(parts[3])
                valid = True
                status = "GOOD"
            elif line.startswith("[GNUPG:] BADSIG"):
                parts = line.split(maxsplit=3)
                if len(parts) >= 3:
                    key_id = parts[2]
                if len(parts) >= 4:
                    signer_uid = parts[3]
                valid = False
                status = "BAD"
            elif line.startswith("[GNUPG:] ERRSIG") or line.startswith("[GNUPG:] NO_PUBKEY"):
                parts = line.split()
                if len(parts) >= 3:
                    key_id = parts[2]
                valid = False
                status = "NO_KEY"
            elif line.startswith("[GNUPG:] EXPKEYSIG"):
                valid = False
                status = "EXPIRED"
            elif line.startswith("[GNUPG:] TRUST_ULTIMATE"):
                trust = "Ultimate"
            elif line.startswith("[GNUPG:] TRUST_FULLY"):
                trust = "Full"
            elif line.startswith("[GNUPG:] TRUST_MARGINAL"):
                trust = "Marginal"
            elif line.startswith("[GNUPG:] TRUST_UNDEFINED") or line.startswith("[GNUPG:] TRUST_NEVER"):
                trust = "Untrusted"

        if status == "GOOD":
            summary = f"Valid signature from '{signer_uid or key_id}'"
            if timestamp:
                summary += f" on {timestamp}"
        elif status == "BAD":
            summary = f"BAD signature from '{signer_uid or key_id}'! Data has been modified or corrupted."
        elif status == "NO_KEY":
            summary = f"Signature made by unknown key {key_id}. Public key not found in keyring."
        elif status == "EXPIRED":
            summary = f"Signature valid, but signing key {key_id} is expired."
        else:
            summary = "No signature found or verification error."

        return VerifyResult(
            valid=valid,
            status=status,
            signer_uid=signer_uid,
            key_id=key_id,
            fingerprint=fingerprint,
            timestamp=timestamp,
            trust=trust,
            summary=summary,
        )

    def get_system_info(self) -> Dict[str, Any]:
        """Returns GPG version, home, and supported algorithms."""
        info: Dict[str, Any] = {
            "binary": self.gpg_binary,
            "version": "Unknown",
            "home": "Unknown",
            "pubkey_algos": [],
            "ciphers": [],
            "hashes": [],
        }

        code, out, _ = self._run(["--version"])
        if code == 0:
            lines = out.splitlines()
            if lines:
                info["version"] = lines[0].replace("gpg (GnuPG)", "").strip()
            for line in lines:
                if line.startswith("Home:"):
                    info["home"] = line.replace("Home:", "").strip()
                elif line.startswith("Pubkey:"):
                    info["pubkey_algos"] = [
                        x.strip() for x in line.replace("Pubkey:", "").split(",") if x.strip()
                    ]
                elif line.startswith("Cipher:"):
                    info["ciphers"] = [
                        x.strip() for x in line.replace("Cipher:", "").split(",") if x.strip()
                    ]
                elif line.startswith("Hash:"):
                    info["hashes"] = [
                        x.strip() for x in line.replace("Hash:", "").split(",") if x.strip()
                    ]

        if self.gnupg_home:
            info["home"] = f"{self.gnupg_home} (Custom)"
        elif info["home"] == "Unknown":
            info["home"] = os.path.expanduser("~/.gnupg")

        return info
