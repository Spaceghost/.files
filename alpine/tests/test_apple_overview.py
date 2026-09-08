"""The engraved Apple overview keys must not consume Fn function keys."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'alpine/desktop/.local/lib'))
from mbp_intel.shortcut_sources import ShortcutProvider


class AppleOverviewTests(unittest.TestCase):
    def setUp(self):
        fragments = ROOT / 'alpine/desktop/.config/sway/local.d'
        self.apple = (fragments / 'apple-overview.conf').read_text()
        self.switcher = (fragments / 'window-switcher.conf').read_text()

    def rows(self, mode='default'):
        return {row['key']: row['description'] for row in
                ShortcutProvider._parse_sway_bindings(self.apple + self.switcher, mode)}

    def test_default_keys_have_recognizable_help(self):
        rows = self.rows()
        self.assertEqual(rows['Mission Control (F3)'],
                         'Browse every workspace: choose a window, then Enter to land')
        self.assertEqual(rows['Launchpad (F4)'], 'Open application launcher')

    def test_second_mode_block_preserves_escape_and_adds_both_actions(self):
        rows = self.rows('window-switcher')
        self.assertEqual(rows['Mission Control (F3)'],
                         'Leave the overview and return to your window')
        self.assertEqual(rows['Launchpad (F4)'],
                         'Leave the overview and open the application launcher')
        self.assertEqual(rows['Escape'], 'Leave the overview and return to your window')
        self.assertIn('Super+Escape', rows)
        self.assertIn('Alt+Escape', rows)

    def test_fn_function_keys_remain_available_in_both_modes(self):
        for mode in ('default', 'window-switcher'):
            with self.subTest(mode=mode):
                rows = self.rows(mode)
                self.assertNotIn('F3', rows)
                self.assertNotIn('F4', rows)
        self.assertEqual(ShortcutProvider._sway_key('F3', 'bindsym'), 'F3')
        self.assertEqual(ShortcutProvider._sway_key('F4', 'bindsym'), 'F4')

    def test_held_key_does_not_repeatedly_open_and_close(self):
        bindings = [line.strip() for line in self.apple.splitlines()
                    if line.strip().startswith('bindsym ')]
        self.assertEqual(len(bindings), 4)
        self.assertTrue(all(line.startswith('bindsym --no-repeat ') for line in bindings))


if __name__ == '__main__':
    unittest.main()
