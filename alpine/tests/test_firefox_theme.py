"""Firefox has no system theme to follow; this is the palette it gets fed."""
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
import firefox_theme

HOST = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-firefox-theme-host'


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

    def test_native_host_reasserts_palette_after_browser_falls_behind(self):
        host = runpy.run_path(str(HOST))
        target = Path(self.temp.name) / 'state.json'
        target.write_text('{}')
        clock = iter((0, 1, 5, 6))
        sent = []
        waits = []

        def wait(seconds):
            waits.append(seconds)
            if len(waits) == 4:
                raise StopIteration

        with mock.patch.dict(host['relay'].__globals__, {
                'current_message': lambda: {'colors': {'frame': '#1d2021'}}}):
            with self.assertRaises(StopIteration):
                host['relay'](target, sent.append, lambda: next(clock), wait)

        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0], sent[1])
        self.assertEqual(waits, [1, 1, 1, 1])

    def test_native_host_relays_file_change_without_waiting_for_heartbeat(self):
        host = runpy.run_path(str(HOST))
        target = Path(self.temp.name) / 'state.json'
        target.write_text('{}')
        sent = []
        cycles = 0

        def wait(_seconds):
            nonlocal cycles
            cycles += 1
            if cycles == 1:
                target.write_text('{"changed": true}')
            elif cycles == 2:
                raise StopIteration

        with mock.patch.dict(host['relay'].__globals__, {'current_message': lambda: {}}):
            with self.assertRaises(StopIteration):
                host['relay'](target, sent.append, lambda: cycles, wait)

        self.assertEqual(sent, [{}, {}])


if __name__ == '__main__':
    unittest.main()
