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
    _SCHEMA = Secret.Schema.new(
        "cz.polyweb.translatorscreener",
        Secret.SchemaFlags.NONE,
        {"key": Secret.SchemaAttributeType.STRING},
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
    return Secret.password_lookup_sync(_SCHEMA, _ATTR, None)


def clear():
    if not AVAILABLE:
        return False
    return Secret.password_clear_sync(_SCHEMA, _ATTR, None)
