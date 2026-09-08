"""Share the active MBP Intel palette across GTK and Qt overlays."""
import json
from pathlib import Path
import re

THEMES = Path(__file__).resolve().parents[5] / 'alpine/themes'
FALLBACK = {'background': '#202020', 'background_hard': '#181818', 'surface': '#303030',
            'foreground': '#eeeeee', 'muted': '#aaaaaa', 'border': '#505050', 'accent': '#dddddd'}


def read_palette(directory=THEMES):
    try:
        identity = (directory / 'current').read_text().strip()
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', identity):
            return dict(FALLBACK)
        source = json.loads((directory / (identity + '.json')).read_text())['palette']
        colors = {key: value for key, value in source.items()
                  if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value)}
        background = colors.get('background', FALLBACK['background'])
        foreground = colors.get('foreground', FALLBACK['foreground'])
        surface = colors.get('surface', background)
        return {'background': background, 'foreground': foreground,
                'background_hard': colors.get('background_hard', background),
                'surface': surface, 'border': colors.get('border', surface),
                'muted': colors.get('muted', foreground),
                'accent': colors.get('accent', colors.get('yellow', foreground))}
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
    """MBP Intel-specific adapter; the portable Hold to Help app stays theme-native."""
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
    app.mbp_intel_theme_timer = timer
    refresh()
