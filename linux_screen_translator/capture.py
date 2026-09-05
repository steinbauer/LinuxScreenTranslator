"""Screen capture through the XDG Desktop Portal.

The portal is the only route that works on both Wayland and X11 — a Wayland
compositor deliberately denies direct access to the framebuffer.
"""

import random
import string

from gi.repository import Gio, GLib

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
REQUEST_IFACE = "org.freedesktop.portal.Request"


def _token():
    return "ts_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))


def _request_path(connection, token):
    """The path the portal will answer on.

    We have to subscribe before calling the method, otherwise the response
    signal can arrive before we are listening.
    """
    sender = connection.get_unique_name()[1:].replace(".", "_")
    return f"{PORTAL_PATH}/request/{sender}/{token}"


def take_screenshot(interactive=True, parent_window="", timeout_ms=120_000):
    """Return the path of the captured file, or None if the user cancelled.

    interactive=True opens the desktop's own area selection UI.
    """
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    token = _token()
    path = _request_path(connection, token)

    loop = GLib.MainLoop()
    result = {"uri": None, "code": None}

    def on_response(_conn, _sender, _path, _iface, _signal, params):
        result["code"], response = params.unpack()
        result["uri"] = response.get("uri")
        loop.quit()

    subscription = connection.signal_subscribe(
        PORTAL_BUS, REQUEST_IFACE, "Response", path, None,
        Gio.DBusSignalFlags.NONE, on_response,
    )

    # Safety net so the app cannot hang forever if the portal never answers.
    timeout_id = GLib.timeout_add(timeout_ms, lambda: (loop.quit(), False)[1])

    try:
        connection.call_sync(
            PORTAL_BUS, PORTAL_PATH, SCREENSHOT_IFACE, "Screenshot",
            GLib.Variant("(sa{sv})", (parent_window, {
                "handle_token": GLib.Variant("s", token),
                "interactive": GLib.Variant("b", interactive),
            })),
            GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None,
        )
        loop.run()
    finally:
        GLib.source_remove(timeout_id)
        connection.signal_unsubscribe(subscription)

    # code 0 = success, 1 = cancelled by the user, 2 = other failure
    if result["code"] != 0 or not result["uri"]:
        return None
    return Gio.File.new_for_uri(result["uri"]).get_path()
