"""The palette Firefox's own theme API reads, and the file that carries it out.

Firefox has no notion of a system theme to follow: the closest real hook is the
`browser.theme` WebExtension API, which only takes colors from inside the
browser itself. `oldbook-firefox-theme-host`, a native messaging host Firefox
keeps alive for as long as a themed window is open, watches this one file's
mtime and relays a fresh copy whenever it changes -- the same "there is
nothing to signal, just something to watch" shape `refresh_claude` already
uses for Claude Code's own theme directory.
"""
import json
import os
from pathlib import Path

from overlay_theme import THEMES, read_palette


def state_path():
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
    return Path(base) / 'oldbook/firefox-theme.json'


def firefox_colors(palette):
    """Map the desktop's normalized palette onto browser.theme.update()'s color keys."""
    return {
        'frame': palette['background_hard'],
        'frame_inactive': palette['background_hard'],
        'tab_background_text': palette['muted'],
        'tab_line': palette['accent'],
        'toolbar': palette['surface'],
        'toolbar_text': palette['foreground'],
        'toolbar_field': palette['background'],
        'toolbar_field_text': palette['foreground'],
        'toolbar_field_border': palette['border'],
        'icons': palette['foreground'],
        'popup': palette['surface'],
        'popup_text': palette['foreground'],
        'popup_border': palette['border'],
        'button_background_active': palette['accent'],
        'ntp_background': palette['background'],
        'ntp_text': palette['foreground'],
    }


def current_message(directory=THEMES):
    return {'colors': firefox_colors(read_palette(directory))}


def write_state(directory=THEMES, path=None):
    """Replace the watched file, so the native host notices within its next poll."""
    path = path or state_path()
    message = current_message(directory)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(message))
    temporary.replace(path)
    return message
