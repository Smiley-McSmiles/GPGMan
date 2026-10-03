"""
Passphrase Prompt - desktop-environment agnostic passphrase dialog.

GnuPG normally asks for passphrases through the system pinentry, which only
works when a matching pinentry front-end is installed (e.g. pinentry-gnome3).
GPGMan instead collects the passphrase itself and hands it to gpg via
loopback pinentry. On GNOME a Libadwaita dialog is used; everywhere else a
plain GTK4 window is shown so Libadwaita widgets are never required.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk


def is_gnome_session() -> bool:
    """True when running under GNOME (XDG_CURRENT_DESKTOP / DESKTOP_SESSION)."""
    desktops = os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    if "GNOME" in desktops:
        return True
    return "GNOME" in os.environ.get("DESKTOP_SESSION", "").upper()


def _prompt_adw(parent, heading, body, on_result) -> bool:
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Adw
        dialog = Adw.MessageDialog(transient_for=parent, heading=heading, body=body)
    except (ValueError, ImportError, AttributeError):
        return False

    entry = Gtk.PasswordEntry(show_peek_icon=True, activates_default=True)
    entry.set_hexpand(True)
    dialog.set_extra_child(entry)
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("ok", "Unlock")
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("ok")
    dialog.set_close_response("cancel")

    def on_resp(_, resp):
        on_result(entry.get_text() if resp == "ok" else None)

    dialog.connect("response", on_resp)
    dialog.present()
    GLib.idle_add(entry.grab_focus)
    return True


def _prompt_gtk(parent, heading, body, on_result) -> None:
    win = Gtk.Window(transient_for=parent, modal=True, title=heading, resizable=False)
    win.set_destroy_with_parent(True)
    win.set_default_size(380, -1)
    state = {"done": False}

    def finish(value: Optional[str]):
        if state["done"]:
            return
        state["done"] = True
        win.destroy()
        on_result(value)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(18)

    title = Gtk.Label(label=heading, xalign=0, wrap=True)
    title.add_css_class("title-3")
    box.append(title)
    box.append(Gtk.Label(label=body, xalign=0, wrap=True))

    entry = Gtk.PasswordEntry(show_peek_icon=True)
    entry.connect("activate", lambda e: finish(e.get_text()))
    box.append(entry)

    buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
    cancel = Gtk.Button(label="Cancel")
    cancel.connect("clicked", lambda _: finish(None))
    ok = Gtk.Button(label="Unlock")
    ok.add_css_class("suggested-action")
    ok.connect("clicked", lambda _: finish(entry.get_text()))
    buttons.append(cancel)
    buttons.append(ok)
    box.append(buttons)

    key_ctrl = Gtk.EventControllerKey.new()
    key_ctrl.connect(
        "key-pressed",
        lambda c, keyval, *_: (finish(None), True)[1] if keyval == Gdk.KEY_Escape else False,
    )
    win.add_controller(key_ctrl)
    win.connect("close-request", lambda _: (finish(None), False)[1])
    win.set_child(box)
    win.set_default_widget(ok)
    win.present()
    entry.grab_focus()


def ask_passphrase(
    parent: Gtk.Window,
    heading: str,
    body: str,
    on_result: Callable[[Optional[str]], None],
) -> None:
    """Prompt for a passphrase; on_result gets the text, or None if cancelled."""
    if is_gnome_session() and _prompt_adw(parent, heading, body, on_result):
        return
    _prompt_gtk(parent, heading, body, on_result)
