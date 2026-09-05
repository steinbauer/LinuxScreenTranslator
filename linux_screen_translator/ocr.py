"""Text recognition through RapidOCR, plus grouping of lines into paragraphs.

RapidOCR returns individual lines. Translating those separately would feed the
translator torn sentence fragments, so lines that visually belong together are
merged into a paragraph first.
"""

import math
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class Block:
    """A single line recognised by OCR."""

    text: str
    score: float
    quad: list  # four corner points [(x, y), ...]

    @property
    def bbox(self):
        xs = [p[0] for p in self.quad]
        ys = [p[1] for p in self.quad]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def height(self):
        _x0, y0, _x1, y1 = self.bbox
        return y1 - y0

    @property
    def angle(self):
        """Tilt of the baseline in degrees, positive going down to the right.

        The quad comes ordered top-left, top-right, bottom-right, bottom-left,
        so the first edge is the baseline direction.
        """
        (x0, y0), (x1, y1) = self.quad[0], self.quad[1]
        return math.degrees(math.atan2(y1 - y0, x1 - x0))

    @property
    def centre(self):
        xs = [p[0] for p in self.quad]
        ys = [p[1] for p in self.quad]
        return sum(xs) / 4, sum(ys) / 4

    @property
    def left_mid(self):
        """Midpoint of the left edge — the anchor for left-aligned text."""
        (x0, y0), (x3, y3) = self.quad[0], self.quad[3]
        return (x0 + x3) / 2, (y0 + y3) / 2

    @property
    def oriented_size(self):
        """Width along the baseline and height across it.

        For tilted text the axis-aligned box is much larger than the letters,
        so measuring along the baseline is the only way to get the real size.
        """
        (x0, y0), (x1, y1), (x2, y2) = self.quad[0], self.quad[1], self.quad[2]
        width = math.hypot(x1 - x0, y1 - y0)
        height = math.hypot(x2 - x1, y2 - y1)
        return width, height


def _rotate(point, degrees, origin=(0.0, 0.0)):
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    return (origin[0] + dx * cos - dy * sin, origin[1] + dx * sin + dy * cos)


@dataclass
class Group:
    """A paragraph: the unit that gets translated and typeset as a whole."""

    blocks: list = field(default_factory=list)
    translated: str = ""

    @property
    def text(self):
        return " ".join(b.text.strip() for b in self.blocks if b.text.strip())

    @property
    def bbox(self):
        boxes = [b.bbox for b in self.blocks]
        return (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )

    @property
    def line_height(self):
        return sum(b.height for b in self.blocks) / len(self.blocks)

    @property
    def angle(self):
        """Baseline tilt of the paragraph, weighted by how long each line is."""
        weights = [b.oriented_size[0] for b in self.blocks]
        total = sum(weights) or 1.0
        return sum(b.angle * w for b, w in zip(self.blocks, weights)) / total

    @property
    def oriented_line_height(self):
        return sum(b.oriented_size[1] for b in self.blocks) / len(self.blocks)

    @property
    def oriented_box(self):
        """The paragraph measured in its own tilted frame.

        Returns (centre_x, centre_y, width, height) where width and height are
        along and across the baseline.
        """
        angle = self.angle
        points = [p for block in self.blocks for p in block.quad]
        upright = [_rotate(p, -angle) for p in points]
        xs = [p[0] for p in upright]
        ys = [p[1] for p in upright]
        centre = _rotate(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2), angle)
        return centre[0], centre[1], max(xs) - min(xs), max(ys) - min(ys)


@lru_cache(maxsize=1)
def _engine():
    # Loading the models takes about 0.2 s, so keep a single instance around.
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def _longest_letter_run(text):
    longest = run = 0
    for ch in text:
        run = run + 1 if unicodedata.category(ch).startswith("L") else 0
        longest = max(longest, run)
    return longest


def _worth_translating(text):
    """Drop blocks that hold no real words — timestamps, counters, icon labels.

    Re-typesetting "0:01 / 0:27" gains nothing and only degrades the image.

    Counters are the awkward case: the bar-chart glyph in front of a view
    count is read as letters, so "ili 625" and "15 tis." look like text. What
    separates them from genuine short labels such as "Chat" or "Alcohol" is
    that they carry digits while their longest run of letters stays tiny.
    """
    letters = sum(1 for ch in text if unicodedata.category(ch).startswith("L"))
    if letters < 2:
        return False
    if any(ch.isdigit() for ch in text) and _longest_letter_run(text) <= 3:
        return False
    return True


def recognise(image_path, min_confidence=0.5, box_thresh=0.3):
    """Return a list of Block sorted top to bottom.

    box_thresh is the detector's confidence threshold. RapidOCR defaults to
    0.5, which is too strict for text that is curved or strongly rotated —
    lettering across a T-shirt, for instance, gets dropped entirely. 0.3
    recovers those lines without noticeably adding noise.
    """
    result, _elapsed = _engine()(str(image_path), box_thresh=box_thresh)
    blocks = [
        Block(text=text, score=float(score), quad=[tuple(p) for p in quad])
        for quad, text, score in (result or [])
        if text.strip() and float(score) >= min_confidence and _worth_translating(text)
    ]
    blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    return blocks


# Characters a bullet is read as. OCR rarely recognises the glyph itself and
# usually returns a stand-in, or nothing but the space that followed it.
BULLET_MARKS = frozenset("•·‣∙▪▫◦-–—*:;.")


def _starts_list_item(previous, block, indent_ratio=0.25, min_step=6.0):
    """True when a line steps back to the left and opens with a bullet.

    Consecutive list items sit as close together as the wrapped lines of one
    paragraph — measured on a news column, 15px between items against 12 to
    15px within them — so spacing cannot separate them. The left edge can:
    items begin at the bullet while their continuations are indented past it.

    That alone is not enough, because text flowing around a floated image also
    steps left once it clears the image. Requiring a bullet as well keeps such
    a paragraph in one piece.
    """
    if not _bulleted(block.text):
        return False

    step = previous.bbox[0] - block.bbox[0]
    if step > max(min_step, indent_ratio * block.height):
        return True

    # A one-line item leaves the next one nothing to step back from, since
    # both begin at the same left edge. Two consecutive lines opening with a
    # bullet are two items; inside a paragraph that does not happen.
    return _bulleted(previous.text)


def _bulleted(text):
    return bool(text) and (text[0].isspace() or text[0] in BULLET_MARKS)


def _overlap_ratio(a, b):
    """How much two boxes overlap horizontally, relative to the narrower one."""
    left = max(a[0], b[0])
    right = min(a[2], b[2])
    if right <= left:
        return 0.0
    narrower = min(a[2] - a[0], b[2] - b[0])
    return (right - left) / narrower if narrower else 0.0


def group_blocks(blocks, max_gap_ratio=0.8, min_overlap=0.35, height_ratio=0.35):
    """Merge stacked lines into paragraphs.

    Two lines belong together when they overlap horizontally, the vertical gap
    between them is no larger than max_gap_ratio of a line height, and their
    type is of similar size. Without the last condition an author's name would
    merge into the body of a post and the paragraph would be typeset at the
    wrong size.
    """
    groups = []
    for block in blocks:
        placed = False
        for group in groups:
            last = group.blocks[-1]
            gap = block.bbox[1] - last.bbox[3]
            limit = max_gap_ratio * max(last.height, block.height)
            taller = max(last.height, block.height)
            similar_size = abs(last.height - block.height) <= height_ratio * taller
            if (-last.height < gap <= limit
                    and similar_size
                    and not _starts_list_item(last, block)
                    and _overlap_ratio(last.bbox, block.bbox) >= min_overlap):
                group.blocks.append(block)
                placed = True
                break
        if not placed:
            groups.append(Group(blocks=[block]))
    return merge_overlapping(groups)


def _intersection_area(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    return width * height if width > 0 and height > 0 else 0.0


def _area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def merge_overlapping(groups, min_ratio=0.2):
    """Merge paragraphs whose boxes overlap.

    Typesetting two overlapping texts on top of each other leaves neither of
    them readable, so they are joined into one block and drawn once.
    """
    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                overlap = _intersection_area(groups[i].bbox, groups[j].bbox)
                if not overlap:
                    continue
                smaller = min(_area(groups[i].bbox), _area(groups[j].bbox))
                if smaller and overlap / smaller >= min_ratio:
                    groups[i].blocks.extend(groups[j].blocks)
                    groups[i].blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
                    del groups[j]
                    changed = True
                    break
            if changed:
                break
    return groups


def display_name_indices(groups, max_words=4, gap_ratio=2.5, min_overlap=0.5):
    """Groups that look like an account's display name beside its @handle.

    A proper name is not text to translate, and translating it does real harm:
    the display name "TAREK" came back from DeepL as a Czech verb. What marks
    one out is position — a short piece of text sitting on the same line,
    immediately to the left of a block that starts with an @.
    """
    handles = [g.bbox for g in groups if g.text.lstrip().startswith("@")]
    if not handles:
        return set()

    found = set()
    for index, group in enumerate(groups):
        if group.text.lstrip().startswith("@") or len(group.text.split()) > max_words:
            continue
        x0, y0, x1, y1 = group.bbox
        height = y1 - y0
        for hx0, hy0, hx1, hy1 in handles:
            shared = min(y1, hy1) - max(y0, hy0)
            if shared <= min_overlap * min(height, hy1 - hy0):
                continue
            if 0 <= hx0 - x1 <= gap_ratio * height:
                found.add(index)
                break
    return found


def split_bullet(text):
    """Separate a leading bullet stand-in from the text that follows.

    OCR reads the glyph as a colon, a full stop, or nothing but the space
    after it. Carrying that into the translation reproduces the stand-in
    rather than the bullet, so it is stripped before translating and a proper
    bullet is put back when the line is drawn.
    """
    body = text.lstrip()
    if not body:
        return "", text
    if body[0] in BULLET_MARKS and len(body) > 1 and body[1].isspace():
        return body[0], body[1:].lstrip()
    if text[:1].isspace() and body:
        return " ", body
    return "", text
