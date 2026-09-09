"""Render complete desktop profiles from shared controls and constrained designs."""
import colorsys
import functools
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from theme_catalog import has_symlink, safe_theme_id

DESIGN_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'font': {'type': 'string', 'enum': ['Inter', 'DejaVu Serif', 'DejaVu Sans', 'JetBrainsMono Nerd Font']},
        'radius': {'type': 'integer', 'minimum': 0, 'maximum': 24},
        'spacing': {'type': 'integer', 'minimum': 2, 'maximum': 16},
        'opacity': {'type': 'number', 'minimum': 0.75, 'maximum': 1},
        'bar_position': {'type': 'string', 'enum': ['top', 'bottom']},
        'widget_edge': {'type': 'string', 'enum': ['left', 'right']},
        'launcher_width': {'type': 'integer', 'minimum': 40, 'maximum': 60},
        # The pointer set the drawn Oldbook-Ghost shapes inherit every other
        # shape from. Only the waiting shapes are drawn here; the arrow, the
        # text bar and the resize handles come from an installed Xcursor theme,
        # so a theme that cannot name its own leaves the pointer in the previous
        # theme's colours. An icon-theme directory name, never a path.
        'cursors': {'type': 'string', 'pattern': r'[A-Za-z][A-Za-z0-9._+-]{0,63}'},
        # The folder icon set, built by alpine/bin/build-icon-theme from the
        # locked Papirus package in this theme's own colours. Named rather than
        # generated at switch time because 881 SVGs are versioned, not rendered.
        'icons': {'type': 'string', 'pattern': r'[A-Za-z][A-Za-z0-9._+-]{0,63}'}},
    'required': ['font', 'radius', 'spacing', 'opacity', 'bar_position', 'widget_edge',
                 'launcher_width', 'cursors', 'icons']}

# Roles a complete theme may declare beyond the thirteen the palette started
# with. Every one of them exists because a real consumer needed a value the
# thirteen could not express, and each has a derivation so dropping in a new
# theme stays a thirteen-colour job:
#   *_dim            the ANSI 1-6 half of a terminal palette. Without these the
#                    renderer snapped every dark ANSI slot onto its bright
#                    sibling -- or worse, onto an unrelated role: Gruvbox's dark
#                    yellow landed on green and its dark magenta and cyan both
#                    landed on muted -- so Foot, Ghostty, btop, Neovim, the
#                    Linux console and the LUKS prompt lost half their colours.
#   surface_bright   the raised surface above `border`: selection grounds,
#                    divider rules, btop's followed rows.
#   subtle           ANSI 7, and the dim neutral the bar labels itself with.
#   foreground_dim   secondary text: inactive titles, sidebars, footers. It used
#                    to snap to `purple`.
OPTIONAL_ROLES = ('red_dim', 'green_dim', 'yellow_dim', 'blue_dim', 'purple_dim',
                  'aqua_dim', 'orange_dim', 'surface_bright', 'subtle', 'foreground_dim')


# The two asset sets a descriptor may leave unnamed. Both name something that is
# installed rather than generated, and a theme with no pointer set at all has a
# broken pointer, so an older descriptor inherits the shipped sets instead of
# being refused. Anything a descriptor does name is validated as strictly as
# every other design value.
DESIGN_DEFAULTS = {'cursors': 'simp1e-cursors-gruvbox-dark', 'icons': 'Oldbook-Gruvbox'}


def validate_design(design):
    if isinstance(design, dict):
        design = {**DESIGN_DEFAULTS, **design}
    if not isinstance(design, dict) or set(design) != set(DESIGN_SCHEMA['required']):
        raise ValueError('A complete theme requires typography, geometry, windows, bar and widget design')
    for key, rule in DESIGN_SCHEMA['properties'].items():
        value = design[key]
        if 'enum' in rule:
            valid = isinstance(value, str) and value in rule['enum']
        elif 'pattern' in rule:
            valid = isinstance(value, str) and re.fullmatch(rule['pattern'], value) is not None
        else:
            valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                     and math.isfinite(value) and rule['minimum'] <= value <= rule['maximum']
                     and (rule['type'] != 'integer' or isinstance(value, int)))
        if not valid:
            raise ValueError('Invalid theme design ' + key)
    return design


@functools.lru_cache(maxsize=8192)
def rgb(value):
    return tuple(int(value.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))


@functools.lru_cache(maxsize=1 << 16)
def blend(first, second, amount):
    return '#%02x%02x%02x' % tuple(round(a * (1 - amount) + b * amount)
                                 for a, b in zip(rgb(first), rgb(second)))


def colors(theme):
    palette = theme['palette']
    for value in palette.values():
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError('Invalid theme color')
    background, foreground = palette['background'], palette['foreground']
    accent = palette.get('accent', palette.get('yellow', foreground))
    result = {'background': background, 'foreground': foreground, 'accent': accent,
              'background_hard': blend(background, '#000000', .26),
              'surface': blend(background, foreground, .10),
              'border': blend(background, foreground, .22),
              'muted': blend(background, foreground, .60)}
    for name, hue in [('red', .01), ('green', .29), ('yellow', .13), ('blue', .57),
                      ('purple', .78), ('aqua', .46), ('orange', .07)]:
        color = '#%02x%02x%02x' % tuple(round(c * 255) for c in colorsys.hls_to_rgb(hue, .66, .55))
        result[name] = blend(color, accent, .16)
    result.update(palette)
    result['yellow'] = accent
    # Derive the roles a thirteen-colour descriptor leaves out, so dropping in a
    # new theme never has to author them, and a theme that does declare them
    # (Gruvbox owns a canonical sixteen-colour terminal palette) keeps its own.
    for name in ('red', 'green', 'yellow', 'blue', 'purple', 'aqua', 'orange'):
        result.setdefault(name + '_dim', blend(result[name], background, .32))
    result.setdefault('surface_bright', blend(background, foreground, .32))
    result.setdefault('subtle', blend(background, foreground, .66))
    result.setdefault('foreground_dim', blend(background, foreground, .78))
    return result


def is_light(palette):
    """True when the theme paints dark text on a light ground."""
    def luminance(value):
        return sum(channel * weight for channel, weight
                   in zip(rgb(value), (.2126, .7152, .0722))) / 255
    return luminance(palette['background']) > luminance(palette['foreground'])


def distance(first, second):
    return sum((a - b) ** 2 for a, b in zip(rgb(first), rgb(second)))


# The grounds a template tint is laid over: the two dark grounds, the raised
# surface, the text colour and the cream the renderer derives from it.
BLEND_BASES = ('#282828', '#1d2021', '#3c3836', '#ebdbb2', '#fbf1c7')


# How finely a tint is fitted. Twenty-one steps put the reconstruction within
# half a step -- under three per cent of the distance between the two roles --
# which is finer than the shades the templates were hand-picked to.
BLEND_STEPS = 21


@functools.lru_cache(maxsize=8192)
def decompose(value, sources):
    """Express one shade as (base, tint, amount) in the baseline's own shades.

    The search runs entirely in the template palette, so its answer does not
    depend on the theme being rendered and one result serves every theme.
    """
    best = None
    for base in BLEND_BASES:
        if base not in sources:
            continue
        for tint in sources:
            for step in range(BLEND_STEPS):
                amount = step / (BLEND_STEPS - 1)
                found = distance(value, blend(base, tint, amount))
                if best is None or found < best[0]:
                    best = (found, base, tint, amount)
                if not found:
                    return best[1:]
    return best[1:]


def fit(value, replacements):
    """Rebuild an off-palette shade as a blend of two of the theme's roles.

    Snapping to whichever single role sits nearest is what let a file full of
    hand-picked shades look themed while it was not: the bar's amber
    keep-awake ground (#504018) is `background` carrying a little accent, and
    the nearest single role to it is a flat `surface`, so under another theme
    the tint simply disappeared and every status ground collapsed into the same
    grey. Fitting `blend(base, tint, amount)` keeps both the ground it sits on
    and the colour it is tinted with, and reproduces the plain nearest-role
    answer whenever the amount comes out at one, so nothing that was already
    landing exactly moves.
    """
    base, tint, amount = decompose(value, tuple(sorted(replacements)))
    return blend(replacements[base], replacements[tint], amount)


def recolor(body, baseline, palette, path):
    if path == '.config/waybar/style.css':
        # The command-deck ghost is fixed branding, including its hover glow.
        # Recolor the surrounding controls while keeping these authored rules.
        parts = re.split(r'(?m)(^[ \t]*#custom-ghost(?:\s*|:hover\s*)\{[^}]*\})', body)
        if len(parts) > 1:
            return ''.join(part if index % 2 else recolor(part, baseline, palette, path)
                           for index, part in enumerate(parts))
    replacements = {value.lower(): palette[key] for key, value in baseline.items() if key in palette}
    replacements['#fabd2f'] = palette['accent']
    replacements['#fbf1c7'] = blend(palette['foreground'], '#ffffff', .2)
    replacements['#32302f'] = blend(palette['background'], palette['foreground'], .055)
    fitted = {}
    def color(value):
        value = value.lower()
        if value in replacements:
            return replacements[value]
        if value not in fitted:
            fitted[value] = fit(value, replacements)
        return fitted[value]
    def replace(match):
        value = match.group(0)
        prefix = '#' if value.startswith('#') else ''
        digits = value.lstrip('#')
        if len(digits) == 8:
            if 'qt6ct/' in path or (path.endswith('foot.ini') and digits.startswith('ff')):
                return prefix + digits[:2] + color('#' + digits[2:])[1:]
            return prefix + color('#' + digits[:6])[1:] + digits[6:]
        return prefix + color('#' + digits)[1:]
    body = re.sub(r'(?<![\w])#?(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6})(?![\w])', replace, body)
    def rgba(match):
        old = '#%02x%02x%02x' % tuple(int(match[i]) for i in (2, 3, 4))
        return match[1] + '(' + ', '.join(map(str, rgb(color(old)))) + match[5] + ')'
    return re.sub(r'\b(rgb|rgba)\(\s*(\d+),\s*(\d+),\s*(\d+)([^)]*)\)', rgba, body)


def render_profile(repo, theme):
    design = validate_design(theme.get('design'))
    palette = colors(theme)
    base = repo / 'alpine/desktop'
    reference = repo / 'alpine/themes/profiles/gruvbox-dark'
    baseline = json.loads((repo / 'alpine/themes/gruvbox-dark.json').read_text())['palette']
    paths = {str(p.relative_to(reference)) for p in reference.rglob('*') if p.is_file()
             and not str(p.relative_to(reference)).startswith(ASSET_PREFIXES)}
    # Surfaces that carry colour but were never in the reference profile, so a
    # theme switch used to leave them in the previous theme: LXQt's own Qt
    # settings and its selectable palette preset, and the screenshot annotator.
    paths.update(('.config/waybar/config.jsonc', '.config/conky/panels.json',
                  '.config/lxqt/lxqt.conf', '.config/satty/config.toml', LXQT_PRESET,
                  CLAUDE_THEME))
    files = {}
    for path in sorted(paths):
        source = base / path
        if not source.is_file():
            source = reference / path
        if has_symlink(source, repo):
            raise RuntimeError('Theme template must be a regular checkout file: ' + path)
        # Every template banner names the theme it was authored for. Carrying
        # "Gruvbox Dark" into another theme's profile makes a generated file
        # read as a copy of someone else's; the identifiers applications key on
        # are the lower-case id, which this leaves alone.
        files[path] = recolor(source.read_text(), baseline, palette, path
                              ).replace('Gruvbox Dark', theme['name'])
    radius, spacing, font = design['radius'], design['spacing'], design['font']
    def change(path, pattern, replacement):
        files[path] = re.sub(pattern, replacement, files[path], flags=re.MULTILINE)
    change('.config/sway/theme.conf', r'^font .*', f'font pango:{font} 9.5')
    files['.config/sway/theme.conf'] += f'\ngaps inner {spacing}\ngaps outer {spacing + 1}\n'
    change('.config/swayfx/effects.conf', r'^corner_radius \d+', f'corner_radius {radius}')
    # SceneFX reaches 2^(blur_passes + 1) * blur_radius, so one pass at radius 4
    # samples 16 pixels, not 8. Reaching past the gap into a neighbouring window
    # is what blur is *for* and is not the defect it was once blamed for: the
    # smearing was SceneFX skipping its damage compensation, fixed upstream and
    # carried in alpine/packages/scenefx. What still needs bounding is the
    # derivation, because the corner radius alone generated 11 here -- a 44
    # pixel reach, expensive and muddy at any gap.
    change('.config/swayfx/effects.conf', r'^blur_radius \d+',
           f'blur_radius {max(2, min(radius // 2, 8))}')
    # Claude Code decides its own dimming and contrast from this one word, so a
    # light palette has to say so; the file name is what `custom:oldbook` in
    # ~/.claude/settings.json resolves against and never varies.
    change(CLAUDE_THEME, r'"base": "\w+"',
           '"base": "%s"' % ('light' if is_light(palette) else 'dark'))
    change('.config/foot/foot.ini', r'^pad=.*', f'pad={spacing}x{spacing} center')
    change('.config/foot/foot.ini', r'^alpha=.*', f'alpha={design["opacity"]}')
    change('.config/ghostty/config', r'^background-opacity\s*=.*', f'background-opacity = {design["opacity"]}')
    for axis in ('x', 'y'):
        change('.config/ghostty/config', f'^window-padding-{axis}.*', f'window-padding-{axis} = {spacing}')
    change('.config/lxqt/lxqt.conf', r'^font=.*', f'font="{font},11,-1,5,50,0,0,0,0,0"')
    change('.config/lxqt/lxqt.conf', r'^icon_theme=.*', f'icon_theme={design["icons"]}')
    change('.config/qt6ct/qt6ct.conf', r'^icon_theme=.*', f'icon_theme={design["icons"]}')
    # The preset is a named entry in LXQt Appearance, so it carries the theme's
    # own name; the previous theme's preset stays selectable beside it.
    files[f'.local/share/lxqt/palettes/{preset_name(theme)}'] = files.pop(LXQT_PRESET)
    for version in ('3.0', '4.0'):
        change(f'.config/gtk-{version}/settings.ini', r'^gtk-font-name=.*', f'gtk-font-name={font} 11')
        change(f'.config/gtk-{version}/settings.ini', r'^gtk-icon-theme-name=.*',
               f'gtk-icon-theme-name={design["icons"]}')
        change(f'.config/gtk-{version}/settings.ini', r'^gtk-cursor-theme-name=.*',
               'gtk-cursor-theme-name=Oldbook-Ghost')
        files[f'.config/gtk-{version}/gtk.css'] += (
            f'\nbutton, entry, popover > contents {{ border-radius: {radius}px; }}\n'
            f'button {{ padding: {max(3, spacing // 2)}px {spacing}px; }}\n')
    change('.config/qt6ct/qt6ct.conf', r'^general=.*', f'general="{font},11,-1,5,50,0,0,0,0,0"')
    change('.config/qt6ct/qt6ct.conf', r'^color_scheme_path=.*',
           f'color_scheme_path={Path.home()}/.config/qt6ct/colors/gruvbox-dark.conf')
    change('.config/fuzzel/fuzzel.ini', r'^font=.*', f'font={font}:size=13')
    change('.config/fuzzel/fuzzel.ini', r'^width=48$', f'width={design["launcher_width"]}')
    change('.config/fuzzel/fuzzel.ini', r'^radius=.*', f'radius={radius}')
    change('.config/fuzzel/fuzzel.ini', r'^horizontal-pad=.*', f'horizontal-pad={spacing + 16}')
    bar = json.loads(files['.config/waybar/config.jsonc'])
    bar[0]['position'] = design['bar_position']
    bar[0]['spacing'] = max(2, spacing // 2)
    files['.config/waybar/config.jsonc'] = json.dumps(bar, indent=2) + '\n'
    files['.config/waybar/waybar-state.css'] = '/* Refreshed by oldbook-waybar-dim. */\n'
    files['.config/waybar/style.css'] += (
        f'\n/* {theme["id"]}: typography and panel shape */\n'
        f'* {{ font-family: "{font}", "Symbols Nerd Font", sans-serif; }}\n'
        f'window#waybar.top .modules-left, window#waybar.top .modules-right {{ border-radius: {radius}px; }}\n'
        f'#workspaces button {{ padding: 0 {spacing}px; }}\n')
    document = json.loads(files['.config/conky/panels.json'])
    document['font'] = f'{font}:size=9'
    document['gap'] = spacing
    for panel in document['panels']:
        if panel['prefer'] in ('left', 'right'):
            panel['prefer'] = design['widget_edge']
        panel['text'] = panel['text'].replace('JetBrainsMono Nerd Font', font)
    files['.config/conky/panels.json'] = json.dumps(document, indent=2) + '\n'
    files[CURSOR_INDEX] = cursor_index(theme)
    return files


# The pointer set the desktop actually loads. Its name is fixed -- the sway
# seat line names `Oldbook-Ghost` and must keep working across themes -- while
# what it inherits is per theme, so the shapes this repository does not draw
# follow the selection instead of staying Gruvbox for ever.
CURSOR_INDEX = '.local/share/icons/Oldbook-Ghost/index.theme'
CURSOR_DIRECTORY = '.local/share/icons/Oldbook-Ghost'
# Drawn, not recoloured: the text pass must skip these or it tries to decode a
# cursor as UTF-8. `render_assets` owns everything under them.
ASSET_PREFIXES = (CURSOR_DIRECTORY + '/cursors/', '.config/wlogout/icons/')
# Claude Code watches this directory and repaints a running session when the
# file under it changes, so switching desktop themes restyles open sessions
# without restarting them. The name is fixed: settings.json selects the theme by
# it, and a per-theme name would break that reference on every switch.
CLAUDE_THEME = '.claude/themes/oldbook.json'
# LXQt reads its selectable palettes by file name, so the rendered preset takes
# the theme's own name rather than staying Gruvbox's in every profile.
LXQT_PRESET = '.local/share/lxqt/palettes/Gruvbox-Dark'


def preset_name(theme):
    """A safe file name for one theme's LXQt palette preset."""
    return re.sub(r'[^A-Za-z0-9_-]+', '-', theme['name']).strip('-') or theme['id']


def cursor_index(theme):
    """The Xcursor index for one theme, naming the set it inherits."""
    inherits = validate_design(theme.get('design'))['cursors']
    return ('[Icon Theme]\n'
            'Name=Oldbook-Ghost\n'
            f'Comment={theme["name"]} cursors: a turning ring in the theme accent, '
            f'inheriting {inherits}\n'
            f'Inherits={inherits}\n')


def _builder(repo, name):
    """Import one of the hyphenated image builders in alpine/bin/."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(
        name.replace('-', '_'), str(Path(repo) / 'alpine/bin' / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def render_assets(repo, theme):
    """The theme's binary surfaces: pointer shapes and power-deck glyph tiles.

    `render_profile` is text, and for a long time that was the whole theme file
    set, which is why the cursors and the deck's tiles stayed in one theme's
    colours whatever was selected. They are drawn with cairo rather than
    compiled, so generating them per theme costs a second and needs no toolchain
    beyond the one the desktop already has.
    """
    palette = colors(theme)
    assets = {}
    cursors = _builder(repo, 'build-cursor-theme')
    shapes = cursors.shapes(cursors.cursor_palette(palette))
    for name, data in shapes.items():
        assets[f'{CURSOR_DIRECTORY}/cursors/{name}'] = data
    deck = _builder(repo, 'build-wlogout-icons')
    for name, data in deck.tiles(deck.tile_colors(palette)).items():
        assets[f'.config/wlogout/icons/{name}'] = data
    return assets


def write_assets(repo, theme, destination, notes=None):
    """Add any missing binary asset to a profile, reporting what stopped it.

    Missing-only, exactly like the text pass: an authored or already generated
    asset is never rewritten, so an existing profile keeps the bytes it shipped.
    """
    notes = [] if notes is None else notes
    builders = [Path(repo) / 'alpine/bin' / name
                for name in ('build-cursor-theme', 'build-wlogout-icons')]
    if not all(builder.is_file() for builder in builders):
        # A checkout without the image builders has nothing to draw from; that
        # is not a failure to report, exactly as a missing console palette
        # builder is not. A builder that is present and cannot draw is.
        return notes
    try:
        assets = render_assets(repo, theme)
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        notes.append('theme assets FAILED (cursors and power deck tiles keep the '
                     'previous theme): ' + str(error))
        return notes
    for name, data in assets.items():
        target = Path(destination) / name
        if has_symlink(target, repo):
            raise RuntimeError('Theme profile must not follow symlinks: ' + name)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    return notes


def ensure_profile(repo, theme, *, assets=True, notes=None):
    identity = theme['id']
    if not safe_theme_id(identity):
        raise ValueError('Invalid theme identity')
    destination = repo / 'alpine/themes/profiles' / identity
    if has_symlink(destination, repo):
        raise RuntimeError('Theme profile must not follow symlinks')
    files = render_profile(repo, theme)
    if destination.is_dir():
        # Authored files stay editable. Complete older profiles with any missing
        # application files rather than treating them as a lesser theme class.
        for name, body in files.items():
            target = destination / name
            if has_symlink(target, repo):
                raise RuntimeError('Theme profile must not follow symlinks')
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('x') as stream:
                    stream.write(body)
        if assets:
            write_assets(repo, theme, destination, notes)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.theme-', dir=destination.parent))
    # mkdtemp is 0700; a profile is read by the deployer and by the user's own
    # applications through the links it hands out, so it takes the same mode the
    # rest of the checkout has.
    temporary.chmod(destination.parent.stat().st_mode & 0o7777)
    try:
        for name, body in files.items():
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body)
        if assets:
            write_assets(repo, theme, temporary, notes)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination
