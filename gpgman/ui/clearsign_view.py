"""
Clearsign & Verification View - Sign messages/files and verify digital signatures.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import threading
from typing import TYPE_CHECKING, Dict, List, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from gpgman.ui.caps_lock import attach_caps_lock_hint
from gpgman.gpg_backend import GPGBackend, GPGKey, VerifyResult
from gpgman.ui.file_chooser import choose_file

if TYPE_CHECKING:
    from gpgman.ui.window import MainWindow


class ClearsignView(Gtk.Box):
    def __init__(self, backend: GPGBackend, window: MainWindow):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.backend = backend
        self.window = window
        self.secret_keys: List[GPGKey] = []

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._build_ui()
        self.reload_keys()

    def _connect_enter(self, entry_widget, action_target):
        """Allow pressing Enter / Return inside the entry to trigger the action."""
        def _trigger(*_):
            if isinstance(action_target, str):
                cb = getattr(self, action_target, None)
            else:
                cb = getattr(self, action_target.__name__, action_target)
            if callable(cb):
                cb(None)

        entry_widget.connect("entry-activated", _trigger)
        ctrl = Gtk.EventControllerKey.new()
        def _on_key(c, keyval, keycode, state):
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                _trigger()
                return True
            return False
        ctrl.connect("key-pressed", _on_key)
        entry_widget.add_controller(ctrl)

    def _build_ui(self):
        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)

        switcher_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        switcher = Adw.ViewSwitcher(
            stack=self.view_stack,
            policy=Adw.ViewSwitcherPolicy.WIDE,
        )
        switcher_bar.append(switcher)
        self.append(switcher_bar)

        # Tab 1: Clearsign Message
        self.cs_msg_box = self._build_clearsign_text_tab()
        self.view_stack.add_titled(self.cs_msg_box, "cs_text", "Sign Text")

        # Tab 2: Sign File
        self.sign_file_box = self._build_sign_file_tab()
        self.view_stack.add_titled(self.sign_file_box, "sign_file", "Sign File")

        # Tab 3: Verify Text
        self.verify_text_box = self._build_verify_text_tab()
        self.view_stack.add_titled(self.verify_text_box, "verify_text", "Verify Text")

        # Tab 4: Verify File
        self.verify_file_box = self._build_verify_file_tab()
        self.view_stack.add_titled(self.verify_file_box, "verify_file", "Verify File")

        self.append(self.view_stack)

    # --------------------------------------------------------------------------
    # 1. CLEARSIGN TEXT TAB
    # --------------------------------------------------------------------------
    def _build_clearsign_text_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=860)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(8)
        box.set_margin_bottom(24)

        # Input group
        in_group = Adw.PreferencesGroup(
            title="Text to Sign",
            description="Enter the message you want to sign with an OpenPGP clearsigned block.",
        )
        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        paste_btn = Gtk.Button(label="Paste", icon_name="edit-paste-symbolic")
        paste_btn.add_css_class("flat")
        paste_btn.connect("clicked", lambda _: self._paste_into(self.cs_input_tv))
        tools.append(paste_btn)

        clear_btn = Gtk.Button(label="Clear", icon_name="edit-clear-symbolic")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", lambda _: self.cs_input_tv.get_buffer().set_text(""))
        tools.append(clear_btn)
        in_group.set_header_suffix(tools)

        in_scroll = Gtk.ScrolledWindow()
        in_scroll.set_min_content_height(140)
        self.cs_input_tv = Gtk.TextView()
        self.cs_input_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.cs_input_tv.set_top_margin(8)
        self.cs_input_tv.set_bottom_margin(8)
        self.cs_input_tv.set_left_margin(10)
        self.cs_input_tv.set_right_margin(10)
        self.cs_input_tv.add_css_class("card")
        in_scroll.set_child(self.cs_input_tv)
        in_group.add(in_scroll)
        box.append(in_group)

        # Signing Key group
        key_group = Adw.PreferencesGroup(title="Signing Key")
        self.cs_key_combo = Adw.ComboRow(title="Sign With")
        key_group.add(self.cs_key_combo)

        self.cs_pass_entry = Adw.PasswordEntryRow(title="Signing Passphrase (if password-protected)")

        attach_caps_lock_hint(self.cs_pass_entry)
        self._connect_enter(self.cs_pass_entry, self._on_clearsign_text_clicked)
        key_group.add(self.cs_pass_entry)
        box.append(key_group)

        # Action Button
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        cs_btn = Gtk.Button(label="Clearsign Message", icon_name="document-send-symbolic")
        cs_btn.add_css_class("suggested-action")
        cs_btn.add_css_class("pill")
        cs_btn.set_size_request(220, 48)
        cs_btn.connect("clicked", self._on_clearsign_text_clicked)
        act_box.append(cs_btn)
        box.append(act_box)

        # Output group
        out_group = Adw.PreferencesGroup(title="Clearsigned Output")
        out_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)

        copy_btn = Gtk.Button(label="Copy", icon_name="edit-copy-symbolic")
        copy_btn.add_css_class("flat")
        copy_btn.connect("clicked", lambda _: self._copy_from(self.cs_output_tv))
        out_tools.append(copy_btn)

        save_btn = Gtk.Button(label="Save...", icon_name="document-save-symbolic")
        save_btn.add_css_class("flat")
        save_btn.connect("clicked", self._on_save_cs_output)
        out_tools.append(save_btn)
        out_group.set_header_suffix(out_tools)

        out_scroll = Gtk.ScrolledWindow()
        out_scroll.set_min_content_height(180)
        self.cs_output_tv = Gtk.TextView()
        self.cs_output_tv.set_monospace(True)
        self.cs_output_tv.set_wrap_mode(Gtk.WrapMode.NONE)
        self.cs_output_tv.set_editable(False)
        self.cs_output_tv.set_top_margin(8)
        self.cs_output_tv.set_bottom_margin(8)
        self.cs_output_tv.set_left_margin(10)
        self.cs_output_tv.set_right_margin(10)
        self.cs_output_tv.add_css_class("card")
        out_scroll.set_child(self.cs_output_tv)
        out_group.add(out_scroll)
        box.append(out_group)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        return scrolled

    # --------------------------------------------------------------------------
    # 2. SIGN FILE TAB
    # --------------------------------------------------------------------------
    def _build_sign_file_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=860)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(8)
        box.set_margin_bottom(24)

        # Source File
        src_group = Adw.PreferencesGroup(title="File to Sign")
        self.sign_file_src_row = Adw.ActionRow(title="Select File", subtitle="No file selected")
        browse_btn = Gtk.Button(label="Browse...", icon_name="document-open-symbolic", valign=Gtk.Align.CENTER)
        browse_btn.connect("clicked", self._on_browse_sign_file)
        self.sign_file_src_row.add_suffix(browse_btn)
        src_group.add(self.sign_file_src_row)
        box.append(src_group)

        # Options
        opt_group = Adw.PreferencesGroup(title="Signing Options")
        self.sign_file_key_combo = Adw.ComboRow(title="Sign With Private Key")
        opt_group.add(self.sign_file_key_combo)

        self.sign_file_pass_entry = Adw.PasswordEntryRow(title="Signing Passphrase (if password-protected)")

        attach_caps_lock_hint(self.sign_file_pass_entry)
        self._connect_enter(self.sign_file_pass_entry, self._on_sign_file_clicked)
        opt_group.add(self.sign_file_pass_entry)

        sig_type_model = Gtk.StringList.new([
            "Detached ASCII Armored Signature (.asc)",
            "Clearsigned Document (.asc)",
        ])
        self.sign_file_type_combo = Adw.ComboRow(title="Signature Mode", model=sig_type_model)
        opt_group.add(self.sign_file_type_combo)

        self.sign_file_dest_row = Adw.ActionRow(title="Signature Output Path", subtitle="Auto-generated")
        dest_btn = Gtk.Button(label="Change...", valign=Gtk.Align.CENTER)
        dest_btn.connect("clicked", self._on_browse_sign_dest)
        self.sign_file_dest_row.add_suffix(dest_btn)
        opt_group.add(self.sign_file_dest_row)
        box.append(opt_group)

        # Action Button
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        sign_btn = Gtk.Button(label="Sign File", icon_name="document-send-symbolic")
        sign_btn.add_css_class("suggested-action")
        sign_btn.add_css_class("pill")
        sign_btn.set_size_request(220, 48)
        sign_btn.connect("clicked", self._on_sign_file_clicked)
        act_box.append(sign_btn)
        box.append(act_box)

        # Result box
        self.sign_file_res_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.sign_file_res_box.add_css_class("card")
        self.sign_file_res_box.add_css_class("success-banner")
        self.sign_file_res_box.set_visible(False)

        res_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        res_icon.set_pixel_size(24)
        self.sign_file_res_box.append(res_icon)

        self.sign_file_res_label = Gtk.Label(wrap=True, halign=Gtk.Align.START, hexpand=True)
        self.sign_file_res_box.append(self.sign_file_res_label)
        box.append(self.sign_file_res_box)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        return scrolled

    # --------------------------------------------------------------------------
    # 3. VERIFY TEXT TAB
    # --------------------------------------------------------------------------
    def _build_verify_text_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=860)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(8)
        box.set_margin_bottom(24)

        # Input group
        in_group = Adw.PreferencesGroup(
            title="Signed Message",
            description="Paste the clearsigned OpenPGP message block (including -----BEGIN PGP SIGNED MESSAGE-----).",
        )
        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        paste_btn = Gtk.Button(label="Paste", icon_name="edit-paste-symbolic")
        paste_btn.add_css_class("flat")
        paste_btn.connect("clicked", lambda _: self._paste_into(self.verify_input_tv))
        tools.append(paste_btn)

        open_btn = Gtk.Button(label="Open File...", icon_name="document-open-symbolic")
        open_btn.add_css_class("flat")
        open_btn.connect("clicked", self._on_load_verify_text_file)
        tools.append(open_btn)

        clear_btn = Gtk.Button(label="Clear", icon_name="edit-clear-symbolic")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", lambda _: self.verify_input_tv.get_buffer().set_text(""))
        tools.append(clear_btn)
        in_group.set_header_suffix(tools)

        in_scroll = Gtk.ScrolledWindow()
        in_scroll.set_min_content_height(160)
        self.verify_input_tv = Gtk.TextView()
        self.verify_input_tv.set_monospace(True)
        self.verify_input_tv.set_wrap_mode(Gtk.WrapMode.NONE)
        self.verify_input_tv.set_top_margin(8)
        self.verify_input_tv.set_bottom_margin(8)
        self.verify_input_tv.set_left_margin(10)
        self.verify_input_tv.set_right_margin(10)
        self.verify_input_tv.add_css_class("card")
        in_scroll.set_child(self.verify_input_tv)
        in_group.add(in_scroll)
        box.append(in_group)

        # Action Button
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        v_btn = Gtk.Button(label="Verify Signature", icon_name="security-high-symbolic")
        v_btn.add_css_class("suggested-action")
        v_btn.add_css_class("pill")
        v_btn.set_size_request(220, 48)
        v_btn.connect("clicked", self._on_verify_text_clicked)
        act_box.append(v_btn)
        box.append(act_box)

        # Result card
        self.verify_text_res_card = self._build_verify_result_card()
        box.append(self.verify_text_res_card)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        return scrolled

    # --------------------------------------------------------------------------
    # 4. VERIFY FILE TAB
    # --------------------------------------------------------------------------
    def _build_verify_file_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=860)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(8)
        box.set_margin_bottom(24)

        # 1. File selection group
        file_group = Adw.PreferencesGroup(
            title="Files to Verify",
            description="Select the data file and its detached signature, or select a signed file.",
        )

        self.vf_data_row = Adw.ActionRow(title="Data File", subtitle="No file selected")
        data_btn = Gtk.Button(label="Browse...", icon_name="document-open-symbolic", valign=Gtk.Align.CENTER)
        data_btn.connect("clicked", self._on_browse_vf_data)
        self.vf_data_row.add_suffix(data_btn)
        file_group.add(self.vf_data_row)

        self.vf_sig_row = Adw.ActionRow(title="Signature File (.asc / .sig)", subtitle="Optional if data file is standalone signed")
        sig_btn = Gtk.Button(label="Browse...", icon_name="document-open-symbolic", valign=Gtk.Align.CENTER)
        sig_btn.connect("clicked", self._on_browse_vf_sig)
        self.vf_sig_row.add_suffix(sig_btn)
        file_group.add(self.vf_sig_row)
        box.append(file_group)

        # 2. GPG GUI Verification Action Button
        act_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        v_btn = Gtk.Button(label="Verify File Signature (GPG)", icon_name="security-high-symbolic")
        v_btn.add_css_class("suggested-action")
        v_btn.add_css_class("pill")
        v_btn.set_size_request(240, 48)
        v_btn.connect("clicked", self._on_verify_file_clicked)
        act_box.append(v_btn)
        box.append(act_box)

        # 3. GPG GUI Result Card
        self.verify_file_res_card = self._build_verify_result_card()
        box.append(self.verify_file_res_card)

        # 4. Hashes & Checksums Section
        hash_group = Adw.PreferencesGroup(
            title="File Cryptographic Hashes &amp; Checksums",
            description="Verify data integrity using SHA-256, SHA-512, SHA-1, or MD5 hashes.",
        )

        hash_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        calc_btn = Gtk.Button(label="Compute Hashes", icon_name="system-run-symbolic")
        calc_btn.add_css_class("flat")
        calc_btn.connect("clicked", lambda _: self._on_compute_hashes_clicked())
        hash_tools.append(calc_btn)
        hash_group.set_header_suffix(hash_tools)

        # Expected hash row & matching status
        matcher_row = Adw.ActionRow(
            title="Compare Expected Hash / Checksum",
            subtitle="Type or paste expected hash to check file integrity",
        )
        matcher_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
        
        self.expected_hash_entry = Gtk.Entry(
            placeholder_text="Paste SHA256 / SHA512 hash or line...",
            hexpand=True,
            width_chars=28,
        )
        self.expected_hash_entry.connect("changed", self._on_expected_hash_changed)
        matcher_box.append(self.expected_hash_entry)

        paste_hash_btn = Gtk.Button(icon_name="edit-paste-symbolic", tooltip_text="Paste from clipboard")
        paste_hash_btn.connect("clicked", self._on_paste_expected_hash)
        matcher_box.append(paste_hash_btn)

        open_sums_btn = Gtk.Button(label="Load File...", icon_name="document-open-symbolic", tooltip_text="Load SHA256SUMS file")
        open_sums_btn.connect("clicked", self._on_load_checksum_file)
        matcher_box.append(open_sums_btn)

        matcher_row.add_suffix(matcher_box)
        hash_group.add(matcher_row)

        # Match status card
        self.hash_match_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.hash_match_box.add_css_class("card")
        self.hash_match_box.set_margin_top(4)
        self.hash_match_box.set_margin_bottom(4)
        self.hash_match_box.set_visible(False)

        self.hash_match_icon = Gtk.Image()
        self.hash_match_icon.set_pixel_size(24)
        self.hash_match_box.append(self.hash_match_icon)

        self.hash_match_label = Gtk.Label(halign=Gtk.Align.START, wrap=True, hexpand=True)
        self.hash_match_box.append(self.hash_match_label)
        hash_group.add(self.hash_match_box)

        # Individual hash rows
        self.sha256_row = self._create_hash_row("SHA-256")
        hash_group.add(self.sha256_row)

        self.sha512_row = self._create_hash_row("SHA-512")
        hash_group.add(self.sha512_row)

        self.sha1_row = self._create_hash_row("SHA-1")
        hash_group.add(self.sha1_row)

        self.md5_row = self._create_hash_row("MD5")
        hash_group.add(self.md5_row)

        box.append(hash_group)

        # 5. Command Line Verification Section
        cli_group = Adw.PreferencesGroup(
            title="Command Line Verification (GPG &amp; Hashes)",
            description="Inspect shell commands to verify files using gpg and hash tools, or execute them directly.",
        )

        cli_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        copy_cli_btn = Gtk.Button(label="Copy Commands", icon_name="edit-copy-symbolic")
        copy_cli_btn.add_css_class("flat")
        copy_cli_btn.connect("clicked", self._on_copy_cli_commands)
        cli_tools.append(copy_cli_btn)

        run_cli_btn = Gtk.Button(label="Run in Terminal Console", icon_name="utilities-terminal-symbolic")
        run_cli_btn.add_css_class("suggested-action")
        run_cli_btn.connect("clicked", self._on_run_cli_verification)
        cli_tools.append(run_cli_btn)
        cli_group.set_header_suffix(cli_tools)

        # Shell command preview
        cmd_scroll = Gtk.ScrolledWindow()
        cmd_scroll.set_min_content_height(100)
        self.cli_cmd_tv = Gtk.TextView()
        self.cli_cmd_tv.set_editable(False)
        self.cli_cmd_tv.set_monospace(True)
        self.cli_cmd_tv.set_wrap_mode(Gtk.WrapMode.NONE)
        self.cli_cmd_tv.set_top_margin(8)
        self.cli_cmd_tv.set_bottom_margin(8)
        self.cli_cmd_tv.set_left_margin(10)
        self.cli_cmd_tv.set_right_margin(10)
        self.cli_cmd_tv.add_css_class("card")
        cmd_scroll.set_child(self.cli_cmd_tv)
        cli_group.add(cmd_scroll)

        # Live terminal output console
        self.cli_expander = Gtk.Expander(label="Terminal Execution Output")
        self.cli_expander.set_expanded(False)
        console_scroll = Gtk.ScrolledWindow()
        console_scroll.set_min_content_height(140)
        self.cli_console_tv = Gtk.TextView()
        self.cli_console_tv.set_editable(False)
        self.cli_console_tv.set_monospace(True)
        self.cli_console_tv.set_wrap_mode(Gtk.WrapMode.NONE)
        self.cli_console_tv.set_top_margin(8)
        self.cli_console_tv.set_bottom_margin(8)
        self.cli_console_tv.set_left_margin(10)
        self.cli_console_tv.set_right_margin(10)
        self.cli_console_tv.add_css_class("card")
        console_scroll.set_child(self.cli_console_tv)
        self.cli_expander.set_child(console_scroll)
        cli_group.add(self.cli_expander)

        box.append(cli_group)

        self.computed_hashes: Dict[str, str] = {}
        self._update_cli_commands()

        clamp.set_child(box)
        scrolled.set_child(clamp)
        return scrolled

    # --------------------------------------------------------------------------
    # VERIFY RESULT CARD WIDGET
    # --------------------------------------------------------------------------
    def _build_verify_result_card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("card")
        card.set_margin_top(4)
        card.set_margin_bottom(4)
        card.set_visible(False)

        # Status header banner
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status_icon = Gtk.Image()
        status_icon.set_pixel_size(28)
        header_box.append(status_icon)

        title_label = Gtk.Label(halign=Gtk.Align.START, hexpand=True)
        title_label.add_css_class("title-3")
        header_box.append(title_label)
        card.append(header_box)

        # Details list
        details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        signer_label = Gtk.Label(halign=Gtk.Align.START, wrap=True)
        details_box.append(signer_label)

        key_label = Gtk.Label(halign=Gtk.Align.START, wrap=True)
        key_label.add_css_class("monospace")
        details_box.append(key_label)

        date_label = Gtk.Label(halign=Gtk.Align.START)
        details_box.append(date_label)

        trust_label = Gtk.Label(halign=Gtk.Align.START)
        details_box.append(trust_label)
        card.append(details_box)

        # Raw output expander
        expander = Gtk.Expander(label="GPG Diagnostic Output")
        raw_scroll = Gtk.ScrolledWindow()
        raw_scroll.set_min_content_height(100)
        raw_tv = Gtk.TextView()
        raw_tv.set_editable(False)
        raw_tv.set_monospace(True)
        raw_tv.set_wrap_mode(Gtk.WrapMode.NONE)
        raw_tv.set_top_margin(8)
        raw_tv.set_bottom_margin(8)
        raw_tv.set_left_margin(10)
        raw_tv.set_right_margin(10)
        raw_scroll.set_child(raw_tv)
        expander.set_child(raw_scroll)
        card.append(expander)

        # Store references in widget
        card.status_icon = status_icon
        card.title_label = title_label
        card.signer_label = signer_label
        card.key_label = key_label
        card.date_label = date_label
        card.trust_label = trust_label
        card.raw_tv = raw_tv

        return card

    def _update_result_card(self, card: Gtk.Box, res: VerifyResult, raw: str):
        card.set_visible(True)
        for c in ["success-banner", "error-banner", "warning-banner", "info-banner"]:
            card.remove_css_class(c)

        if res.status == "GOOD":
            card.add_css_class("success-banner")
            card.status_icon.set_from_icon_name("emblem-ok-symbolic")
            card.title_label.set_text("Valid Signature")
        elif res.status == "BAD":
            card.add_css_class("error-banner")
            card.status_icon.set_from_icon_name("dialog-error-symbolic")
            card.title_label.set_text("BAD SIGNATURE - Verification Failed!")
        elif res.status == "NO_KEY":
            card.add_css_class("warning-banner")
            card.status_icon.set_from_icon_name("dialog-warning-symbolic")
            card.title_label.set_text("Unknown Signing Key")
        else:
            card.add_css_class("info-banner")
            card.status_icon.set_from_icon_name("dialog-information-symbolic")
            card.title_label.set_text("Verification Result")

        card.signer_label.set_text(f"Signer: {res.signer_uid or 'Unknown'}")
        card.key_label.set_text(f"Key ID: {res.key_id or 'Unknown'}{f' • FP: {res.fingerprint}' if res.fingerprint else ''}")
        card.date_label.set_text(f"Signed at: {res.timestamp or 'Unknown timestamp'}")
        card.trust_label.set_text(f"Key Trust: {res.trust}")
        card.raw_tv.get_buffer().set_text(raw or res.raw_output)

    # --------------------------------------------------------------------------
    # DATA RELOAD
    # --------------------------------------------------------------------------
    def reload_keys(self):
        try:
            all_keys = self.backend.list_keys(secret_only=True)
            self.secret_keys = [
                k for k in all_keys
                if "Sign" in k.capabilities or not k.capabilities
            ]
        except Exception:
            self.secret_keys = []

        items = [f"{k.display_name} ({k.key_id})" for k in self.secret_keys]
        if not items:
            items = ["No private keys available"]

        model1 = Gtk.StringList.new(items)
        self.cs_key_combo.set_model(model1)

        model2 = Gtk.StringList.new(items)
        self.sign_file_key_combo.set_model(model2)

    # --------------------------------------------------------------------------
    # ACTIONS
    # --------------------------------------------------------------------------
    def _on_clearsign_text_clicked(self, _):
        if not self.secret_keys:
            self.window.show_toast("No private signing keys found in keyring.")
            return

        buf = self.cs_input_tv.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True)
        if not text.strip():
            self.window.show_toast("Please enter text to sign.")
            return

        idx = self.cs_key_combo.get_selected()
        if idx >= len(self.secret_keys):
            return
        key_id = self.secret_keys[idx].key_id

        passphrase = self.cs_pass_entry.get_text() or None
        success, signed_text, err = self.backend.clearsign_text(
            plaintext=text,
            sign_key_id=key_id,
            passphrase=passphrase,
        )
        if success:
            self.cs_output_tv.get_buffer().set_text(signed_text)
            self.window.show_toast("Message clearsigned successfully!")
        else:
            hint = ""
            if "unusable secret key" in err.lower() or "inappropriate ioctl" in err.lower() or "bad passphrase" in err.lower():
                hint = "\n\nTip: The signing key requires a passphrase to unlock. Please enter its password in the 'Signing Passphrase' field above."
            dialog = Adw.MessageDialog(
                transient_for=self.window,
                heading="Signing Error",
                body=f"{err}{hint}",
            )
            dialog.add_response("ok", "OK")
            dialog.present()

    def _create_hash_row(self, name: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=name, subtitle="Not computed")
        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=f"Copy {name} to clipboard")
        copy_btn.add_css_class("flat")
        copy_btn.connect("clicked", lambda _: self._copy_hash_value(row.get_subtitle()))
        row.add_suffix(copy_btn)
        return row

    def _copy_hash_value(self, val: str):
        if not val or val == "Not computed" or "..." in val:
            return
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(val)
        self.window.show_toast("Hash copied to clipboard.")

    def _on_browse_sign_file(self, _):
        def on_selected(path: str):
            self.sign_file_src_path = path
            self.sign_file_src_row.set_subtitle(path)
            self.sign_file_dest_path = f"{path}.asc"
            self.sign_file_dest_row.set_subtitle(self.sign_file_dest_path)

        choose_file(
            parent=self.window,
            title="Select File to Sign",
            action=Gtk.FileChooserAction.OPEN,
            filters=[("All Files", ["*"])],
            on_selected=on_selected,
        )

    def _on_browse_sign_dest(self, _):
        def on_selected(path: str):
            self.sign_file_dest_path = path
            self.sign_file_dest_row.set_subtitle(path)

        default_name = None
        if hasattr(self, "sign_file_dest_path") and self.sign_file_dest_path:
            default_name = os.path.basename(self.sign_file_dest_path)

        choose_file(
            parent=self.window,
            title="Select Signature Destination",
            action=Gtk.FileChooserAction.SAVE,
            default_name=default_name,
            on_selected=on_selected,
        )

    def _on_sign_file_clicked(self, _):
        if not hasattr(self, "sign_file_src_path") or not self.sign_file_src_path:
            self.window.show_toast("Please select a file to sign.")
            return

        if not self.secret_keys:
            self.window.show_toast("No private keys available for signing.")
            return

        idx = self.sign_file_key_combo.get_selected()
        if idx >= len(self.secret_keys):
            return
        key_id = self.secret_keys[idx].key_id

        detached = self.sign_file_type_combo.get_selected() == 0
        dest_path = getattr(self, "sign_file_dest_path", f"{self.sign_file_src_path}.asc")

        passphrase = self.sign_file_pass_entry.get_text() or None
        success, msg = self.backend.sign_file(
            src_path=self.sign_file_src_path,
            dest_path=dest_path,
            sign_key_id=key_id,
            passphrase=passphrase,
            detached=detached,
            armor=True,
        )

        if success:
            self.sign_file_res_box.set_visible(True)
            self.sign_file_res_label.set_text(f"Signed successfully:\n{dest_path}")
            self.window.show_toast(f"Signed: {os.path.basename(dest_path)}")
        else:
            self.sign_file_res_box.set_visible(False)
            hint = ""
            if "unusable secret key" in msg.lower() or "inappropriate ioctl" in msg.lower() or "bad passphrase" in msg.lower():
                hint = "\n\nTip: The signing key requires a passphrase to unlock. Please enter its password in the 'Signing Passphrase' field above."
            dialog = Adw.MessageDialog(
                transient_for=self.window,
                heading="Signing Error",
                body=f"{msg}{hint}",
            )
            dialog.add_response("ok", "OK")
            dialog.present()

    def _on_verify_text_clicked(self, _):
        buf = self.verify_input_tv.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True).strip()
        if not text:
            self.window.show_toast("Please paste signed text to verify.")
            return

        valid, res = self.backend.verify_text(text)
        self._update_result_card(self.verify_text_res_card, res, res.raw_output)
        self.window.show_toast("Verification complete.")

    def _on_browse_vf_data(self, _):
        choose_file(
            parent=self.window,
            title="Select Data File to Verify",
            action=Gtk.FileChooserAction.OPEN,
            filters=[("All Files", ["*"])],
            on_selected=self._set_vf_data,
        )

    def _set_vf_data(self, path: str):
        self.vf_data_path = path
        self.vf_data_row.set_subtitle(path)

        # Auto-detect detached signature if present
        for ext in [".asc", ".sig"]:
            cand = f"{path}{ext}"
            if os.path.exists(cand):
                self._set_vf_sig(cand)
                break

        self._update_cli_commands()
        self._start_compute_hashes(path)

    def _on_browse_vf_sig(self, _):
        choose_file(
            parent=self.window,
            title="Select Detached Signature File",
            action=Gtk.FileChooserAction.OPEN,
            filters=[
                ("Signature Files (*.asc, *.sig)", ["*.asc", "*.sig"]),
                ("All Files", ["*"]),
            ],
            on_selected=self._set_vf_sig,
        )

    def _set_vf_sig(self, path: str):
        self.vf_sig_path = path
        self.vf_sig_row.set_subtitle(path)
        self._update_cli_commands()

    # --------------------------------------------------------------------------
    # HASH COMPUTATION & MATCHING
    # --------------------------------------------------------------------------
    def _on_compute_hashes_clicked(self):
        data_path = getattr(self, "vf_data_path", None)
        if not data_path or not os.path.exists(data_path):
            self.window.show_toast("Please select a data file first.")
            return
        self._start_compute_hashes(data_path)

    def _start_compute_hashes(self, path: str):
        self.sha256_row.set_subtitle("Calculating SHA-256...")
        self.sha512_row.set_subtitle("Calculating SHA-512...")
        self.sha1_row.set_subtitle("Calculating SHA-1...")
        self.md5_row.set_subtitle("Calculating MD5...")

        def worker():
            try:
                h_sha256 = hashlib.sha256()
                h_sha512 = hashlib.sha512()
                h_sha1 = hashlib.sha1()
                h_md5 = hashlib.md5()
                with open(path, "rb") as f:
                    while chunk := f.read(65536):
                        h_sha256.update(chunk)
                        h_sha512.update(chunk)
                        h_sha1.update(chunk)
                        h_md5.update(chunk)

                hashes = {
                    "sha256": h_sha256.hexdigest(),
                    "sha512": h_sha512.hexdigest(),
                    "sha1": h_sha1.hexdigest(),
                    "md5": h_md5.hexdigest(),
                }
                GLib.idle_add(self._on_hashes_computed, path, hashes)
            except Exception as e:
                GLib.idle_add(self._on_hashes_failed, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_hashes_computed(self, path: str, hashes: Dict[str, str]):
        self.computed_hashes = hashes
        self.sha256_row.set_subtitle(hashes.get("sha256", "Error"))
        self.sha512_row.set_subtitle(hashes.get("sha512", "Error"))
        self.sha1_row.set_subtitle(hashes.get("sha1", "Error"))
        self.md5_row.set_subtitle(hashes.get("md5", "Error"))
        self._check_hash_match()
        self._update_cli_commands()

    def _on_hashes_failed(self, err: str):
        self.sha256_row.set_subtitle("Failed to calculate")
        self.sha512_row.set_subtitle("Failed to calculate")
        self.sha1_row.set_subtitle("Failed to calculate")
        self.md5_row.set_subtitle("Failed to calculate")
        self.window.show_toast(f"Hash calculation error: {err}")

    def _on_expected_hash_changed(self, _):
        self._check_hash_match()

    def _check_hash_match(self):
        raw = self.expected_hash_entry.get_text().strip().lower()
        if not raw:
            self.hash_match_box.set_visible(False)
            return

        if not self.computed_hashes:
            self.hash_match_box.set_visible(True)
            self._set_hash_banner(
                icon="dialog-warning-symbolic",
                css_class="warning-banner",
                text="Hashes not yet computed. Click 'Compute Hashes' or wait for calculation.",
            )
            return

        # Extract hex strings (32 to 128 chars)
        tokens = re.findall(r"\b[a-f0-9]{32,128}\b", raw)
        target = tokens[0] if tokens else raw

        matched_algo = None
        for algo, h_val in self.computed_hashes.items():
            if target == h_val.lower():
                matched_algo = algo.upper()
                break

        self.hash_match_box.set_visible(True)
        if matched_algo:
            self._set_hash_banner(
                icon="emblem-ok-symbolic",
                css_class="success-banner",
                text=f"CHECKSUM VERIFIED: Matches calculated {matched_algo} integrity hash!",
            )
        else:
            self._set_hash_banner(
                icon="dialog-error-symbolic",
                css_class="error-banner",
                text="CHECKSUM MISMATCH: Entered hash does NOT match this file!",
            )

    def _set_hash_banner(self, icon: str, css_class: str, text: str):
        for c in ["success-banner", "error-banner", "warning-banner", "info-banner"]:
            self.hash_match_box.remove_css_class(c)
        self.hash_match_box.add_css_class(css_class)
        self.hash_match_icon.set_from_icon_name(icon)
        self.hash_match_label.set_text(text)

    def _on_paste_expected_hash(self, _):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_text_async(None, lambda c, res: self._finish_paste_entry(self.expected_hash_entry, c, res))

    def _finish_paste_entry(self, entry: Gtk.Entry, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                entry.set_text(text.strip())
        except Exception:
            pass

    def _on_load_checksum_file(self, _):
        def on_selected(path: str):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                # If data path exists, look for line matching data filename
                data_name = os.path.basename(getattr(self, "vf_data_path", ""))
                matched_hash = None
                for line in content.splitlines():
                    if data_name and data_name in line:
                        tokens = re.findall(r"\b[a-f0-9]{32,128}\b", line.lower())
                        if tokens:
                            matched_hash = tokens[0]
                            break

                if not matched_hash:
                    # Grab first valid hex token
                    tokens = re.findall(r"\b[a-f0-9]{32,128}\b", content.lower())
                    if tokens:
                        matched_hash = tokens[0]

                if matched_hash:
                    self.expected_hash_entry.set_text(matched_hash)
                    self.window.show_toast(f"Loaded checksum from {os.path.basename(path)}")
                else:
                    self.window.show_toast("No valid hash found in checksum file.")
            except Exception as e:
                self.window.show_toast(f"Error reading checksum file: {e}")

        choose_file(
            parent=self.window,
            title="Open Checksum File",
            action=Gtk.FileChooserAction.OPEN,
            filters=[
                ("Checksum Files (*SUMS, *.txt, *.sha256, *.sha512, *.md5)", ["*SUMS*", "*.txt", "*.sha256", "*.sha512", "*.md5"]),
                ("All Files", ["*"]),
            ],
            on_selected=on_selected,
        )

    # --------------------------------------------------------------------------
    # COMMAND LINE VERIFICATION
    # --------------------------------------------------------------------------
    def _update_cli_commands(self):
        data_path = getattr(self, "vf_data_path", "/path/to/data_file")
        sig_path = getattr(self, "vf_sig_path", None)

        data_q = shlex.quote(data_path)
        lines = []

        lines.append("# --- 1. GPG Signature Verification ---")
        if sig_path:
            sig_q = shlex.quote(sig_path)
            lines.append(f"gpg --verify {sig_q} {data_q}")
        else:
            lines.append(f"gpg --verify {data_q}")

        lines.append("\n# --- 2. Cryptographic Hash Verification ---")
        lines.append(f"sha256sum {data_q}")
        lines.append(f"sha512sum {data_q}")

        cmd_text = "\n".join(lines)
        self.cli_cmd_tv.get_buffer().set_text(cmd_text)

    def _on_copy_cli_commands(self, _):
        buf = self.cli_cmd_tv.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True).strip()
        if text:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
            self.window.show_toast("Command line commands copied to clipboard.")

    def _on_run_cli_verification(self, _):
        data_path = getattr(self, "vf_data_path", None)
        sig_path = getattr(self, "vf_sig_path", None)

        if not data_path and not sig_path:
            self.window.show_toast("Please select a data or signature file first.")
            return

        self.cli_expander.set_expanded(True)
        buf = self.cli_console_tv.get_buffer()
        buf.set_text("Executing command-line verification...\n\n")

        def worker():
            outputs = []
            
            # 1. GPG Verification
            gpg_cmd = ["gpg", "--verify"]
            if sig_path and data_path:
                gpg_cmd.extend([sig_path, data_path])
            elif data_path:
                gpg_cmd.append(data_path)
            elif sig_path:
                gpg_cmd.append(sig_path)

            outputs.append(f"$ {' '.join(shlex.quote(c) for c in gpg_cmd)}")
            try:
                proc = subprocess.run(gpg_cmd, capture_output=True, text=True, timeout=30)
                out = (proc.stdout + proc.stderr).strip()
                outputs.append(out if out else "[No output]")
                outputs.append(f"[Exit code: {proc.returncode}]\n")
            except Exception as e:
                outputs.append(f"Error running gpg: {e}\n")

            # 2. SHA256 Hash
            if data_path and os.path.exists(data_path):
                sha_cmd = ["sha256sum", data_path]
                outputs.append(f"$ {' '.join(shlex.quote(c) for c in sha_cmd)}")
                try:
                    proc = subprocess.run(sha_cmd, capture_output=True, text=True, timeout=60)
                    out = (proc.stdout + proc.stderr).strip()
                    outputs.append(out if out else "[No output]")
                    outputs.append(f"[Exit code: {proc.returncode}]\n")
                except Exception as e:
                    outputs.append(f"Error running sha256sum: {e}\n")

            final_text = "\n".join(outputs)
            GLib.idle_add(lambda: buf.set_text(final_text))
            GLib.idle_add(lambda: self.window.show_toast("Command line execution completed."))

        threading.Thread(target=worker, daemon=True).start()

    def _on_verify_file_clicked(self, _):
        data_path = getattr(self, "vf_data_path", None)
        sig_path = getattr(self, "vf_sig_path", None)

        if not data_path and not sig_path:
            self.window.show_toast("Please select a file to verify.")
            return

        if sig_path and data_path:
            valid, res = self.backend.verify_file(data_or_sig_path=sig_path, data_path=data_path)
        elif data_path:
            valid, res = self.backend.verify_file(data_or_sig_path=data_path)
        else:
            valid, res = self.backend.verify_file(data_or_sig_path=sig_path)

        self._update_result_card(self.verify_file_res_card, res, res.raw_output)
        self.window.show_toast("File verification complete.")

    def _on_load_verify_text_file(self, _):
        def on_selected(path: str):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    self.verify_input_tv.get_buffer().set_text(f.read())
            except Exception as e:
                self.window.show_toast(f"Error loading file: {e}")

        choose_file(
            parent=self.window,
            title="Open Signed Text File",
            action=Gtk.FileChooserAction.OPEN,
            filters=[("All Files", ["*"])],
            on_selected=on_selected,
        )

    def _paste_into(self, tv: Gtk.TextView):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_text_async(None, lambda c, res: self._finish_paste(tv, c, res))

    def _finish_paste(self, tv: Gtk.TextView, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                tv.get_buffer().set_text(text)
        except Exception:
            pass

    def _copy_from(self, tv: Gtk.TextView):
        buf = tv.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True)
        if text:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
            self.window.show_toast("Copied to clipboard.")

    def _on_save_cs_output(self, _):
        buf = self.cs_output_tv.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True)
        if not text.strip():
            return

        def on_selected(path: str):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.window.show_toast(f"Saved to {os.path.basename(path)}")
            except Exception as e:
                self.window.show_toast(f"Save failed: {e}")

        choose_file(
            parent=self.window,
            title="Save Signed Message",
            action=Gtk.FileChooserAction.SAVE,
            default_name="signed_message.asc",
            on_selected=on_selected,
        )
