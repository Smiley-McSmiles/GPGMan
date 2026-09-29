"""
Dialog Utilities - Standard Libadwaita / GTK4 modal dialog configuration.
Enforces ESC-to-close on all popup windows and prevents Cinnamon window manager
(Muffin) from resizing/enlarging modal dialogs on focus changes.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, Gtk


def setup_modal_window(window: Gtk.Window) -> None:
    """
    Configure a popup/modal window with standard Libadwaita behaviors:
    1. Close immediately when pressing the ESC key.
    2. Disable arbitrary resizing to prevent Cinnamon / Muffin from expanding
       the window when clicking outside or changing focus.
    3. Ensure destroy-with-parent and modal flags are correctly bound.
    """
    window.set_modal(True)
    window.set_destroy_with_parent(True)
    # Cinnamon's Muffin expands modal windows on blur if resizable is True
    window.set_resizable(False)

    # Attach key event controller for ESC key
    controller = Gtk.EventControllerKey.new()

    def _on_key_pressed(ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            window.close()
            return True
        return False

    controller.connect("key-pressed", _on_key_pressed)
    window.add_controller(controller)
