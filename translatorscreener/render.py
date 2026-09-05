"""Erase the original text and typeset the translation in its place.

The steps mirror what screen translation does on Android:
  1. build a mask from the recognised boxes,
  2. inpaint the background underneath, which makes the original text vanish,
  3. typeset the translation into the freed space, in the original's colour.
"""

import math
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .ocr import _rotate

MIN_FONT_SIZE = 9
LINE_SPACING = 1.22
# How far a paragraph may grow beyond its original height when there is free
# space around it. Translations are often longer than the source, so some
# room to grow is needed.
MAX_GROWTH = 2.2
# Below this tilt the text is treated as horizontal. Short labels give noisy
# quads — buttons like "Chat" or "More" routinely measure two or three degrees
# off — so the threshold has to clear that noise before anything is rotated.
ROTATION_EPS = 4.0
# Tilted text sits on shirts, signs and posters where there is no free space
# around it, so it may grow far less than text in a page layout.
ROTATED_GROWTH = 1.5


@lru_cache(maxsize=128)
def _font(path, size):
    return ImageFont.truetype(path, size)


def _clamp_bbox(bbox, shape):
    height, width = shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in bbox)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    return x0, y0, x1, y1


def build_mask(shape, groups):
    """The mask of pixels that belong to the original text."""
    mask = np.zeros(shape[:2], np.uint8)
    heights = []
    for group in groups:
        for block in group.blocks:
            cv2.fillPoly(mask, [np.array(block.quad, np.int32)], 255)
            heights.append(block.height)
    if not heights:
        return mask
    # OCR boxes hug the glyphs, so widen the mask to also cover outlines and
    # drop shadows; otherwise inpainting leaves ghosts behind.
    radius = max(5, int(np.median(heights) * 0.34)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius, radius))
    return cv2.dilate(mask, kernel)


def _ring_colour(rgb, bbox, spread=0.7):
    """Mean colour of a ring just outside the box, i.e. the real background."""
    x0, y0, x1, y1 = _clamp_bbox(bbox, rgb.shape)
    pad = max(4, int((y1 - y0) * spread))
    ox0, oy0, ox1, oy1 = _clamp_bbox((x0 - pad, y0 - pad, x1 + pad, y1 + pad), rgb.shape)
    outer = rgb[oy0:oy1, ox0:ox1]
    if outer.size == 0:
        return None
    ring = np.ones(outer.shape[:2], bool)
    ring[y0 - oy0:y1 - oy0, x0 - ox0:x1 - ox0] = False
    return outer[ring].mean(axis=0) if ring.any() else None


def _luminance(colour):
    red, green, blue = colour
    return 0.299 * red + 0.587 * green + 0.114 * blue


def _snap_to_pure(colour, spread=45, bright=200, dark=60):
    """Round near-white or near-black type to the pure colour.

    Averaging across the edge of a glyph always picks up some background, so
    white text comes out slightly tinted. Fix that for single-colour type.
    """
    if max(colour) - min(colour) > spread:
        return colour  # genuinely coloured type is left alone
    luminance = _luminance(colour)
    if luminance >= bright:
        return (255, 255, 255)
    if luminance <= dark:
        return (0, 0, 0)
    return colour


def sample_colours(rgb, bbox):
    """Estimate the colour of the type and of its outline.

    Otsu splits the crop into two classes. Which one is the type cannot be
    decided by pixel count — bold meme text covers more area than its
    background. Comparing against a ring around the box decides instead: the
    type is whichever class differs more from the surroundings.
    """
    x0, y0, x1, y1 = _clamp_bbox(bbox, rgb.shape)
    crop = rgb[y0:y1, x0:x1]
    if crop.size == 0:
        return (255, 255, 255), (0, 0, 0)

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright, dark = otsu == 255, otsu == 0
    if not bright.any() or not dark.any():
        return (255, 255, 255), (0, 0, 0)

    bright_rgb, dark_rgb = crop[bright].mean(axis=0), crop[dark].mean(axis=0)
    ring = _ring_colour(rgb, bbox)
    if ring is None:
        # With no usable surroundings, fall back to "there is less type".
        text_rgb = bright_rgb if bright.sum() < dark.sum() else dark_rgb
    else:
        distances = np.linalg.norm(np.array([bright_rgb, dark_rgb]) - ring, axis=1)
        text_rgb = bright_rgb if distances[0] > distances[1] else dark_rgb

    text = _snap_to_pure(tuple(int(v) for v in text_rgb))
    # The outline is chosen to contrast with the type rather than to match the
    # background: that keeps the text legible over any backdrop, and on memes
    # it reproduces the original stroke.
    outline = (0, 0, 0) if _luminance(text) > 127 else (255, 255, 255)
    return text, outline


def _wrap(draw, text, font, max_width):
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if not current or draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def fit_text(draw, text, font_path, box_w, max_height, max_size):
    """Find the largest font size that still fits the space available."""
    low, high = MIN_FONT_SIZE, max(MIN_FONT_SIZE, int(max_size))
    best = None
    while low <= high:
        mid = (low + high) // 2
        font = _font(font_path, mid)
        lines = _wrap(draw, text, font, box_w)
        widest = max(draw.textlength(line, font=font) for line in lines)
        total_height = mid * LINE_SPACING * len(lines)
        if widest <= box_w and total_height <= max_height:
            best = (font, lines, mid)
            low = mid + 1
        else:
            high = mid - 1
    if best is None:
        font = _font(font_path, MIN_FONT_SIZE)
        best = (font, _wrap(draw, text, font, box_w), MIN_FONT_SIZE)
    return best


def _vertical_room(groups, index, image_height):
    """Vertical bounds a paragraph may grow into without hitting a neighbour.

    Without this limit a longer translation outgrows its box and overprints
    the text next to it, which makes dense pages unreadable.
    """
    x0, y0, x1, y1 = groups[index].bbox
    top, bottom = 0, image_height
    for other_index, other in enumerate(groups):
        if other_index == index:
            continue
        ox0, oy0, ox1, oy1 = other.bbox
        if min(x1, ox1) - max(x0, ox0) <= 0:
            continue  # they miss each other horizontally, no conflict
        if oy1 <= y0:
            top = max(top, oy1)
        elif oy0 >= y1:
            bottom = min(bottom, oy0)
    return top, bottom


def _alignment(group):
    """Guess the paragraph's alignment from the positions of its lines."""
    if len(group.blocks) < 2:
        return "center"
    lefts = [b.bbox[0] for b in group.blocks]
    centres = [(b.bbox[0] + b.bbox[2]) / 2 for b in group.blocks]
    spread = lambda values: max(values) - min(values)
    return "left" if spread(lefts) <= spread(centres) else "center"


def _alignment_oriented(group):
    """Alignment measured along the baseline rather than along the image."""
    if len(group.blocks) < 2:
        return "center"
    angle = group.angle
    lefts, centres = [], []
    for block in group.blocks:
        left = _rotate(block.quad[0], -angle)
        right = _rotate(block.quad[1], -angle)
        lefts.append(left[0])
        centres.append((left[0] + right[0]) / 2)
    spread = lambda values: max(values) - min(values)
    return "left" if spread(lefts) <= spread(centres) else "center"


def _draw_tilted(canvas, draw, group, text_rgb, outline_rgb, font_path):
    """Typeset a tilted paragraph: lay it out flat, rotate it, paste it back."""
    centre_x, centre_y, width, height = group.oriented_box
    angle = group.angle
    if width < 8 or height < 6:
        return

    max_size = max(MIN_FONT_SIZE, int(group.oriented_line_height * 1.05))
    font, lines, size = fit_text(draw, group.translated, font_path,
                                 width, height * ROTATED_GROWTH, max_size)

    line_height = size * LINE_SPACING
    stroke = max(1, round(size / 14))
    padding = size  # keeps the stroke and any overhang inside the layer
    layer = Image.new("RGBA",
                      (int(width) + 2 * padding,
                       int(line_height * len(lines)) + 2 * padding),
                      (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)

    align = _alignment_oriented(group)
    cursor_y = padding
    for line in lines:
        line_width = layer_draw.textlength(line, font=font)
        offset = padding if align == "left" else padding + (width - line_width) / 2
        layer_draw.text((offset, cursor_y), line, font=font, fill=text_rgb,
                        stroke_width=stroke, stroke_fill=outline_rgb)
        cursor_y += line_height

    # PIL rotates counter-clockwise, the measured angle grows clockwise.
    turned = layer.rotate(-angle, expand=True, resample=Image.BICUBIC)
    canvas.paste(turned,
                 (int(round(centre_x - turned.width / 2)),
                  int(round(centre_y - turned.height / 2))),
                 turned)


def render(image_path, groups, font_path, use_inpaint=True):
    """Return a PIL Image with the translation in place of the original text."""
    source = Image.open(image_path).convert("RGB")
    rgb = np.array(source)

    active = [g for g in groups if g.translated.strip()]
    if not active:
        return source

    # Colours have to be sampled from the original, i.e. before erasing.
    colours = [sample_colours(rgb, g.bbox) for g in active]

    if use_inpaint:
        mask = build_mask(rgb.shape, active)
        rgb = cv2.inpaint(rgb, mask, 4, cv2.INPAINT_TELEA)

    canvas = Image.fromarray(rgb)
    draw = ImageDraw.Draw(canvas)

    for index, (group, (text_rgb, outline_rgb)) in enumerate(zip(active, colours)):
        if abs(group.angle) >= ROTATION_EPS:
            _draw_tilted(canvas, draw, group, text_rgb, outline_rgb, font_path)
            continue

        x0, y0, x1, y1 = _clamp_bbox(group.bbox, rgb.shape)
        box_w, box_h = x1 - x0, y1 - y0
        if box_w < 8 or box_h < 6:
            continue

        # How much room there is before we run into neighbouring text.
        top, bottom = _vertical_room(active, index, rgb.shape[0])
        centre_y = (y0 + y1) / 2
        available = 2 * min(centre_y - top, bottom - centre_y) - 4
        max_height = max(box_h, min(available, box_h * MAX_GROWTH))

        max_size = max(MIN_FONT_SIZE, int(group.oriented_line_height * 1.1))
        font, lines, size = fit_text(draw, group.translated, font_path,
                                     box_w, max_height, max_size)

        line_height = size * LINE_SPACING
        total_height = line_height * len(lines)
        cursor_y = centre_y - total_height / 2
        align = _alignment(group)
        # A contrasting outline keeps the text readable even over imperfect
        # inpainting, and on memes it imitates the original stroke.
        stroke = max(1, round(size / 14))

        for line in lines:
            width = draw.textlength(line, font=font)
            offset = 0 if align == "left" else (box_w - width) / 2
            draw.text(
                (x0 + offset, cursor_y),
                line,
                font=font,
                fill=text_rgb,
                stroke_width=stroke,
                stroke_fill=outline_rgb,
            )
            cursor_y += line_height

    return canvas
