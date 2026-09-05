"""Whether the tray icon comes back after a login.

The installer writes an autostart entry, but that is a decision made once at
install time. This lets it be undone, and redone, from the settings.
"""

import os
import subprocess
import sys

ENTRY = "cz.polyweb.LinuxScreenTranslator.tray.desktop"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, ENTRY)
TRAY = os.path.join(ROOT, "tray.py")
ICON = os.path.join(ROOT, "icons", "linux-screen-translator-symbolic.svg")

AUTOSTART_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "autostart"
)
TARGET = os.path.join(AUTOSTART_DIR, ENTRY)


def _python():
    """The interpreter the tray should run under — the venv one if there is one."""
    candidate = os.path.join(ROOT, ".venv", "bin", "python")
    return candidate if os.path.exists(candidate) else sys.executable


def is_enabled():
    """A file removed or disabled by hand counts, so the switch reflects reality."""
    try:
        with open(TARGET, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return False
    return "X-GNOME-Autostart-enabled=false" not in content


def is_running():
    """Whether a tray process of this installation is already up.

    The autostart entry runs it by absolute path, but started from a shell it
    is usually a relative one, so the working directory has to be checked too
    — otherwise a running icon goes unnoticed and a second one is started.
    """
    script = os.path.basename(TRAY)
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as fh:
                command = fh.read().decode("utf-8", "replace")
        except OSError:
            continue  # the process ended while we looked
        if TRAY in command:
            return True
        if script in command:
            try:
                if os.path.realpath(f"/proc/{entry}/cwd") == os.path.realpath(ROOT):
                    return True
            except OSError:
                continue
    return False


def enable(start_now=True):
    """Write the autostart entry, and bring the icon up straight away."""
    try:
        with open(TEMPLATE, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return False

    content = content.replace("REPLACED_BY_INSTALL", f"{_python()} {TRAY}")
    content = content.replace("REPLACED_BY_ICON", ICON)
    try:
        os.makedirs(AUTOSTART_DIR, exist_ok=True)
        with open(TARGET, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError:
        return False

    # Waiting for the next login to see the icon would make the switch feel
    # broken, so start it now unless it is already there.
    if start_now and not is_running():
        subprocess.Popen([_python(), TRAY], cwd=ROOT, start_new_session=True)
    return True


def disable():
    try:
        os.remove(TARGET)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True
