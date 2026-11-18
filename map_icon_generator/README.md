<h1 align="center">
    Map Icon Generator
</h1>

<p align="center">
    Draws small labelled map-marker icons (PNG) from a YAML list: a shape in the middle
    (diamond, circle, shield, or your own SVG) and a short label over it, letters on top
    and the number under them, in one or more sizes.
</p>

<p align="center">
    <img alt="Template" src="https://img.shields.io/badge/template-3.2.0-blue" />
    <img alt="Last Update" src="https://img.shields.io/github/last-commit/kutaycoskuner/python-toolbox?path=map_icon_generator" />
</p>

------------------------------------------------------------------------------------------

## Folders

```bash
map_icon_generator/
├── .venv/              # Virtual environment (gitignored)
├── example/            # Bundled demo data, processed by default
│   ├── input/          # icons.yaml: the example icon list, every entry form (committed)
│   └── output/         # Result of the demo run (gitignored)
├── shapes/             # Backgrounds, SVG templates: diamond.svg, circle.svg, shield.svg
├── config.yaml         # Your settings, may hold personal paths (gitignored, offered on the first run)
├── config.example.yaml # Default settings with comments (committed)
├── main.py             # Entry point; its header docstring explains the steps
├── svg_shapes.py       # Draws the SVG templates with Pillow (no SVG library needed)
├── README.md
└── requirements.txt    # Pinned dependencies
```

------------------------------------------------------------------------------------------

## Usage

```bash
python main.py                                    # Usage guide only, does nothing
python main.py --run                              # Draw example/input/ into example/output/ (first run offers config.yaml)
python main.py --run --dry-run                    # List what would be made, write nothing
python main.py --run --sizes 32,48 --file-name "{size}/{name}"   # Two sizes, a folder each
python main.py --run --input my-icons.yaml --output D:/icons --yes
python main.py --help                             # All flags
```

- What an icon looks like
    - a square PNG (`sizes`, 32 px as shipped) with the shape drawn `art` of its size in the middle (0.7: 22 of 32 px), the rest clear: a map draws an icon at its pixel size, centred on its spot, so the margin keeps it from crowding its neighbours
    - the shape: an SVG from `shapes/` in your colours, its straight edges with a few small chips (`rough`; 0 = clean)
    - the text over it, white with a near-black outline so it reads on any ground, in two lines: letters on top, the number under them (`A12` -> A over 12); the entry's `top` / `bottom` set the lines by hand, `stack: false` keeps one line
    - every icon of a size gets the same text size: the size at which the list's widest label fits (said in the run's output when it is smaller than set), so A1 is as big as C104a
    - each letter is drawn on its own, `letter_spacing` px apart, all outlines first and the letters on top, so they never run together
- The icon list (YAML; `example/input/icons.yaml` shows every form)
    - `- A1`, or `{ text: A1 }` -> `a1.png`
    - `{ text: "P{n}", numbers: [3, 4] }` -> `p3.png`, `p4.png`
    - `{ top: N, bottom: "07", top_colour: "#ffd54a" }`: the two lines set by hand, the upper one yellow
    - `{ text: Home, file: home-blue, shape: shapes/circle.svg, fill: "#3d6aa8" }`: its own shape, colours and file name
    - `{ text: X9, shape: "" }`: no background
    - an entry may set its own `shape`, `colour`, `edge`, `fill`, `inner`, `text_colour`, `top_colour`, `bottom_colour`, `text_stroke`; `note` is only shown in the run's list
    - `input` may be one list or a folder: every `.yaml` in it is read (`{list}` in `file_name` is the list's name)
    - entries without text or with a missing shape are left out and named in the run's output
- File names (`file_name`, `name_case`, `name_separator`)
    - `file_name` is a pattern, `.png` added: `{name}` (the entry's `file`, or its text), `{text}`, `{size}`, `{list}`; a `/` makes subfolders
    - `name_case`: `lower` (default), `upper`, or `keep`; `name_separator` replaces spaces (`Home Blue` -> `home-blue`)

    | `file_name` | Sizes | Files |
    |---|---|---|
    | `{name}` | `[32]` | `a12.png` |
    | `{size}/{name}` | `[32, 48]` | `32/a12.png`, `48/a12.png` |
    | `{name}-{size}` | `[32, 48]` | `a12-32.png`, `a12-48.png` |
    | `{list}/{name}@{size}` | `[32]` | `icons/a12@32.png` |

    - several sizes without `{size}` in the name would overwrite each other: the run stops and says so, nothing written
    - a name used twice in the list is reported (the last one wins); a name with a character a file can't have is left out
- Shapes (`shapes/*.svg`): small SVG files, 32 x 32 viewBox; add your own beside them
    - placeholders filled per icon: `{colour}` (main colour), `{edge}` (a dark edge around the pieces), `{fill}`, `{inner}` (a fainter inner line)
    - drawn by `svg_shapes.py`: `rect` (with `rx`), `circle`, `ellipse`, `line`, `polygon`, `polyline`, `path` with straight lines only (`M L H V Z`), `<g>`; `fill`, `stroke`, `stroke-width`, opacities, also in `style=""`
- Existing PNGs in the output folder are only replaced after a yes, or with `--yes`
- First run
    - `config.yaml` doesn't exist in a fresh checkout (it's gitignored); the first real run asks whether to create it from `config.example.yaml`
    - on `n`, without a terminal, or with `--dry-run`, nothing is created and `config.example.yaml` is used for that run
- After an update (e.g. a `git pull` that adds or removes settings in `config.example.yaml`)
    - every run compares the settings (top-level keys) in your `config.yaml` with the example's; when they differ, it lists missing keys (defaults used) and unknown keys (ignored) and asks
        - `m`: new example, your values kept (new keys and comments come from the example; keys it dropped are listed)
        - `r`: fresh copy of the example, your values are lost
        - `k`: keep `config.yaml` as it is; asked again on the next run
    - before `m` or `r`, the old file is saved as `config.yaml.bak` (gitignored)
    - without a terminal, or with `--dry-run`, nothing is written
- Paths (`input`, `output`, `shape`, `font`)
    - what you type decides absolute vs. relative; `relative_to` only matters for relative paths

    | You write | `relative_to` | Resolves to |
    |---|---|---|
    | `input: C:/Users/me/icons.yaml` | ignored | exactly that file |
    | `input: example/input` | `tool` (default) | `map_icon_generator/example/input`, from any folder you run it in |
    | `input: icons` | `cwd` | `<folder you run the command in>/icons` |

    - Windows: use `/`, or put a path with `\` in single quotes

------------------------------------------------------------------------------------------

## Settings

- Read in this order; later sources override earlier ones
    1. defaults in `main.py`
    2. `config.yaml` (offered on the first real run; until then `config.example.yaml`)
    3. command-line flags
- No secrets, so no `.env`: everything is in `config.yaml`
- Colours: a name (`white`) or `#rrggbb`

| Setting | Flag | Default | What |
|---|---|---|---|
| **Input and output** | | | |
| `relative_to` | `--relative-to` | `tool` | base for relative paths: this tool's folder or the cwd |
| `input` | `--input` | `example/input` | an icon list (`.yaml`), or a folder: every `.yaml` in it |
| `output` | `--output` | `example/output` | folder for the PNGs |
| `dry_run` | `--dry-run` | `false` | list what would be made, write nothing |
| `yes` | `--yes` | `false` | replace existing PNGs without asking |
| **Sizes and names** | | | |
| `sizes` | `--sizes 32,48` | `[32]` | PNG sizes in px; every icon is drawn at each |
| `file_name` | `--file-name` | `{name}` | the PNG's name: `{name}`, `{text}`, `{size}`, `{list}`; `/` = subfolder |
| `name_case` | `--name-case` | `lower` | `lower`, `upper`, or `keep` |
| `name_separator` | `--name-separator` | `-` | replaces spaces in names |
| **Background** | | | |
| `shape` | `--shape` | `shapes/diamond.svg` | the SVG behind the text; `""` = none |
| `art` | `--art` | `0.7` | the shape's share of the PNG, 0-1 (0.7 = 22 of 32 px) |
| `colour` | `--colour` | `#6a35b5` | the shape's main colour `{colour}`: outline and inner diamond (purple) |
| `fill` | `--fill` | `#fcfbf8` | the shape's `{fill}`, where it has one (circle, shield) |
| `inner` | `--inner` | `#c9b5e3` | the shape's `{inner}` line, where it has one (circle, shield) |
| `edge` | `--edge` | `#120d09` | the dark edge around each piece `{edge}`, so it stands out on any ground |
| `rough` | `--rough` | `0.5` | chips in the shape's straight edges (never the text), how deep; `0` = clean |
| **Text** | | | |
| `stack` | `--stack` / `--no-stack` | `true` | upper and lower line: letters on top, the number under them |
| `text_colour` | `--text-colour` | `#ffffff` | both lines |
| `top_colour` | `--top-colour` | `""` | the upper line; `""` = `text_colour` |
| `bottom_colour` | `--bottom-colour` | `""` | the lower line; `""` = `text_colour` |
| `text_stroke` | `--text-stroke` | `#120d09` | the outline's colour; `""` = none |
| `text_stroke_width` | `--text-stroke-width` | `0` | the outline's thickness, px; `0` = size / 24, at least 1.4 px |
| `font` | `--font` | `""` | a `.ttf`/`.otf` file; `""` = Pillow's built-in font |
| `font_size` | `--font-size` | `0` | px at 32 px, scaled for other sizes; `0` = fitted to the shape (0.36 x its size stacked, 0.38 x on one line); then one size for the whole list |
| `text_weight` | `--text-weight` | `0.4` | px added to the letters' weight; `0` = the font's own |
| `letter_spacing` | `--letter-spacing` | `1` | px between letters, so each stands on its own |

------------------------------------------------------------------------------------------

## Setup Python Environment

### Prerequisites
- **Python 3.10+**: [Install Python](https://www.python.org/downloads/) (includes `pip`).

### Steps

```bash
# Go to the tool's folder
cd python-toolbox/map_icon_generator

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
#   Windows:
.venv\Scripts\activate
#   macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Deactivate the environment when done (optional)
deactivate
```
