"""
Caps Lock hint for password fields.

Shows a subtle "Caps Lock is on" note while a password field has focus and Caps Lock is active.
Works on X11 and Wayland through Gdk's keyboard device state (no key-event guessing).
"""

from __future__ import annotations

from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # no Libadwaita import: the non-GNOME passphrase prompt must stay GTK-only

HINT_TEXT = "Caps Lock is on"


def watch_caps_lock(widget: Gtk.Widget, on_change: Callable[[bool], None]) -> None:
    """Call ``on_change(True/False)`` whenever "Caps Lock is on AND the widget has focus" changes."""
    display = widget.get_display()
    seat = display.get_default_seat() if display else None
    keyboard = seat.get_keyboard() if seat else None
    if keyboard is None:
        return

    focus = Gtk.EventControllerFocus.new()
    widget.add_controller(focus)
    last = {"state": None}

    def update(*_args):
        state = bool(keyboard.get_caps_lock_state()) and bool(focus.get_contains_focus())
        if state != last["state"]:
            last["state"] = state
            on_change(state)

    handler = keyboard.connect("notify::caps-lock-state", update)
    focus.connect("notify::contains-focus", update)
    # Don't keep a dead widget alive through the long-lived keyboard device.
    widget.connect("destroy", lambda _w: keyboard.disconnect(handler))
    update()


def attach_caps_lock_hint(row: Gtk.Widget) -> None:
    """For an Adw.PasswordEntryRow: append "· Caps Lock is on" to its floating title while it applies."""
    base_title = row.get_title()

    def on_change(on: bool) -> None:
        row.set_title(f"{base_title} · {HINT_TEXT}" if on else base_title)
        if on:
            row.add_css_class("warning")
        else:
            row.remove_css_class("warning")

    watch_caps_lock(row, on_change)


def make_caps_lock_label(entry: Gtk.Widget) -> Gtk.Label:
    """A small dim label (hidden until needed) to place under a plain Gtk.PasswordEntry."""
    label = Gtk.Label(label=HINT_TEXT, xalign=0, visible=False)
    label.add_css_class("caption")
    label.add_css_class("warning")
    watch_caps_lock(entry, label.set_visible)
    return label
