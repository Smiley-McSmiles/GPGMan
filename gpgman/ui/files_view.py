"""
Files View - File Encryption and Decryption with GPG.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from gpgman.gpg_backend import GPGBackend, GPGKey, VerifyResult
from gpgman.ui.file_chooser import choose_file

if TYPE_CHECKING:
    from gpgman.ui.window import MainWindow


class FilesView(Gtk.Box):
    def __init__(self, backend: GPGBackend, window: MainWindow):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.backend = backend
        self.window = window
        self.public_keys: List[GPGKey] = []
        self.signing_keys: List[GPGKey] = []

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._build_ui()
        self.reload_keys()

    def _build_ui(self):
        # View switcher for Encrypt / Decrypt
        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)

        switcher_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        switcher = Adw.ViewSwitcher(
            stack=self.view_stack,
            policy=Adw.ViewSwitcherPolicy.WIDE,
        )
        switcher_bar.append(switcher)
        self.append(switcher_bar)

        # Tab 1: Encrypt File
        self.encrypt_box = self._build_encrypt_tab()
        self.view_stack.add_titled(self.encrypt_box, "encrypt", "Encrypt File")

        # Tab 2: Decrypt File
        self.decrypt_box = self._build_decrypt_tab()
        self.view_stack.add_titled(self.decrypt_box, "decrypt", "Decrypt File")

        self.append(self.view_stack)

    # --------------------------------------------------------------------------
    # ENCRYPT TAB
    # --------------------------------------------------------------------------
    def _build_encrypt_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=860)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(8)
        box.set_margin_bottom(24)

        # 1. Source File Selection
        src_group = Adw.PreferencesGroup(
            title="Source File",
            description="Select the file you want to encrypt.",
        )
        
        src_row = Adw.ActionRow(title="File to Encrypt")
        self.src_file_label = Gtk.Label(label="No file selected", halign=Gtk.Align.START, hexpand=True)
        self.src_file_label.set_ellipsize(3)
        src_row.set_subtitle("Choose a file from your system")

        browse_src_btn = Gtk.Button(label="Browse...", icon_name="document-open-symbolic", valign=Gtk.Align.CENTER)
        browse_src_btn.connect("clicked", self._on_browse_encrypt_src)
        src_row.add_suffix(browse_src_btn)
        src_group.add(src_row)
        box.append(src_group)

        # 2. Encryption Type & Algorithm Settings
        enc_type_group = Adw.PreferencesGroup(
            title="Encryption Type &amp; Cipher",
            description="Choose how to protect the file.",
        )

        type_model = Gtk.StringList.new([
            "Recipient Public Key(s) (Asymmetric)",
            "Password / Passphrase Only (Symmetric - no keys needed)",
            "Both (Public Keys + Passphrase Fallback)",
        ])
        self.enc_type_combo = Adw.ComboRow(title="Encryption Method", model=type_model)
        self.enc_type_combo.connect("notify::selected-item", self._on_enc_type_changed)
        enc_type_group.add(self.enc_type_combo)

        cipher_model = Gtk.StringList.new([
            "AES-256 (Default, High Security)",
            "AES-192",
            "AES-128",
            "TWOFISH (256-bit)",
            "CAMELLIA256",
            "3DES (Triple DES)",
        ])
        self.cipher_combo = Adw.ComboRow(title="Cipher Algorithm", model=cipher_model)
        enc_type_group.add(self.cipher_combo)

        self.sym_pass_entry = Adw.PasswordEntryRow(title="Encryption Passphrase")
        self.sym_pass_entry.set_visible(False)
        enc_type_group.add(self.sym_pass_entry)

        box.append(enc_type_group)

        # 3. Recipients Selection
        self.recip_group = Adw.PreferencesGroup(
            title="Recipients",
            description="Select public keys that can decrypt this file.",
        )

        recip_ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        sel_all_btn = Gtk.Button(label="Select All")
        sel_all_btn.add_css_class("flat")
        sel_all_btn.connect("clicked", lambda _: self._set_all_recipients(True))
        recip_ctrl_box.append(sel_all_btn)

        desel_all_btn = Gtk.Button(label="Deselect All")
        desel_all_btn.add_css_class("flat")
        desel_all_btn.connect("clicked", lambda _: self._set_all_recipients(False))
        recip_ctrl_box.append(desel_all_btn)
        self.recip_group.set_header_suffix(recip_ctrl_box)

        # Search bar above list of recipients, below Select All
        self.recip_search_entry = Gtk.SearchEntry(
            placeholder_text="Search recipients by name, email, or key ID...",
        )
        self.recip_search_entry.set_margin_bottom(8)
        self.recip_search_entry.connect("search-changed", self._on_recip_search_changed)
        self.recip_group.add(self.recip_search_entry)

        recip_scroll = Gtk.ScrolledWindow()
        recip_scroll.set_min_content_height(140)
        recip_scroll.set_max_content_height(240)
        recip_scroll.set_propagate_natural_height(True)

        self.recipients_list_box = Gtk.ListBox()
        self.recipients_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.recipients_list_box.add_css_class("boxed-list")
        self.recipients_list_box.set_filter_func(self._filter_recipient_row)
        recip_scroll.set_child(self.recipients_list_box)
        self.recip_group.add(recip_scroll)
        box.append(self.recip_group)

        # 4. Encryption Options & Destination
        opt_group = Adw.PreferencesGroup(title="Options &amp; Destination")

        # Output format
        format_model = Gtk.StringList.new(["ASCII Armored (.asc) - Text / Portable", "Binary OpenPGP (.gpg) - Compact"])
        self.format_combo = Adw.ComboRow(title="Output Format", model=format_model)
        self.format_combo.connect("notify::selected-item", self._on_format_changed)
        opt_group.add(self.format_combo)

        # Sign with key
        self.sign_key_combo = Adw.ComboRow(title="Digital Signature (Optional)")
        self.sign_key_combo.connect("notify::selected-item", self._on_sign_key_changed)
        opt_group.add(self.sign_key_combo)

        self.sign_pass_entry = Adw.PasswordEntryRow(title="Signing Passphrase (if key is protected)")
        self.sign_pass_entry.set_visible(False)
        opt_group.add(self.sign_pass_entry)

        # Destination file row
        self.dest_row = Adw.ActionRow(title="Output File Destination", subtitle="Auto-generated based on source file")
        dest_browse_btn = Gtk.Button(label="Change...", valign=Gtk.Align.CENTER)
        dest_browse_btn.connect("clicked", self._on_browse_encrypt_dest)
        self.dest_row.add_suffix(dest_browse_btn)
        opt_group.add(self.dest_row)

        box.append(opt_group)

        # 5. Action button
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        self.encrypt_btn = Gtk.Button(label="Encrypt File", icon_name="channel-secure-symbolic")
        self.encrypt_btn.add_css_class("suggested-action")
        self.encrypt_btn.add_css_class("pill")
        self.encrypt_btn.set_size_request(220, 48)
        self.encrypt_btn.connect("clicked", self._on_encrypt_file_clicked)
        act_box.append(self.encrypt_btn)
        box.append(act_box)

        # 6. Encrypt result status
        self.encrypt_result_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.encrypt_result_box.add_css_class("card")
        self.encrypt_result_box.add_css_class("success-banner")
        self.encrypt_result_box.set_visible(False)

        res_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        res_icon.set_pixel_size(24)
        self.encrypt_result_box.append(res_icon)

        self.encrypt_result_label = Gtk.Label(wrap=True, halign=Gtk.Align.START, hexpand=True)
        self.encrypt_result_box.append(self.encrypt_result_label)
        box.append(self.encrypt_result_box)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        return scrolled

    # --------------------------------------------------------------------------
    # DECRYPT TAB
    # --------------------------------------------------------------------------
    def _build_decrypt_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=860)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(8)
        box.set_margin_bottom(24)

        # 1. Source Encrypted File
        src_group = Adw.PreferencesGroup(
            title="Encrypted File",
            description="Select the encrypted file (.asc, .gpg, .pgp) to decrypt.",
        )

        self.decrypt_src_row = Adw.ActionRow(title="Encrypted Source File", subtitle="No file selected")
        browse_btn = Gtk.Button(label="Browse...", icon_name="document-open-symbolic", valign=Gtk.Align.CENTER)
        browse_btn.connect("clicked", self._on_browse_decrypt_src)
        self.decrypt_src_row.add_suffix(browse_btn)
        src_group.add(self.decrypt_src_row)
        box.append(src_group)

        # 2. Passphrase row for file decryption
        pass_group = Adw.PreferencesGroup(title="Decryption Authorization")
        self.decrypt_pass_entry = Adw.PasswordEntryRow(title="Passphrase (if password-protected)")
        pass_group.add(self.decrypt_pass_entry)
        box.append(pass_group)

        # 3. Destination
        dest_group = Adw.PreferencesGroup(title="Decrypted Output Destination")
        self.decrypt_dest_row = Adw.ActionRow(title="Save Decrypted File To", subtitle="Auto-generated from source file")
        dest_btn = Gtk.Button(label="Change...", valign=Gtk.Align.CENTER)
        dest_btn.connect("clicked", self._on_browse_decrypt_dest)
        self.decrypt_dest_row.add_suffix(dest_btn)
        dest_group.add(self.decrypt_dest_row)
        box.append(dest_group)

        # 4. Decrypt Action Button
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        self.decrypt_btn = Gtk.Button(label="Decrypt File", icon_name="channel-insecure-symbolic")
        self.decrypt_btn.add_css_class("suggested-action")
        self.decrypt_btn.add_css_class("pill")
        self.decrypt_btn.set_size_request(220, 48)
        self.decrypt_btn.connect("clicked", self._on_decrypt_file_clicked)
        act_box.append(self.decrypt_btn)
        box.append(act_box)

        # 5. Decrypt Result Box
        self.decrypt_result_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.decrypt_result_box.add_css_class("card")
        self.decrypt_result_box.set_visible(False)

        self.decrypt_result_icon = Gtk.Image()
        self.decrypt_result_icon.set_pixel_size(24)
        self.decrypt_result_box.append(self.decrypt_result_icon)

        self.decrypt_result_label = Gtk.Label(wrap=True, halign=Gtk.Align.START, hexpand=True)
        self.decrypt_result_box.append(self.decrypt_result_label)
        box.append(self.decrypt_result_box)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        return scrolled

    # --------------------------------------------------------------------------
    # CONTROLS VISIBILITY
    # --------------------------------------------------------------------------
    def _on_enc_type_changed(self, combo: Adw.ComboRow, _):
        idx = combo.get_selected()
        if idx == 1:
            self.recip_group.set_visible(False)
            self.sym_pass_entry.set_visible(True)
        elif idx == 2:
            self.recip_group.set_visible(True)
            self.sym_pass_entry.set_visible(True)
        else:
            self.recip_group.set_visible(True)
            self.sym_pass_entry.set_visible(False)

    def _on_sign_key_changed(self, combo: Adw.ComboRow, _):
        idx = combo.get_selected()
        self.sign_pass_entry.set_visible(idx > 0)

    # --------------------------------------------------------------------------
    # DATA RELOAD
    # --------------------------------------------------------------------------
    def reload_keys(self):
        try:
            all_keys = self.backend.list_keys()
            self.public_keys = all_keys
            self.signing_keys = [
                k for k in all_keys
                if k.is_secret and ("Sign" in k.capabilities or not k.capabilities)
            ]
        except Exception:
            self.public_keys = []
            self.signing_keys = []

        self._populate_recipients()
        self._populate_signing_keys()

    def _populate_recipients(self):
        while child := self.recipients_list_box.get_first_child():
            self.recipients_list_box.remove(child)

        self.recipient_checkboxes: Dict[str, Gtk.CheckButton] = {}

        if not self.public_keys:
            row = Adw.ActionRow(title="No public keys found in keyring.")
            self.recipients_list_box.append(row)
            return

        for k in self.public_keys:
            row = Adw.ActionRow()
            row.set_title(GLib.markup_escape_text(k.display_name))
            row.set_subtitle(f"ID: {k.key_id} • {k.algo} {k.length}b")
            row._gpg_key = k

            chk = Gtk.CheckButton()
            row.add_prefix(chk)
            row.set_activatable_widget(chk)

            self.recipient_checkboxes[k.key_id] = chk
            self.recipients_list_box.append(row)

        self.recipients_list_box.invalidate_filter()

    def _filter_recipient_row(self, row: Gtk.ListBoxRow) -> bool:
        if not hasattr(self, "recip_search_entry"):
            return True
        query = self.recip_search_entry.get_text().strip().lower()
        if not query:
            return True
        key = getattr(row, "_gpg_key", None)
        if not key:
            return True
        searchable = f"{key.display_name} {key.name} {key.email} {key.comment} {key.key_id} {key.fingerprint}".lower()
        return query in searchable

    def _on_recip_search_changed(self, _entry: Gtk.SearchEntry):
        self.recipients_list_box.invalidate_filter()

    def _populate_signing_keys(self):
        items = ["Do not sign"]
        for k in self.signing_keys:
            items.append(f"{k.display_name} ({k.key_id})")

        model = Gtk.StringList.new(items)
        self.sign_key_combo.set_model(model)

    def _set_all_recipients(self, state: bool):
        query = self.recip_search_entry.get_text().strip().lower()
        for k in self.public_keys:
            if query:
                searchable = f"{k.display_name} {k.name} {k.email} {k.comment} {k.key_id} {k.fingerprint}".lower()
                if query not in searchable:
                    continue
            chk = self.recipient_checkboxes.get(k.key_id)
            if chk:
                chk.set_active(state)

    def _get_selected_recipients(self) -> List[str]:
        return [k for k, chk in self.recipient_checkboxes.items() if chk.get_active()]

    # --------------------------------------------------------------------------
    # ENCRYPT HANDLERS
    # --------------------------------------------------------------------------
    def _on_browse_encrypt_src(self, _):
        def on_selected(path: str):
            self.src_file_path = path
            self.src_file_label.set_text(path)
            ext = ".asc" if self.format_combo.get_selected() == 0 else ".gpg"
            self.dest_file_path = f"{path}{ext}"
            self.dest_row.set_subtitle(self.dest_file_path)

        choose_file(
            parent=self.window,
            title="Select File to Encrypt",
            action=Gtk.FileChooserAction.OPEN,
            filters=[("All Files", ["*"])],
            on_selected=on_selected,
        )

    def _on_browse_encrypt_dest(self, _):
        def on_selected(path: str):
            self.dest_file_path = path
            self.dest_row.set_subtitle(self.dest_file_path)

        default_name = None
        if hasattr(self, "dest_file_path") and self.dest_file_path:
            default_name = os.path.basename(self.dest_file_path)

        choose_file(
            parent=self.window,
            title="Select Output Destination",
            action=Gtk.FileChooserAction.SAVE,
            default_name=default_name,
            on_selected=on_selected,
        )

    def _on_format_changed(self, combo, _):
        if hasattr(self, "src_file_path") and self.src_file_path:
            ext = ".asc" if combo.get_selected() == 0 else ".gpg"
            base, _ = os.path.splitext(self.dest_file_path)
            if self.dest_file_path.endswith(".asc") or self.dest_file_path.endswith(".gpg"):
                self.dest_file_path = f"{base}{ext}"
            else:
                self.dest_file_path = f"{self.src_file_path}{ext}"
            self.dest_row.set_subtitle(self.dest_file_path)

    def _on_encrypt_file_clicked(self, _):
        if not hasattr(self, "src_file_path") or not self.src_file_path:
            self.window.show_toast("Please select a file to encrypt.")
            return

        enc_type = self.enc_type_combo.get_selected()
        symmetric = enc_type in (1, 2)
        use_public = enc_type in (0, 2)

        sym_pass = self.sym_pass_entry.get_text()
        if symmetric and not sym_pass:
            self.window.show_toast("Please enter an encryption passphrase.")
            return

        recipients = self._get_selected_recipients() if use_public else []
        if use_public and not recipients:
            self.window.show_toast("Please select at least one recipient key.")
            return

        cipher_map = {
            0: "AES256",
            1: "AES192",
            2: "AES",
            3: "TWOFISH",
            4: "CAMELLIA256",
            5: "3DES",
        }
        cipher_algo = cipher_map.get(self.cipher_combo.get_selected(), "AES256")

        sign_idx = self.sign_key_combo.get_selected()
        sign_key_id = None
        sign_pass = None
        if sign_idx > 0 and sign_idx - 1 < len(self.signing_keys):
            sign_key_id = self.signing_keys[sign_idx - 1].key_id
            sign_pass = self.sign_pass_entry.get_text() or None

        armor = self.format_combo.get_selected() == 0
        dest_path = getattr(self, "dest_file_path", f"{self.src_file_path}.{'asc' if armor else 'gpg'}")

        success, msg = self.backend.encrypt_file(
            src_path=self.src_file_path,
            dest_path=dest_path,
            recipient_ids=recipients if use_public else None,
            sign_key_id=sign_key_id,
            sign_passphrase=sign_pass,
            symmetric=symmetric,
            symmetric_passphrase=sym_pass if symmetric else None,
            cipher_algo=cipher_algo,
            armor=armor,
        )

        if success:
            self.encrypt_result_box.set_visible(True)
            self.encrypt_result_label.set_text(f"Encrypted successfully:\n{dest_path}")
            self.window.show_toast(f"Encrypted: {os.path.basename(dest_path)}")
        else:
            self.encrypt_result_box.set_visible(False)
            hint = ""
            if "unusable secret key" in msg.lower() or "inappropriate ioctl" in msg.lower() or "bad passphrase" in msg.lower():
                hint = "\n\nTip: The signing key requires a passphrase to unlock. Please enter its password in the 'Signing Passphrase' field."

            dialog = Adw.MessageDialog(
                transient_for=self.window,
                heading="Encryption Error",
                body=f"{msg}{hint}",
            )
            dialog.add_response("ok", "OK")
            dialog.present()

    # --------------------------------------------------------------------------
    # DECRYPT HANDLERS
    # --------------------------------------------------------------------------
    def _on_browse_decrypt_src(self, _):
        def on_selected(path: str):
            self.decrypt_src_path = path
            self.decrypt_src_row.set_subtitle(path)

            dest = path
            for ext in [".asc", ".gpg", ".pgp"]:
                if dest.lower().endswith(ext):
                    dest = dest[:-len(ext)]
                    break
            if dest == path:
                dest = f"{path}.decrypted"

            self.decrypt_dest_path = dest
            self.decrypt_dest_row.set_subtitle(dest)

        choose_file(
            parent=self.window,
            title="Select Encrypted File",
            action=Gtk.FileChooserAction.OPEN,
            filters=[
                ("Encrypted Files (*.asc, *.gpg, *.pgp)", ["*.asc", "*.gpg", "*.pgp"]),
                ("All Files", ["*"]),
            ],
            on_selected=on_selected,
        )

    def _on_browse_decrypt_dest(self, _):
        def on_selected(path: str):
            self.decrypt_dest_path = path
            self.decrypt_dest_row.set_subtitle(self.decrypt_dest_path)

        default_name = None
        if hasattr(self, "decrypt_dest_path") and self.decrypt_dest_path:
            default_name = os.path.basename(self.decrypt_dest_path)

        choose_file(
            parent=self.window,
            title="Select Decrypted File Destination",
            action=Gtk.FileChooserAction.SAVE,
            default_name=default_name,
            on_selected=on_selected,
        )

    def _on_decrypt_file_clicked(self, _):
        if not hasattr(self, "decrypt_src_path") or not self.decrypt_src_path:
            self.window.show_toast("Please select an encrypted file to decrypt.")
            return

        dest_path = getattr(self, "decrypt_dest_path", None)
        if not dest_path:
            self.window.show_toast("Please select an output destination.")
            return

        passphrase = self.decrypt_pass_entry.get_text() or None

        success, verify_res, msg = self.backend.decrypt_file(
            src_path=self.decrypt_src_path,
            dest_path=dest_path,
            passphrase=passphrase,
        )

        self.decrypt_result_box.set_visible(True)
        for c in ["success-banner", "error-banner", "warning-banner", "info-banner"]:
            self.decrypt_result_box.remove_css_class(c)

        if success:
            self.decrypt_result_box.add_css_class("success-banner")
            self.decrypt_result_icon.set_from_icon_name("emblem-ok-symbolic")
            res_text = f"Decrypted successfully to:\n{dest_path}"
            if verify_res.status == "GOOD":
                res_text += f"\n\nValid Signature from: {verify_res.signer_uid or verify_res.key_id}"
            elif verify_res.status == "BAD":
                res_text += f"\n\nWARNING: BAD SIGNATURE ({verify_res.signer_uid or verify_res.key_id})"
            self.decrypt_result_label.set_text(res_text)
            self.window.show_toast(f"Decrypted: {os.path.basename(dest_path)}")
        else:
            self.decrypt_result_box.add_css_class("error-banner")
            self.decrypt_result_icon.set_from_icon_name("dialog-error-symbolic")
            self.decrypt_result_label.set_text(f"Decryption failed:\n{msg}")
            hint = ""
            if "bad session key" in msg.lower() or "no secret key" in msg.lower() or "passphrase" in msg.lower():
                hint = "\n\nTip: If this file is password-protected or uses a protected key, enter the password in the 'Passphrase' field and try again."

            dialog = Adw.MessageDialog(
                transient_for=self.window,
                heading="Decryption Error",
                body=f"{msg}{hint}",
            )
            dialog.add_response("ok", "OK")
            dialog.present()

    def _format_size(self, size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
