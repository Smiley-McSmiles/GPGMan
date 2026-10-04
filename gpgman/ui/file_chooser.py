"""
File Chooser Helper - In-process GTK FileChooserDialog with desktop fallback.

Uses GTK's native built-in Gtk.FileChooserDialog directly. This runs in-process
and avoids relying on xdg-desktop-portal-gnome / Nautilus (which crashes to
desktop on Cinnamon and other non-GNOME environments when Nautilus is absent).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from typing import Callable, List, Optional, Tuple

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk


def _in_flatpak() -> bool:
    return os.path.exists("/.flatpak-info")


def _open_portal_file_dialog(
    parent: Optional[Gtk.Window],
    title: str,
    action: Gtk.FileChooserAction,
    filters: Optional[List[Tuple[str, List[str]]]],
    default_name: Optional[str],
    current_folder: Optional[str],
    on_selected: Optional[Callable[[str], None]],
) -> None:
    """Gtk.FileDialog; inside a Flatpak sandbox this goes through the file chooser portal,
    so the app does not need broad filesystem access."""
    dialog = Gtk.FileDialog()
    dialog.set_title(title)
    if filters:
        store = Gio.ListStore.new(Gtk.FileFilter)
        for filter_name, patterns in filters:
            f = Gtk.FileFilter()
            f.set_name(filter_name)
            for pat in patterns:
                f.add_pattern(pat)
            store.append(f)
        dialog.set_filters(store)
    if default_name and action == Gtk.FileChooserAction.SAVE:
        dialog.set_initial_name(default_name)
    if current_folder and os.path.isdir(current_folder):
        dialog.set_initial_folder(Gio.File.new_for_path(current_folder))

    transient = parent if isinstance(parent, Gtk.Window) else None

    def done(d, result):
        try:
            if action == Gtk.FileChooserAction.SAVE:
                gfile = d.save_finish(result)
            elif action == Gtk.FileChooserAction.SELECT_FOLDER:
                gfile = d.select_folder_finish(result)
            else:
                gfile = d.open_finish(result)
        except GLib.Error:
            return  # cancelled or dismissed
        path = gfile.get_path() if gfile else None
        if path and on_selected:
            on_selected(path)

    if action == Gtk.FileChooserAction.SAVE:
        dialog.save(transient, None, done)
    elif action == Gtk.FileChooserAction.SELECT_FOLDER:
        dialog.select_folder(transient, None, done)
    else:
        dialog.open(transient, None, done)


def choose_file(
    parent: Optional[Gtk.Window],
    title: str,
    action: Gtk.FileChooserAction = Gtk.FileChooserAction.OPEN,
    filters: Optional[List[Tuple[str, List[str]]]] = None,
    default_name: Optional[str] = None,
    current_folder: Optional[str] = None,
    on_selected: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Open the file selection dialog.
    In a Flatpak sandbox: Gtk.FileDialog via the file chooser portal.
    Otherwise primary: Gtk.FileChooserDialog (self-contained within GTK4, reliable across Cinnamon,
             MATE, XFCE, GNOME without requiring Nautilus or portals).
    Fallback: System dialog utilities (zenity or kdialog) if available.
    """
    if _in_flatpak() and hasattr(Gtk, "FileDialog"):
        try:
            _open_portal_file_dialog(parent, title, action, filters, default_name, current_folder, on_selected)
            return
        except Exception as exc:
            print(f"[GPGMan] Portal file dialog error: {exc}. Falling back to Gtk.FileChooserDialog...")
    try:
        _open_gtk_file_chooser_dialog(
            parent=parent,
            title=title,
            action=action,
            filters=filters,
            default_name=default_name,
            current_folder=current_folder,
            on_selected=on_selected,
        )
    except Exception as exc:
        print(f"[GPGMan] Gtk.FileChooserDialog error: {exc}. Trying system CLI dialog...")
        _fallback_external_file_chooser(
            title=title,
            action=action,
            filters=filters,
            default_name=default_name,
            current_folder=current_folder,
            on_selected=on_selected,
        )


def _open_gtk_file_chooser_dialog(
    parent: Optional[Gtk.Window],
    title: str,
    action: Gtk.FileChooserAction,
    filters: Optional[List[Tuple[str, List[str]]]],
    default_name: Optional[str],
    current_folder: Optional[str],
    on_selected: Optional[Callable[[str], None]],
) -> None:
    accept_label = "_Save" if action == Gtk.FileChooserAction.SAVE else "_Open"
    if action == Gtk.FileChooserAction.SELECT_FOLDER:
        accept_label = "_Select Folder"

    transient = parent if (parent is not None and isinstance(parent, Gtk.Window)) else None

    dialog = Gtk.FileChooserDialog(
        title=title,
        transient_for=transient,
        action=action,
    )
    dialog.add_buttons(
        "_Cancel", Gtk.ResponseType.CANCEL,
        accept_label, Gtk.ResponseType.ACCEPT,
    )
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    dialog.set_modal(True)

    if default_name and action == Gtk.FileChooserAction.SAVE:
        try:
            dialog.set_current_name(default_name)
        except Exception:
            pass

    if current_folder and os.path.isdir(current_folder):
        try:
            dialog.set_current_folder(Gio.File.new_for_path(current_folder))
        except Exception:
            pass

    if filters:
        for filter_name, patterns in filters:
            f = Gtk.FileFilter()
            f.set_name(filter_name)
            for p in patterns:
                f.add_pattern(p)
            dialog.add_filter(f)

    def on_response(d, response_id: int):
        selected_path = None
        try:
            if response_id == Gtk.ResponseType.ACCEPT:
                gfile = d.get_file()
                if gfile:
                    selected_path = gfile.get_path()
        except Exception as err:
            print(f"[GPGMan] Error retrieving file path: {err}")
        finally:
            d.destroy()

        if selected_path and on_selected:
            on_selected(selected_path)

    dialog.connect("response", on_response)
    dialog.present()


def _fallback_external_file_chooser(
    title: str,
    action: Gtk.FileChooserAction,
    filters: Optional[List[Tuple[str, List[str]]]],
    default_name: Optional[str],
    current_folder: Optional[str],
    on_selected: Optional[Callable[[str], None]],
) -> None:
    """Invokes zenity or kdialog as a fallback if GTK dialog is unavailable."""
    zenity_bin = shutil.which("zenity")
    kdialog_bin = shutil.which("kdialog")

    def worker():
        path = None
        if zenity_bin:
            cmd = [zenity_bin, "--file-selection", f"--title={title}"]
            if action == Gtk.FileChooserAction.SAVE:
                cmd.extend(["--save", "--confirm-overwrite"])
            elif action == Gtk.FileChooserAction.SELECT_FOLDER:
                cmd.append("--directory")
            if default_name:
                cmd.append(f"--filename={default_name}")
            if filters:
                for fname, patterns in filters:
                    pat_str = " ".join(patterns)
                    cmd.append(f"--file-filter={fname} | {pat_str}")
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc.returncode == 0:
                    path = proc.stdout.strip()
            except Exception as e:
                print(f"[GPGMan] zenity fallback failed: {e}")
        elif kdialog_bin:
            cmd = [kdialog_bin, f"--title={title}"]
            if action == Gtk.FileChooserAction.SAVE:
                cmd.append("--getsavefilename")
                cmd.append(default_name or ".")
            elif action == Gtk.FileChooserAction.SELECT_FOLDER:
                cmd.append("--getexistingdirectory")
            else:
                cmd.append("--getopenfilename")
                cmd.append(current_folder or ".")
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc.returncode == 0:
                    path = proc.stdout.strip()
            except Exception as e:
                print(f"[GPGMan] kdialog fallback failed: {e}")

        if path and on_selected:
            GLib.idle_add(on_selected, path)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
