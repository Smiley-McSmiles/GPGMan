"""
System & Info View - Shows system GPG configuration, supported ciphers, and stats.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from gpgman.gpg_backend import GPGBackend
from gpgman.ui.file_chooser import choose_file

if TYPE_CHECKING:
    from gpgman.ui.window import MainWindow


class SystemView(Gtk.Box):
    def __init__(self, backend: GPGBackend, window: MainWindow):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.backend = backend
        self.window = window

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._build_ui()
        self.reload_info()

    def _build_ui(self):
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=860)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(8)
        box.set_margin_bottom(24)

        # 1. GPG System Configuration
        sys_group = Adw.PreferencesGroup(
            title="System GPG Installation",
            description="Details of the underlying GNU Privacy Guard engine.",
        )

        self.ver_row = Adw.ActionRow(title="GPG Engine Version", subtitle="Loading...")
        sys_group.add(self.ver_row)

        self.bin_row = Adw.ActionRow(title="Binary Executable Path", subtitle="Loading...")
        bin_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
        
        edit_bin_btn = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Change GPG binary executable path")
        edit_bin_btn.add_css_class("flat")
        edit_bin_btn.connect("clicked", self._on_edit_binary)
        bin_btn_box.append(edit_bin_btn)

        copy_bin_btn = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy binary path")
        copy_bin_btn.add_css_class("flat")
        copy_bin_btn.connect("clicked", lambda _: self._copy_text(self.bin_row.get_subtitle()))
        bin_btn_box.append(copy_bin_btn)

        self.bin_row.add_suffix(bin_btn_box)
        sys_group.add(self.bin_row)

        self.home_row = Adw.ActionRow(title="GnuPG Home Directory", subtitle="Loading...")
        home_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

        edit_home_btn = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Change GnuPG home directory")
        edit_home_btn.add_css_class("flat")
        edit_home_btn.connect("clicked", self._on_edit_home)
        home_btn_box.append(edit_home_btn)

        copy_home_btn = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy home directory path")
        copy_home_btn.add_css_class("flat")
        copy_home_btn.connect("clicked", lambda _: self._copy_text(self.home_row.get_subtitle()))
        home_btn_box.append(copy_home_btn)

        self.home_row.add_suffix(home_btn_box)
        sys_group.add(self.home_row)

        box.append(sys_group)

        # 2. Keyring Statistics
        stats_group = Adw.PreferencesGroup(title="Keyring Statistics")
        
        self.pub_count_row = Adw.ActionRow(title="Public Keys in Keyring", subtitle="0 keys")
        stats_group.add(self.pub_count_row)

        self.sec_count_row = Adw.ActionRow(title="Private / Secret Keypairs", subtitle="0 keys")
        stats_group.add(self.sec_count_row)

        box.append(stats_group)

        # 3. Supported Cryptography
        crypto_group = Adw.PreferencesGroup(title="Supported Cryptographic Algorithms")

        self.pub_algos_row = Adw.ActionRow(title="Public Key Algorithms", subtitle="Loading...")
        crypto_group.add(self.pub_algos_row)

        self.ciphers_row = Adw.ActionRow(title="Ciphers (Symmetric)", subtitle="Loading...")
        crypto_group.add(self.ciphers_row)

        self.hashes_row = Adw.ActionRow(title="Hash / Digest Algorithms", subtitle="Loading...")
        crypto_group.add(self.hashes_row)

        box.append(crypto_group)

        # 4. GPG Agent & Maintenance Actions
        maint_group = Adw.PreferencesGroup(title="Maintenance &amp; Agent Operations")

        agent_row = Adw.ActionRow(
            title="Reload GPG Agent",
            subtitle="Send SIGHUP / reload command to running gpg-agent daemon",
        )
        reload_agent_btn = Gtk.Button(label="Reload Agent", valign=Gtk.Align.CENTER)
        reload_agent_btn.connect("clicked", self._on_reload_agent)
        agent_row.add_suffix(reload_agent_btn)
        maint_group.add(agent_row)

        refresh_all_row = Adw.ActionRow(
            title="Reload All Keys",
            subtitle="Force re-query of all public and private keyrings",
        )
        refresh_all_btn = Gtk.Button(label="Refresh Keyring", valign=Gtk.Align.CENTER)
        refresh_all_btn.connect("clicked", lambda _: self.window.reload_all_views())
        refresh_all_row.add_suffix(refresh_all_btn)
        maint_group.add(refresh_all_row)

        box.append(maint_group)

        # 5. About applet card
        about_group = Adw.PreferencesGroup(title="About GPGMan")
        about_row = Adw.ActionRow(
            title="GPGMan v1.3.0 (Dual GUI &amp; CLI)",
            subtitle="Lead Architect: WOOSAH · Engineer: Gemini 3.8 · MIT License",
        )
        gh_row = Adw.ActionRow(
            title="GitHub Repository",
            subtitle="https://github.com/Smiley-McSmiles/GPGMan",
        )
        gh_btn = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER)
        gh_btn.set_tooltip_text("Copy GitHub URL")
        gh_btn.connect("clicked", lambda _: self._copy_text("https://github.com/Smiley-McSmiles/GPGMan"))
        gh_row.add_suffix(gh_btn)

        about_group.add(about_row)
        about_group.add(gh_row)
        box.append(about_group)

        clamp.set_child(box)
        scrolled.set_child(clamp)
        self.append(scrolled)

    def reload_info(self):
        info = self.backend.get_system_info()
        self.ver_row.set_subtitle(info.get("version", "Unknown"))
        self.bin_row.set_subtitle(info.get("binary", "Unknown"))
        self.home_row.set_subtitle(info.get("home", "Unknown"))

        self.pub_algos_row.set_subtitle(", ".join(info.get("pubkey_algos", [])) or "None listed")
        self.ciphers_row.set_subtitle(", ".join(info.get("ciphers", [])) or "None listed")
        self.hashes_row.set_subtitle(", ".join(info.get("hashes", [])) or "None listed")

        try:
            all_keys = self.backend.list_keys()
            sec_keys = [k for k in all_keys if k.is_secret]
            self.pub_count_row.set_subtitle(f"{len(all_keys)} public keys")
            self.sec_count_row.set_subtitle(f"{len(sec_keys)} private keypairs")
        except Exception:
            pass

    def _copy_text(self, text: str):
        if text:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
            self.window.show_toast("Copied to clipboard.")

    def _on_reload_agent(self, _):
        code, out, err = self.backend._run(["--reload-agent"])
        if code == 0:
            self.window.show_toast("GPG Agent reloaded.")
        else:
            self.window.show_toast("GPG Agent reload finished.")

    def _on_edit_binary(self, _):
        current_bin = getattr(self.backend, "gpg_binary", "/usr/bin/gpg")
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Configure GPG Binary Path",
            body="Enter or browse for the system GnuPG executable binary (e.g., /usr/bin/gpg, /usr/local/bin/gpg):",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Apply")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)

        entry = Gtk.Entry(hexpand=True, text=current_bin)
        box.append(entry)

        browse_btn = Gtk.Button(label="Browse...", icon_name="document-open-symbolic")
        def on_browse_bin(_btn):
            choose_file(
                parent=dialog,
                title="Select GPG Binary Executable",
                action=Gtk.FileChooserAction.OPEN,
                filters=[("Executable Files", ["*"])],
                on_selected=lambda p: entry.set_text(p),
            )
        browse_btn.connect("clicked", on_browse_bin)
        box.append(browse_btn)

        dialog.set_extra_child(box)

        # Allow ESC to close
        ctrl = Gtk.EventControllerKey.new()
        ctrl.connect("key-pressed", lambda c, k, code, s: dialog.response("cancel") if k == Gdk.KEY_Escape else False)
        dialog.add_controller(ctrl)

        def on_resp(d: Adw.MessageDialog, resp: str):
            if resp == "save":
                new_path = entry.get_text().strip()
                ok, msg = self.backend.set_gpg_binary(new_path)
                if ok:
                    self.window.show_toast(msg)
                    self.window.reload_all_views()
                else:
                    err_dlg = Adw.MessageDialog(
                        transient_for=self.window,
                        heading="Invalid GPG Binary",
                        body=msg,
                    )
                    err_dlg.add_response("ok", "OK")
                    err_dlg.present()

        dialog.connect("response", on_resp)
        dialog.present()

    def _on_edit_home(self, _):
        current_home = getattr(self.backend, "gnupg_home", "") or os.path.expanduser("~/.gnupg")
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Configure GnuPG Home Directory",
            body="Enter or browse for the GnuPG configuration and keyring directory (~/.gnupg):\n(Enter 'default' to restore standard location)",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("default", "Restore Default")
        dialog.add_response("save", "Apply")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)

        entry = Gtk.Entry(hexpand=True, text=current_home)
        box.append(entry)

        browse_btn = Gtk.Button(label="Browse Folder...", icon_name="folder-open-symbolic")
        def on_browse_home(_btn):
            choose_file(
                parent=dialog,
                title="Select GnuPG Home Directory",
                action=Gtk.FileChooserAction.SELECT_FOLDER,
                on_selected=lambda p: entry.set_text(p),
            )
        browse_btn.connect("clicked", on_browse_home)
        box.append(browse_btn)

        dialog.set_extra_child(box)

        # Allow ESC to close
        ctrl = Gtk.EventControllerKey.new()
        ctrl.connect("key-pressed", lambda c, k, code, s: dialog.response("cancel") if k == Gdk.KEY_Escape else False)
        dialog.add_controller(ctrl)

        def on_resp(d: Adw.MessageDialog, resp: str):
            if resp == "default":
                ok, msg = self.backend.set_gnupg_home("default")
                self.window.show_toast(msg)
                self.window.reload_all_views()
            elif resp == "save":
                new_path = entry.get_text().strip()
                ok, msg = self.backend.set_gnupg_home(new_path)
                if ok:
                    self.window.show_toast(msg)
                    self.window.reload_all_views()
                else:
                    err_dlg = Adw.MessageDialog(
                        transient_for=self.window,
                        heading="Invalid Home Directory",
                        body=msg,
                    )
                    err_dlg.add_response("ok", "OK")
                    err_dlg.present()

        dialog.connect("response", on_resp)
        dialog.present()
