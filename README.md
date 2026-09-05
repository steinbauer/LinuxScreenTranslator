# Linux Screen Translator

Screen translation for the Linux desktop — the thing Android does when you
hold the home button and tap *Translate*. Pick an area of the screen, and the
text in it is recognised, **the original lettering is erased, the background
underneath is filled in**, and the translation is typeset in its place.

Built because English memes on X.com cannot otherwise be read without retyping
them by hand.

*Czech version of this file: [README.cs.md](README.cs.md).*

## How it works

| Step | Tool |
|---|---|
| Area capture | XDG Desktop Portal — works on both Wayland and X11 |
| Text recognition | RapidOCR (PaddleOCR as ONNX), locally on the CPU |
| Translation | DeepL API |
| Erasing the original | OpenCV inpainting (Telea) |
| Typesetting | Pillow, matching the original size, tilt and alignment |

A pass takes roughly **1 second** for a small area and about 4 seconds for a
full 4K screen. Nothing but the recognised text leaves the machine — OCR runs
locally.

Text that already is in the target language is skipped, so on a Czech page
only the English parts get translated.

## Install

```bash
./install.sh
```

No `sudo` needed. It creates a virtual environment, an application launcher, a
tray icon that starts with the session, and the `Ctrl+Print` shortcut.

System dependencies (usually already present on Ubuntu):

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
                 gir1.2-ayatanaappindicator3-0.1
```

## Setup

Open the settings from the tray icon, or:

```bash
.venv/bin/python main.py --settings
```

Set the target language and a **DeepL API key** (free at
<https://www.deepl.com/pro-api> — the free tier gives 500,000 characters a
month). The key is stored in the system keyring, not in the config file.

## Use

* `Ctrl+Print`, or the tray icon → *Translate an area…*
* in the result window: hold space for the original, `Ctrl+C` to copy,
  `Ctrl+S` to save

## Without the GUI

```bash
.venv/bin/python -m translatorscreener.cli --image shot.png --out result.png
.venv/bin/python -m translatorscreener.cli --translator mock   # no API key needed
```

## Translating the interface

English is the source language. Catalogues live in `po/`, and the tools are
plain Python, so the GNU gettext utilities are not required:

```bash
python3 tools/i18n_tools.py extract   # refresh po/translatorscreener.pot
cp po/translatorscreener.pot po/de.po # then fill in the msgstr lines
python3 tools/i18n_tools.py compile   # build locale/*/LC_MESSAGES/*.mo
```

To teach the "already in the target language" filter a new language, add an
entry to `TARGET_HINTS` in `translatorscreener/translate.py`.

## Known limitations

* The OCR model is English/Chinese and **does not read diacritics**
  ("Hlavní stránka" comes out as "Hlavni stranka"). That does not matter when
  translating *into* those languages, because such text is skipped anyway, but
  translating *out of* them works poorly.
* Inpainting is classical (Telea). On flat or mildly textured backgrounds the
  result is indistinguishable from the original; over a busy photograph a
  blurred trace remains. LaMa would be sharper, at the cost of ~200 MB and a
  second of compute.
* Multi-column text and italics are not detected.

## Licence

Apache License 2.0 — see [LICENSE](LICENSE).
