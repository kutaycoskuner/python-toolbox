# -----------------------------------------------------------------------------------------
#   author          : Kutay Coskuner
#   ai-contributors : Claude Opus 5.5 (claude-opus-5-5)
#   last update     : 2026-11-18
#   disclaimer      : Provided as is, without warranty of any kind; use at your own risk.
#                     Check outputs before relying on them.
# -----------------------------------------------------------------------------------------
"""
svg_shapes.py: draws a small SVG template as a Pillow image, for the tile icons' background.

Why: the shapes behind the text (diamond, circle, shield ...) are plain SVG files in
shapes/, easy to edit or add by hand, while the tool needs no SVG library (cairosvg needs
the Cairo DLL on Windows). Only what simple flat shapes need is read:
- elements: rect (x, y, width, height, rx), circle, ellipse, line, polygon, polyline, path
  (M L H V Z and their lower-case relative forms; no curves), nested <g>
- attributes: fill, stroke, stroke-width, opacity, fill-opacity, stroke-opacity, also
  inside style="..."; colours as #rgb / #rrggbb / names / none
- placeholders: {colour}, {fill} ... in the file are replaced by the icon's values first
- the viewBox is scaled to the output size; drawn 4x larger and scaled down, so edges are
  smooth (no anti-aliasing otherwise)
- rough > 0: chipped, like a worn stamp. The edges stay straight and the corners sharp,
  but here and there a small notch, up to `rough` viewBox units deep, is cut into the
  line toward the shape's middle; the fill follows it. Seeded by the icon and the outline,
  so the same icon always comes out the same, and layers on one outline chip alike.

Used by: main.py (draw_tile).
"""

import math
import random
import zlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

SUPERSAMPLE = 4
NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?")
PIECE = 2.5  # rough: how far apart a chip may fall along an edge, in viewBox units
CHIP_WIDTH = 1.4  # rough: a chip's width along the edge, viewBox units
CHIP_CHANCE = 0.3  # rough: the chance of a chip at each step along an edge


def render_svg(path: Path, size: int, values: dict[str, str], rough: float = 0.0, seed: int = 0) -> Image.Image:
    """
    The SVG at `path`, with {name} placeholders filled from `values`, as a size x size RGBA
    image; rough > 0 draws it by hand (see the module notes), seeded by `seed`.
    """
    text = path.read_text(encoding="utf-8")
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    root = ET.fromstring(text)
    box = [float(n) for n in NUMBER.findall(root.get("viewBox", f"0 0 {size} {size}"))]
    big = size * SUPERSAMPLE
    scale = big / max(box[2], box[3])
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    hand = {"rough": rough, "seed": seed}
    _draw_children(canvas, root, scale, (-box[0], -box[1]), {}, hand)
    return canvas.resize((size, size), Image.LANCZOS)


def _tag(element: ET.Element) -> str:
    return element.tag.split("}")[-1]


def _style(element: ET.Element, inherited: dict) -> dict:
    """Paint attributes, inherited from the parent <g>, then own attributes, then style=."""
    style = dict(inherited)
    for key in ("fill", "stroke", "stroke-width", "opacity", "fill-opacity", "stroke-opacity"):
        if element.get(key) is not None:
            style[key] = element.get(key)
    for part in (element.get("style") or "").split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            style[key.strip()] = value.strip()
    return style


def _rgba(colour: str | None, opacity: float) -> tuple[int, int, int, int] | None:
    if not colour or colour == "none":
        return None
    r, g, b, *a = ImageColor.getrgb(colour)
    return r, g, b, round((a[0] if a else 255) * opacity)


def _draw_children(canvas: Image.Image, parent: ET.Element, scale: float, shift: tuple, inherited: dict, hand: dict):
    for element in parent:
        style = _style(element, inherited)
        if _tag(element) == "g":
            _draw_children(canvas, element, scale, shift, style, hand)
        else:
            _draw_shape(canvas, element, style, scale, shift, hand)


def _rings(element: ET.Element) -> list[tuple[list[tuple[float, float]], bool]]:
    """Any shape as point lists in viewBox units, each with whether it is closed."""
    tag = _tag(element)
    num = lambda key, default=0.0: float(element.get(key, default))  # noqa: E731
    if tag == "rect":
        x, y, w, h = num("x"), num("y"), num("width"), num("height")
        return [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
    if tag in ("circle", "ellipse"):
        rx = num("r") if tag == "circle" else num("rx")
        ry = num("r") if tag == "circle" else num("ry")
        steps = max(12, round(2 * math.pi * max(rx, ry) / PIECE))
        return [([(num("cx") + rx * math.cos(2 * math.pi * i / steps), num("cy") + ry * math.sin(2 * math.pi * i / steps))
                  for i in range(steps)], True)]
    if tag == "line":
        return [([(num("x1"), num("y1")), (num("x2"), num("y2"))], False)]
    if tag == "path":
        return _path_rings(element.get("d", ""))
    if tag in ("polygon", "polyline"):
        return [(_pairs(element.get("points", "")), tag == "polygon")]
    return []


def _wobble(ring: list[tuple[float, float]], closed: bool, rough: float, rng: random.Random) -> list[tuple[float, float]]:
    """The ring with a few small chips cut into its straight edges."""
    points = ring + ([ring[0]] if closed else [])
    # the edges stay straight and the corners sharp; here and there a small chip is cut into
    # the line, toward the shape's middle: a short notch `rough` units deep at most
    cx = sum(x for x, _ in ring) / len(ring)
    cy = sum(y for _, y in ring) / len(ring)
    out = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        out.append((x0, y0))
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 3 * CHIP_WIDTH:
            continue
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux  # a normal; turned toward the middle below
        if (cx - x0) * nx + (cy - y0) * ny < 0:
            nx, ny = -nx, -ny
        at = CHIP_WIDTH * 1.5
        while at < length - CHIP_WIDTH * 1.5:
            if rng.random() < CHIP_CHANCE:
                depth = rough * rng.uniform(0.5, 1.0)
                half = CHIP_WIDTH * rng.uniform(0.6, 1.0) / 2
                for along, sink in ((at - half, 0), (at, depth), (at + half, 0)):
                    out.append((x0 + ux * along + nx * sink, y0 + uy * along + ny * sink))
                at += CHIP_WIDTH * 2
            at += PIECE
    if not closed:
        out.append(points[-1])
    return out


def _draw_shape(canvas: Image.Image, element: ET.Element, style: dict, scale: float, shift: tuple, hand: dict):
    """One shape on its own layer (so its opacity applies to it alone), then laid on the canvas."""
    opacity = float(style.get("opacity", 1))
    fill = _rgba(style.get("fill", "#000"), opacity * float(style.get("fill-opacity", 1)))
    stroke = _rgba(style.get("stroke"), opacity * float(style.get("stroke-opacity", 1)))
    width = max(1, round(float(style.get("stroke-width", 1)) * scale)) if stroke else 0
    point = lambda x, y: ((x + shift[0]) * scale, (y + shift[1]) * scale)  # noqa: E731

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    rough = hand["rough"]
    for ring, closed in _rings(element):
        if len(ring) < 2:
            continue
        if rough <= 0:
            points = [point(x, y) for x, y in ring]
            if closed and fill:
                pen.polygon(points, fill=fill)
            if stroke:
                pen.line(points + ([points[0], points[1]] if closed else []), fill=stroke, width=width, joint="curve")
            continue
        # by hand: one outline with slightly uneven edges, the fill right under it
        # chips seeded by the icon and the outline itself: two layers drawn on the same outline
        # (a dark edge under a coloured line) chip in the same places
        rng = random.Random(hand["seed"] ^ zlib.crc32(repr([(round(x, 2), round(y, 2)) for x, y in ring]).encode()))
        line = [point(x, y) for x, y in _wobble(ring, closed, rough, rng)]
        if closed and fill:
            pen.polygon(line, fill=fill)
        if stroke:
            pen.line(line + ([line[0], line[1]] if closed else []), fill=stroke, width=width, joint="curve")
    canvas.alpha_composite(layer)


def _pairs(text: str) -> list[tuple[float, float]]:
    numbers = [float(n) for n in NUMBER.findall(text)]
    return list(zip(numbers[0::2], numbers[1::2]))


def _path_rings(d: str) -> list[tuple[list[tuple[float, float]], bool]]:
    """A path's sub-paths as point lists, each with whether it is closed (Z). Straight lines only."""
    rings, ring, x, y, start = [], [], 0.0, 0.0, (0.0, 0.0)
    for command, args in re.findall(r"([MmLlHhVvZz])([^MmLlHhVvZz]*)", d):
        numbers = [float(n) for n in NUMBER.findall(args)]
        relative = command.islower()
        kind = command.upper()
        if kind == "Z":
            if ring:
                rings.append((ring, True))
            ring, (x, y) = [], start
            continue
        if kind in ("M", "L"):
            for i, (dx, dy) in enumerate(zip(numbers[0::2], numbers[1::2])):
                x, y = (x + dx, y + dy) if relative else (dx, dy)
                if kind == "M" and i == 0:
                    if ring:
                        rings.append((ring, False))
                    ring, start = [], (x, y)
                ring.append((x, y))
        elif kind == "H":
            for n in numbers:
                x = x + n if relative else n
                ring.append((x, y))
        elif kind == "V":
            for n in numbers:
                y = y + n if relative else n
                ring.append((x, y))
    if ring:
        rings.append((ring, False))
    return rings
