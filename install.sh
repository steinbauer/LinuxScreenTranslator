#!/usr/bin/env bash
# Install Linux Screen Translator for the current user. Nothing goes outside $HOME,
# so no sudo is required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
APPS="$HOME/.local/share/applications"
AUTOSTART="$HOME/.config/autostart"
METAINFO="$HOME/.local/share/metainfo"
ICON="$ROOT/icons/linux-screen-translator-symbolic.svg"
APP_ID="cz.polyweb.LinuxScreenTranslator"

echo "==> Preparing the virtual environment"
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv --system-site-packages "$VENV"
else
    # GTK and PyGObject come from the system, so the venv must see them.
    sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' \
        "$VENV/pyvenv.cfg"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$ROOT/requirements.txt"

echo "==> Checking system dependencies"
# GTK4 and AppIndicator (which is built on GTK3) have to be probed in separate
# processes: two GTK versions cannot coexist in one.
MISSING=""
"$VENV/bin/python" -c "
import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')
from gi.repository import Gtk, Adw
" 2>/dev/null || MISSING="$MISSING gir1.2-gtk-4.0 gir1.2-adw-1"

"$VENV/bin/python" -c "
import gi; gi.require_version('AyatanaAppIndicator3','0.1')
from gi.repository import AyatanaAppIndicator3
" 2>/dev/null || MISSING="$MISSING gir1.2-ayatanaappindicator3-0.1"

if [ -n "$MISSING" ]; then
    echo "  Missing:$MISSING"
    echo "  Install with: sudo apt install python3-gi$MISSING"
    exit 1
fi
echo "  All present."

echo "==> Building translation catalogues"
python3 "$ROOT/tools/i18n_tools.py" compile | sed 's/^/  /'

echo "==> Installing launchers"
mkdir -p "$APPS" "$AUTOSTART" "$METAINFO"
# Leftovers from an earlier naming, so the menu does not list it twice.
rm -f "$APPS/translatorscreener.desktop" "$AUTOSTART/translatorscreener-tray.desktop" \
       "$APPS/cz.polyweb.translatorScreener.desktop" \
       "$AUTOSTART/cz.polyweb.translatorScreener.tray.desktop"

sed -e "s|REPLACED_BY_INSTALL|$VENV/bin/python $ROOT/main.py|" \
    -e "s|REPLACED_BY_ICON|$ICON|" \
    "$ROOT/$APP_ID.desktop" > "$APPS/$APP_ID.desktop"
sed -e "s|REPLACED_BY_INSTALL|$VENV/bin/python $ROOT/tray.py|" \
    -e "s|REPLACED_BY_ICON|$ICON|" \
    "$ROOT/$APP_ID.tray.desktop" > "$AUTOSTART/$APP_ID.tray.desktop"
cp "$ROOT/$APP_ID.metainfo.xml" "$METAINFO/"
update-desktop-database "$APPS" 2>/dev/null || true

echo "==> Binding Ctrl+Print"
BASE="org.gnome.settings-daemon.plugins.media-keys"
PATHSPEC="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/translatorscreener/"
CURRENT="$(gsettings get $BASE custom-keybindings)"
if [[ "$CURRENT" != *"translatorscreener"* ]]; then
    if [[ "$CURRENT" == "@as []" || "$CURRENT" == "[]" ]]; then
        gsettings set $BASE custom-keybindings "['$PATHSPEC']"
    else
        gsettings set $BASE custom-keybindings "${CURRENT%]}, '$PATHSPEC']"
    fi
fi
KEY="$BASE.custom-keybinding:$PATHSPEC"
gsettings set "$KEY" name "Linux Screen Translator"
gsettings set "$KEY" command "$VENV/bin/python $ROOT/main.py"
gsettings set "$KEY" binding "<Control>Print"

echo
echo "Done."
echo "  • Ctrl+Print     translate a screen area"
echo "  • tray icon      appears after the next login, or start it now with:"
echo "                   $VENV/bin/python $ROOT/tray.py &"
echo "  • settings       $VENV/bin/python $ROOT/main.py --settings"
