"""Command line entry point, mainly for exercising the pipeline without a GUI."""

import argparse
import sys

from . import config, keyring_store, pipeline
from .i18n import _


def main(argv=None):
    parser = argparse.ArgumentParser(prog="translatorscreener")
    parser.add_argument("--image", help=_("image to process; without it the screen is captured"))
    parser.add_argument("--out", default="translated.png", help=_("where to write the result"))
    parser.add_argument("--lang", help=_("target language, e.g. CS"))
    parser.add_argument("--translator", choices=["deepl", "mock"])
    parser.add_argument("--no-inpaint", action="store_true",
                        help=_("keep the original text instead of erasing it"))
    args = parser.parse_args(argv)

    cfg = config.load()
    if args.lang:
        cfg["target_lang"] = args.lang
    if args.translator:
        cfg["translator"] = args.translator
    if args.no_inpaint:
        cfg["inpaint"] = False

    path = args.image
    if not path:
        from .capture import take_screenshot
        path = take_screenshot(interactive=True)
        if not path:
            print(_("Selection cancelled."))
            return 1

    try:
        result = pipeline.process(
            path, cfg,
            api_key=keyring_store.lookup() or cfg.get("deepl_api_key"),
            progress=lambda message: print(f"  {message}"),
        )
    except pipeline.NoTextFound as exc:
        print(exc)
        return 1

    result.image.save(args.out)
    print("\n" + _("Done — {summary}, written to {path}").format(
        summary=result.summary, path=args.out) + "\n")
    for group in result.groups:
        arrow = f"→ {group.translated!r}" if group.translated else _("→ (left unchanged)")
        print(f"  {group.text!r}\n     {arrow}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
