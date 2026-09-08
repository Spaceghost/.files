"""Render complete desktop profiles from shared controls and constrained designs."""
import colorsys
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
        'radius': {'type': 'integer', 'minimum': 0, 'maximum': 18},
        'spacing': {'type': 'integer', 'minimum': 2, 'maximum': 16},
        'opacity': {'type': 'number', 'minimum': 0.75, 'maximum': 1},
        'bar_position': {'type': 'string', 'enum': ['top', 'bottom']},
        'widget_edge': {'type': 'string', 'enum': ['left', 'right']},
        'launcher_width': {'type': 'integer', 'minimum': 40, 'maximum': 60}},
    'required': ['font', 'radius', 'spacing', 'opacity', 'bar_position', 'widget_edge', 'launcher_width']}


def validate_design(design):
    if not isinstance(design, dict) or set(design) != set(DESIGN_SCHEMA['required']):
        raise ValueError('A complete theme requires typography, geometry, windows, bar and widget design')
    for key, rule in DESIGN_SCHEMA['properties'].items():
        value = design[key]
        if 'enum' in rule:
            valid = isinstance(value, str) and value in rule['enum']
        else:
            valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                     and math.isfinite(value) and rule['minimum'] <= value <= rule['maximum']
                     and (rule['type'] != 'integer' or isinstance(value, int)))
        if not valid:
            raise ValueError('Invalid theme design ' + key)
    return design


def rgb(value):
    return tuple(int(value.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))


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
    return result


def recolor(body, baseline, palette, path):
    replacements = {value.lower(): palette[key] for key, value in baseline.items() if key in palette}
    replacements['#fabd2f'] = palette['accent']
    replacements['#fbf1c7'] = blend(palette['foreground'], '#ffffff', .2)
    replacements['#32302f'] = blend(palette['background'], palette['foreground'], .055)
    def color(value):
        value = value.lower()
        if value in replacements:
            return replacements[value]
        # Preserve semantic color families for shades in the authored template.
        nearest = min(replacements, key=lambda candidate: sum((a - b) ** 2
                      for a, b in zip(rgb(value), rgb(candidate))))
        return replacements[nearest]
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
    paths = {str(p.relative_to(reference)) for p in reference.rglob('*') if p.is_file()}
    paths.update(('.config/waybar/config.jsonc', '.config/conky/panels.json'))
    files = {}
    for path in sorted(paths):
        source = base / path
        if not source.is_file():
            source = reference / path
        if has_symlink(source, repo):
            raise RuntimeError('Theme template must be a regular checkout file: ' + path)
        files[path] = recolor(source.read_text(), baseline, palette, path)
    radius, spacing, font = design['radius'], design['spacing'], design['font']
    def change(path, pattern, replacement):
        files[path] = re.sub(pattern, replacement, files[path], flags=re.MULTILINE)
    change('.config/sway/theme.conf', r'^font .*', f'font pango:{font} 9.5')
    files['.config/sway/theme.conf'] += f'\ngaps inner {spacing}\ngaps outer {spacing + 1}\n'
    change('.config/swayfx/effects.conf', r'^corner_radius \d+', f'corner_radius {radius}')
    change('.config/swayfx/effects.conf', r'^blur_radius \d+', f'blur_radius {max(2, radius // 2)}')
    change('.config/foot/foot.ini', r'^pad=.*', f'pad={spacing}x{spacing} center')
    change('.config/foot/foot.ini', r'^alpha=.*', f'alpha={design["opacity"]}')
    change('.config/ghostty/config', r'^background-opacity\s*=.*', f'background-opacity = {design["opacity"]}')
    for axis in ('x', 'y'):
        change('.config/ghostty/config', f'^window-padding-{axis}.*', f'window-padding-{axis} = {spacing}')
    for version in ('3.0', '4.0'):
        change(f'.config/gtk-{version}/settings.ini', r'^gtk-font-name=.*', f'gtk-font-name={font} 11')
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
        f'window#waybar.top .modules-left, #status {{ border-radius: {radius}px; }}\n'
        f'#workspaces button {{ padding: 0 {spacing}px; }}\n')
    document = json.loads(files['.config/conky/panels.json'])
    document['font'] = f'{font}:size=9'
    document['gap'] = spacing
    for panel in document['panels']:
        if panel['prefer'] in ('left', 'right'):
            panel['prefer'] = design['widget_edge']
        panel['text'] = panel['text'].replace('JetBrainsMono Nerd Font', font)
    files['.config/conky/panels.json'] = json.dumps(document, indent=2) + '\n'
    return files


def ensure_profile(repo, theme):
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
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.theme-', dir=destination.parent))
    try:
        for name, body in files.items():
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination
