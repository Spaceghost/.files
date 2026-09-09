"""A pure black-and-white theme makes an un-themed surface impossible to miss.

The theme renderer maps declared colours to the active theme's roles and snaps
anything off-palette to whichever role sits nearest, which means a surface that
themes only approximately still *looks* themed. Rendering the whole desktop in a
palette with no colour in it at all removes that cover: under monochrome-test
every value should be greyscale, so anything with saturation left in it is a
colour the theme could not reach.
"""
import importlib
import json
from pathlib import Path
import re
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/wallpapers'))

HEX = re.compile(r'#?\b([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?\b')
ARGB = re.compile(r'#?\b([0-9a-fA-F]{2})([0-9a-fA-F]{6})\b')
RGB = re.compile(r'rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)')
# How far apart the channels may be before a value counts as carrying a hue.
CHROMA = 12

# The command deck's ghost is fixed branding, not a themed surface: `recolor`
# splits its rules out and leaves them alone on purpose, and the brand contract
# says so. It is the one place a colour is meant to survive every theme.
BRANDED = {'.config/waybar/style.css': {
    '#b765eb', '#77369e', '#ce579e', '#e3baff',   # the badge at rest
    '#d997ff', '#a355d7', '#f284bd',              # and its hover glow
}}


def saturated(value):
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return max(red, green, blue) - min(red, green, blue) > CHROMA


def leaks(name, body):
    """Colours in one rendered file that still carry a hue."""
    found = set()
    # qt6ct and Foot write #AARRGGBB, so the first pair is alpha rather than
    # red. Reading it as colour reports every opaque black as pure red.
    alpha_first = 'qt6ct/' in name or name.endswith('foot.ini')
    for match in HEX.finditer(body):
        digits = match.group(1)
        if alpha_first:
            wider = ARGB.match(match.group(0))
            if wider:
                digits = wider.group(2)
        if saturated(digits):
            found.add('#' + digits.lower())
    for red, green, blue in RGB.findall(body):
        digits = '%02x%02x%02x' % (int(red), int(green), int(blue))
        if saturated(digits):
            found.add('#' + digits)
    return found - BRANDED.get(name, set())


class MonochromeLeaks(unittest.TestCase):
    def setUp(self):
        self.renderer = importlib.import_module('desktop_theme')
        self.theme = json.loads((REPO / 'alpine/themes/monochrome-test.json').read_text())

    def test_the_test_theme_declares_no_colour_at_all(self):
        for role, value in self.theme['palette'].items():
            with self.subTest(role=role):
                self.assertIn(value.lower(), ('#000000', '#ffffff'), role)

    def test_its_geometry_matches_gruvbox_so_only_colour_varies(self):
        """One variable at a time: anything that moves is a colour fault."""
        gruvbox = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())
        for key in ('radius', 'spacing', 'bar_position', 'widget_edge', 'launcher_width'):
            with self.subTest(key=key):
                self.assertEqual(self.theme['design'][key], gruvbox['design'][key])

    def test_no_surface_keeps_a_colour_the_theme_cannot_reach(self):
        rendered = self.renderer.render_profile(REPO, self.theme)
        offenders = {name: sorted(found) for name in sorted(rendered)
                     if (found := leaks(name, rendered[name]))}
        self.assertEqual(offenders, {},
                         'these surfaces still carry a hue under a colourless theme')


if __name__ == '__main__':
    unittest.main()
