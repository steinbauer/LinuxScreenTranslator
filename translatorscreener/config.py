"""Settings stored in ~/.config/translatorscreener/config.json."""

import json
import os

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "translatorscreener",
)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "target_lang": "CS",
    "source_lang": "",           # empty means auto-detect
    "deepl_api_key": "",
    "translator": "deepl",       # deepl | mock
    "inpaint": True,             # erase the original text and fill the background
    "keep_capture": False,       # keep the screenshot in the Screenshots folder
    "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "min_confidence": 0.5,       # ignore OCR blocks below this confidence
    "box_thresh": 0.3,           # OCR detector threshold; lower finds curved text
}


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as exc:
        print(f"warning: could not read settings ({exc}), using defaults")
    return cfg


def save(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
    # The file may hold an API key, so keep it readable by its owner only.
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG_PATH)
