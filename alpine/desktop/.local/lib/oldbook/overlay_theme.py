"""Share the active Oldbook palette across GTK and Qt overlays."""
import json
import os
from pathlib import Path
import re

THEMES = Path(__file__).resolve().parents[5] / 'alpine/themes'
FALLBACK = {'background': '#202020', 'background_hard': '#181818', 'surface': '#303030',
            'foreground': '#eeeeee', 'muted': '#aaaaaa', 'border': '#505050', 'accent': '#dddddd'}
HEX = re.compile(r'#[0-9a-fA-F]{6}')


def override_path():
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
    return Path(base) / 'oldbook/palette-override.json'


def accent_override(identity, colors):
    """The accent the painting on screen asked for, when the theme allows it.

    `oldbook-palette` writes this record after every image change. It is only
    honoured for the theme that produced it and only when it names colours the
    theme itself declares, so a stale record from another theme, or one edited
    by hand, can never introduce a colour the design does not own. Any problem
    reading it simply leaves the declared accent in place.
    """
    try:
        record = json.loads(override_path().read_text())
        if not isinstance(record, dict) or record.get('theme') != identity:
            return {}
        owned = {value.lower() for value in colors.values() if isinstance(value, str)}
        chosen = {}
        for key in ('accent', 'accent_secondary'):
            value = record.get(key)
            if isinstance(value, str) and HEX.fullmatch(value) and value.lower() in owned:
                chosen[key] = value.lower()
        return chosen if 'accent' in chosen else {}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def read_palette(directory=THEMES):
    try:
        identity = (directory / 'current').read_text().strip()
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', identity):
            return dict(FALLBACK)
        descriptor = json.loads((directory / (identity + '.json')).read_text())
        source = descriptor['palette']
        colors = {key: value for key, value in source.items()
                  if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value)}
        background = colors.get('background', FALLBACK['background'])
        foreground = colors.get('foreground', FALLBACK['foreground'])
        surface = colors.get('surface', background)
        accent = colors.get('accent', colors.get('yellow', foreground))
        palette = {'background': background, 'foreground': foreground,
                   'background_hard': colors.get('background_hard', background),
                   'surface': surface, 'border': colors.get('border', surface),
                   'muted': colors.get('muted', foreground),
                   'accent': accent, 'accent_secondary': accent}
        # A theme opts out with "reactive_accent": false and keeps its declared
        # accent whatever is on the wall.
        if descriptor.get('reactive_accent', True):
            palette.update(accent_override(identity, colors))
        return palette
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return dict(FALLBACK)


def gtk_css(template, palette):
    definitions = '\n'.join('@define-color theme_' + key + ' ' + value + ';'
                            for key, value in palette.items())
    return (definitions + '\n' + template).encode()


def qt_palette(base, palette):
    from PyQt6.QtGui import QColor, QPalette
    result = QPalette(base)
    roles = {'Window': 'background', 'WindowText': 'foreground', 'Base': 'background_hard',
             'AlternateBase': 'surface', 'Text': 'foreground', 'Button': 'surface',
             'ButtonText': 'foreground', 'Highlight': 'accent', 'HighlightedText': 'background_hard',
             'ToolTipBase': 'surface', 'ToolTipText': 'foreground', 'PlaceholderText': 'muted',
             'Light': 'border', 'Midlight': 'surface', 'Mid': 'border', 'Dark': 'background_hard',
             'Shadow': 'background_hard', 'Link': 'accent', 'LinkVisited': 'muted', 'Accent': 'accent'}
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        for role, key in roles.items():
            if group == QPalette.ColorGroup.Disabled and role in ('WindowText', 'Text', 'ButtonText'):
                key = 'muted'
            result.setColor(group, getattr(QPalette.ColorRole, role), QColor(palette[key]))
    return result


def follow_qt_theme(app):
    """Oldbook-specific adapter; the portable Hold to Help app stays theme-native."""
    from PyQt6.QtCore import QTimer
    base = app.palette()
    previous = None
    def refresh():
        nonlocal previous
        palette = read_palette()
        if palette != previous:
            app.setPalette(qt_palette(base, palette))
            previous = palette
    timer = QTimer(app)
    timer.timeout.connect(refresh)
    timer.start(1000)
    app.oldbook_theme_timer = timer
    refresh()
