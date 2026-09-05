"""Pick a typeface that can actually draw the target language.

DejaVu covers Latin, Cyrillic and Greek, which is most of what DeepL offers,
but it has no CJK, Arabic, Hebrew, Devanagari or Thai glyphs at all — asking
it for those draws rows of empty boxes rather than failing, so the choice has
to be made before rendering rather than discovered afterwards.
"""

import os

DEFAULT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Target language prefixes that need a typeface of their own.
SCRIPT_FONTS = (
    (("JA", "ZH", "KO"), "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    (("AR",), "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"),
    (("HE",), "/usr/share/fonts/truetype/noto/NotoSansHebrew-Bold.ttf"),
    (("HI", "MR", "NE"), "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
    (("TH",), "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf"),
)

FALLBACKS = (
    DEFAULT,
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def for_language(target_lang, configured=""):
    """Font for this target language; `configured` overrides when set."""
    if configured:
        return configured

    base = (target_lang or "").split("-")[0].upper()
    for languages, path in SCRIPT_FONTS:
        if base in languages and os.path.exists(path):
            return path

    for path in FALLBACKS:
        if os.path.exists(path):
            return path
    raise RuntimeError("no usable font found")
