import importlib.util
import json
from pathlib import Path
import runpy
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))


class RecoveryTests(unittest.TestCase):
    def test_prompt_keeps_the_module_styles_and_fossil_command(self):
        for name in ('gruvbox-dark', 'catppuccin-mocha', 'monochrome-test'):
            data = tomllib.loads((REPO / 'alpine/themes/profiles' / name /
                                  '.config/starship.toml').read_text())
            self.assertEqual(data.get('custom', {}).get('fossil', {}).get('command'),
                             'fossil branch current')
            self.assertTrue(data.get('username', {}).get('show_always'))
            self.assertIn('bg:', data.get('directory', {}).get('style', ''))

    def test_theme_can_disable_and_replace_the_global_default(self):
        import decoration
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / 'decoration.json'
            config.write_text('{"ripple":{"enabled":true}}')
            effects = Path(root) / 'theme-effects.json'
            effects.write_text('{"ripple":{"enabled":false}}')
            self.assertFalse(decoration.load_settings(config)['ripple']['enabled'])
            effects.write_text('{"ripple":{"module":".local/share/oldbook/themes/test/effect.py"}}')
            settings = decoration.load_settings(config)['ripple']
            self.assertTrue(settings['enabled'])
            self.assertEqual(settings['module'], '.local/share/oldbook/themes/test/effect.py')
            effects.write_text('{"ripple":{}}')
            self.assertEqual(decoration.load_settings(config)['ripple']['module'], 'ripple')

    def test_disabled_effect_is_never_imported(self):
        loader = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-decoration'))
        with patch.dict(loader['ripple_module'].__globals__,
                        {'_load_ripple': lambda name: self.fail('disabled effect imported')}):
            self.assertIsNone(loader['ripple_module']({'ripple': {'enabled': False, 'module': 'missing'}}))

    def test_lock_readiness_does_not_stop_catbed(self):
        lock = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-lock'))
        with tempfile.TemporaryDirectory() as root:
            runtime = Path(root)
            runtime.chmod(0o700)
            with patch.dict(lock['acquire_lock'].__globals__, {
                'begin_catbed_mode': lambda runtime: True,
                'compositor_identity': lambda runtime: {},
                'ready_process': lambda *args: True,
                'end_catbed_mode': lambda: self.fail('catbed stopped at readiness'),
            }):
                lock['acquire_lock'](runtime)


if __name__ == '__main__':
    unittest.main()
