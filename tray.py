#!/usr/bin/env python3
"""The status icon in the top bar.

This runs as its own process: AyatanaAppIndicator3 is built on GTK3 while the
windows use GTK4, and the two GTK versions cannot share a process.
"""

import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator, Gtk  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from translatorscreener.i18n import APP_NAME, _  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(ROOT, ".venv", "bin", "python")
MAIN = os.path.join(ROOT, "main.py")


def launch(*args):
    """Start the main app in the background so the icon stays responsive."""
    subprocess.Popen([PYTHON if os.path.exists(PYTHON) else sys.executable, MAIN, *args],
                     cwd=ROOT, start_new_session=True)


def build_menu():
    menu = Gtk.Menu()
    for label, args in ((_("Translate an area…"), ()), (_("Settings…"), ("--settings",))):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", lambda _item, a=args: launch(*a))
        menu.append(item)

    menu.append(Gtk.SeparatorMenuItem())
    quit_item = Gtk.MenuItem(label=_("Quit"))
    quit_item.connect("activate", lambda _item: Gtk.main_quit())
    menu.append(quit_item)

    menu.show_all()
    return menu


def main():
    indicator = AppIndicator.Indicator.new_with_path(
        "linux-screen-translator", "linux-screen-translator-symbolic",
        AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        os.path.join(ROOT, "icons"),
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    indicator.set_title(APP_NAME)
    menu = build_menu()
    indicator.set_menu(menu)
    # A middle click on the icon starts a translation straight away.
    indicator.set_secondary_activate_target(menu.get_children()[0])
    Gtk.main()


if __name__ == "__main__":
    main()
