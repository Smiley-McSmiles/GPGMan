"""
Main Application Window - Libadwaita Application Window.
"""

from __future__ import annotations

import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from gpgman.gpg_backend import GPGBackend
from gpgman.ui.clearsign_view import ClearsignView
from gpgman.ui.files_view import FilesView
from gpgman.ui.keys_view import KeysView
from gpgman.ui.messages_view import MessagesView
from gpgman.ui.system_view import SystemView


APP_CSS = """
.badge-secret {
    background-color: alpha(@accent_color, 0.18);
    color: @accent_color;
    font-weight: bold;
    font-size: 0.82em;
    padding: 2px 8px;
    border-radius: 9999px;
}

.badge-public {
    background-color: alpha(@window_fg_color, 0.08);
    color: @window_fg_color;
    font-size: 0.82em;
    padding: 2px 8px;
    border-radius: 9999px;
}

.badge-expired {
    background-color: alpha(@destructive_color, 0.18);
    color: @destructive_color;
    font-weight: bold;
    font-size: 0.82em;
    padding: 2px 8px;
    border-radius: 9999px;
}

.success-banner {
    background-color: alpha(#2ec27e, 0.15);
    border: 1px solid alpha(#2ec27e, 0.35);
    border-radius: 12px;
    padding: 12px 16px;
}

.error-banner {
    background-color: alpha(#e01b24, 0.15);
    border: 1px solid alpha(#e01b24, 0.35);
    border-radius: 12px;
    padding: 12px 16px;
}

.warning-banner {
    background-color: alpha(#e5a50a, 0.15);
    border: 1px solid alpha(#e5a50a, 0.35);
    border-radius: 12px;
    padding: 12px 16px;
}

.info-banner {
    background-color: alpha(@accent_color, 0.12);
    border: 1px solid alpha(@accent_color, 0.25);
    border-radius: 12px;
    padding: 12px 16px;
}

textview text {
    padding: 8px 10px;
}
"""


# --- Donation menu (About dialog) --------------------------------------------
# TODO: Replace the placeholders below with your own text.
# DONATION_BUTTON_LABEL is the title of the row in the About dialog; it opens a
# sub-page (like Credits / Legal) listing the options below. Each option is
# (button title, text copied to the user's clipboard when pressed).
DONATION_BUTTON_LABEL = "Donate"  # TODO: custom button text
DONATION_PAGE_TITLE = "Donate"  # TODO: custom sub-page title
DONATION_OPTIONS = [
    ("BTC", "bc1qy2gtdhnfxp9dcs6v9jda748npmsjx3jgwp99mx"),  # TODO: custom text copied for Option 1
    ("XMR", "82xtMVSmesuLjPtgHfBCEhM5Fpqh1SLLNf9pzHRRNPqQZsvrnmoM1ZGC7AiLyPfsufdyrMWHrWYV2hsC8jc5rEBVLMHWTLy"),  # TODO: custom text copied for Option 2
    ("CashApp", "$SmileyMcSmiles"),  # TODO: custom text copied for Option 3
]


def _iter_descendants(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from _iter_descendants(child)
        child = child.get_next_sibling()


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, backend: GPGBackend):
        super().__init__(application=app)
        self.backend = backend

        # Register application icon search paths
        try:
            display = Gdk.Display.get_default()
            if display:
                theme = Gtk.IconTheme.get_for_display(display)
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                theme.add_search_path(os.path.join(base_dir, "icons"))
                theme.add_search_path(base_dir)
                theme.add_search_path("/opt/gpgman")
                theme.add_search_path("/usr/local/share/gpgman")
        except Exception:
            pass

        self.set_title("GPGMan")
        self.set_default_size(920, 680)

        self._apply_css()
        self._build_ui()
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        # Keyboard controller for Ctrl+Q and Ctrl+W
        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and keyval in (Gdk.KEY_q, Gdk.KEY_Q, Gdk.KEY_w, Gdk.KEY_W):
            app = self.get_application()
            if app:
                app.quit()
            else:
                self.close()
            return True
        return False

    def _apply_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(APP_CSS.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def _build_ui(self):
        # Toast overlay as root
        self.toast_overlay = Adw.ToastOverlay()
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Main View Stack
        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)

        # Header Bar
        header = Adw.HeaderBar()
        title_widget = Adw.ViewSwitcherTitle(stack=self.view_stack, title="GPGMan")
        header.set_title_widget(title_widget)

        # Left / Leading header widgets
        app_icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
        app_icon.add_css_class("accent")
        header.pack_start(app_icon)

        # Right / Trailing header widgets
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh all keyrings and views")
        refresh_btn.connect("clicked", lambda _: self.reload_all_views(notify=True))
        header.pack_end(refresh_btn)

        # Theme toggle button
        self.style_manager = Adw.StyleManager.get_default()
        theme_btn = Gtk.Button(icon_name="night-light-symbolic")
        theme_btn.set_tooltip_text("Toggle Dark / Light Theme")
        theme_btn.connect("clicked", self._toggle_theme)
        header.pack_end(theme_btn)

        # About button
        about_btn = Gtk.Button(icon_name="help-about-symbolic")
        about_btn.set_tooltip_text("About GPGMan")
        about_btn.connect("clicked", self._show_about)
        header.pack_end(about_btn)

        main_box.append(header)

        # Subviews
        self.keys_view = KeysView(self.backend, self)
        page1 = self.view_stack.add_titled(self.keys_view, "keys", "Keys")
        page1.set_icon_name("dialog-password-symbolic")

        self.messages_view = MessagesView(self.backend, self)
        page2 = self.view_stack.add_titled(self.messages_view, "messages", "Messages")
        page2.set_icon_name("mail-message-new-symbolic")

        self.files_view = FilesView(self.backend, self)
        page3 = self.view_stack.add_titled(self.files_view, "files", "Files")
        page3.set_icon_name("folder-documents-symbolic")

        self.clearsign_view = ClearsignView(self.backend, self)
        page4 = self.view_stack.add_titled(self.clearsign_view, "clearsign", "Sign & Verify")
        page4.set_icon_name("document-send-symbolic")

        self.system_view = SystemView(self.backend, self)
        page5 = self.view_stack.add_titled(self.system_view, "system", "System")
        page5.set_icon_name("preferences-system-symbolic")

        main_box.append(self.view_stack)

        # Bottom switcher bar for narrow views
        self.switcher_bar = Adw.ViewSwitcherBar(stack=self.view_stack)
        title_widget.bind_property(
            "title-visible",
            self.switcher_bar,
            "reveal",
            GObject.BindingFlags.SYNC_CREATE,
        )
        main_box.append(self.switcher_bar)

        self.toast_overlay.set_child(main_box)
        self.set_content(self.toast_overlay)

    def show_toast(self, message: str, timeout: int = 3):
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

    def reload_all_views(self, notify: bool = False):
        self.keys_view.reload_keys()
        self.messages_view.reload_keys()
        self.files_view.reload_keys()
        self.clearsign_view.reload_keys()
        self.system_view.reload_info()
        if notify:
            self.show_toast("Keyrings refreshed.")

    def _toggle_theme(self, _):
        if self.style_manager.get_dark():
            self.style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            self.style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def _show_about(self, _):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        icon_path = os.path.join(base_dir, "gpgman-icon.svg")
        if not os.path.exists(icon_path):
            for candidate in [
                "/opt/gpgman/gpgman-icon.svg",
                "/usr/local/share/gpgman/gpgman-icon.svg",
                "/usr/share/icons/hicolor/scalable/apps/gpgman-icon.svg",
                "/usr/share/pixmaps/gpgman-icon.svg",
            ]:
                if os.path.exists(candidate):
                    icon_path = candidate
                    break

        dialog = Adw.AboutWindow(
            transient_for=self,
            application_name="GPGMan",
            application_icon="gpgman-icon",
            developer_name="WOOSAH",
            developers=["WOOSAH (Lead Architect)", "Gemini 3.8 (Engineer)"],
            version="1.3.3",
            copyright="© 2026 WOOSAH &amp; Gemini 3.8",
            comments="Dual-Style OpenPGP Cryptographic Suite featuring a modern GTK4 / Libadwaita desktop GUI and 1:1 feature-parity terminal CLI.",
            website="https://github.com/Smiley-McSmiles/GPGMan",
            issue_url="https://github.com/Smiley-McSmiles/GPGMan/issues",
            support_url="https://github.com/Smiley-McSmiles/GPGMan",
            license_type=Gtk.License.MIT_X11,
        )

        if os.path.exists(icon_path):
            try:
                gfile = Gio.File.new_for_path(icon_path)
                texture = Gdk.Texture.new_from_file(gfile)
                dialog.set_logo(texture)
            except Exception:
                dialog.set_application_icon("gpgman-icon")

        added = self._add_donation_row(dialog)

        # Allow ESC to close
        ctrl = Gtk.EventControllerKey.new()
        ctrl.connect("key-pressed", lambda c, k, code, s: dialog.close() if k == Gdk.KEY_Escape else False)
        dialog.add_controller(ctrl)

        dialog.present()
        if not added:
            # Retry once the dialog is mapped, in case its rows are built lazily.
            GLib.idle_add(lambda: self._add_donation_row(dialog) and False)

    def _add_donation_row(self, dialog: Adw.AboutWindow) -> bool:
        """Insert a donation row between the "Credits" and "Legal" rows of the About dialog.

        Adw.AboutWindow has no API for custom rows, so find the list rows by
        their label text and insert one in between. Returns True on success;
        if the layout differs, the row is simply skipped.
        """
        try:
            def row_for(label_text):
                for w in _iter_descendants(dialog):
                    if isinstance(w, Gtk.Label) and w.get_text().strip() == label_text:
                        parent = w.get_parent()
                        while parent is not None and not isinstance(parent, Gtk.ListBoxRow):
                            parent = parent.get_parent()
                        if parent is not None and isinstance(parent.get_parent(), Gtk.ListBox):
                            return parent
                return None

            legal_row = row_for("Legal")
            credits_row = row_for("Credits")
            if legal_row is None or credits_row is None:
                return False
            listbox = legal_row.get_parent()
            if listbox is not credits_row.get_parent():
                return False

            donate_row = Adw.ActionRow(title=DONATION_BUTTON_LABEL, activatable=True)
            donate_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            donate_row.connect("activated", lambda _: self._open_donation_page(dialog))
            listbox.insert(donate_row, legal_row.get_index())
            return True
        except Exception as exc:
            print(f"Warning: could not add donation row to About dialog: {exc}", file=sys.stderr)
            return False

    def _build_donation_content(self) -> Gtk.Widget:
        group = Adw.PreferencesGroup()
        for title, text in DONATION_OPTIONS:
            row = Adw.ActionRow(title=title, activatable=True)
            row.add_suffix(Gtk.Image.new_from_icon_name("edit-copy-symbolic"))
            row.connect("activated", lambda _, t=text: self._copy_donation_text(t))
            group.add(row)
        clamp = Adw.Clamp(maximum_size=480)
        clamp.set_margin_top(18)
        clamp.set_margin_bottom(18)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        clamp.set_child(group)
        return clamp

    def _open_donation_page(self, dialog: Adw.AboutWindow):
        """Push a sub-page inside the About dialog, like Credits / Legal."""
        nav = None
        if hasattr(Adw, "NavigationView"):
            nav = next((w for w in _iter_descendants(dialog) if isinstance(w, Adw.NavigationView)), None)

        if nav is not None:
            toolbar = Adw.ToolbarView()
            toolbar.add_top_bar(Adw.HeaderBar())
            scrolled = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
            scrolled.set_child(self._build_donation_content())
            toolbar.set_content(scrolled)
            nav.push(Adw.NavigationPage.new(toolbar, DONATION_PAGE_TITLE))
            return

        # Older libadwaita without NavigationView: show a small modal window instead.
        win = Adw.Window(transient_for=dialog, modal=True, title=DONATION_PAGE_TITLE)
        win.set_default_size(380, 240)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        box.append(self._build_donation_content())
        win.set_content(box)
        ctrl = Gtk.EventControllerKey.new()
        ctrl.connect("key-pressed", lambda c, k, code, s: win.close() if k == Gdk.KEY_Escape else False)
        win.add_controller(ctrl)
        win.present()

    def _copy_donation_text(self, text: str):
        Gdk.Display.get_default().get_clipboard().set(text)
        self.show_toast("Copied to clipboard.")
