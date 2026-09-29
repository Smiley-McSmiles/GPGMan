"""
Keys View - Manage GPG / PGP Keys (List, Create, Import, Export, Delete, Details).
"""

from __future__ import annotations

import os
import tempfile
import threading
import urllib.request
from typing import TYPE_CHECKING, List, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from gpgman.gpg_backend import GPGBackend, GPGKey
from gpgman.ui.dialog_utils import setup_modal_window
from gpgman.ui.file_chooser import choose_file

if TYPE_CHECKING:
    from gpgman.ui.window import MainWindow


class KeysView(Gtk.Box):
    def __init__(self, backend: GPGBackend, window: MainWindow):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.backend = backend
        self.window = window
        self.keys: List[GPGKey] = []
        self.filter_text = ""
        self.filter_mode = "all"  # "all", "secret", "public"

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._build_ui()
        self.reload_keys()

    def _build_ui(self):
        # Top toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        # Search entry
        self.search_entry = Gtk.SearchEntry(hexpand=True)
        self.search_entry.set_property("placeholder-text", "Search keys by name, email, key ID, or fingerprint...")
        self.search_entry.connect("search-changed", self._on_search_changed)
        toolbar.append(self.search_entry)

        # Filter dropdown (All / Secret / Public)
        filter_model = Gtk.StringList.new(["All Keys", "Secret Keys Only", "Public Keys Only"])
        self.filter_combo = Gtk.DropDown.new(filter_model, None)
        self.filter_combo.connect("notify::selected-item", self._on_filter_changed)
        toolbar.append(self.filter_combo)

        # Action buttons
        new_key_btn = Gtk.Button(label="New Key", icon_name="list-add-symbolic")
        new_key_btn.add_css_class("suggested-action")
        new_key_btn.connect("clicked", self._on_new_key_clicked)
        toolbar.append(new_key_btn)

        import_key_btn = Gtk.Button(label="Import", icon_name="document-open-symbolic")
        import_key_btn.connect("clicked", self._on_import_key_clicked)
        toolbar.append(import_key_btn)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh keyring")
        refresh_btn.connect("clicked", lambda _: self.window.reload_all_views(notify=True))
        toolbar.append(refresh_btn)

        self.append(toolbar)

        # Content stack: List or Empty placeholder
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_vexpand(True)

        # 1. Scrolled key list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        clamp = Adw.Clamp(maximum_size=860)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        clamp.set_child(self.list_box)
        scrolled.set_child(clamp)
        self.stack.add_named(scrolled, "list")

        # 2. Empty state status page
        self.empty_status = Adw.StatusPage()
        self.empty_status.set_icon_name("dialog-password-symbolic")
        self.empty_status.set_title("No Keys Found")
        self.empty_status.set_description("No GPG keys match your current filter, or your keyring is empty.")
        
        empty_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        empty_new_btn = Gtk.Button(label="Create New Key", icon_name="list-add-symbolic")
        empty_new_btn.add_css_class("suggested-action")
        empty_new_btn.add_css_class("pill")
        empty_new_btn.connect("clicked", self._on_new_key_clicked)
        empty_box.append(empty_new_btn)

        empty_imp_btn = Gtk.Button(label="Import Key", icon_name="document-open-symbolic")
        empty_imp_btn.add_css_class("pill")
        empty_imp_btn.connect("clicked", self._on_import_key_clicked)
        empty_box.append(empty_imp_btn)

        self.empty_status.set_child(empty_box)
        self.stack.add_named(self.empty_status, "empty")

        self.append(self.stack)

    def reload_keys(self):
        try:
            self.keys = self.backend.list_keys()
        except Exception as e:
            self.window.show_toast(f"Error loading keys: {e}")
            self.keys = []
        self._populate_list()

    def _on_search_changed(self, entry: Gtk.SearchEntry):
        self.filter_text = entry.get_text().strip().lower()
        self._populate_list()

    def _on_filter_changed(self, combo: Gtk.DropDown, _):
        idx = combo.get_selected()
        if idx == 1:
            self.filter_mode = "secret"
        elif idx == 2:
            self.filter_mode = "public"
        else:
            self.filter_mode = "all"
        self._populate_list()

    def _populate_list(self):
        # Clear existing rows
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        matched_keys = []
        for k in self.keys:
            if self.filter_mode == "secret" and not k.is_secret:
                continue
            if self.filter_mode == "public" and k.is_secret:
                continue

            if self.filter_text:
                q = self.filter_text
                in_name = q in k.name.lower()
                in_email = q in k.email.lower()
                in_id = q in k.key_id.lower()
                in_fp = q in k.fingerprint.lower()
                in_uid = any(q in u.lower() for u in k.uids)
                if not (in_name or in_email or in_id or in_fp or in_uid):
                    continue

            matched_keys.append(k)

        if not matched_keys:
            self.stack.set_visible_child_name("empty")
            return

        self.stack.set_visible_child_name("list")
        for k in matched_keys:
            row = self._create_key_row(k)
            self.list_box.append(row)

    def _create_key_row(self, key: GPGKey) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_activatable(True)
        row.connect("activated", lambda _: self._show_key_details(key))

        # Title: Name or UID
        title = key.name if key.name else (key.primary_uid if key.primary_uid else f"Key {key.key_id}")
        row.set_title(GLib.markup_escape_text(title))

        # Subtitle: Email, ID, Algo
        sub_parts = []
        if key.email:
            sub_parts.append(key.email)
        sub_parts.append(f"ID: {key.key_id}")
        sub_parts.append(f"{key.algo} {key.length}b" if key.length else key.algo)
        if key.expires:
            sub_parts.append(f"Expires: {key.expires}")
        elif key.created:
            sub_parts.append(f"Created: {key.created}")

        row.set_subtitle(" • ".join(sub_parts))

        # Leading icon
        icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic" if key.is_secret else "channel-insecure-symbolic")
        icon.add_css_class("accent" if key.is_secret else "dim-label")
        row.add_prefix(icon)

        # Badges
        badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
        
        if key.is_secret:
            sec_badge = Gtk.Label(label="Sec / Pub")
            sec_badge.add_css_class("badge-secret")
            badge_box.append(sec_badge)
        else:
            pub_badge = Gtk.Label(label="Public")
            pub_badge.add_css_class("badge-public")
            badge_box.append(pub_badge)

        if key.is_expired:
            exp_badge = Gtk.Label(label="Expired")
            exp_badge.add_css_class("badge-expired")
            badge_box.append(exp_badge)

        row.add_suffix(badge_box)

        # Action buttons
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, valign=Gtk.Align.CENTER)

        # Details button
        details_btn = Gtk.Button(icon_name="document-properties-symbolic")
        details_btn.set_tooltip_text("View Key Details")
        details_btn.add_css_class("flat")
        details_btn.connect("clicked", lambda _: self._show_key_details(key))
        actions_box.append(details_btn)

        # Export button
        export_btn = Gtk.Button(icon_name="document-save-symbolic")
        export_btn.set_tooltip_text("Export Public Key")
        export_btn.add_css_class("flat")
        export_btn.connect("clicked", lambda _: self._export_key(key, secret=False))
        actions_box.append(export_btn)

        # Delete button
        delete_btn = Gtk.Button(icon_name="user-trash-symbolic")
        delete_btn.set_tooltip_text("Delete Key")
        delete_btn.add_css_class("flat")
        delete_btn.add_css_class("destructive-action")
        delete_btn.connect("clicked", lambda _: self._confirm_delete_key(key))
        actions_box.append(delete_btn)

        row.add_suffix(actions_box)
        return row

    def _show_key_details(self, key: GPGKey):
        dialog = KeyDetailsDialog(
            self.window,
            self.backend,
            key,
            on_key_updated=lambda: self.window.reload_all_views(notify=False),
        )
        dialog.present()

    def _on_new_key_clicked(self, _):
        dialog = CreateKeyDialog(
            self.window,
            self.backend,
            on_created=lambda: self.window.reload_all_views(notify=False),
        )
        dialog.present()

    def _on_import_key_clicked(self, _):
        dialog = ImportKeyDialog(
            self.window,
            self.backend,
            on_imported=lambda: self.window.reload_all_views(notify=False),
        )
        dialog.present()

    def _export_key(self, key: GPGKey, secret: bool = False):
        if secret:
            success, data = self.backend.export_secret_key(key.key_id, armor=True)
        else:
            success, data = self.backend.export_public_key(key.key_id, armor=True)

        if not success:
            self.window.show_toast(f"Export failed: {data}")
            return

        # Show export preview and save dialog
        dialog = ExportPreviewDialog(self.window, key, data, secret=secret)
        dialog.present()

    def _confirm_delete_key(self, key: GPGKey):
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Delete GPG Key?",
            body=f"Are you sure you want to delete the key for '{key.display_name}' ({key.key_id})?\n\nThis action cannot be undone.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_, response):
            if response == "delete":
                success, msg = self.backend.delete_key(key.key_id)
                if success:
                    self.window.show_toast(f"Key {key.key_id} deleted successfully.")
                    self.window.reload_all_views(notify=False)
                else:
                    self.window.show_toast(f"Failed to delete key: {msg}")

        dialog.connect("response", on_response)
        dialog.present()


class KeyDetailsDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, backend: GPGBackend, key: GPGKey, on_key_updated):
        super().__init__(transient_for=parent)
        setup_modal_window(self)
        self.set_title("Key Details")
        self.set_default_size(580, 560)
        self.backend = backend
        self.key = key
        self.on_key_updated = on_key_updated

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        content.append(header)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=540)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(24)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Key Identity Group
        id_group = Adw.PreferencesGroup(title="Key Identity")
        
        name_row = Adw.ActionRow(title="Name", subtitle=self.key.name or "N/A")
        id_group.add(name_row)

        if self.key.email:
            email_row = Adw.ActionRow(title="Email", subtitle=self.key.email)
            id_group.add(email_row)

        if self.key.comment:
            comment_row = Adw.ActionRow(title="Comment", subtitle=self.key.comment)
            id_group.add(comment_row)

        # Key ID row with copy button
        keyid_row = Adw.ActionRow(title="Key ID", subtitle=self.key.key_id)
        copy_id_btn = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER)
        copy_id_btn.add_css_class("flat")
        copy_id_btn.set_tooltip_text("Copy Key ID")
        copy_id_btn.connect("clicked", lambda _: self._copy_text(self.key.key_id))
        keyid_row.add_suffix(copy_id_btn)
        id_group.add(keyid_row)

        # Fingerprint row with copy button
        fp_row = Adw.ActionRow(title="Fingerprint")
        fp_label = Gtk.Label(label=self.key.formatted_fingerprint or self.key.fingerprint or "N/A")
        fp_label.add_css_class("monospace")
        fp_label.set_wrap(True)
        fp_label.set_selectable(True)
        fp_label.set_halign(Gtk.Align.START)
        fp_row.set_subtitle(self.key.formatted_fingerprint or self.key.fingerprint or "N/A")
        
        copy_fp_btn = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER)
        copy_fp_btn.add_css_class("flat")
        copy_fp_btn.set_tooltip_text("Copy Fingerprint")
        copy_fp_btn.connect("clicked", lambda _: self._copy_text(self.key.fingerprint))
        fp_row.add_suffix(copy_fp_btn)
        id_group.add(fp_row)

        box.append(id_group)

        # Technical Details Group
        tech_group = Adw.PreferencesGroup(title="Technical Properties")
        
        type_row = Adw.ActionRow(
            title="Key Type",
            subtitle=f"{self.key.algo} ({self.key.length} bits)" if self.key.length else self.key.algo,
        )
        tech_group.add(type_row)

        sec_row = Adw.ActionRow(
            title="Key Nature",
            subtitle="Secret &amp; Public Key (Full Key Pair)" if self.key.is_secret else "Public Key Only",
        )
        tech_group.add(sec_row)

        created_row = Adw.ActionRow(title="Created", subtitle=self.key.created or "Unknown")
        tech_group.add(created_row)

        exp_row = Adw.ActionRow(title="Expires", subtitle=self.key.expires or "Never")
        tech_group.add(exp_row)

        val_row = Adw.ActionRow(title="Trust Validity", subtitle=self.key.validity)
        tech_group.add(val_row)

        if self.key.capabilities:
            caps_row = Adw.ActionRow(title="Capabilities", subtitle=", ".join(self.key.capabilities))
            tech_group.add(caps_row)

        box.append(tech_group)

        # Subkeys Group if present
        if self.key.subkeys:
            sub_group = Adw.PreferencesGroup(title=f"Subkeys ({len(self.key.subkeys)})")
            for sub in self.key.subkeys:
                sub_row = Adw.ActionRow(
                    title=f"Subkey {sub.key_id}",
                    subtitle=f"{sub.algo} {sub.length}b • Caps: {', '.join(sub.capabilities)} • Expires: {sub.expires or 'Never'}",
                )
                sub_group.add(sub_row)
            box.append(sub_group)

        # Action buttons Group
        act_group = Adw.PreferencesGroup(title="Key Operations")
        
        # Export Public
        exp_pub_row = Adw.ActionRow(title="Export Public Key", subtitle="Export ASCII armored public key")
        exp_pub_btn = Gtk.Button(label="Export", valign=Gtk.Align.CENTER)
        exp_pub_btn.connect("clicked", lambda _: self._export(secret=False))
        exp_pub_row.add_suffix(exp_pub_btn)
        act_group.add(exp_pub_row)

        # Export Secret (if secret)
        if self.key.is_secret:
            exp_sec_row = Adw.ActionRow(
                title="Export Secret Key",
                subtitle="Export private key backup (keep secure!)",
            )
            exp_sec_btn = Gtk.Button(label="Export Secret", valign=Gtk.Align.CENTER)
            exp_sec_btn.add_css_class("destructive-action")
            exp_sec_btn.connect("clicked", lambda _: self._export(secret=True))
            exp_sec_row.add_suffix(exp_sec_btn)
            act_group.add(exp_sec_row)

            # Change password
            pass_row = Adw.ActionRow(title="Change Password", subtitle="Update key passphrase")
            pass_btn = Gtk.Button(label="Change Passphrase", valign=Gtk.Align.CENTER)
            pass_btn.connect("clicked", self._change_passphrase)
            pass_row.add_suffix(pass_btn)
            act_group.add(pass_row)

        box.append(act_group)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        content.append(scrolled)
        self.set_content(content)

    def _copy_text(self, text: str):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(text)
        if hasattr(self.get_transient_for(), "show_toast"):
            self.get_transient_for().show_toast("Copied to clipboard.")

    def _export(self, secret: bool):
        if secret:
            success, data = self.backend.export_secret_key(self.key.key_id, armor=True)
        else:
            success, data = self.backend.export_public_key(self.key.key_id, armor=True)

        if not success:
            if hasattr(self.get_transient_for(), "show_toast"):
                self.get_transient_for().show_toast(f"Export failed: {data}")
            return

        preview = ExportPreviewDialog(self, self.key, data, secret=secret)
        preview.present()

    def _change_passphrase(self, _):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Change Passphrase",
            body=f"Launch GPG passphrase update for {self.key.key_id}?\nYour system pinentry or terminal will prompt for the current and new passphrase.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("continue", "Continue")
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)

        def on_resp(_, resp):
            if resp == "continue":
                self.backend.change_passphrase(self.key.key_id)
                if hasattr(self.get_transient_for(), "show_toast"):
                    self.get_transient_for().show_toast("Passphrase prompt launched.")

        dialog.connect("response", on_resp)
        dialog.present()


class CreateKeyDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, backend: GPGBackend, on_created):
        super().__init__(transient_for=parent)
        setup_modal_window(self)
        self.set_title("Create New GPG Key")
        self.set_default_size(500, 560)
        self.backend = backend
        self.on_created = on_created

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        content.append(header)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(24)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Identity Group
        id_group = Adw.PreferencesGroup(title="User Identity")

        self.name_entry = Adw.EntryRow(title="Full Name")
        id_group.add(self.name_entry)

        self.email_entry = Adw.EntryRow(title="Email Address")
        id_group.add(self.email_entry)

        self.comment_entry = Adw.EntryRow(title="Comment (Optional)")
        id_group.add(self.comment_entry)

        box.append(id_group)

        # Cryptography Group
        crypto_group = Adw.PreferencesGroup(title="Key Cryptography &amp; Usage")

        # Algorithm selection
        algo_model = Gtk.StringList.new([
            "Ed25519 / Cv25519 (Elliptic Curve - Fast, Modern, Compact)",
            "RSA 4096 bits (Maximum Security & Full Compatibility)",
            "RSA 3072 bits (Standard NIST Recommended)",
            "RSA 2048 bits (Standard RSA Compatibility)",
            "ECDSA NIST P-256 (Elliptic Curve 256-bit)",
            "ECDSA NIST P-384 (High-Grade Elliptic Curve 384-bit)",
            "ECDSA NIST P-521 (Maximum Elliptic Curve 521-bit)",
        ])
        self.algo_combo = Adw.ComboRow(title="Key Type / Algorithm", model=algo_model)
        crypto_group.add(self.algo_combo)

        # Key Usage selection
        usage_model = Gtk.StringList.new([
            "Sign and Encrypt (Standard Keypair for all operations)",
            "Sign Only (Digital Signatures & Certification)",
            "Encrypt Only (Encryption only)",
        ])
        self.usage_combo = Adw.ComboRow(title="Key Usage / Purpose", model=usage_model)
        crypto_group.add(self.usage_combo)

        # Expiration Mode selection
        exp_mode_model = Gtk.StringList.new([
            "Custom Expiration Period",
            "Never Expires (Key does not expire)",
        ])
        self.exp_mode_combo = Adw.ComboRow(title="Expiration Policy", model=exp_mode_model)
        self.exp_mode_combo.connect("notify::selected", self._on_exp_mode_changed)
        crypto_group.add(self.exp_mode_combo)

        # Custom expiration duration row
        self.exp_custom_row = Adw.ActionRow(
            title="Expiration Duration",
            subtitle="Specify duration number and choose time unit",
        )
        exp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, valign=Gtk.Align.CENTER)

        self.exp_value_spin = Gtk.SpinButton.new_with_range(1, 9999, 1)
        self.exp_value_spin.set_value(1)
        self.exp_value_spin.set_width_chars(5)
        exp_box.append(self.exp_value_spin)

        unit_model = Gtk.StringList.new(["Years", "Months", "Days", "Hours"])
        self.exp_unit_dropdown = Gtk.DropDown.new(model=unit_model)
        self.exp_unit_dropdown.set_selected(0)  # Default: Years
        exp_box.append(self.exp_unit_dropdown)

        self.exp_custom_row.add_suffix(exp_box)
        crypto_group.add(self.exp_custom_row)

        # Passphrase
        self.pass_entry = Adw.PasswordEntryRow(title="Passphrase (Optional)")
        crypto_group.add(self.pass_entry)

        box.append(crypto_group)

        # Submit button
        self.submit_btn = Gtk.Button(label="Generate Key")
        self.submit_btn.add_css_class("suggested-action")
        self.submit_btn.add_css_class("pill")
        self.submit_btn.set_size_request(200, 48)
        self.submit_btn.set_halign(Gtk.Align.CENTER)
        self.submit_btn.connect("clicked", self._on_generate)
        box.append(self.submit_btn)

        self.spinner = Gtk.Spinner()
        box.append(self.spinner)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        content.append(scrolled)
        self.set_content(content)

    def _on_exp_mode_changed(self, combo, _):
        # 0 = Custom, 1 = Never
        is_custom = (combo.get_selected() == 0)
        self.exp_custom_row.set_sensitive(is_custom)
        if not is_custom:
            self.exp_custom_row.set_subtitle("Key will have no expiration date")
        else:
            self.exp_custom_row.set_subtitle("Specify duration number and choose time unit")

    def _on_generate(self, _):
        name = self.name_entry.get_text().strip()
        email = self.email_entry.get_text().strip()
        comment = self.comment_entry.get_text().strip()
        passphrase = self.pass_entry.get_text()

        if not name:
            self._show_error("Name is required to generate a key.")
            return

        algo_idx = self.algo_combo.get_selected()
        algo_map = {
            0: "ed25519",
            1: "4096",
            2: "3072",
            3: "2048",
            4: "ecdsa256",
            5: "ecdsa384",
            6: "ecdsa521",
        }
        algo_name = algo_map.get(algo_idx, "ed25519")

        usage_idx = self.usage_combo.get_selected()
        usage_map = {
            0: "all",
            1: "sign",
            2: "encrypt",
        }
        usage_val = usage_map.get(usage_idx, "all")

        # Expiration calculation
        if self.exp_mode_combo.get_selected() == 1:
            expire_str = "0"
        else:
            val = max(1, int(self.exp_value_spin.get_value()))
            unit_idx = self.exp_unit_dropdown.get_selected()
            unit_codes = {0: "y", 1: "m", 2: "d", 3: "h"}
            code = unit_codes.get(unit_idx, "y")
            expire_str = f"{val}{code}"

        self.submit_btn.set_sensitive(False)
        self.spinner.start()

        # Run generation
        def do_gen():
            success, msg = self.backend.generate_key(
                name=name,
                email=email,
                comment=comment,
                algo=algo_name,
                usage=usage_val,
                expire=expire_str,
                passphrase=passphrase,
            )
            GLib.idle_add(lambda: self._finish_generate(success, msg))

        import threading
        threading.Thread(target=do_gen, daemon=True).start()

    def _finish_generate(self, success: bool, msg: str):
        self.spinner.stop()
        self.submit_btn.set_sensitive(True)

        if success:
            if hasattr(self.get_transient_for(), "show_toast"):
                self.get_transient_for().show_toast("Key created successfully!")
            self.on_created()
            self.close()
        else:
            self._show_error(f"Failed to create key:\n{msg}")

    def _show_error(self, message: str):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Key Generation Error",
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.present()


class ImportKeyDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, backend: GPGBackend, on_imported):
        super().__init__(transient_for=parent)
        setup_modal_window(self)
        self.set_title("Import GPG Key")
        self.set_default_size(520, 500)
        self.backend = backend
        self.on_imported = on_imported
        self.selected_file_path: Optional[str] = None

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        content.append(header)

        # View switcher for File / Text
        view_stack = Adw.ViewStack()
        switcher_title = Adw.ViewSwitcher(stack=view_stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher_title)

        # Tab 1: From File
        file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        file_box.set_margin_top(24)
        file_box.set_margin_bottom(24)
        file_box.set_margin_start(24)
        file_box.set_margin_end(24)

        file_desc = Gtk.Label(
            label="Select a public or private key file (.asc, .gpg, .key) to import into your keyring.",
            wrap=True,
            halign=Gtk.Align.START,
        )
        file_box.append(file_desc)

        file_picker_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.file_entry = Gtk.Entry(hexpand=True, placeholder_text="/path/to/key.asc")
        file_picker_box.append(self.file_entry)

        browse_btn = Gtk.Button(label="Browse...", icon_name="document-open-symbolic")
        browse_btn.connect("clicked", self._on_browse_file)
        file_picker_box.append(browse_btn)
        file_box.append(file_picker_box)

        import_file_btn = Gtk.Button(label="Import from File")
        import_file_btn.add_css_class("suggested-action")
        import_file_btn.add_css_class("pill")
        import_file_btn.set_halign(Gtk.Align.CENTER)
        import_file_btn.set_size_request(180, 42)
        import_file_btn.connect("clicked", self._on_import_file)
        file_box.append(import_file_btn)

        view_stack.add_titled(file_box, "file", "From File")

        # Tab 2: Paste Text
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        text_box.set_margin_top(16)
        text_box.set_margin_bottom(16)
        text_box.set_margin_start(16)
        text_box.set_margin_end(16)

        text_desc = Gtk.Label(
            label="Paste ASCII-armored key block (-----BEGIN PGP PUBLIC/PRIVATE KEY BLOCK-----):",
            wrap=True,
            halign=Gtk.Align.START,
        )
        text_box.append(text_desc)

        scrolled_text = Gtk.ScrolledWindow(vexpand=True)
        scrolled_text.set_min_content_height(200)
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.NONE)
        self.text_view.set_monospace(True)
        self.text_view.set_top_margin(10)
        self.text_view.set_bottom_margin(10)
        self.text_view.set_left_margin(12)
        self.text_view.set_right_margin(12)
        self.text_view.add_css_class("card")
        scrolled_text.set_child(self.text_view)
        text_box.append(scrolled_text)

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        paste_btn = Gtk.Button(label="Paste from Clipboard", icon_name="edit-paste-symbolic")
        paste_btn.connect("clicked", self._on_paste_text)
        btn_bar.append(paste_btn)

        import_text_btn = Gtk.Button(label="Import Key Text")
        import_text_btn.add_css_class("suggested-action")
        import_text_btn.add_css_class("pill")
        import_text_btn.connect("clicked", self._on_import_text)
        btn_bar.append(import_text_btn)
        text_box.append(btn_bar)

        view_stack.add_titled(text_box, "text", "Paste Text")

        # Tab 3: Download from Link
        url_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        url_box.set_margin_top(24)
        url_box.set_margin_bottom(24)
        url_box.set_margin_start(24)
        url_box.set_margin_end(24)

        url_desc = Gtk.Label(
            label="Download and import an OpenPGP public key directly from a web URL (HTTP/HTTPS):",
            wrap=True,
            halign=Gtk.Align.START,
        )
        url_box.append(url_desc)

        url_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.url_entry = Gtk.Entry(
            hexpand=True,
            placeholder_text="https://example.org/key.asc or https://github.com/username.gpg",
        )
        url_input_box.append(self.url_entry)

        url_paste_btn = Gtk.Button(label="Paste", icon_name="edit-paste-symbolic")
        url_paste_btn.connect("clicked", self._on_paste_url)
        url_input_box.append(url_paste_btn)
        url_box.append(url_input_box)

        self.url_spinner = Gtk.Spinner()
        self.url_spinner.set_size_request(24, 24)
        self.url_spinner.set_visible(False)

        url_act_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        url_act_bar.append(self.url_spinner)

        self.import_url_btn = Gtk.Button(label="Download & Import Key", icon_name="folder-download-symbolic")
        self.import_url_btn.add_css_class("suggested-action")
        self.import_url_btn.add_css_class("pill")
        self.import_url_btn.set_size_request(220, 42)
        self.import_url_btn.connect("clicked", self._on_import_url)
        url_act_bar.append(self.import_url_btn)
        url_box.append(url_act_bar)

        view_stack.add_titled(url_box, "url", "Download Link")

        content.append(view_stack)
        self.set_content(content)

    def _on_browse_file(self, _):
        choose_file(
            parent=self,
            title="Select GPG Key File",
            action=Gtk.FileChooserAction.OPEN,
            filters=[
                ("GPG / PGP Keys (*.asc, *.gpg, *.key, *.pub)", ["*.asc", "*.gpg", "*.key", "*.pub"]),
                ("All Files", ["*"]),
            ],
            on_selected=lambda path: self.file_entry.set_text(path),
        )

    def _on_paste_url(self, _):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_text_async(None, self._on_url_clipboard_read)

    def _on_url_clipboard_read(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self.url_entry.set_text(text.strip())
        except Exception:
            pass

    def _on_import_url(self, _):
        raw_url = self.url_entry.get_text().strip()
        if not raw_url:
            self._show_error("Please enter a valid HTTP or HTTPS key URL.")
            return

        if not raw_url.startswith(("http://", "https://")):
            raw_url = f"https://{raw_url}"

        self.url_spinner.set_visible(True)
        self.url_spinner.start()
        self.import_url_btn.set_sensitive(False)

        def download_and_import():
            try:
                req = urllib.request.Request(
                    raw_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; GPGMan/1.0; +https://github.com)"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()

                # Write to temp file and import
                with tempfile.NamedTemporaryFile(delete=False, suffix=".asc") as tmp:
                    tmp.write(data)
                    tmp_path = tmp.name

                success, count, msg = self.backend.import_key_file(tmp_path)
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

                GLib.idle_add(self._on_url_import_finished, success, count, msg)
            except Exception as e:
                GLib.idle_add(self._on_url_import_finished, False, 0, f"Download failed: {e}")

        threading.Thread(target=download_and_import, daemon=True).start()

    def _on_url_import_finished(self, success: bool, count: int, msg: str):
        self.url_spinner.stop()
        self.url_spinner.set_visible(False)
        self.import_url_btn.set_sensitive(True)

        if success:
            if hasattr(self.get_transient_for(), "show_toast"):
                self.get_transient_for().show_toast(f"Downloaded and imported {count} key(s) successfully.")
            self.on_imported()
            self.close()
        else:
            self._show_error(f"Failed to import key from link:\n{msg}")

    def _on_paste_text(self, _):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.read_text_async(None, self._on_clipboard_read)

    def _on_clipboard_read(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                buf = self.text_view.get_buffer()
                buf.set_text(text)
        except Exception:
            pass

    def _on_import_file(self, _):
        path = self.file_entry.get_text().strip()
        if not path or not os.path.exists(path):
            self._show_error("Please enter or select a valid key file.")
            return

        success, count, msg = self.backend.import_key_file(path)
        if success:
            if hasattr(self.get_transient_for(), "show_toast"):
                self.get_transient_for().show_toast(f"Imported {count} key(s) successfully.")
            self.on_imported()
            self.close()
        else:
            self._show_error(f"Import failed:\n{msg}")

    def _on_import_text(self, _):
        buf = self.text_view.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, True).strip()

        if not text:
            self._show_error("Please paste the key text into the editor.")
            return

        success, count, msg = self.backend.import_key_text(text)
        if success:
            if hasattr(self.get_transient_for(), "show_toast"):
                self.get_transient_for().show_toast(f"Imported {count} key(s) successfully.")
            self.on_imported()
            self.close()
        else:
            self._show_error(f"Import failed:\n{msg}")

    def _show_error(self, message: str):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Import Error",
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.present()


class ExportPreviewDialog(Adw.Window):
    def __init__(self, parent: Gtk.Window, key: GPGKey, key_data: str, secret: bool = False):
        super().__init__(transient_for=parent)
        setup_modal_window(self)
        title = f"Export {'Secret' if secret else 'Public'} Key - {key.key_id}"
        self.set_title(title)
        self.set_default_size(540, 500)
        self.key = key
        self.key_data = key_data
        self.secret = secret

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        content.append(header)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        if secret:
            warning_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            warning_box.add_css_class("warning-banner")
            warn_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            warning_box.append(warn_icon)
            warn_label = Gtk.Label(
                label="Warning: Keep this private key safe and confidential!",
                wrap=True,
                halign=Gtk.Align.START,
            )
            warning_box.append(warn_label)
            box.append(warning_box)

        # Monospace Text view
        tv_scroll = Gtk.ScrolledWindow(vexpand=True)
        tv_scroll.set_min_content_height(300)
        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.NONE)
        tv.set_top_margin(10)
        tv.set_bottom_margin(10)
        tv.set_left_margin(12)
        tv.set_right_margin(12)
        tv.get_buffer().set_text(key_data)
        tv_scroll.set_child(tv)
        box.append(tv_scroll)

        # Action buttons
        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.END)
        
        copy_btn = Gtk.Button(label="Copy to Clipboard", icon_name="edit-copy-symbolic")
        copy_btn.connect("clicked", self._on_copy)
        btn_bar.append(copy_btn)

        save_btn = Gtk.Button(label="Save to File...", icon_name="document-save-symbolic")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_file)
        btn_bar.append(save_btn)

        box.append(btn_bar)
        scrolled.set_child(box)
        content.append(scrolled)
        self.set_content(content)

    def _on_copy(self, _):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(self.key_data)
        if hasattr(self.get_transient_for(), "show_toast"):
            self.get_transient_for().show_toast("Key copied to clipboard.")

    def _on_save_file(self, _):
        default_name = f"{self.key.key_id}_{'secret' if self.secret else 'public'}.asc"

        def on_selected(dest_path: str):
            try:
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(self.key_data)
                if hasattr(self.get_transient_for(), "show_toast"):
                    self.get_transient_for().show_toast(f"Saved to {os.path.basename(dest_path)}")
                self.close()
            except Exception as e:
                err_dialog = Adw.MessageDialog(
                    transient_for=self,
                    heading="Save Error",
                    body=str(e),
                )
                err_dialog.add_response("ok", "OK")
                err_dialog.present()

        choose_file(
            parent=self,
            title="Save Key File",
            action=Gtk.FileChooserAction.SAVE,
            default_name=default_name,
            on_selected=on_selected,
        )
