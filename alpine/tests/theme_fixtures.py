"""Theme fixtures that survive a theme being retired.

Several suites are written against Space Ghost, the violet theme this desktop
started from, because a second theme is what proves a palette actually reaches
the bar, the Scripture strip, Neovim and the profile stylesheets. Gruvbox Dark
is now the only theme shipped live, and Space Ghost moved to
`alpine/archive/themes/` with its descriptor and profile intact.

Rather than delete that coverage or weaken it to a single palette, these
helpers look in the live tree first and fall back to the archive, so a retired
theme keeps proving the same contract and a genuinely missing one skips loudly.
"""
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[2]
THEME_ROOTS = (REPO / 'alpine/themes', REPO / 'alpine/archive/themes')


def theme_descriptor(name):
    """Path to one theme's JSON descriptor, live or archived."""
    for root in THEME_ROOTS:
        candidate = root / f'{name}.json'
        if candidate.is_file():
            return candidate
    raise unittest.SkipTest(f'No descriptor for the {name} theme')


def theme_profile(name):
    """Path to one theme's rendered profile directory, live or archived."""
    for root in (REPO / 'alpine/themes/profiles', REPO / 'alpine/archive/themes'):
        candidate = root / name
        if candidate.is_dir():
            return candidate
    raise unittest.SkipTest(f'No profile for the {name} theme')
