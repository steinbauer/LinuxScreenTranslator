"""Store the DeepL key in the GNOME keyring through libsecret.

This keeps the key out of the configuration file. When no keyring is
available the caller falls back to config.json (mode 600).
"""

import gi

try:
    gi.require_version("Secret", "1")
    from gi.repository import Secret
    AVAILABLE = True
except (ValueError, ImportError):
    AVAILABLE = False

_ATTR = {"key": "deepl_api_key"}
_LABEL = "Linux Screen Translator — DeepL API key"

if AVAILABLE:
    _ATTRIBUTES = {"key": Secret.SchemaAttributeType.STRING}
    _SCHEMA = Secret.Schema.new(
        "cz.polyweb.LinuxScreenTranslator", Secret.SchemaFlags.NONE, _ATTRIBUTES
    )
    # The schema used before the project was renamed.
    _LEGACY_SCHEMA = Secret.Schema.new(
        "cz.polyweb.translatorscreener", Secret.SchemaFlags.NONE, _ATTRIBUTES
    )


def store(api_key):
    if not AVAILABLE:
        return False
    return Secret.password_store_sync(
        _SCHEMA, _ATTR, Secret.COLLECTION_DEFAULT, _LABEL, api_key, None
    )


def lookup():
    if not AVAILABLE:
        return None
    stored = Secret.password_lookup_sync(_SCHEMA, _ATTR, None)
    if stored:
        return stored
    return _adopt_legacy()


def _adopt_legacy():
    """Move a key stored under the pre-rename schema across.

    The old entry is only cleared once the new one has been read back, so a
    failure part way through leaves the key where it was rather than losing it.
    """
    legacy = Secret.password_lookup_sync(_LEGACY_SCHEMA, _ATTR, None)
    if not legacy:
        return None
    if store(legacy) and Secret.password_lookup_sync(_SCHEMA, _ATTR, None) == legacy:
        Secret.password_clear_sync(_LEGACY_SCHEMA, _ATTR, None)
    return legacy


def clear():
    if not AVAILABLE:
        return False
    return Secret.password_clear_sync(_SCHEMA, _ATTR, None)
