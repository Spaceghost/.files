"""The original ghost badge keeps its identity across desktop themes."""

import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'alpine/wallpapers'))
from desktop_theme import colors, recolor, render_profile


def badge(css, hover=False):
    selector = '#custom-ghost:hover' if hover else '#custom-ghost'
    match = re.search(re.escape(selector) + r'\s*\{([^}]+)\}', css)
    if not match:
        raise AssertionError('missing ghost badge selector')
    return dict((name.strip(), value.strip()) for name, value in
                (part.split(':', 1) for part in match[1].split(';') if ':' in part))


class GhostBrandingTests(unittest.TestCase):
    def assert_brand(self, css):
        normal, hover = badge(css), badge(css, True)
        self.assertEqual(normal['font-size'], '21px')
        self.assertEqual(normal['color'], '#fff6ff')
        self.assertEqual(normal['background'],
                         'linear-gradient(135deg, #b765eb, #77369e 60%, #ce579e)')
        self.assertEqual(normal['text-shadow'], '0 0 5px #e3baff')
        self.assertEqual(hover['background'],
                         'linear-gradient(135deg, #d997ff, #a355d7 65%, #f284bd)')
        self.assertEqual(normal['min-width'], '36px')
        self.assertEqual(normal['padding'], '0')

    def test_existing_profiles_and_base_keep_original_badge(self):
        paths = [ROOT / 'alpine/desktop/.config/waybar/style.css',
                 *sorted((ROOT / 'alpine/themes/profiles').glob('*/.config/waybar/style.css'))]
        self.assertGreater(len(paths), 2)
        for path in paths:
            with self.subTest(profile=str(path.relative_to(ROOT))):
                self.assert_brand(path.read_text())

    def test_generated_distinct_palettes_keep_badge_while_bar_changes(self):
        rendered = []
        for theme_id in ('spaceghost', 'gruvbox-dark', 'waxen-meridian-373c11cb12f0'):
            theme = json.loads((ROOT / 'alpine/themes' / (theme_id + '.json')).read_text())
            with self.subTest(theme=theme_id):
                css = render_profile(ROOT, theme)['.config/waybar/style.css']
                self.assert_brand(css)
                rendered.append(css)
        self.assertEqual(len(set(rendered)), len(rendered))

    def test_brand_protection_does_not_swallow_neighboring_selectors(self):
        theme = json.loads((ROOT / 'alpine/themes/gruvbox-dark.json').read_text())
        palette = colors(dict(theme, palette=dict(theme['palette'], accent='#123456')))
        source = ('#custom-ghost { color: #fabd2f; }\n'
                  '#custom-ghost:hover { background: #fabd2f; }\n'
                  '#custom-ghost-extra { color: #fabd2f; }\n'
                  '#workspaces button { color: #fabd2f; }\n')
        result = recolor(source, theme['palette'], palette, '.config/waybar/style.css')
        self.assertEqual(badge(result)['color'], '#fabd2f')
        self.assertEqual(badge(result, True)['background'], '#fabd2f')
        self.assertIn('#custom-ghost-extra { color: #123456; }', result)
        self.assertIn('#workspaces button { color: #123456; }', result)


if __name__ == '__main__':
    unittest.main()
