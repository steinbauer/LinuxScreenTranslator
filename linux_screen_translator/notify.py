"""Desktop notifications over the freedesktop D-Bus interface.

Used when the result window may not be the focused window, so the outcome is
noticed even if the window ends up behind something else.
"""

from gi.repository import Gio, GLib

from .i18n import APP_NAME

BUS = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"


def send(summary, body="", icon="linux-screen-translator-symbolic", timeout_ms=5000):
    """Post a notification. Never raises: a missing daemon must not break a run."""
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        connection.call_sync(
            BUS, PATH, BUS, "Notify",
            GLib.Variant("(susssasa{sv}i)",
                         (APP_NAME, 0, icon, summary, body, [], {}, timeout_ms)),
            None, Gio.DBusCallFlags.NONE, -1, None,
        )
        return True
    except GLib.Error:
        return False
