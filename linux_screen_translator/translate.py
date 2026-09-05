"""Translation backends: DeepL, plus a mock used to test without a key."""

import unicodedata
from dataclasses import dataclass

import requests

from .i18n import _

DEEPL_FREE = "https://api-free.deepl.com/v2/translate"
DEEPL_PRO = "https://api.deepl.com/v2/translate"

# Cheap hints that a block is already in the target language, so that it never
# reaches the API and never costs quota. Add an entry to support a language.
#
# "chars" are letters the language has and English does not. Those alone are
# not enough: OCR runs an English/Chinese model that tends to swallow
# diacritics ("Hlavní stránka" comes back as "Hlavni stranka"), so "words"
# lists common function words that are not also English words — deliberately
# without the likes of "to", "do" or "a", which mean something else in English.
TARGET_HINTS = {
    "CS": {
        "chars": set("ěščřžůťďňĚŠČŘŽŮŤĎŇ"),
        "words": {
            "se", "ze", "nez", "uz", "jak", "kdyz", "ktery", "ktera", "ktere",
            "jsem", "jsou", "jsme", "jste", "byl", "byla", "bylo", "bude",
            "budou", "neni", "vas", "vam", "sve", "svuj", "ale", "nebo",
            "jeste", "pro", "pri", "tak", "protoze", "takze", "podle", "mezi",
            "proti", "bez", "pred", "nad", "pod", "kde", "kdo", "jako",
            "vsak", "ted", "vice", "muze", "musi", "chce", "si", "jen",
            "uzivatel", "uzivatele", "prave", "hlavni", "stranka",
        },
    },
    "ES": {
        "chars": set("ñÑ¿¡"),
        "words": {
            "que", "los", "las", "una", "por", "con", "para", "esta", "pero",
            "como", "todo", "desde", "cuando", "porque", "sobre", "muy", "del",
            "ya", "está", "más", "también", "hay",
        },
    },
    "DE": {
        "chars": set("äöüßÄÖÜ"),
        "words": {
            "und", "der", "die", "das", "nicht", "mit", "ist", "ein", "eine",
            "auch", "aber", "wenn", "wie", "noch", "schon", "werden", "haben",
            "sich", "einen", "einer", "mehr",
        },
    },
    "FR": {
        "chars": set("àâçéèêëîïôùûÀÂÇÉÈÊ"),
        "words": {
            "que", "les", "des", "une", "pour", "dans", "avec", "est", "sont",
            "mais", "comme", "tout", "plus", "cette", "être", "fait", "vous",
            "nous", "sur", "pas",
        },
    },
}


class TranslationError(RuntimeError):
    pass


def group_digits(number):
    """1240 -> "1 240". A plain space reads the same in every language."""
    return f"{number:,}".replace(",", "\u00a0")


@dataclass
class Usage:
    """What the translation service says about the account's allowance."""

    ok: bool
    message: str
    used: int = 0
    limit: int = 0

    @property
    def fraction(self):
        return min(1.0, self.used / self.limit) if self.limit else 0.0

    @property
    def remaining(self):
        return max(0, self.limit - self.used)


@dataclass
class Translation:
    """The result for a single block."""

    text: str
    detected: str = ""      # language the backend detected

    def same_as(self, original):
        return self.text.strip().casefold() == original.strip().casefold()


def is_shouty(text):
    """True for text set entirely in capitals, with at least two letters."""
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 2 and all(ch.isupper() for ch in letters)


def base_lang(code):
    """Turn "EN-GB" into "EN" so languages can be compared."""
    return (code or "").split("-")[0].upper()


def fold(text):
    """Strip accents, so a word matches whether or not it carries them.

    The word lists are written without diacritics. That used to be enough
    because the recogniser dropped accents anyway; now that it keeps them,
    both sides have to be folded or nothing matches.
    """
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def looks_like_target(text, target_lang, min_hits=2):
    """Cheap guess whether the text already is in the target language.

    This only saves quota; the backend's own detector has the final say on
    whatever slips through.
    """
    hints = TARGET_HINTS.get(base_lang(target_lang))
    if not hints:
        return False
    if any(ch in hints["chars"] for ch in text):
        return True
    wanted = {fold(w) for w in hints["words"]}
    words = [fold(w.strip(".,:;!?()[]\"'„“").lower()) for w in text.split()]
    return sum(1 for w in words if w in wanted) >= min_hits


class DeepLTranslator:
    def __init__(self, api_key, target_lang="CS", source_lang=""):
        if not api_key:
            raise TranslationError(_("No DeepL API key has been set."))
        self.api_key = api_key
        self.target_lang = target_lang
        self.source_lang = source_lang
        # Free-tier keys end in ":fx" and use a different endpoint.
        self.endpoint = DEEPL_FREE if api_key.rstrip().endswith(":fx") else DEEPL_PRO

    def translate(self, texts):
        """Translate a list of strings in one request, preserving order.

        Blocks that already are in the target language are not sent and come
        back unchanged.
        """
        if not texts:
            return []

        send = [i for i, text in enumerate(texts)
                if not looks_like_target(text, self.target_lang)]
        results = [Translation(text=t, detected=base_lang(self.target_lang)) for t in texts]
        if not send:
            return results

        # Capitals confuse the translator: "TAREK" comes back as a verb, and a
        # shouted sentence translates worse than the same words in ordinary
        # case. Send them cased normally and shout the result instead.
        shouty = {i for i in send if is_shouty(texts[i])}
        payload = [texts[i].capitalize() if i in shouty else texts[i] for i in send]

        data = {"text": payload, "target_lang": self.target_lang}
        if self.source_lang:
            data["source_lang"] = self.source_lang
        try:
            response = requests.post(
                self.endpoint,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                data=data,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise TranslationError(_("DeepL is unreachable: {error}").format(error=exc)) from exc

        if response.status_code == 403:
            raise TranslationError(_("DeepL rejected the key (403). Check your API key."))
        if response.status_code == 456:
            raise TranslationError(_("The monthly DeepL quota is used up (456)."))
        if response.status_code != 200:
            raise TranslationError(
                _("DeepL returned {status}: {body}").format(
                    status=response.status_code, body=response.text[:200])
            )

        for index, item in zip(send, response.json()["translations"]):
            text = item["text"].upper() if index in shouty else item["text"]
            results[index] = Translation(
                text=text,
                detected=base_lang(item.get("detected_source_language", "")),
            )
        return results


class MockTranslator:
    """Does not translate, only marks the text — used to exercise the pipeline."""

    def __init__(self, target_lang="CS", **_kwargs):
        self.target_lang = target_lang

    def translate(self, texts):
        return [
            Translation(text=t, detected=base_lang(self.target_lang))
            if looks_like_target(t, self.target_lang)
            else Translation(text=f"«{t}»", detected="EN")
            for t in texts
        ]


def build(cfg, api_key=None):
    if cfg.get("translator") == "mock":
        return MockTranslator(target_lang=cfg["target_lang"])
    if cfg.get("translator") == "offline":
        from .offline import OfflineTranslator
        return OfflineTranslator(target_lang=cfg["target_lang"],
                                 source_lang=cfg.get("source_lang") or "EN")
    return DeepLTranslator(
        api_key=api_key or cfg.get("deepl_api_key", ""),
        target_lang=cfg["target_lang"],
        source_lang=cfg.get("source_lang", ""),
    )


def check_key(api_key):
    """Ask the service how much of the allowance is gone. Never raises."""
    api_key = (api_key or "").strip()
    if not api_key:
        return Usage(False, _("Enter a key to see the remaining quota."))

    base = DEEPL_FREE if api_key.endswith(":fx") else DEEPL_PRO
    try:
        response = requests.get(
            base.replace("/translate", "/usage"),
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        return Usage(False, _("Could not reach DeepL: {error}").format(error=exc))

    if response.status_code == 403:
        return Usage(False, _("DeepL rejected the key (403). Check that you copied all of it."))
    if response.status_code != 200:
        return Usage(False, _("DeepL returned {status}.").format(status=response.status_code))

    data = response.json()
    used = int(data.get("character_count", 0))
    limit = int(data.get("character_limit", 0))
    usage = Usage(True, "", used, limit)
    tier = _("free") if api_key.endswith(":fx") else _("paid")
    usage.message = _("{used} of {limit} characters used, {left} left ({tier} tier)").format(
        used=group_digits(used), limit=group_digits(limit),
        left=group_digits(usage.remaining), tier=tier)
    return usage
