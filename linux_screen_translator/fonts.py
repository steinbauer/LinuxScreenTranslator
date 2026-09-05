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


# A short piece of the target script, used to check a font really covers it.
SAMPLES = {
    "JA": "日本語のテキスト", "ZH": "中文文本", "KO": "한국어 텍스트",
    "AR": "نص عربي", "HE": "טקסט עברי", "HI": "हिन्दी पाठ", "TH": "ข้อความไทย",
    "RU": "Пример текста", "UK": "Зразок тексту", "BG": "Примерен текст",
    "EL": "Δείγμα κειμένου",
}
DEFAULT_SAMPLE = "Sample áéíóú ñ ř ž ő"

# A private-use codepoint no font defines, so it always draws the placeholder.
_NOTDEF = ""


def sample_for(target_lang):
    return SAMPLES.get((target_lang or "").split("-")[0].upper(), DEFAULT_SAMPLE)


def _bitmap(font, character):
    from PIL import Image, ImageDraw
    image = Image.new("L", (64, 64), 0)
    ImageDraw.Draw(image).text((4, 4), character, font=font, fill=255)
    return image.tobytes()


def can_render(font_path, text):
    """Whether the font really has these glyphs.

    A font missing a character does not fail — it draws a placeholder box, so
    the page comes out full of empty rectangles with nothing reported. The
    only reliable test is to compare against a codepoint no font defines: if
    a character draws the same thing, the font does not have it.
    """
    from PIL import ImageFont
    try:
        font = ImageFont.truetype(font_path, 24)
    except (OSError, ValueError):
        return False

    placeholder = _bitmap(font, _NOTDEF)
    characters = [c for c in dict.fromkeys(text) if not c.isspace()][:12]
    return all(_bitmap(font, c) != placeholder for c in characters)
