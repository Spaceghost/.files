"""Firefox has no system theme to follow; this is the palette it gets fed."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
import firefox_theme


class FirefoxThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.themes = Path(self.temp.name)
        (self.themes / 'current').write_text('warm')
        (self.themes / 'warm.json').write_text(json.dumps({'palette': {
            'background': '#282828', 'background_hard': '#1d2021', 'surface': '#3c3836',
            'foreground': '#ebdbb2', 'muted': '#928374', 'border': '#504945', 'yellow': '#fabd2f'}}))

    def test_firefox_colors_maps_every_key_to_a_hex_string(self):
        colors = firefox_theme.firefox_colors({
            'background': '#282828', 'background_hard': '#1d2021', 'surface': '#3c3836',
            'foreground': '#ebdbb2', 'muted': '#928374', 'border': '#504945', 'accent': '#fabd2f'})
        self.assertEqual(colors['frame'], '#1d2021')
        self.assertEqual(colors['toolbar'], '#3c3836')
        self.assertEqual(colors['tab_line'], '#fabd2f')
        for value in colors.values():
            self.assertRegex(value, r'^#[0-9a-fA-F]{6}$')

    def test_current_message_follows_the_active_theme(self):
        first = firefox_theme.current_message(self.themes)
        self.assertEqual(first['colors']['toolbar'], '#3c3836')
        (self.themes / 'cool.json').write_text(json.dumps({'palette': {
            'background': '#13091f', 'foreground': '#eaddf5', 'accent': '#dca7ff'}}))
        (self.themes / 'current').write_text('cool')
        second = firefox_theme.current_message(self.themes)
        self.assertNotEqual(first, second)

    def test_write_state_is_atomic_and_readable(self):
        target = Path(self.temp.name) / 'state.json'
        message = firefox_theme.write_state(self.themes, target)
        self.assertEqual(json.loads(target.read_text()), message)
        self.assertFalse(target.with_suffix('.tmp').exists())


if __name__ == '__main__':
    unittest.main()
