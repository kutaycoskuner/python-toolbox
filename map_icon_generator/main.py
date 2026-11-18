# -----------------------------------------------------------------------------------------
#   author          : Kutay Coskuner
#   ai-contributors : Claude Opus 5.5 (claude-opus-5-5)
#   last update     : 2026-11-18
#   template        : 3.2.0
#   disclaimer      : Provided as is, without warranty of any kind; use at your own risk.
#                     Check outputs before relying on them.
# -----------------------------------------------------------------------------------------
"""
Map Icon Generator: small labelled map-marker icons (PNG) from a YAML list.

Draws one square PNG per icon and size: an SVG shape in the middle (shapes/diamond.svg
as shipped: a thin outline and a solid inner diamond, the gap transparent; also
circle.svg and shield.svg; svg_shapes.py draws them), its edges straight with a few
small chips (rough), and the icon's text over it: white with a near-black outline,
letters on top and the number under them (A over 12). Every icon in a run gets the same
text size, the size at which the list's widest label fits.

1. Bare run prints this guide and exits (no-args-usage-guide).
2. The first real run offers to create config.yaml from config.example.yaml
   (ensure_config); later runs compare its keys with config.example.yaml's and offer
   to update it when they differ (update_config).
3. Settings come from CLI flags > config.yaml > DEFAULTS (load_settings).
4. The icon lists are read (one YAML file, or every .yaml in a folder); entries without
   text and missing shapes are reported (read_icons).
5. Every icon is drawn at every size (draw_tile) and named by file_name; names used twice
   are reported, and several sizes without {size} in the name stop the run (plan_files).
6. The PNGs are written to the output folder; existing ones are replaced only after a
   yes, or with --yes (run).

Requires: this folder's .venv (pip install -r requirements.txt): PyYAML, Pillow (with
FreeType); svg_shapes.py beside this file (no SVG library needed). config.yaml is
gitignored: personal paths go there, never into the committed config.example.yaml.
No secrets, so no .env.

Inputs -> outputs: example/input/*.yaml -> example/output/<file_name>.png until
config.yaml points elsewhere. Paths may be absolute (used as-is) or relative: resolved
against this tool's folder (relative_to: tool, default) or the current working
directory (relative_to: cwd). The icon list (example/input/icons.yaml shows every form):
    icons:
      - { text: A12, note: shown in the run's list only }   -> a12.png
      - { text: "P{n}", numbers: [1, 2] }                   -> p1.png, p2.png
      - { text: Home, file: home-blue, shape: shapes/circle.svg, fill: "#3d6aa8" }
      - { top: N, bottom: "07", top_colour: "#ffd54a" }     -> n07.png

Run:
    python main.py --run                     icons from example/input/ into example/output/
    python main.py --run --dry-run           list what would be made, write nothing
    python main.py --run --sizes 32,48 --file-name "{size}/{name}"
    python main.py --run --input my-icons.yaml --output D:/icons --yes
    python main.py --help                    all flags; see README.md
"""

# -----------------------------------------------------------------------------------------
#                libraries
# -----------------------------------------------------------------------------------------
import argparse
import json
import re
import shutil
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

from svg_shapes import render_svg

# -----------------------------------------------------------------------------------------
#                variables
# -----------------------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
DEFAULTS = {
    "input": "example/input", "output": "example/output", "relative_to": "tool",
    "dry_run": False, "yes": False,
    # which sizes, and how the files are named
    "sizes": [32], "file_name": "{name}", "name_case": "lower", "name_separator": "-",
    # a thin outline and a solid inner diamond in purple, white text outlined near-black
    "colour": "#6a35b5", "edge": "#120d09", "fill": "#fcfbf8", "inner": "#c9b5e3",
    "text_colour": "#ffffff", "top_colour": "", "bottom_colour": "",
    "text_stroke": "#120d09", "text_stroke_width": 0,
    "font": "", "font_size": 0, "stack": True, "text_weight": 0.4, "letter_spacing": 1,
    "art": 0.7, "shape": "shapes/diamond.svg", "rough": 0.5,
}
RELATIVE_TO = ("tool", "cwd")
NAME_CASES = ("lower", "upper", "keep")
PATH_KEYS = ("input", "output", "shape", "font")  # resolved against relative_to
ICON_KEYS = ("colour", "edge", "fill", "inner", "text_colour", "top_colour",
             "bottom_colour", "text_stroke")  # an icon may set its own
NAME_FIELDS = ("name", "text", "size", "list")  # the placeholders file_name may use
BAD_NAME_CHARS = re.compile(r'[<>:"\\|?*\x00-\x1f]')  # not allowed in Windows file names


@dataclass
class Icon:
    """One icon to draw: its text, name, the list it came from and its own settings."""

    text: str
    name: str  # the entry's file, or its text: {name} in file_name
    list_name: str  # the list file's name without .yaml: {list} in file_name
    look: dict  # ICON_KEYS: the settings' values, or the icon's own
    shape: Path | None  # the SVG behind the text
    lines: list[str]  # the text as drawn: [top, bottom], or one line
    note: str = ""


# -----------------------------------------------------------------------------------------
#                functions: settings (template 3.2.0)
# -----------------------------------------------------------------------------------------
def parse_args(argv: list[str]) -> argparse.Namespace:
    """Defines the CLI; flags default to None so unset ones don't override config."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--run", action="store_true", help="run with config defaults")
    parser.add_argument("--input",
                        help="an icon list (YAML), or a folder of them (default: "
                             "example/input)")
    parser.add_argument("--output", help="folder for the PNGs (default: example/output/)")
    parser.add_argument("--relative-to", choices=RELATIVE_TO,
                        help="base for relative paths: this tool's folder or the cwd")
    parser.add_argument("--dry-run", action="store_true", default=None,
                        help="list what would be made, write nothing")
    parser.add_argument("--yes", action="store_true", default=None,
                        help="replace existing PNGs without asking")
    parser.add_argument("--sizes",
                        help="comma-separated PNG sizes in px, e.g. 32,48,64 "
                             "(default: 32)")
    parser.add_argument("--file-name",
                        help="PNG name: {name}, {text}, {size}, {list}; a / makes "
                             "subfolders, e.g. '{size}/{name}' (default: {name})")
    parser.add_argument("--name-case", choices=NAME_CASES,
                        help="names in lower case, upper case, or as written")
    parser.add_argument("--name-separator", help="replaces spaces in names (default: -)")
    parser.add_argument("--colour", help="the shape's {colour}: outline and inner diamond")
    parser.add_argument("--edge", help="the dark edge around the shape's pieces ({edge})")
    parser.add_argument("--fill", help="the shape's {fill}, e.g. '#3d6aa8'")
    parser.add_argument("--inner", help="the shape's inner line ({inner})")
    parser.add_argument("--text-colour", help="the text, e.g. '#ffffff'")
    parser.add_argument("--top-colour", help="the upper line; '' = text_colour")
    parser.add_argument("--bottom-colour", help="the lower line; '' = text_colour")
    parser.add_argument("--text-stroke", help="the line around the text; '' = none")
    parser.add_argument("--text-stroke-width", type=float,
                        help="in px; 0 = size / 24, at least 1.4 px")
    parser.add_argument("--font", help="a .ttf/.otf file; '' = Pillow's built-in font")
    parser.add_argument("--font-size", type=int,
                        help="text size in px at 32 px; 0 = fitted to the drawing")
    parser.add_argument("--stack", action=argparse.BooleanOptionalAction, default=None,
                        help="letters on top, the number under them (A over 12)")
    parser.add_argument("--text-weight", type=float,
                        help="px added to the letters' weight, 0 = the font's own")
    parser.add_argument("--letter-spacing", type=float,
                        help="px between letters, so each stands on its own")
    parser.add_argument("--art", type=float,
                        help="the drawing's share of the PNG, 0-1 (0.7 = 22 of 32 px)")
    parser.add_argument("--shape", help="the SVG template behind the text (shapes/)")
    parser.add_argument("--rough", type=float,
                        help="chips in the shape's edges, how deep (viewBox units); "
                             "0 = none")
    return parser.parse_args(argv)


def ensure_config(dry_run: bool) -> Path | None:
    """
    Returns the config file to read, offering to create config.yaml on the first run.

    config.yaml is personal and gitignored, so a fresh checkout only has the committed
    config.example.yaml. A real run asks before copying it (inform-and-confirm-each-step);
    on "no", without a terminal, or in a dry run, nothing is written and the example is
    read for this run only.

    Returns:
        config.yaml, config.example.yaml (until config.yaml exists), or None when
        neither exists.
    """
    config, example = HERE / "config.yaml", HERE / "config.example.yaml"
    if config.exists():
        if example.exists():
            update_config(config, example, dry_run)
        return config
    if not example.exists():
        return None
    if not dry_run:
        try:
            answer = input("config.yaml not found. "
                           "Create it from config.example.yaml? (y/n): ")
        except EOFError:
            answer = ""
            print()
        if answer.strip().lower() == "y":
            shutil.copyfile(example, config)  # byte-identical, so it diffs cleanly later
            print(f"Created {config.name}; edit it to use your own data.")
            return config
    print("Using config.example.yaml for this run; config.yaml was not created.")
    return example


def merge_config_text(example_text: str, old: dict) -> tuple[str, list[str]]:
    """
    Puts the values of an old config into the text of a new example.

    Only top-level keys are touched, so comments, order and new keys come from the
    example. A `key: value` line gets the old value as JSON (valid YAML), unless it equals
    the example's; a key followed by an indented block (a nested mapping or list) gets
    the old value as a YAML block.

    Returns:
        (merged text, old keys the example no longer has).
    """
    # key : spacing : value (a quoted value may contain #) : optional comment : line ending
    line_re = re.compile(r"^([A-Za-z_][\w-]*):([ \t]*)"
                         r"(\"(?:[^\"\\r\n]|\.)*\"|'(?:[^'\r\n]|'')*'|[^#\r\n]*?)"
                         r"([ \t]*#[^\r\n]*)?(\r?\n)?$")
    lines = example_text.splitlines(keepends=True)
    merged, used, i = [], set(), 0
    while i < len(lines):
        line, i = lines[i], i + 1
        match = line_re.match(line)
        if not match or match.group(1) not in old:
            merged.append(line)
            continue
        key, space, value, comment, newline = match.groups()
        used.add(key)
        if value.strip():
            if yaml.safe_load(value) == old[key]:
                merged.append(line)  # unchanged: keep the example's text and spacing
                continue
            new_value = json.dumps(old[key], ensure_ascii=False).ljust(len(value))
            merged.append(f"{key}:{space}{new_value}{comment or ''}{newline or ''}")
            continue
        while i < len(lines) and lines[i].startswith((" ", "\t", "- ")):
            i += 1  # skip the example's block; the old value replaces it
        block = yaml.safe_dump({key: old[key]}, sort_keys=False, allow_unicode=True,
                               default_flow_style=False).splitlines()
        nl = newline or "\n"
        merged.append(f"{block[0]}{comment or ''}{nl}")
        merged.extend(f"{b}{nl}" for b in block[1:])
    return "".join(merged), [key for key in old if key not in used]


def update_config(config: Path, example: Path, dry_run: bool) -> None:
    """
    Offers to update config.yaml when its settings differ from config.example.yaml's.

    Compares top-level keys only: the values are the user's own, and a nested block may
    hold the user's own entries. A key only the example has falls back to DEFAULTS, a key
    only config.yaml has is ignored; comment-only changes to the example don't count.
    Asked on every run until the keys match. Before overwriting, the old config.yaml is
    saved as config.yaml.bak (gitignored). Without a terminal or in a dry run, nothing is
    written (inform-and-confirm-each-step).
    """
    old = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    with open(example, encoding="utf-8", newline="") as f:
        example_text = f.read()
    new = yaml.safe_load(example_text) or {}
    missing = [key for key in new if key not in old]
    unknown = [key for key in old if key not in new]
    if not missing and not unknown:
        return
    print("config.yaml differs from config.example.yaml:")
    if missing:
        print(f"  missing (defaults used): {', '.join(missing)}")
    if unknown:
        print(f"  not read by this tool (ignored): {', '.join(unknown)}")
    if dry_run:
        print("Dry run: config.yaml left as it is.")
        return
    try:
        answer = input("  m = update: new example, keep your values (recommended)\n"
                       "  r = replace: fresh copy of the example, your values are lost\n"
                       "  k = keep config.yaml as it is (asked again on the next run)\n"
                       "Choice (m/r/k): ").strip().lower()
    except EOFError:
        print("\nNo terminal to ask on: config.yaml left as it is.")
        return
    backup = config.with_name("config.yaml.bak")
    if answer == "m":
        merged, dropped = merge_config_text(example_text, old)
        shutil.copyfile(config, backup)
        with open(config, "w", encoding="utf-8", newline="") as f:
            f.write(merged)
        print(f"Updated config.yaml, your values kept (old one: {backup.name}).")
        if dropped:
            print(f"No longer in the example, dropped: {', '.join(dropped)}.")
        for key, value in new.items():
            if isinstance(value, dict) and isinstance(old.get(key), dict):
                added = [k for k in value if k not in old[key]]
                if added:
                    print(f"New in the example, not added to your {key}: "
                          f"{', '.join(added)} (copy them from config.example.yaml).")
    elif answer == "r":
        shutil.copyfile(config, backup)
        shutil.copyfile(example, config)
        print(f"Replaced config.yaml with the example (old one: {backup.name}).")
    else:
        print("Kept config.yaml; you'll be asked again on the next run.")


def load_settings(args: argparse.Namespace) -> dict:
    """
    Merges settings: CLI flags > config.yaml > DEFAULTS, and checks them.

    Paths ("input", "output", "shape", "font"): an absolute one is used as-is; a relative
    one is resolved against this tool's folder (relative_to: tool) or the current working
    directory (relative_to: cwd); an empty "shape" or "font" stays None (no shape, the
    built-in font).

    Returns:
        Settings with the path keys as absolute Paths (or None), "sizes" as a list of
        whole numbers.

    Raises:
        SystemExit: a setting has a value the tool can't use; the message names it.
    """
    settings = dict(DEFAULTS)
    config_file = ensure_config(bool(args.dry_run))
    if config_file:
        loaded = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        settings.update(loaded)
    settings.update({k: v for k, v in vars(args).items() if v is not None and k != "run"})
    if settings["relative_to"] not in RELATIVE_TO:
        raise SystemExit(f"Invalid relative_to {settings['relative_to']!r}: "
                         "choose 'tool' or 'cwd'.")
    sizes = settings["sizes"]
    if isinstance(sizes, (str, int)):  # from --sizes "32,48", or a single number
        sizes = str(sizes).split(",")
    try:
        settings["sizes"] = list(dict.fromkeys(int(str(s).strip()) for s in sizes))
    except ValueError:
        raise SystemExit(f"Invalid sizes {sizes!r}: whole numbers of px, e.g. [32, 48].")
    if not settings["sizes"] or min(settings["sizes"]) < 8:
        raise SystemExit(f"Invalid sizes {settings['sizes']!r}: at least one, each 8 px "
                         "or more.")
    if not 0 < settings["art"] <= 1:
        raise SystemExit(f"Invalid art {settings['art']!r}: the drawing's share of the "
                         "PNG, more than 0 and at most 1 (0.7 = 22 of 32 px).")
    if settings["name_case"] not in NAME_CASES:
        raise SystemExit(f"Invalid name_case {settings['name_case']!r}: choose "
                         f"{', '.join(NAME_CASES)}.")
    try:
        settings["file_name"].format(**{field: "x" for field in NAME_FIELDS})
    except (KeyError, IndexError, ValueError) as error:
        raise SystemExit(f"Invalid file_name {settings['file_name']!r} ({error}): use "
                         f"{', '.join('{' + f + '}' for f in NAME_FIELDS)}.")
    base = HERE if settings["relative_to"] == "tool" else Path.cwd()
    for key in PATH_KEYS:
        settings[key] = resolve(settings[key], base)
    return settings


def resolve(value: str | None, base: Path) -> Path | None:
    """A path setting as an absolute Path; empty means none."""
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


# -----------------------------------------------------------------------------------------
#                functions: the icon lists and file names
# -----------------------------------------------------------------------------------------
def list_files(source: Path) -> list[Path] | None:
    """The input list itself, or the folder's .yaml/.yml lists; None if it isn't there."""
    if source.is_file():
        return [source]
    if source.is_dir():
        return sorted(p for p in source.iterdir() if p.suffix.lower() in (".yaml", ".yml"))
    return None


def read_icons(files: list[Path], settings: dict) -> tuple[list[Icon], list[str]]:
    """
    The icons in the YAML lists, and one line per entry left out.

    An entry is a text (`- A12`) or a mapping: text (`{n}` with `numbers` makes one icon
    per number), or top and bottom (the two lines, set by hand), file, note, shape and any
    of ICON_KEYS (colours of the shape and the text). An entry without text, or with a
    missing shape, is left out.
    """
    base = HERE if settings["relative_to"] == "tool" else Path.cwd()
    icons: list[Icon] = []
    problems: list[str] = []
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = data.get("icons", []) if isinstance(data, dict) else data
        for number, entry in enumerate(entries or [], start=1):
            where = f"{path.name} entry {number}"
            if isinstance(entry, (str, int)):
                entry = {"text": str(entry)}
            if not isinstance(entry, dict):
                problems.append(f"{where} left out: not a text or a mapping ({entry!r})")
                continue
            parts = [str(entry.get(k) or "").strip() for k in ("top", "bottom")]
            text = "".join(parts) if any(parts) else str(entry.get("text") or "").strip()
            if not text:
                problems.append(f"{where} left out: no text, top or bottom ({entry!r})")
                continue
            numbers = entry.get("numbers")
            look = {key: str(entry[key]) if entry.get(key) is not None else settings[key]
                    for key in ICON_KEYS}
            # its own shape: a path (relative to relative_to) or '' for none
            shape = (resolve(entry["shape"], base) if "shape" in entry
                     else settings["shape"])
            if shape and not shape.is_file():
                problems.append(f"{where} left out: shape not found ({shape})")
                continue
            for n in numbers or [None]:
                fill_in = (lambda s: s.replace("{n}", str(n))) if numbers else str
                if any(parts):  # top / bottom set by hand: drawn as given
                    lines = [fill_in(p) for p in parts if p]
                    one = "".join(lines)
                else:
                    one = fill_in(text)
                    lines = stacked(one) if settings["stack"] else [one]
                icons.append(Icon(text=one,
                                  name=one if numbers else str(entry.get("file") or one),
                                  list_name=path.stem, look=look, shape=shape,
                                  lines=lines, note=str(entry.get("note", ""))))
    return icons, problems


def clean_name(text: str, settings: dict) -> str:
    """A name part: name_case applied, spaces replaced by name_separator."""
    text = text.strip()
    if settings["name_case"] == "lower":
        text = text.lower()
    elif settings["name_case"] == "upper":
        text = text.upper()
    return re.sub(r"\s+", settings["name_separator"], text)


def plan_files(icons: list[Icon],
               settings: dict) -> tuple[list[tuple[Icon, int, str]], list[str], str]:
    """
    Every (icon, size, file) to write, its file named by file_name.

    A name used twice is a note (the last one wins), unless it only repeats across
    sizes: then file_name lacks {size} and every size would overwrite the one before,
    so the run stops.

    Returns:
        (the planned files in list order, notes, the error that stops the run or "").
    """
    planned, notes, seen = [], [], {}
    for icon in icons:
        for size in settings["sizes"]:
            fields = {"name": clean_name(icon.name, settings),
                      "text": clean_name(icon.text, settings), "size": size,
                      "list": clean_name(icon.list_name, settings)}
            file = settings["file_name"].format(**fields).strip("/") + ".png"
            if BAD_NAME_CHARS.search(file):
                notes.append(f"{file} left out: a character a file name can't have")
                continue
            planned.append((icon, size, file))
            seen.setdefault(file, []).append((icon, size))
    for file, uses in seen.items():
        if len(uses) < 2:
            continue
        if len({id(icon) for icon, _ in uses}) == 1:
            return planned, notes, (f"{file} would be written for sizes "
                                    f"{', '.join(str(s) for _, s in uses)}: add {{size}} "
                                    "to file_name, e.g. '{size}/{name}' or "
                                    "'{name}-{size}'")
        notes.append(f"{file} is in the list {len(uses)} times: the last one wins")
    return planned, notes, ""


# -----------------------------------------------------------------------------------------
#                functions: drawing
# -----------------------------------------------------------------------------------------
def art_size(size: int, settings: dict) -> int:
    """The drawing's size in px in the middle of a size x size PNG."""
    return max(1, min(size, round(size * settings["art"])))


def load_font(settings: dict, size: int) -> ImageFont.FreeTypeFont:
    """
    The text font for one PNG size: a .ttf/.otf file, else Pillow's built-in one.
    font_size 0 = 0.36 x the drawing's size stacked in two lines (A over 12), else 0.38 x;
    a set font_size is meant for 32 px and scaled with the size. run() then fits it to
    the whole list (fitted_font).
    """
    share = 0.36 if settings["stack"] else 0.38
    px = (round(settings["font_size"] * size / 32) if settings["font_size"]
          else round(art_size(size, settings) * share))
    if settings["font"]:
        return ImageFont.truetype(str(settings["font"]), px)
    return ImageFont.load_default(px)


def text_style(settings: dict, stroke: str, size: int) -> dict:
    """How the text is drawn: outline, weight and letter spacing, px (outline 0 = auto)."""
    outline = settings["text_stroke_width"] or max(1.4, size / 24)
    return {"outline": outline if stroke else 0, "weight": settings["text_weight"],
            "spacing": settings["letter_spacing"]}


def draw_tile(icon: Icon, size: int, settings: dict,
              font: ImageFont.FreeTypeFont) -> Image.Image:
    """
    A square PNG, size px: the SVG shape (its {colour}, {edge}, {fill}, {inner} from the
    icon's look; a few chips in its edges when rough > 0, seeded by the text) drawn
    art x size px big in the middle, the rest clear, since a map draws an icon at its
    pixel size, centred on its spot; the text over it (stacked: A over 12), which may
    use the whole canvas, outlined in text_stroke so it reads on any shape and ground.
    """
    look, art = icon.look, art_size(size, settings)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if icon.shape:
        colours = {k: look[k] for k in ("colour", "edge", "fill", "inner")}
        shape = render_svg(icon.shape, art, colours, rough=settings["rough"],
                           seed=zlib.crc32(icon.text.encode("utf-8")))
        image.alpha_composite(shape, ((size - art) // 2, (size - art) // 2))
    stroke = look["text_stroke"]
    top = look["top_colour"] or look["text_colour"]
    bottom = look["bottom_colour"] or look["text_colour"]
    # one line: top_colour; two: top_colour, bottom_colour
    colours = [top] if len(icon.lines) == 1 else [top] + [bottom] * (len(icon.lines) - 1)
    image.alpha_composite(text_layer(icon.lines, font, size, colours, stroke,
                                     **text_style(settings, stroke, size)))
    return image


def fitted_font(icons: list[Icon], settings: dict, font: ImageFont.FreeTypeFont,
                size: int) -> ImageFont.FreeTypeFont:
    """
    One text size for every icon of a PNG size: the configured size, or smaller until
    every label of the list fits the canvas, so every icon's letters are the same size
    (A1 as big as C104a).
    """
    if not icons:
        return font
    labels = {tuple(icon.lines) for icon in icons}
    style = text_style(settings, icons[0].look["text_stroke"], size)
    while font.size > 6:
        if all(max(text_extent(list(lines), font, **style)) <= size for lines in labels):
            return font
        font = font.font_variant(size=font.size - 1)
    return font


def text_extent(lines: list[str], font: ImageFont.FreeTypeFont, outline: float,
                weight: float, spacing: float) -> tuple[float, float]:
    """How wide and tall the lines are when drawn (letters, spacing, outline), px."""
    reach = outline + weight
    width = max(sum(font.getlength(c) for c in line) + spacing * (len(line) - 1)
                for line in lines) + 2 * reach
    _, top, _, bottom = font.getbbox("H0")
    cap = bottom - top
    height = cap * len(lines) + cap * 0.22 * (len(lines) - 1) + 2 * reach
    return width, height


def stacked(text: str) -> list[str]:
    """
    The text in lines: a line break where the text has one ("A\\n12"), else letters on
    top and the number under them (A12 -> A / 12); a text without both stays one line.
    """
    if "\n" in text:
        return [line.strip() for line in text.split("\n") if line.strip()]
    match = re.fullmatch(r"\s*([^\d\s]+)\s*(\d.*?)\s*", text)
    return [match.group(1), match.group(2)] if match else [text]


def text_layer(lines: list[str], font: ImageFont.FreeTypeFont, size: int,
               colours: list[str], stroke: str, outline: float, weight: float,
               spacing: float) -> Image.Image:
    """
    The lines centred on a size x size layer, one under the other (each in its colour
    from `colours`), each letter on its own,
    `spacing` px apart: first every letter wide in the stroke colour (the outline,
    `outline` px past it), then every letter on top, `weight` px bolder than the font; so
    letters
    never run into each other, the dark outline runs between them. Drawn 4x larger and
    scaled down, so fractions of a pixel show and the edges stay clean. The font is already
    sized for the whole list (fitted_font), so it is not shrunk here.
    """
    s = 4  # supersampling
    big = font.font_variant(size=font.size * s)
    reach = round((outline + weight) * s) if stroke else 0
    thick = round(weight * s)
    _, top, _, bottom = big.getbbox("H0")  # one line height for all: capitals and digits
    cap = bottom - top
    gap = cap * 0.22  # space between the lines
    total = cap * len(lines) + gap * (len(lines) - 1)

    # every letter's place: lines centred across, the block centred down
    letters = []
    y = (size * s - total) / 2 - top
    for line, colour in zip(lines, colours):
        widths = [big.getlength(c) for c in line]
        x = (size * s - (sum(widths) + spacing * s * (len(line) - 1))) / 2
        for char, w in zip(line, widths):
            letters.append((char, (x, y), colour))
            x += w + spacing * s
        y += cap + gap

    layer = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    if stroke:
        for char, at, _ in letters:
            draw.text(at, char, font=big, fill=stroke, stroke_width=reach,
                      stroke_fill=stroke)
    for char, at, colour in letters:
        draw.text(at, char, font=big, fill=colour, stroke_width=thick, stroke_fill=colour)
    return layer.resize((size, size), Image.LANCZOS)


# -----------------------------------------------------------------------------------------
#                functions: work
# -----------------------------------------------------------------------------------------
def run(settings: dict, files: list[Path]) -> int:
    """
    Reads the lists, draws every icon at every size, writes the PNGs (none in a dry run).

    Returns:
        0 when done (or a dry run), 1 when names collide across sizes or the user
        declined replacing existing PNGs.
    """
    out = settings["output"]
    print(f"input : {settings['input']} ({len(files)} list(s))")
    print(f"output: {out}")
    print(f"sizes : {', '.join(f'{s}x{s}' for s in settings['sizes'])}, "
          f"named {settings['file_name']}.png")
    icons, problems = read_icons(files, settings)
    planned, notes, error = plan_files(icons, settings)
    problems += notes
    if error:
        print(f"\nStopped, nothing written: {error}")
        return 1
    # one text size per PNG size: the size at which the list's widest label fits
    fonts = {}
    for size in settings["sizes"]:
        wanted = load_font(settings, size)
        fonts[size] = fitted_font(icons, settings, wanted, size)
        if fonts[size].size < wanted.size:
            problems.append(f"{size} px: text set at {fonts[size].size} px for every icon "
                            f"(not {wanted.size}), so the widest label fits")
    images = {file: draw_tile(icon, size, settings, fonts[size])
              for icon, size, file in planned}
    existing = [file for file in images if (out / file).exists()]

    if problems:
        print("\n== notes ==")
        for line in problems:
            print(f"  {line}")
    print(f"\n== icons ({len(images)} PNGs) ==")
    for icon, size, file in planned:
        state = "replace" if file in existing else "new"
        note = f"  # {icon.note}" if icon.note else ""
        print(f"  {file}  {icon.text!r}  {size}x{size}  {state}{note}")

    if settings["dry_run"]:
        print("\ndry run: nothing written")
        return 0
    if existing and not settings["yes"]:
        try:
            answer = input(f"\n{len(existing)} PNG(s) in the output folder would be "
                           "replaced. Go ahead? (y/n): ")
        except EOFError:
            answer = ""
            print()
        if answer.strip().lower() != "y":
            print("nothing written")
            return 1
    for file, image in images.items():
        (out / file).parent.mkdir(parents=True, exist_ok=True)
        image.save(out / file)
    print(f"\nwritten: {len(images)} PNG(s) to {out}")
    return 0


# -----------------------------------------------------------------------------------------
#                main
# -----------------------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    # 1. No arguments: usage guide only, never work (no-args-usage-guide)
    if not argv:
        print(__doc__.strip())
        return 0
    args = parse_args(argv)
    # settings without a command word: the guide, and the command with --run added
    if not args.run and not args.dry_run:
        print(__doc__.strip())
        print(f"\nNo command given: add --run, e.g. python main.py --run {' '.join(argv)}")
        return 2
    # 2.-3. Settings from CLI, config.yaml (offered on the first real run), defaults
    settings = load_settings(args)
    files = list_files(settings["input"])
    if not files:
        print(f"No icon list found: {settings['input']} (a .yaml file, or a folder "
              "with .yaml files)")
        return 1
    # 4.-6. Read, name, draw, write
    return run(settings, files)


# -----------------------------------------------------------------------------------------
#                start
# -----------------------------------------------------------------------------------------
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
