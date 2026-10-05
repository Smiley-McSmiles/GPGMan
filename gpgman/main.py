"""
Application Entry Point for GPGMan - Dual-Style GUI & CLI Application.
"""

from __future__ import annotations

import os
import sys

from gpgman import __app_id__, __version__
from gpgman.gpg_backend import GPGBackend


def run_gui(argv: list[str]) -> int:
    """Launch the GTK4 / Libadwaita graphical interface."""
    import gi
    # X11 desktops (Cinnamon, MATE, XFCE, ...) match a window to its launcher / dock entry by
    # WM_CLASS, which GTK derives from the program name. Set it before GTK is initialised so it
    # equals the launcher's StartupWMClass (the app ID) instead of "python3" / "main.py".
    from gi.repository import GLib
    GLib.set_prgname(__app_id__)
    GLib.set_application_name("GPGMan")

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, Gtk
    from gpgman.ui.window import MainWindow

    # GTK ignores icons added to a theme dir whose icon-theme.cache is stale (package installs
    # can leave it that way), which gives a blank window / dock icon. Also search our bundled copy.
    display = Gdk.Display.get_default()
    if display:
        theme = Gtk.IconTheme.get_for_display(display)
        if not theme.has_icon(__app_id__):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for d in (
                os.path.join(base_dir, "icons"),
                "/opt/gpgman/icons",
                "/usr/local/share/gpgman/icons",
                "/usr/share/gpgman/icons",
            ):
                if os.path.isdir(os.path.join(d, "hicolor")):
                    theme.add_search_path(d)
    Gtk.Window.set_default_icon_name(__app_id__)

    class GpgManApplication(Adw.Application):
        def __init__(self):
            super().__init__(
                application_id=__app_id__,
                flags=Gio.ApplicationFlags.HANDLES_OPEN,
            )
            self.backend: GPGBackend | None = None
            self.window: MainWindow | None = None
            self.connect("startup", self._on_startup)
            self.connect("activate", self._on_activate)
            self.connect("open", self._on_open)
            self.connect("shutdown", self._on_shutdown)

        def _on_startup(self, app):
            quit_action = Gio.SimpleAction.new("quit", None)
            quit_action.connect("activate", lambda *_: self.quit())
            self.add_action(quit_action)
            self.set_accels_for_action("app.quit", ["<Control>q", "<Control>w"])

            try:
                self.backend = GPGBackend()
            except Exception as e:
                print(f"Warning: Failed to initialize GPG backend: {e}", file=sys.stderr)
                self.backend = None

        def _on_activate(self, app):
            if not self.window:
                if not self.backend:
                    self.backend = GPGBackend()
                self.window = MainWindow(self, self.backend)
            self.window.present()

        def _on_shutdown(self, app):
            # Don't leave unlocked keys cached in gpg-agent after the app quits.
            if self.backend:
                self.backend.clear_agent_cache()

        def _on_open(self, app, files, n_files, hint):
            # Files passed by the desktop ("Open With GPGMan") or the command line.
            self._on_activate(app)
            for f in files:
                path = f.get_path()
                if path:
                    self.window.open_asc_file(path)

    app = GpgManApplication()
    paths = [a for a in argv[1:] if not a.startswith("-") and os.path.isfile(a)]
    return app.run([argv[0]] + paths)


def main(argv=None):
    if argv is None:
        argv = sys.argv

    # Check invocation name (e.g. gpgman-cli)
    invoked_name = os.path.basename(argv[0]).lower()
    force_cli = "cli" in invoked_name

    # Check version flag
    if len(argv) > 1 and argv[1] in ("-v", "--version"):
        print(f"GPGMan v{__version__} (Dual-Style GUI & CLI Suite)")
        return 0

    # Explicit GUI flag
    if "--gui" in argv or "-g" in argv:
        clean_argv = [a for a in argv if a not in ("--gui", "-g")]
        return run_gui(clean_argv)

    # Check CLI subcommands or flags
    cli_subcommands = {
        "interactive", "keys", "key-generate", "key-import", "key-export",
        "key-delete", "encrypt-text", "decrypt-text", "encrypt-file",
        "decrypt-file", "clearsign", "verify", "checksum", "system",
    }

    has_cli_flag = any(a in ("--cli", "-c", "cli") for a in argv[1:])
    has_subcommand = any(a in cli_subcommands for a in argv[1:])

    if force_cli or has_cli_flag or has_subcommand:
        from gpgman.cli import build_cli_parser, run_cli_args
        clean_argv = [a for a in argv[1:] if a not in ("--cli", "-c")]
        if not clean_argv:
            clean_argv = ["interactive"]
        parser = build_cli_parser()
        args = parser.parse_args(clean_argv)
        return run_cli_args(args)

    # If other arguments (e.g. --help)
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        from gpgman.cli import build_cli_parser
        parser = build_cli_parser()
        parser.print_help()
        return 0

    # No arguments provided:
    # Check if a graphical display environment is available
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if has_display:
        try:
            return run_gui(argv)
        except Exception as exc:
            print(f"[GPGMan] Graphical interface failed to launch ({exc}). Falling back to CLI...", file=sys.stderr)
            from gpgman.cli import GPGManCLI
            cli = GPGManCLI()
            cli.run_interactive()
            return 0
    else:
        print("[GPGMan] No graphical display detected. Launching interactive terminal CLI...")
        from gpgman.cli import GPGManCLI
        cli = GPGManCLI()
        cli.run_interactive()
        return 0


if __name__ == "__main__":
    sys.exit(main())

