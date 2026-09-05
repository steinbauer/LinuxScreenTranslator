"""The whole chain: screenshot to OCR to translation to rendering."""

import time
from dataclasses import dataclass

from . import fonts, ocr, render, translate
from .i18n import _


class NoTextFound(RuntimeError):
    pass


@dataclass
class Result:
    image: object          # PIL.Image carrying the translation
    groups: list           # paragraphs with both the original and the translation
    seconds: float

    @property
    def summary(self):
        return _("{count} blocks in {seconds:.1f} s").format(
            count=len(self.groups), seconds=self.seconds)


def process(image_path, cfg, api_key=None, translator=None, progress=None):
    """Process an image and return a Result. `translator` can be injected in tests."""
    say = progress or (lambda _message: None)
    started = time.time()

    say(_("Recognising text…"))
    blocks = ocr.recognise(image_path, cfg.get("min_confidence", 0.5),
                           cfg.get("box_thresh", 0.3))
    if not blocks:
        raise NoTextFound(_("No text was found in the selected area."))
    groups = ocr.group_blocks(blocks)

    # Account names are left alone: they are proper nouns, and translating
    # them produces nonsense rather than a translation.
    skip = ocr.display_name_indices(groups)
    wanted = [i for i in range(len(groups)) if i not in skip]

    say(_("Translating {count} blocks…").format(count=len(wanted)))
    engine = translator or translate.build(cfg, api_key)
    target = translate.base_lang(cfg.get("target_lang", "CS"))
    outcome = engine.translate([groups[i].text for i in wanted])
    for group, result in zip((groups[i] for i in wanted), outcome):
        # Leave anything already in the target language alone: re-typesetting
        # it merely because it happened to be on screen would only degrade it.
        already_target = translate.base_lang(result.detected) == target
        group.translated = "" if already_target or result.same_as(group.text) else result.text

    say(_("Rendering the translation…"))
    font_path = fonts.for_language(cfg.get("target_lang", "CS"), cfg.get("font_path", ""))
    image = render.render(
        image_path, groups, font_path, use_inpaint=cfg.get("inpaint", True)
    )
    return Result(image=image, groups=groups, seconds=time.time() - started)
