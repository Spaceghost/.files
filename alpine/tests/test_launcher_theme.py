"""Menus remain readable even when a generated palette has unusable contrast."""
import runpy
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook/launcher_theme.py'


def contrast(a, b):
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))
    x, y = sorted((luminance(a), luminance(b)))
    return (y + .05) / (x + .05)


class LauncherThemeTests(unittest.TestCase):
    def test_generated_dark_light_and_flat_palettes_remain_readable(self):
        self.assertTrue(MODULE.exists(), 'Launchers need a generated-palette adapter')
        colors = runpy.run_path(str(MODULE))['menu_colors']
        for background, foreground, accent in (
            ('#13091f', '#eaddf5', '#dca7ff'),
            ('#fff6df', '#44392d', '#b98938'),
            ('#777777', '#777777', '#777777'),
            ('#000000', '#000000', '#000000'),
            ('#ffffff', '#ffffff', '#ffffff'),
        ):
            with self.subTest(background=background):
                palette = colors(dict(background=background, foreground=foreground, accent=accent))
                self.assertEqual(palette['background'], background)
                for role in ('text', 'input', 'prompt', 'placeholder', 'match', 'counter'):
                    self.assertGreaterEqual(contrast(palette[role], background), 4.5, role)
                for role in ('selection-text', 'selection-match'):
                    self.assertGreaterEqual(contrast(palette[role], palette['selection']), 4.5, role)
                self.assertGreaterEqual(contrast(palette['selection'], background), 1.3)

    def test_readable_theme_accent_is_preserved(self):
        self.assertTrue(MODULE.exists(), 'Launchers need a generated-palette adapter')
        palette = runpy.run_path(str(MODULE))['menu_colors'](
            dict(background='#282828', foreground='#ebdbb2', accent='#fabd2f'))
        self.assertEqual(palette['text'], '#ebdbb2')
        self.assertEqual(palette['match'], '#fabd2f')


if __name__ == '__main__':
    unittest.main()
