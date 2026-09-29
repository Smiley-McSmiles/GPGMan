"""
Messages View - Text Encryption and Decryption with PGP Armor and Cipher Selection.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from gpgman.gpg_backend import GPGBackend, GPGKey, VerifyResult
from gpgman.ui.file_chooser import choose_file

if TYPE_CHECKING:
    from gpgman.ui.window import MainWindow


class MessagesView(Gtk.Box):
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

        # Tab 1: Encrypt
        self.encrypt_box = self._build_encrypt_tab()
        self.view_stack.add_titled(self.encrypt_box, "encrypt", "Encrypt Message")

        # Tab 2: Decrypt
        self.decrypt_box = self._build_decrypt_tab()
        self.view_stack.add_titled(self.decrypt_box, "decrypt", "Decrypt Message")

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

        # 1. Plaintext input group
        text_group = Adw.PreferencesGroup(
            title="Plaintext Message",
            description="Enter or paste the message you want to encrypt.",
        )
        
        tools_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        paste_btn = Gtk.Button(label="Paste", icon_name="edit-paste-symbolic")
        paste_btn.add_css_class("flat")
        paste_btn.connect("clicked", lambda _: self._paste_into(self.encrypt_input_tv))
        tools_box.append(paste_btn)

        clear_btn = Gtk.Button(label="Clear", icon_name="edit-clear-symbolic")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", lambda _: self.encrypt_input_tv.get_buffer().set_text(""))
        tools_box.append(clear_btn)
        text_group.set_header_suffix(tools_box)

        input_scroll = Gtk.ScrolledWindow()
        input_scroll.set_min_content_height(140)
        self.encrypt_input_tv = Gtk.TextView()
        self.encrypt_input_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.encrypt_input_tv.set_top_margin(8)
        self.encrypt_input_tv.set_bottom_margin(8)
        self.encrypt_input_tv.set_left_margin(10)
        self.encrypt_input_tv.set_right_margin(10)
        self.encrypt_input_tv.add_css_class("card")
        input_scroll.set_child(self.encrypt_input_tv)
        text_group.add(input_scroll)
        box.append(text_group)

        # 2. Encryption Type & Algorithm Settings
        enc_type_group = Adw.PreferencesGroup(
            title="Encryption Type &amp; Cipher",
            description="Select how to encrypt the message (Public Key, Password/Symmetric, or Both).",
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
            "AES-256 (Default, Recommended High Security)",
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

        # 3. Recipient selection group
        self.recip_group = Adw.PreferencesGroup(
            title="Recipients",
            description="Select public keys of the recipients who can decrypt this message.",
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

        # Search bar: Above the list of recipients, below Select All
        self.recip_search_entry = Gtk.SearchEntry(
            placeholder_text="Search recipients by name, email, or key ID...",
        )
        self.recip_search_entry.set_margin_bottom(8)
        self.recip_search_entry.connect("search-changed", self._on_recip_search_changed)
        self.recip_group.add(self.recip_search_entry)

        recip_scroll = Gtk.ScrolledWindow()
        recip_scroll.set_min_content_height(140)
        recip_scroll.set_max_content_height(260)
        recip_scroll.set_propagate_natural_height(True)

        self.recipients_list_box = Gtk.ListBox()
        self.recipients_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.recipients_list_box.add_css_class("boxed-list")
        self.recipients_list_box.set_filter_func(self._filter_recipient_row)
        recip_scroll.set_child(self.recipients_list_box)
        self.recip_group.add(recip_scroll)
        box.append(self.recip_group)

        # 4. Optional signing group
        sign_group = Adw.PreferencesGroup(title="Digital Signature (Optional)")
        
        self.sign_key_combo = Adw.ComboRow(title="Sign with Private Key")
        self.sign_key_combo.connect("notify::selected-item", self._on_sign_key_changed)
        sign_group.add(self.sign_key_combo)

        self.sign_pass_entry = Adw.PasswordEntryRow(title="Signing Passphrase (if key is protected)")
        self.sign_pass_entry.set_visible(False)
        sign_group.add(self.sign_pass_entry)

        box.append(sign_group)

        # 5. Encrypt action button
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        self.encrypt_action_btn = Gtk.Button(label="Encrypt Message", icon_name="channel-secure-symbolic")
        self.encrypt_action_btn.add_css_class("suggested-action")
        self.encrypt_action_btn.add_css_class("pill")
        self.encrypt_action_btn.set_size_request(220, 48)
        self.encrypt_action_btn.connect("clicked", self._on_encrypt_clicked)
        act_box.append(self.encrypt_action_btn)
        box.append(act_box)

        # 6. Output group
        out_group = Adw.PreferencesGroup(title="Encrypted Output (ASCII Armor)")
        out_ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        
        copy_out_btn = Gtk.Button(label="Copy", icon_name="edit-copy-symbolic")
        copy_out_btn.add_css_class("flat")
        copy_out_btn.connect("clicked", lambda _: self._copy_from(self.encrypt_output_tv))
        out_ctrl_box.append(copy_out_btn)

        save_out_btn = Gtk.Button(label="Save...", icon_name="document-save-symbolic")
        save_out_btn.add_css_class("flat")
        save_out_btn.connect("clicked", self._on_save_encrypted_output)
        out_ctrl_box.append(save_out_btn)
        out_group.set_header_suffix(out_ctrl_box)

        out_scroll = Gtk.ScrolledWindow()
        out_scroll.set_min_content_height(180)
        self.encrypt_output_tv = Gtk.TextView()
        self.encrypt_output_tv.set_monospace(True)
        self.encrypt_output_tv.set_wrap_mode(Gtk.WrapMode.NONE)
        self.encrypt_output_tv.set_editable(False)
        self.encrypt_output_tv.set_top_margin(8)
        self.encrypt_output_tv.set_bottom_margin(8)
        self.encrypt_output_tv.set_left_margin(10)
        self.encrypt_output_tv.set_right_margin(10)
        self.encrypt_output_tv.add_css_class("card")
        out_scroll.set_child(self.encrypt_output_tv)
        out_group.add(out_scroll)
        box.append(out_group)

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

        # 1. Ciphertext input group
        in_group = Adw.PreferencesGroup(
            title="Encrypted PGP Message",
            description="Paste the ASCII armored PGP message block (including -----BEGIN PGP MESSAGE-----).",
        )
        
        in_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        paste_btn = Gtk.Button(label="Paste", icon_name="edit-paste-symbolic")
        paste_btn.add_css_class("flat")
        paste_btn.connect("clicked", lambda _: self._paste_into(self.decrypt_input_tv))
        in_tools.append(paste_btn)

        open_file_btn = Gtk.Button(label="Open File...", icon_name="document-open-symbolic")
        open_file_btn.add_css_class("flat")
        open_file_btn.connect("clicked", self._on_load_ciphertext_file)
        in_tools.append(open_file_btn)

        clear_btn = Gtk.Button(label="Clear", icon_name="edit-clear-symbolic")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", lambda _: self.decrypt_input_tv.get_buffer().set_text(""))
        in_tools.append(clear_btn)
        in_group.set_header_suffix(in_tools)

        in_scroll = Gtk.ScrolledWindow()
        in_scroll.set_min_content_height(160)
        self.decrypt_input_tv = Gtk.TextView()
        self.decrypt_input_tv.set_monospace(True)
        self.decrypt_input_tv.set_wrap_mode(Gtk.WrapMode.NONE)
        self.decrypt_input_tv.set_top_margin(8)
        self.decrypt_input_tv.set_bottom_margin(8)
        self.decrypt_input_tv.set_left_margin(10)
        self.decrypt_input_tv.set_right_margin(10)
        self.decrypt_input_tv.add_css_class("card")
        in_scroll.set_child(self.decrypt_input_tv)
        in_group.add(in_scroll)
        box.append(in_group)

        # 2. Passphrase row for decryption
        pass_group = Adw.PreferencesGroup(title="Decryption Authorization")
        self.decrypt_pass_entry = Adw.PasswordEntryRow(title="Passphrase (if password-protected)")
        pass_group.add(self.decrypt_pass_entry)
        box.append(pass_group)

        # 3. Decrypt button
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        self.decrypt_action_btn = Gtk.Button(label="Decrypt Message", icon_name="channel-insecure-symbolic")
        self.decrypt_action_btn.add_css_class("suggested-action")
        self.decrypt_action_btn.add_css_class("pill")
        self.decrypt_action_btn.set_size_request(220, 48)
        self.decrypt_action_btn.connect("clicked", self._on_decrypt_clicked)
        act_box.append(self.decrypt_action_btn)
        box.append(act_box)

        # 4. Verification status box
        self.verify_status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.verify_status_box.add_css_class("card")
        self.verify_status_box.set_margin_top(4)
        self.verify_status_box.set_margin_bottom(4)
        self.verify_status_box.set_visible(False)

        self.verify_status_icon = Gtk.Image()
        self.verify_status_icon.set_pixel_size(24)
        self.verify_status_box.append(self.verify_status_icon)

        self.verify_status_label = Gtk.Label(wrap=True, halign=Gtk.Align.START, hexpand=True)
        self.verify_status_box.append(self.verify_status_label)
        box.append(self.verify_status_box)

        # 5. Decrypted Plaintext Output
        out_group = Adw.PreferencesGroup(title="Decrypted Plaintext")
        out_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)

        copy_btn = Gtk.Button(label="Copy", icon_name="edit-copy-symbolic")
        copy_btn.add_css_class("flat")
        copy_btn.connect("clicked", lambda _: self._copy_from(self.decrypt_output_tv))
        out_tools.append(copy_btn)

        save_btn = Gtk.Button(label="Save...", icon_name="document-save-symbolic")
        save_btn.add_css_class("flat")
        save_btn.connect("clicked", self._on_save_decrypted_output)
        out_tools.append(save_btn)
        out_group.set_header_suffix(out_tools)

        out_scroll = Gtk.ScrolledWindow()
        out_scroll.set_min_content_height(160)
        self.decrypt_output_tv = Gtk.TextView()
        self.decrypt_output_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.decrypt_output_tv.set_editable(False)
        self.decrypt_output_tv.set_top_margin(8)
        self.decrypt_output_tv.set_bottom_margin(8)
        self.decrypt_output_tv.set_left_margin(10)
        self.decrypt_output_tv.set_right_margin(10)
        self.decrypt_output_tv.add_css_class("card")
        out_scroll.set_child(self.decrypt_output_tv)
        out_group.add(out_scroll)
        box.append(out_group)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        return scrolled

    # --------------------------------------------------------------------------
    # CONTROLS VISIBILITY
    # --------------------------------------------------------------------------
    def _on_enc_type_changed(self, combo: Adw.ComboRow, _):
        idx = combo.get_selected()
        # 0: Asymmetric, 1: Symmetric, 2: Both
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
    # DATA & KEY RELOADING
    # --------------------------------------------------------------------------
    def reload_keys(self):
        try:
            all_keys = self.backend.list_keys()
            self.public_keys = all_keys
            # Filter secret keys that have signing capability
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
            title = k.display_name
            row.set_title(GLib.markup_escape_text(title))
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
        items = ["Do not sign (Encryption only)"]
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
        selected = []
        for key_id, chk in self.recipient_checkboxes.items():
            if chk.get_active():
                selected.append(key_id)
        return selected

    # --------------------------------------------------------------------------
    # ENCRYPT ACTION
    # --------------------------------------------------------------------------
    def _on_encrypt_clicked(self, _):
        buf = self.encrypt_input_tv.get_buffer()
        start, end = buf.get_bounds()
        plaintext = buf.get_text(start, end, True)

        if not plaintext.strip():
            self.window.show_toast("Please enter a message to encrypt.")
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

        success, ciphertext, err = self.backend.encrypt_text(
            plaintext=plaintext,
            recipient_ids=recipients if use_public else None,
            sign_key_id=sign_key_id,
            sign_passphrase=sign_pass,
            symmetric=symmetric,
            symmetric_passphrase=sym_pass if symmetric else None,
            cipher_algo=cipher_algo,
            armor=True,
        )

        if success:
            self.encrypt_output_tv.get_buffer().set_text(ciphertext)
            self.window.show_toast("Message encrypted successfully!")
        else:
            hint = ""
            if "unusable secret key" in err.lower() or "inappropriate ioctl" in err.lower() or "bad passphrase" in err.lower():
                hint = "\n\nTip: The chosen signing key is protected with a passphrase. Please enter its password in the 'Signing Passphrase' field."

            dialog = Adw.MessageDialog(
                transient_for=self.window,
                heading="Encryption Failed",
                body=f"{err}{hint}",
            )
            dialog.add_response("ok", "OK")
            dialog.present()

    # --------------------------------------------------------------------------
    # DECRYPT ACTION
    # --------------------------------------------------------------------------
    def _on_decrypt_clicked(self, _):
        buf = self.decrypt_input_tv.get_buffer()
        start, end = buf.get_bounds()
        ciphertext = buf.get_text(start, end, True).strip()

        if not ciphertext:
            self.window.show_toast("Please paste encrypted text to decrypt.")
            return

        passphrase = self.decrypt_pass_entry.get_text() or None

        success, plaintext, verify_res, err = self.backend.decrypt_text(
            ciphertext=ciphertext,
            passphrase=passphrase,
        )

        if success:
            self.decrypt_output_tv.get_buffer().set_text(plaintext)
            self._update_verify_banner(verify_res)
            self.window.show_toast("Message decrypted successfully!")
        else:
            self.verify_status_box.set_visible(False)
            hint = ""
            if "bad session key" in err.lower() or "no secret key" in err.lower() or "passphrase" in err.lower():
                hint = "\n\nTip: If this message requires a password or secret key passphrase, enter it in the 'Passphrase' field above and try again."

            dialog = Adw.MessageDialog(
                transient_for=self.window,
                heading="Decryption Failed",
                body=f"Failed to decrypt message:\n{err}{hint}",
            )
            dialog.add_response("ok", "OK")
            dialog.present()

    def _update_verify_banner(self, verify_res: VerifyResult):
        self.verify_status_box.set_visible(True)
        # Clear existing classes
        for c in ["success-banner", "error-banner", "warning-banner", "info-banner"]:
            self.verify_status_box.remove_css_class(c)

        if verify_res.status == "GOOD":
            self.verify_status_box.add_css_class("success-banner")
            self.verify_status_icon.set_from_icon_name("emblem-ok-symbolic")
            self.verify_status_label.set_text(
                f"Valid Signature by: {verify_res.signer_uid or verify_res.key_id} (Trust: {verify_res.trust})"
            )
        elif verify_res.status == "BAD":
            self.verify_status_box.add_css_class("error-banner")
            self.verify_status_icon.set_from_icon_name("dialog-error-symbolic")
            self.verify_status_label.set_text(
                f"BAD SIGNATURE: Data altered or signature forged! ({verify_res.signer_uid or verify_res.key_id})"
            )
        elif verify_res.status == "NO_KEY":
            self.verify_status_box.add_css_class("warning-banner")
            self.verify_status_icon.set_from_icon_name("dialog-warning-symbolic")
            self.verify_status_label.set_text(
                f"Message was signed, but signer key {verify_res.key_id} is not in your keyring."
            )
        else:
            self.verify_status_box.add_css_class("info-banner")
            self.verify_status_icon.set_from_icon_name("dialog-information-symbolic")
            self.verify_status_label.set_text("Decrypted successfully. (Message was not signed)")

    # --------------------------------------------------------------------------
    # HELPERS: Clipboard & Files
    # --------------------------------------------------------------------------
    def _paste_into(self, text_view: Gtk.TextView):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_text_async(None, lambda c, res: self._finish_paste(text_view, c, res))

    def _finish_paste(self, text_view: Gtk.TextView, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                text_view.get_buffer().set_text(text)
        except Exception:
            pass

    def _copy_from(self, text_view: Gtk.TextView):
        buf = text_view.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True)
        if text:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
            self.window.show_toast("Copied to clipboard.")

    def _on_save_encrypted_output(self, _):
        buf = self.encrypt_output_tv.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True)
        if not text.strip():
            return
        self._prompt_save_file("encrypted_message.asc", text)

    def _on_save_decrypted_output(self, _):
        buf = self.decrypt_output_tv.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True)
        if not text.strip():
            return
        self._prompt_save_file("decrypted_message.txt", text)

    def _on_load_ciphertext_file(self, _):
        def on_selected(path: str):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    self.decrypt_input_tv.get_buffer().set_text(f.read())
            except Exception as e:
                self.window.show_toast(f"Error opening file: {e}")

        choose_file(
            parent=self.window,
            title="Open Encrypted Message File",
            action=Gtk.FileChooserAction.OPEN,
            filters=[
                ("Encrypted PGP Files (*.asc, *.gpg, *.pgp, *.txt)", ["*.asc", "*.gpg", "*.pgp", "*.txt"]),
                ("All Files", ["*"]),
            ],
            on_selected=on_selected,
        )

    def _prompt_save_file(self, default_name: str, content: str):
        def on_selected(path: str):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.window.show_toast(f"Saved to {os.path.basename(path)}")
            except Exception as e:
                self.window.show_toast(f"Save failed: {e}")

        choose_file(
            parent=self.window,
            title="Save File",
            action=Gtk.FileChooserAction.SAVE,
            default_name=default_name,
            on_selected=on_selected,
        )
