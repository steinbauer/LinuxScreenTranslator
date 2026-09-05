"""Offline translation, as an alternative to sending text to a service.

Argos Translate publishes CTranslate2 models under an open licence, but its
own package pulls in torch, spaCy, stanza and the CUDA toolkit — gigabytes of
dependencies for a tool that otherwise fits in a hundred megabytes. The models
themselves need none of that: a CTranslate2 model directory and a subword-nmt
BPE vocabulary are enough, which is what this loads directly.

Quality sits below a paid service, noticeably on slang and idiom. The trade is
that nothing leaves the machine and there is no account, key or quota.
"""

import json
import os
import re
import shutil
import tempfile
import zipfile

import requests

from .i18n import _
from .translate import (Translation, TranslationError, base_lang, is_shouty,
                        looks_like_target)

INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
MODEL_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "linux-screen-translator", "models",
)

# Spacing the tokeniser cannot know about: it emits every token separated, so
# punctuation ends up adrift from the word it belongs to.
_BEFORE = re.compile(r"\s+([.,!?;:%)\]}»”’…])")
_AFTER = re.compile(r"([(\[{«“‘])\s+")


def pair_name(source, target):
    return f"{base_lang(source).lower()}_{base_lang(target).lower()}"


def model_path(source, target):
    return os.path.join(MODEL_DIR, pair_name(source, target))


# Argos changed tokeniser between model generations: the older packages carry
# a sentencepiece model, the newer ones subword-nmt BPE codes. Both are still
# published, so both have to be read.
TOKENISERS = ("bpe.model", "sentencepiece.model")


def tokeniser_file(path):
    for name in TOKENISERS:
        candidate = os.path.join(path, name)
        if os.path.exists(candidate):
            return candidate
    return None


def is_installed(source, target):
    path = model_path(source, target)
    return os.path.isdir(os.path.join(path, "model")) and tokeniser_file(path) is not None


def available_pairs(timeout=20):
    """Language pairs published in the Argos index."""
    try:
        response = requests.get(INDEX_URL, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise TranslationError(
            _("Could not fetch the model list: {error}").format(error=exc)) from exc
    return response.json()


def download(source, target, progress=None, timeout=60):
    """Fetch and unpack the model for one language pair."""
    say = progress or (lambda _message: None)
    source_code, target_code = base_lang(source).lower(), base_lang(target).lower()

    say(_("Looking for a model…"))
    entry = next(
        (p for p in available_pairs()
         if p.get("from_code") == source_code and p.get("to_code") == target_code),
        None,
    )
    if entry is None:
        raise TranslationError(
            _("No offline model is published for {pair}.").format(
                pair=f"{source_code} → {target_code}"))

    links = entry.get("links") or ([entry["link"]] if entry.get("link") else [])
    if not links:
        raise TranslationError(_("The model entry carries no download link."))

    say(_("Downloading the model…"))
    destination = model_path(source, target)
    with tempfile.TemporaryDirectory() as work:
        archive = os.path.join(work, "model.argosmodel")
        try:
            with requests.get(links[0], stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with open(archive, "wb") as fh:
                    for chunk in response.iter_content(1 << 20):
                        fh.write(chunk)
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(work)
        except (requests.RequestException, zipfile.BadZipFile, OSError) as exc:
            raise TranslationError(
                _("Downloading the model failed: {error}").format(error=exc)) from exc

        # The archive holds one directory; its contents are what we keep.
        inner = [os.path.join(work, name) for name in os.listdir(work)
                 if os.path.isdir(os.path.join(work, name))]
        if not inner:
            raise TranslationError(_("The downloaded model looks empty."))

        say(_("Installing the model…"))
        os.makedirs(MODEL_DIR, exist_ok=True)
        shutil.rmtree(destination, ignore_errors=True)
        shutil.move(inner[0], destination)
    return destination


def detokenise(tokens):
    """Reassemble BPE tokens into a sentence."""
    text = " ".join(tokens).replace("@@ ", "").replace("@@", "")
    text = _BEFORE.sub(r"\1", text)
    text = _AFTER.sub(r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


class OfflineTranslator:
    """Same interface as the DeepL backend, without the network."""

    def __init__(self, target_lang="CS", source_lang="EN", beam_size=4):
        self.target_lang = target_lang
        self.source_lang = source_lang or "EN"
        self.beam_size = beam_size
        self._engine = None
        self._bpe = None
        self._sp = None

    def _load(self):
        if self._engine is not None:
            return
        try:
            import ctranslate2
        except ImportError as exc:
            raise TranslationError(_(
                "Offline translation needs extra packages. Install them with: "
                "pip install ctranslate2 subword-nmt sentencepiece")) from exc

        path = model_path(self.source_lang, self.target_lang)
        tokeniser = tokeniser_file(path)
        if not os.path.isdir(os.path.join(path, "model")) or tokeniser is None:
            raise TranslationError(_(
                "No offline model for {pair} is installed yet.").format(
                    pair=f"{base_lang(self.source_lang)} → {base_lang(self.target_lang)}"))

        if os.path.basename(tokeniser) == "sentencepiece.model":
            import sentencepiece
            self._sp = sentencepiece.SentencePieceProcessor(model_file=tokeniser)
        else:
            from subword_nmt import apply_bpe
            with open(tokeniser, encoding="utf-8") as fh:
                self._bpe = apply_bpe.BPE(fh)
        self._engine = ctranslate2.Translator(os.path.join(path, "model"), device="cpu")

    def _encode(self, text):
        if self._sp is not None:
            return self._sp.encode(text.strip(), out_type=str)
        return self._bpe.process_line(text.strip()).split()

    def _decode(self, tokens):
        if self._sp is not None:
            return self._sp.decode(tokens)
        return detokenise(tokens)

    def translate(self, texts):
        """Same contract as the online backend, including its two guards.

        Both matter more here, not less: the model is trained on ordinary
        prose, so shouted text confuses it badly, and it has no language
        detection of its own to notice text already in the target language.
        """
        if not texts:
            return []
        self._load()
        target = base_lang(self.target_lang)

        results = [Translation(text=t, detected=target) for t in texts]
        send = [i for i, text in enumerate(texts)
                if not looks_like_target(text, self.target_lang)]
        if not send:
            return results

        shouty = {i for i in send if is_shouty(texts[i])}
        payload = [texts[i].capitalize() if i in shouty else texts[i] for i in send]

        batch = [self._encode(text) for text in payload]
        translated = self._engine.translate_batch(batch, beam_size=self.beam_size)
        for index, result in zip(send, translated):
            text = self._decode(result.hypotheses[0])
            results[index] = Translation(
                text=text.upper() if index in shouty else text,
                detected=base_lang(self.source_lang),
            )
        return results
