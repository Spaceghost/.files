"""Complete application profiles, with real rendering and disposable deployment."""
import importlib
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/wallpapers'))


class CompleteThemes(unittest.TestCase):
    def test_every_theme_can_render_a_complete_profile(self):
        renderer = importlib.import_module('desktop_theme')
        for source in (REPO / 'alpine/themes').glob('*.json'):
            theme = json.loads(source.read_text())
            with self.subTest(theme=theme['id']):
                files = renderer.render_profile(REPO, theme)
                for name in ('.config/foot/foot.ini', '.config/ghostty/config',
                             '.config/gtk-3.0/gtk.css', '.config/qt6ct/qt6ct.conf',
                             '.config/sway/theme.conf', '.config/swayfx/effects.conf',
                             '.config/waybar/config.jsonc', '.config/conky/panels.json',
                             '.config/fuzzel/fuzzel.ini', '.config/nvim/init.lua',
                             '.config/btop/btop.conf', '.tmux.conf'):
                    self.assertIn(name, files)
                bar = json.loads(files['.config/waybar/config.jsonc'])[0]
                self.assertEqual(bar['mpris']['on-click-middle'], '~/.local/bin/oldbook-pithos middle')

    def test_design_changes_geometry_and_typography_with_identical_colors(self):
        renderer = importlib.import_module('desktop_theme')
        theme = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())
        first = renderer.render_profile(REPO, theme)
        theme['design'] = dict(theme['design'], font='DejaVu Serif', radius=14,
                               spacing=12, widget_edge='left', launcher_width=58)
        second = renderer.render_profile(REPO, theme)
        for path in ('.config/swayfx/effects.conf', '.config/conky/panels.json',
                     '.config/gtk-3.0/settings.ini', '.config/fuzzel/fuzzel.ini'):
            self.assertNotEqual(first[path], second[path], path)

    def test_rendered_profile_deploys_and_can_be_restored(self):
        renderer = importlib.import_module('desktop_theme')
        theme = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())
        deployer = runpy.run_path(str(REPO / 'alpine/bin/deploy-home'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile, home = root / 'profile', root / 'home'
            home.mkdir()
            for name, body in renderer.render_profile(REPO, theme).items():
                target = profile / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body)
            original = home / '.tmux.conf'
            original.write_text('original settings\n')
            backup = deployer['deploy'](home, profile)
            self.assertTrue(original.is_symlink())
            deployer['rollback'](home, backup)
            self.assertEqual(original.read_text(), 'original settings\n')
