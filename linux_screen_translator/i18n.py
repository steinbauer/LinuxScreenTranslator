"""Translation setup.

English is the source language of every user-visible string. Other languages
live as .po catalogues under po/ and are compiled into locale/ at install time.
"""

import gettext
import os

DOMAIN = "linux-screen-translator"
LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locale"
)

# fallback=True keeps the app running in English when no catalogue is built.
_translation = gettext.translation(DOMAIN, LOCALE_DIR, fallback=True)
_ = _translation.gettext

# The user-visible product name, in one place.
APP_NAME = _("Linux Screen Translator")
