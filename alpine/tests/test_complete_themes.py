"""Complete application profiles, with real rendering and disposable deployment."""
import importlib
import json
from pathlib import Path
import re
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
                             '.config/btop/btop.conf', '.tmux.conf',
                             '.claude/themes/oldbook.json'):
                    self.assertIn(name, files)
                bar = json.loads(files['.config/waybar/config.jsonc'])[0]
                self.assertEqual(bar['mpris']['on-click-middle'], '~/.local/bin/oldbook-pithos middle')

    def test_claude_code_carries_the_whole_palette_and_its_own_light_or_dark(self):
        renderer = importlib.import_module('desktop_theme')
        baseline = json.loads(
            (REPO / 'alpine/desktop/.claude/themes/oldbook.json').read_text())
        for source in (REPO / 'alpine/themes').glob('*.json'):
            theme = json.loads(source.read_text())
            palette = renderer.colors(theme)
            with self.subTest(theme=theme['id']):
                body = json.loads(
                    renderer.render_profile(REPO, theme)['.claude/themes/oldbook.json'])
                # The file name is what "custom:oldbook" resolves against, so a
                # per-theme name would break the reference on every switch.
                self.assertEqual(body['name'], 'oldbook')
                self.assertEqual(body['base'],
                                 'light' if renderer.is_light(palette) else 'dark')
                self.assertEqual(set(body['overrides']), set(baseline['overrides']))
                for key, value in body['overrides'].items():
                    self.assertRegex(value, r'^rgb\(\d{1,3}, \d{1,3}, \d{1,3}\)$', key)
                self.assertEqual(body['overrides']['text'],
                                 'rgb(%d, %d, %d)' % renderer.rgb(palette['foreground']))
                self.assertEqual(body['overrides']['inverseText'],
                                 'rgb(%d, %d, %d)' % renderer.rgb(palette['background']))
                # Two themes must not produce the same guide colours.
                self.assertNotEqual(body['overrides'], baseline['overrides']
                                    if theme['id'] != 'gruvbox-dark' else None)

    def test_the_derived_blur_stays_within_a_sane_reach(self):
        """SceneFX reaches 2^(blur_passes + 1) * blur_radius. Deriving the
        radius from the corner radius alone generated 11 for a 22px corner:
        a 44 pixel reach, which is expensive and muddy at any gap. Reaching
        past the gap is not itself a defect -- the smearing once blamed on it
        was SceneFX skipping damage compensation, fixed upstream."""
        renderer = importlib.import_module('desktop_theme')
        theme = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())
        for spacing in range(2, 17):
            for radius in (0, 4, 14, 22, 24):   # the schema's whole legal range
                with self.subTest(spacing=spacing, radius=radius):
                    theme['design'] = dict(theme['design'], radius=radius, spacing=spacing)
                    effects = renderer.render_profile(REPO, theme)['.config/swayfx/effects.conf']
                    values = dict(re.findall(r'^(blur_radius|blur_passes) (\d+)$',
                                             effects, re.MULTILINE))
                    reach = int(values['blur_radius']) * 2 ** (int(values['blur_passes']) + 1)
                    self.assertLessEqual(reach, 32, f'blur reaches {reach}px')
                    self.assertGreaterEqual(int(values['blur_radius']), 2)

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

    def test_every_declared_theme_carries_a_full_sixteen_colour_terminal(self):
        """A second theme is what proves the palette is complete rather than
        approximately complete. Before the dim roles existed every dark ANSI
        slot was snapped onto whichever single role sat nearest, so a generated
        theme reached Foot, Ghostty, btop, Neovim, the Linux console and the
        LUKS prompt with eight distinct colours instead of sixteen -- and with
        dark yellow landing on green, dark magenta and dark cyan both on
        muted."""
        renderer = importlib.import_module('desktop_theme')
        sys.path.insert(0, str(REPO / 'alpine/system/boot'))
        import console_palette
        for source in sorted((REPO / 'alpine/themes').glob('*.json')):
            theme = json.loads(source.read_text())
            with self.subTest(theme=theme['id']):
                foot = renderer.render_profile(REPO, theme)['.config/foot/foot.ini']
                colors = console_palette.terminal_colors(foot)
                self.assertEqual(len(set(colors)), 16, colors)
                self.assertEqual(colors[0], theme['palette']['background'])
                self.assertEqual(colors[15], theme['palette']['foreground'])

    def test_optional_roles_are_derived_when_a_descriptor_leaves_them_out(self):
        renderer = importlib.import_module('desktop_theme')
        theme = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())
        thirteen = {name: value for name, value in theme['palette'].items()
                    if not name.endswith('_dim') and name not in
                    ('surface_bright', 'subtle', 'foreground_dim')}
        self.assertEqual(len(thirteen), 13)
        derived = renderer.colors(dict(theme, palette=thirteen))
        for role in renderer.OPTIONAL_ROLES:
            with self.subTest(role=role):
                self.assertRegex(derived[role], r'^#[0-9a-f]{6}$')
        # A declared role always wins over its derivation.
        declared = renderer.colors(theme)
        self.assertEqual(declared['red_dim'], theme['palette']['red_dim'])
        self.assertNotEqual(derived['red_dim'], declared['red_dim'])

    def test_a_tinted_ground_keeps_its_ground_and_its_tint(self):
        """Snapping to one role turned every tinted status ground into the same
        flat surface. Each of these is a role blended over a role, and the
        reconstruction has to name the same two roles the template meant."""
        renderer = importlib.import_module('desktop_theme')
        theme = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())
        sources = tuple(sorted({value.lower() for value in theme['palette'].values()}
                               | {'#fbf1c7', '#32302f'}))
        role = {value.lower(): name for name, value in theme['palette'].items()}
        for shade, tint in (('#504018', 'yellow_dim'),   # keep-awake ground
                            ('#9d2420', 'red_dim'),      # battery critical ground
                            ('#442722', 'red_dim'),      # temperature critical
                            ('#32361a', 'green_dim'),    # AI complete
                            ('#3c1f1e', 'red_dim')):     # Neovim diff removed
            with self.subTest(shade=shade):
                base, chosen, amount = renderer.decompose(shade, sources)
                self.assertEqual(role[chosen], tint)
                self.assertIn(role[base], ('background', 'background_hard'))
                self.assertGreater(amount, 0)

    def test_the_design_names_a_pointer_and_folder_set_for_every_theme(self):
        renderer = importlib.import_module('desktop_theme')
        for source in sorted((REPO / 'alpine/themes').glob('*.json')):
            theme = json.loads(source.read_text())
            with self.subTest(theme=theme['id']):
                design = renderer.validate_design(theme['design'])
                index = renderer.render_profile(REPO, theme)[renderer.CURSOR_INDEX]
                self.assertIn('Name=Oldbook-Ghost\n', index)
                self.assertIn('Inherits=' + design['cursors'] + '\n', index)
                self.assertIn('gtk-icon-theme-name=' + design['icons'],
                              renderer.render_profile(REPO, theme)['.config/gtk-3.0/settings.ini'])

    def test_a_descriptor_without_asset_names_still_renders(self):
        """An older descriptor must not lose its pointer to a stricter schema."""
        renderer = importlib.import_module('desktop_theme')
        theme = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())
        theme['design'] = {name: value for name, value in theme['design'].items()
                           if name not in ('cursors', 'icons')}
        design = renderer.validate_design(theme['design'])
        self.assertEqual(design['cursors'], renderer.DESIGN_DEFAULTS['cursors'])
        self.assertIn('Inherits=' + renderer.DESIGN_DEFAULTS['cursors'],
                      renderer.render_profile(REPO, theme)[renderer.CURSOR_INDEX])
        for bad in ({**theme['design'], 'cursors': '../elsewhere'},
                    {**theme['design'], 'icons': ''},
                    {**theme['design'], 'cursors': 7}):
            with self.subTest(design=bad):
                with self.assertRaises(ValueError):
                    renderer.validate_design(bad)

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
