"""Derive the console palette document from the selected desktop theme.

Every text-mode screen reads one sixteen-colour VT palette: the initramfs LUKS
passphrase prompt, the kernel messages and the rescue gettys.  That palette used
to be a hand-written Gruvbox file, which pinned the whole boot chain to a single
theme while the session followed whichever theme was selected, so choosing a
theme stopped at the edge of the compositor.

Nothing new has to be authored to fix that.  The theme renderer already writes a
complete sixteen-colour terminal palette into every profile's Foot
configuration, and `oldbook-theme` already derives Ghostty's palette from that
same file; the console is simply the third reader.  Deriving it here keeps Foot,
Ghostty, the console and the GRUB menu on one set of colours per theme --- the
invariant `alpine/tests/test_boot_console.py` has always asserted for Gruvbox,
now constructed instead of maintained by hand.

The kernel font, the cream-on-charcoal default attribute and the ANSI ordering
are structural rather than thematic, so they stay fixed.  Writing the rendered
document belongs to `alpine/bin/build-console-palette`; nothing here touches
/etc or /boot, and nothing here needs root.
"""
import configparser
import json
from pathlib import Path
import re
import sys

RELATIVE = 'alpine/system/boot/console-palette.json'
FONT = 'TER16x32'
FONT_CONFIG_SYMBOL = 'CONFIG_FONT_TER16x32'
# Cream on charcoal: the last and first entries of the ANSI sixteen, whichever
# tones a theme puts there.
DEFAULT_FOREGROUND = 15
DEFAULT_BACKGROUND = 0
DESCRIPTION = (
    'Linux console (VT) palette for every text-mode screen: the initramfs LUKS prompt, '
    'kernel messages and the rescue gettys. Indices follow the ANSI order: black, red, '
    'green, yellow, blue, magenta, cyan, white, then the bright variants. The values are '
    'the {name} terminal colors shared with Foot and Ghostty.')


def terminal_colors(foot_ini):
    """The sixteen VT colours, in ANSI order, from a theme's Foot palette."""
    parser = configparser.ConfigParser(interpolation=None, strict=False,
                                       inline_comment_prefixes=('#',))
    parser.read_string(foot_ini)
    if not parser.has_section('colors-dark'):
        raise ValueError('the theme Foot configuration has no [colors-dark] palette')
    section = parser['colors-dark']
    colors = []
    for prefix in ('regular', 'bright'):
        for index in range(8):
            key = prefix + str(index)
            if key not in section:
                raise ValueError('the theme Foot palette is missing ' + key)
            value = section[key].strip().lstrip('#').lower()
            if not re.fullmatch(r'[0-9a-f]{6}', value):
                raise ValueError('a Foot colour must be rrggbb: ' + section[key])
            colors.append('#' + value)
    return colors


def document(theme, colors):
    """The palette document for one theme, in the order the file stores it."""
    if len(colors) != 16:
        raise ValueError('a console palette needs exactly sixteen colours')
    return {
        'theme': theme['id'],
        'description': DESCRIPTION.format(name=theme['name']),
        'font': FONT,
        'font_config_symbol': FONT_CONFIG_SYMBOL,
        'default_foreground': DEFAULT_FOREGROUND,
        'default_background': DEFAULT_BACKGROUND,
        'colors': colors,
    }


def render(palette):
    """The document as the versioned file stores it, trailing newline included."""
    return json.dumps(palette, indent=2) + '\n'


def _themes(repo):
    """The theme modules, which live in the checkout rather than on sys.path."""
    location = str(Path(repo) / 'alpine/wallpapers')
    if location not in sys.path:
        sys.path.insert(0, location)
    import desktop_theme
    import theme_catalog
    return theme_catalog, desktop_theme


def terminal_configuration(repo, theme):
    """A theme's Foot palette: its deployed profile when it has one, else a render.

    An authored profile is what the running desktop actually reads, so it wins;
    a theme that has never been materialised is rendered on the spot rather than
    reported as unavailable.
    """
    profile = Path(repo) / 'alpine/themes/profiles' / theme['id'] / '.config/foot/foot.ini'
    if profile.is_file():
        return profile.read_text()
    _catalog, renderer = _themes(repo)
    return renderer.render_profile(Path(repo), theme)['.config/foot/foot.ini']


def for_theme(repo, theme):
    return document(theme, terminal_colors(terminal_configuration(repo, theme)))


def for_selection(repo, selection='active'):
    """The palette the named (or selected) theme asks the boot chain to use."""
    catalog, _renderer = _themes(repo)
    return for_theme(repo, catalog.load_theme(Path(repo), selection))


def committed(repo):
    path = Path(repo) / RELATIVE
    return path.read_text() if path.is_file() else ''


def stale(repo):
    """The rendered palette the selection wants, or None when the file matches.

    Callers that must not fail on an unreadable theme tree get an exception
    here and can decide for themselves; a definite mismatch is the only thing
    that returns text.
    """
    expected = render(for_selection(repo))
    return None if expected == committed(repo) else expected
