"""Deriving a Ghostty palette from a theme's Foot colours, and naming the active theme."""
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
THEME = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/mbp-intel-theme'))

FOOT = '''[main]
term=xterm-256color
font=DejaVu Serif:size=9.5

[colors-dark]
alpha=0.94
foreground=eaddf5
background=13091f
selection-foreground=180a28
selection-background=dca7ff
regular0=261631
regular1=ff7abf
regular2=a9e6b1
regular3=ffd58a
regular4=aeaeff
regular5=e9a6ff
regular6=9fe8ff
regular7=eaddf5
bright0=816b91
bright1=ff9fd4
bright2=c4f8c9
bright3=ffe7b2
bright4=c8c6ff
bright5=f2c1ff
bright6=c1f2ff
bright7=fff7ff
cursor=13091f dca7ff

[csd]
preferred=server
'''

BASE = ['font-family = JetBrainsMono Nerd Font', 'font-size = 11', 'window-theme = dark']


def derive(text=FOOT, name='Space Ghost Violet'):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / 'foot.ini'
        source.write_text(text)
        return THEME['ghostty_from_foot'](source, BASE, name)


class GhosttyPalette(unittest.TestCase):
    def test_every_ansi_slot_is_carried_over(self):
        body = derive()
        for index in range(16):
            self.assertIn(f'palette = {index}=#', body)

    def test_regular_and_bright_map_to_the_low_and_high_halves(self):
        body = derive()
        self.assertIn('palette = 0=#261631', body)
        self.assertIn('palette = 7=#eaddf5', body)
        self.assertIn('palette = 8=#816b91', body)
        self.assertIn('palette = 15=#fff7ff', body)

    def test_surface_colours_and_opacity_follow_foot(self):
        body = derive()
        for expected in ('background = 13091f', 'foreground = eaddf5',
                         'selection-background = dca7ff', 'selection-foreground = 180a28',
                         'background-opacity = 0.94'):
            self.assertIn(expected, body)

    def test_cursor_pair_splits_into_text_and_colour(self):
        body = derive()
        self.assertIn('cursor-text = 13091f', body)
        self.assertIn('cursor-color = dca7ff', body)

    def test_shared_settings_survive_and_the_theme_names_itself(self):
        body = derive()
        self.assertIn('window-theme = dark', body)
        self.assertTrue(body.startswith('# Space Ghost Violet:'))

    def test_font_family_and_size_follow_foot(self):
        body = derive()
        self.assertIn('font-family = DejaVu Serif', body)
        self.assertIn('font-size = 9.5', body)
        self.assertNotIn('font-size = 11', body)

    def test_a_theme_without_dark_colours_is_skipped_rather_than_half_written(self):
        self.assertIsNone(derive('[main]\nterm=xterm-256color\n'))

    def test_a_partial_palette_omits_only_what_is_missing(self):
        body = derive('[colors-dark]\nbackground=101010\nregular0=202020\n')
        self.assertIn('background = 101010', body)
        self.assertIn('palette = 0=#202020', body)
        self.assertNotIn('palette = 1=', body)
        self.assertNotIn('cursor-color', body)


class ShippedProfiles(unittest.TestCase):
    def test_selecting_a_theme_refreshes_ghostty_before_deploying_it(self):
        # An existing profile may have a newer Foot font than its derived
        # Ghostty file. Selecting it must repair that drift without manual sync.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'
            home = Path(directory) / 'home'
            home.mkdir()
            for relative in ('alpine/desktop', 'alpine/themes/profiles/gruvbox-dark'):
                shutil.copytree(REPO / relative, root / relative,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            for relative in ('alpine/themes/gruvbox-dark.json', 'alpine/bin/deploy-home'):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / relative, target)
            theme = runpy.run_path(str(root / 'alpine/desktop/.local/bin/mbp-intel-theme'))
            profile = root / 'alpine/themes/profiles/gruvbox-dark'
            foot = profile / '.config/foot/foot.ini'
            for font, expected_family, expected_size in (
                    ('DejaVu Sans Mono:size=13', 'DejaVu Sans Mono', '13'),
                    ('monospace:size=10.5', 'monospace', '10.5')):
                foot.write_text(FOOT.replace('DejaVu Serif:size=9.5', font))
                with mock.patch.object(Path, 'home', return_value=home):
                    theme['use']('gruvbox-dark', reload=False)
                deployed = home / '.config/ghostty/config'
                self.assertTrue(deployed.is_symlink())
                self.assertIn(f'font-family = {expected_family}', deployed.read_text())
                self.assertIn(f'font-size = {expected_size}\n', deployed.read_text())

    def test_every_profile_with_foot_colours_has_a_matching_ghostty_config(self):
        # `mbp-intel-theme sync` generates these; a profile that drifts fails here.
        for profile in sorted((REPO / 'alpine/themes/profiles').glob('*')):
            foot = profile / '.config/foot/foot.ini'
            if not foot.is_file():
                continue
            with self.subTest(theme=profile.name):
                ghostty = profile / '.config/ghostty/config'
                self.assertTrue(ghostty.is_file(), 'run: mbp-intel-theme sync')
                body = ghostty.read_text()
                self.assertIn('palette = 0=#', body)
                foot_font = next(line.split('=', 1)[1] for line in foot.read_text().splitlines()
                                 if line.startswith('font='))
                family, *attributes = foot_font.split(':')
                size = next(part.split('=', 1)[1] for part in attributes
                            if part.startswith('size='))
                self.assertIn(f'font-family = {family}', body)
                self.assertIn(f'font-size = {size}', body)

    def test_the_active_theme_is_a_real_theme(self):
        active = (REPO / 'alpine/themes/current').read_text().strip()
        self.assertTrue((REPO / 'alpine/themes' / (active + '.json')).is_file())


if __name__ == '__main__':
    unittest.main()
