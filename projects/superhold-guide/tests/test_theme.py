"""Desktop CSS changes take effect without touching preferences or restarting."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from superhold.theme import DesktopTheme, MAX_THEME_BYTES, _config_directory


class FakeWindow:
    def __init__(self):
        self.screen = object()
        self.handlers = {}

    def get_screen(self):
        return self.screen

    def connect(self, event, callback):
        self.handlers[1] = callback
        return 1

    def disconnect(self, handler):
        del self.handlers[handler]

    def destroy(self):
        for callback in list(self.handlers.values()):
            callback(self)


class ThemeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.css = self.directory / 'gtk-3.0/gtk.css'
        self.css.parent.mkdir()
        self.providers = []
        self.load_paths = []
        self.sources = {}
        self.parse_hook = None
        owner = self

        class Provider:
            def connect(self, event, callback):
                self.error_callback = callback
                return 1

            def disconnect(self, handler):
                self.error_callback = None

            def load_from_path(self, path):
                owner.load_paths.append(Path(path))
                self.content = Path(path).read_text()
                if 'INVALID' in self.content:
                    self.error_callback(self, None, SimpleNamespace(code=1))
                if 'DEPRECATED' in self.content:
                    self.error_callback(self, None, SimpleNamespace(code=9))
                if owner.parse_hook:
                    owner.parse_hook()

        def add_provider(screen, provider, priority):
            self.assertIs(screen, self.window.screen)
            self.assertEqual(priority, 800)
            self.providers.append(provider)

        def remove_provider(screen, provider):
            self.assertIs(screen, self.window.screen)
            self.providers.remove(provider)

        def timeout(seconds, callback):
            self.assertEqual(seconds, 1)
            self.sources[42] = callback
            return 42

        self.gtk = SimpleNamespace(
            CssProvider=Provider,
            CssProviderError=SimpleNamespace(DEPRECATED=9),
            STYLE_PROVIDER_PRIORITY_USER=800,
            StyleContext=SimpleNamespace(add_provider_for_screen=add_provider,
                                         remove_provider_for_screen=remove_provider))
        self.glib = SimpleNamespace(Error=RuntimeError, timeout_add_seconds=timeout,
                                    source_remove=lambda identity: self.sources.pop(identity))
        patcher = mock.patch('superhold.theme._gtk_bindings', return_value=(self.glib, self.gtk))
        patcher.start()
        self.addCleanup(patcher.stop)
        environment = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.directory)})
        environment.start()
        self.addCleanup(environment.stop)
        self.window = FakeWindow()

    def start(self):
        follower = DesktopTheme(self.window)
        self.addCleanup(follower.close)
        return follower

    def tick(self):
        self.assertTrue(self.sources[42]())

    def test_native_theme_works_without_user_css_then_picks_up_a_new_file(self):
        self.start()
        self.assertEqual(self.providers, [])
        self.css.write_text('@define-color theme_bg_color #282828;')
        self.tick()
        self.assertEqual(len(self.providers), 1)
        self.assertEqual(self.providers[0].content, self.css.read_text())
        self.assertEqual(self.load_paths, [self.css])
        self.tick()
        self.assertEqual(self.load_paths, [self.css])

    def test_live_edits_atomic_replacement_and_retargeted_symlinks_are_followed(self):
        target = self.directory / 'palette.css'
        target.write_text('first palette')
        self.css.symlink_to(target)
        self.start()
        target.write_text('second palette')
        self.tick()
        self.assertEqual(self.providers[0].content, 'second palette')
        replacement = self.directory / 'replacement.css'
        replacement.write_text('third palette')
        replacement.replace(target)
        self.tick()
        self.assertEqual(self.providers[0].content, 'third palette')
        alternate = self.directory / 'alternate.css'
        alternate.write_text('fourth palette')
        self.css.unlink()
        self.css.symlink_to(alternate)
        self.tick()
        self.assertEqual(self.providers[0].content, 'fourth palette')
        self.assertEqual(len(self.providers), 1)

    def test_content_changes_are_detected_even_when_timestamp_and_size_match(self):
        self.css.write_text('red')
        self.start()
        metadata = self.css.stat()
        self.css.write_text('tan')
        os.utime(self.css, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        self.tick()
        self.assertEqual(self.providers[0].content, 'tan')

    def test_malformed_or_missing_css_keeps_last_good_then_recovers(self):
        self.css.write_text('good')
        self.start()
        good = self.providers[0]
        self.css.write_text('INVALID')
        self.tick()
        self.assertIs(self.providers[0], good)
        failed_load_count = len(self.load_paths)
        self.tick()
        self.assertEqual(len(self.load_paths), failed_load_count)
        self.css.unlink()
        self.tick()
        self.assertIs(self.providers[0], good)
        self.css.write_text('recovered')
        self.tick()
        self.assertEqual(self.providers[0].content, 'recovered')

    def test_deprecation_warning_does_not_discard_otherwise_valid_css(self):
        self.css.write_text('DEPRECATED but valid')
        self.start()
        self.assertEqual(len(self.providers), 1)

    def test_replacement_during_parse_is_retried_before_application(self):
        self.css.write_text('first')
        self.start()
        good = self.providers[0]
        self.css.write_text('second')
        self.parse_hook = lambda: self.css.write_text('third')
        self.tick()
        self.assertIs(self.providers[0], good)
        self.parse_hook = None
        self.tick()
        self.assertEqual(self.providers[0].content, 'third')

    def test_oversized_file_and_fifo_do_not_get_passed_to_gtk(self):
        self.css.write_bytes(b'x' * (MAX_THEME_BYTES + 1))
        self.start()
        self.assertEqual(self.load_paths, [])
        self.css.unlink()
        os.mkfifo(self.css)
        self.tick()
        self.assertEqual(self.load_paths, [])
        self.assertEqual(self.providers, [])

    def test_destroy_stops_watch_and_removes_only_its_own_provider(self):
        self.css.write_text('good')
        unrelated = object()
        self.providers.append(unrelated)
        follower = self.start()
        self.window.destroy()
        self.assertEqual(self.sources, {})
        self.assertEqual(self.providers, [unrelated])
        self.assertEqual(self.window.handlers, {})
        self.assertFalse(follower.refresh())
        follower.close()

    def test_relative_xdg_home_falls_back_to_home_config(self):
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}):
            self.assertEqual(_config_directory(), Path.home() / '.config')


if __name__ == '__main__':
    unittest.main()
