"""Clicking a notification lands on the window that sent it, or on nothing."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-notify-focus'


def load():
    loader = importlib.machinery.SourceFileLoader('notify_focus', str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def window(identifier, name='', **extra):
    return dict({'id': abs(hash(identifier + name)) % 10000, 'app_id': identifier,
                 'name': name}, **extra)


class Matching(unittest.TestCase):
    def setUp(self):
        self.focus = load()

    def pick(self, windows, entry='', name=''):
        self.focus.windows = lambda node, found=None: windows
        self.focus.tree = lambda: {}
        return self.focus.target(entry, name)

    def test_the_desktop_entry_wins_over_the_display_name(self):
        """The entry is the only identifier an application actually promises."""
        chosen = self.pick([window('firefox', 'Mozilla Firefox'),
                            window('thunderbird', 'Firefox news')],
                           entry='firefox', name='Firefox news')
        self.assertEqual(chosen['app_id'], 'firefox')

    def test_a_reversed_dns_entry_matches_the_plain_app_id(self):
        chosen = self.pick([window('pithos', 'Radio')], entry='io.github.Pithos')
        self.assertEqual(chosen['app_id'], 'pithos')

    def test_a_title_alone_is_the_weakest_evidence(self):
        """A window whose title mentions the sender is usually not the sender."""
        chosen = self.pick([window('foot', 'reading about Pithos'),
                            window('pithos', 'Radio')], name='Pithos')
        self.assertEqual(chosen['app_id'], 'pithos')

    def test_an_unknown_sender_focuses_nothing(self):
        """Doing nothing beats focusing the wrong window."""
        self.assertIsNone(self.pick([window('foot', '~')], name='Some Other App'))

    def test_a_short_name_never_matches_on_title_alone(self):
        self.assertIsNone(self.pick([window('foot', 'log output')], name='og'))

    def test_windows_that_park_themselves_are_never_a_destination(self):
        """A drop-down is summoned, not somewhere to be sent."""
        self.assertIsNone(self.pick([window('com.oldbook.dropdown', 'Drop-down terminal')],
                                    name='oldbook-dropdown'))

    def test_a_tie_prefers_the_window_already_focused(self):
        chosen = self.pick([window('foot', 'one'), window('foot', 'two', focused=True)],
                           entry='foot')
        self.assertTrue(chosen['focused'])


if __name__ == '__main__':
    unittest.main()
