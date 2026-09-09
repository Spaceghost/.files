"""Theme selection at the edges of the session: the power deck and the boot chain.

The lock already follows the active palette and there is no login screen to
follow it, so the surfaces a theme switch used to miss were the power deck
(wlogout, which was not in the profile set at all) and everything before the
compositor: the GRUB menu, the kernel console, the initramfs passphrase prompt
and the rescue gettys, all of which read one hardcoded Gruvbox palette.

The load-bearing assertion here is that generalising those two surfaces changed
nothing about Gruvbox Dark: the palette document renders byte for byte as it was
committed, the kernel parameters are the same string, the GRUB roles resolve to
the same shades, and the deck's stylesheet renders identically to its source.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import re
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BOOT = REPO / 'alpine/system/boot'
sys.path.insert(0, str(REPO / 'alpine/wallpapers'))
sys.path.insert(0, str(BOOT))
import boot_console  # noqa: E402
import console_palette  # noqa: E402
import desktop_theme  # noqa: E402

THEME = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-theme'))
DECK = '.config/wlogout/style.css'
GRUVBOX = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())

# The kernel command line the boot console has always installed. Generation must
# not move a single channel value.
PINNED_PARAMETERS = [
    'vt.default_red=40,204,152,215,69,177,104,168,146,251,184,250,131,211,142,235',
    'vt.default_grn=40,36,151,153,133,98,157,153,131,73,187,189,165,134,192,219',
    'vt.default_blu=40,29,26,33,136,134,106,132,116,52,38,47,152,155,124,178',
    'vt.color=0x0F',
    'fbcon=font:TER16x32',
]
# The shades the GRUB menu paints, as they were when they were hardcoded.
PINNED_GRUB_ROLES = {
    'background': '#282828', 'background_hard': '#1d2021', 'red': '#cc241d',
    'green': '#98971a', 'amber': '#fabd2f', 'blue': '#458588', 'purple': '#b16286',
    'aqua': '#689d6a', 'muted': '#a89984', 'grey': '#928374', 'orange': '#d79921',
    'foreground': '#ebdbb2', 'surface': '#3c3836', 'border': '#504945',
}

ALTERNATE = {
    'id': 'boundary-probe',
    'name': 'Boundary Probe',
    'palette': {'background': '#101820', 'background_hard': '#070c11', 'surface': '#1b2733',
                'border': '#2d3d4d', 'foreground': '#d8e6f2', 'muted': '#6f8296',
                'red': '#e05c5c', 'green': '#7fc98a', 'yellow': '#59c2ff', 'blue': '#4aa3df',
                'purple': '#b48ead', 'aqua': '#78d0c8', 'orange': '#e89a4a'},
    'reactive_accent': False,
    'image_style': 'A probe theme used only by the tests.',
    'design': dict(GRUVBOX['design'], cursors='simp1e-cursors-nord-dark',
                    icons='Oldbook-Boundary-Probe'),
}


def load_script(name):
    """Import one of the hyphenated commands in alpine/bin/ as a module."""
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'),
                                                  str(REPO / 'alpine/bin' / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def literals(css):
    """Every colour a stylesheet declares, as #rrggbb."""
    found = {value.lower() for value in re.findall(r'#[0-9a-fA-F]{6}\b', css)}
    for match in re.finditer(r'\brgba?\(\s*(\d+),\s*(\d+),\s*(\d+)', css):
        found.add('#%02x%02x%02x' % tuple(int(value) for value in match.groups()))
    return found


class ConsolePalette(unittest.TestCase):
    def test_gruvbox_renders_the_committed_palette_byte_for_byte(self):
        # The regression that matters: this file was authored by hand and is now
        # generated, and generalising it must not restyle the boot chain.
        generated = console_palette.render(console_palette.for_theme(REPO, GRUVBOX))
        self.assertEqual(generated, (REPO / console_palette.RELATIVE).read_text())

    def test_the_committed_palette_belongs_to_the_selected_theme(self):
        selected = (REPO / 'alpine/themes/current').read_text().strip()
        document = boot_console.load_palette((REPO / console_palette.RELATIVE).read_text())
        self.assertEqual(document['theme'], selected,
                         'run alpine/bin/build-console-palette')

    def test_kernel_parameters_are_unchanged_by_generation(self):
        document = console_palette.for_theme(REPO, GRUVBOX)
        self.assertEqual(boot_console.kernel_parameters(document), PINNED_PARAMETERS)

    def test_generated_documents_satisfy_the_boot_console_validator(self):
        for theme in (GRUVBOX, ALTERNATE):
            with self.subTest(theme=theme['id']):
                document = console_palette.for_theme(REPO, theme)
                text = console_palette.render(document)
                self.assertEqual(boot_console.load_palette(text), document)

    def test_another_theme_moves_every_console_colour_to_its_own_palette(self):
        document = console_palette.for_theme(REPO, ALTERNATE)
        rendered = desktop_theme.render_profile(REPO, ALTERNATE)['.config/foot/foot.ini']
        expected = console_palette.terminal_colors(rendered)
        self.assertEqual(document['colors'], expected)
        self.assertEqual(document['theme'], 'boundary-probe')
        self.assertIn('Boundary Probe terminal colors', document['description'])
        gruvbox = console_palette.for_theme(REPO, GRUVBOX)['colors']
        self.assertEqual(len(set(document['colors']) & set(gruvbox)), 0)
        # The console's default attribute names indices, so cream on charcoal
        # stays cream on charcoal in whatever tones the theme puts there.
        self.assertEqual(document['colors'][15], ALTERNATE['palette']['foreground'])
        self.assertEqual(document['colors'][0], ALTERNATE['palette']['background'])

    def test_a_broken_or_unsafe_source_is_refused(self):
        with self.assertRaises(ValueError):
            console_palette.terminal_colors('[main]\nfont=x\n')
        with self.assertRaises(ValueError):
            console_palette.terminal_colors('[colors-dark]\nregular0=282828\n')
        with self.assertRaises(ValueError):
            console_palette.terminal_colors('[colors-dark]\n' + ''.join(
                '%s%d=zzzzzz\n' % (prefix, index)
                for prefix in ('regular', 'bright') for index in range(8)))
        document = console_palette.for_theme(REPO, GRUVBOX)
        with self.assertRaises(ValueError):
            boot_console.load_palette(json.dumps(dict(document, theme='../elsewhere')))
        with self.assertRaises(ValueError):
            boot_console.load_palette(json.dumps(dict(document, theme=7)))

    def test_the_builder_writes_only_when_the_selection_moved(self):
        build = load_script('build-console-palette')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'console-palette.json'
            _path, changed, palette = build.build(REPO, 'gruvbox-dark', output)
            self.assertTrue(changed)
            self.assertEqual(palette['theme'], 'gruvbox-dark')
            self.assertEqual(output.read_text(), (REPO / console_palette.RELATIVE).read_text())
            self.assertFalse(build.build(REPO, 'gruvbox-dark', output)[1])
            with contextlib.redirect_stdout(io.StringIO()) as said:
                self.assertEqual(build.main(['--check', '--theme', 'gruvbox-dark',
                                             '--output', str(output)]), 0)
            self.assertIn(str(output), said.getvalue())


class InstallerGuard(unittest.TestCase):
    """A stale palette must stop the root install rather than reach /boot."""

    def setUp(self):
        self.installer = load_script('install-boot-console')

    def test_a_definite_mismatch_stops_the_run(self):
        with mock.patch.object(console_palette, 'stale', return_value='{"theme": "other"}\n'):
            with self.assertRaises(RuntimeError) as caught:
                self.installer.check_palette_current()
        self.assertIn('build-console-palette', str(caught.exception))

    def test_a_matching_palette_passes(self):
        with mock.patch.object(console_palette, 'stale', return_value=None):
            self.installer.check_palette_current()
        # The committed checkout is expected to be current on its own.
        self.installer.check_palette_current()

    def test_an_unreadable_theme_tree_warns_instead_of_blocking(self):
        with mock.patch.object(console_palette, 'stale', side_effect=RuntimeError('no themes')):
            self.installer.check_palette_current()


class GrubMenu(unittest.TestCase):
    """The menu reads the palette document, including which theme it names."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.builder = load_script('build-grub-theme')
        except ImportError as error:  # pragma: no cover - depends on the host
            raise unittest.SkipTest('build-grub-theme needs cairo/Pango/numpy: %s' % error)

    def test_roles_are_the_shades_the_menu_has_always_painted(self):
        self.assertEqual(self.builder.palette(), PINNED_GRUB_ROLES)

    def test_chrome_follows_the_theme_the_palette_names(self):
        roles = desktop_theme.colors(ALTERNATE)
        with mock.patch.object(desktop_theme, 'colors', return_value=roles):
            with mock.patch('theme_catalog.load_theme', return_value=ALTERNATE):
                chrome = self.builder.chrome_roles('boundary-probe')
        self.assertEqual(chrome, {name: ALTERNATE['palette'][name]
                                  for name in self.builder.FALLBACK_ROLES})

    def test_a_missing_or_unknown_theme_keeps_a_buildable_menu(self):
        self.assertEqual(self.builder.chrome_roles(None), self.builder.FALLBACK_ROLES)
        self.assertEqual(self.builder.chrome_roles('no-such-theme'), self.builder.FALLBACK_ROLES)

    def test_the_specification_declares_no_colour_of_its_own(self):
        roles = self.builder.palette()
        fonts = [{'name': 'Ghost Mono Regular 32'}, {'name': 'Ghost Mono Regular 20'}]
        text = json.dumps(self.builder.theme_specification(roles, fonts))
        for value in literals(text):
            self.assertIn(value, set(roles.values()), value)


class PowerDeck(unittest.TestCase):
    """wlogout is a themed surface like any other, not a Gruvbox-only overlay."""

    def setUp(self):
        self.source = (REPO / 'alpine/desktop' / DECK).read_text()

    def test_only_declared_palette_roles_are_used(self):
        # Off-palette shades are snapped to whichever role sits nearest, so a
        # hand-picked one themes approximately. The renderer's two derived
        # shades are the only values it maps beyond the theme's own thirteen.
        allowed = {value.lower() for value in GRUVBOX['palette'].values()}
        allowed |= {'#fbf1c7', '#32302f'}
        for value in literals(self.source):
            self.assertIn(value, allowed, value)

    def test_the_deck_is_rendered_into_every_theme_profile(self):
        rendered = desktop_theme.render_profile(REPO, GRUVBOX)
        self.assertIn(DECK, rendered)
        self.assertEqual(rendered[DECK], self.source)
        self.assertEqual((REPO / 'alpine/themes/profiles/gruvbox-dark' / DECK).read_text(),
                         self.source)

    def test_another_theme_repaints_the_whole_deck(self):
        rendered = desktop_theme.render_profile(REPO, ALTERNATE)[DECK]
        palette = ALTERNATE['palette']
        self.assertEqual(literals(rendered),
                         {palette['background_hard'], palette['surface'],
                          palette['foreground'], palette['yellow'], palette['orange']})
        self.assertEqual(len(rendered.splitlines()), len(self.source.splitlines()))

    def test_glyph_tiles_resolve_beside_the_deployed_stylesheet(self):
        # The stylesheet becomes a symlink into a theme profile once a theme is
        # applied; GTK resolves these against the path it was handed, so they
        # must keep answering from the shared HOME overlay.
        icons = REPO / 'alpine/desktop/.config/wlogout/icons'
        referenced = set(re.findall(r'url\("icons/([^"]+)"\)', self.source))
        self.assertTrue(referenced)
        for name in sorted(referenced):
            self.assertTrue((icons / name).is_file(), name)


class ConfirmationBars(unittest.TestCase):
    """The swaynag bars that ask before logging out, rebooting or shutting down.

    They were already Gruvbox rather than stock, but hardcoded: the file sat
    outside the theme file set, so the one screen that appears at the moment a
    session ends kept one theme's colours whatever was selected.
    """

    NAG = '.config/swaynag/config'

    def setUp(self):
        self.source = (REPO / 'alpine/desktop' / self.NAG).read_text()

    def test_only_declared_palette_roles_are_used(self):
        allowed = {value.lower() for value in GRUVBOX['palette'].values()}
        allowed |= {'#fbf1c7', '#32302f'}
        for value in literals(self.source):
            self.assertIn(value, allowed, value)

    def test_the_bars_are_rendered_into_every_theme_profile(self):
        rendered = desktop_theme.render_profile(REPO, GRUVBOX)
        self.assertIn(self.NAG, rendered)
        self.assertEqual(rendered[self.NAG], self.source)
        self.assertEqual((REPO / 'alpine/themes/profiles/gruvbox-dark' / self.NAG).read_text(),
                         self.source)

    def test_no_gruvbox_shade_survives_into_another_theme(self):
        """The values carry no leading #, so prove the renderer still maps them."""
        rendered = desktop_theme.render_profile(REPO, ALTERNATE)[self.NAG]
        for shade in ('282828', 'ebdbb2', 'fabd2f', '3c3836', '1d2021', 'fb4934'):
            self.assertNotIn(shade, rendered, shade)
        for key in ('background', 'text', 'border-bottom', 'button-background',
                    'details-background'):
            with self.subTest(key=key):
                self.assertRegex(rendered, rf'(?m)^{key}=[0-9a-f]{{6}}$')


class BinaryAssets(unittest.TestCase):
    """The pointer shapes and the power deck's glyph tiles.

    `render_profile` is text, and for a long time that was the whole theme file
    set, so these two drawn surfaces stayed in Gruvbox's amber and cream under
    every theme. They are drawn with cairo rather than compiled, so each profile
    can carry its own; the load-bearing assertion here is that drawing Gruvbox's
    reproduces the committed bytes exactly.
    """

    @classmethod
    def setUpClass(cls):
        try:
            cls.assets = desktop_theme.render_assets(REPO, GRUVBOX)
        except ImportError as error:  # pragma: no cover - depends on the host
            raise unittest.SkipTest('theme assets need cairo/Pango: %s' % error)

    def test_gruvbox_assets_are_drawn_exactly_as_they_were_committed(self):
        shared = REPO / 'alpine/desktop'
        for name, data in sorted(self.assets.items()):
            with self.subTest(asset=name):
                self.assertEqual((shared / name).read_bytes(), data)

    def test_every_profile_carries_its_own_pointer_and_deck_tiles(self):
        for profile in sorted((REPO / 'alpine/themes/profiles').glob('*')):
            if not profile.is_dir():
                continue
            with self.subTest(theme=profile.name):
                for name in self.assets:
                    self.assertTrue((profile / name).is_file(), name)

    def test_another_theme_draws_its_own_ring_and_tiles(self):
        other = desktop_theme.render_assets(REPO, ALTERNATE)
        self.assertEqual(set(other), set(self.assets))
        for name in sorted(self.assets):
            with self.subTest(asset=name):
                self.assertNotEqual(other[name], self.assets[name])

    def test_the_text_pass_never_tries_to_decode_a_drawn_asset(self):
        rendered = desktop_theme.render_profile(REPO, ALTERNATE)
        for name in self.assets:
            self.assertNotIn(name, rendered)

    def test_the_pointer_index_follows_the_theme_and_keeps_its_name(self):
        for theme, expected in ((GRUVBOX, 'simp1e-cursors-gruvbox-dark'),
                                (ALTERNATE, ALTERNATE['design']['cursors'])):
            with self.subTest(theme=theme['id']):
                index = desktop_theme.render_profile(REPO, theme)[desktop_theme.CURSOR_INDEX]
                # The deployed sway seat names Oldbook-Ghost, so only what it
                # inherits may move between themes.
                self.assertIn('Name=Oldbook-Ghost\n', index)
                self.assertIn('Inherits=' + expected + '\n', index)
        seat = (REPO / 'alpine/desktop/.config/sway/theme.conf').read_text()
        self.assertRegex(seat, r'(?m)^seat \* xcursor_theme Oldbook-Ghost \d+$')


class SurfacesOutsideTheOldFileSet(unittest.TestCase):
    """Colour-bearing files a theme switch used to leave behind entirely.

    LXQt's own Qt settings retint a running application within two seconds, and
    the screenshot annotator is spawned fresh for every capture, so both were
    ready to follow a theme and simply were not in the file set.
    """

    PATHS = ('.config/lxqt/lxqt.conf', '.config/satty/config.toml')

    def test_they_are_rendered_into_every_theme_profile(self):
        rendered = desktop_theme.render_profile(REPO, GRUVBOX)
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertIn(path, rendered)
                for profile in sorted((REPO / 'alpine/themes/profiles').glob('*')):
                    if profile.is_dir():
                        self.assertTrue((profile / path).is_file(), profile.name)

    def test_no_gruvbox_shade_survives_into_another_theme(self):
        rendered = desktop_theme.render_profile(REPO, ALTERNATE)
        owned = {value.lower() for value in ALTERNATE['palette'].values()}
        for path in self.PATHS:
            with self.subTest(path=path):
                found = literals(rendered[path])
                self.assertTrue(found)
                self.assertFalse(found & {value.lower()
                                          for value in GRUVBOX['palette'].values()})
                self.assertTrue(found & owned)

    def test_the_palette_preset_takes_the_theme_s_own_name(self):
        rendered = desktop_theme.render_profile(REPO, ALTERNATE)
        self.assertIn('.local/share/lxqt/palettes/Boundary-Probe', rendered)
        self.assertNotIn(desktop_theme.LXQT_PRESET, rendered)
        self.assertIn(desktop_theme.LXQT_PRESET,
                      desktop_theme.render_profile(REPO, GRUVBOX))

    def test_the_icon_and_pointer_names_reach_every_toolkit(self):
        rendered = desktop_theme.render_profile(REPO, ALTERNATE)
        icons = ALTERNATE['design']['icons']
        self.assertIn('icon_theme=' + icons, rendered['.config/lxqt/lxqt.conf'])
        self.assertIn('icon_theme=' + icons, rendered['.config/qt6ct/qt6ct.conf'])
        for version in ('3.0', '4.0'):
            settings = rendered[f'.config/gtk-{version}/settings.ini']
            self.assertIn('gtk-icon-theme-name=' + icons, settings)
            self.assertIn('gtk-cursor-theme-name=Oldbook-Ghost', settings)


class SwitchingReachesTheBootChain(unittest.TestCase):
    """Selecting a theme leaves the checkout ready for one root command."""

    def repository(self, root):
        for relative in ('alpine/desktop', 'alpine/themes/profiles/gruvbox-dark',
                         'alpine/system/boot'):
            shutil.copytree(REPO / relative, root / relative,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for relative in ('alpine/themes/gruvbox-dark.json', 'alpine/themes/current',
                         'alpine/bin/deploy-home', 'alpine/bin/build-console-palette'):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        (root / 'alpine/themes/boundary-probe.json').write_text(json.dumps(ALTERNATE) + '\n')
        return root

    def test_selecting_a_theme_regenerates_the_console_palette_and_says_so(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.repository(Path(directory) / 'repo')
            home = Path(directory) / 'home'
            home.mkdir()
            theme = runpy.run_path(str(root / 'alpine/desktop/.local/bin/oldbook-theme'))
            palette = root / console_palette.RELATIVE
            with mock.patch.object(Path, 'home', return_value=home):
                _theme, _profile, _deployed, notes = theme['use']('boundary-probe', reload=False)
            document = boot_console.load_palette(palette.read_text())
            self.assertEqual(document['theme'], 'boundary-probe')
            self.assertEqual(document['colors'][15], ALTERNATE['palette']['foreground'])
            self.assertEqual([note for note in notes if 'FAILED' in note], [])
            self.assertTrue(any('install-boot-console' in note for note in notes), notes)
            # Reapplying the same theme is not a change to carry into the boot.
            with mock.patch.object(Path, 'home', return_value=home):
                _theme, _profile, _deployed, again = theme['use']('boundary-probe', reload=False)
            self.assertEqual(again, [])

    def test_a_checkout_without_the_boot_sources_still_switches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.repository(Path(directory) / 'repo')
            (root / 'alpine/bin/build-console-palette').unlink()
            home = Path(directory) / 'home'
            home.mkdir()
            theme = runpy.run_path(str(root / 'alpine/desktop/.local/bin/oldbook-theme'))
            with mock.patch.object(Path, 'home', return_value=home):
                _theme, _profile, _deployed, notes = theme['use']('gruvbox-dark', reload=False)
            self.assertEqual(notes, [])

    def test_a_broken_palette_source_is_reported_rather_than_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.repository(Path(directory) / 'repo')
            (root / 'alpine/themes/profiles/gruvbox-dark/.config/foot/foot.ini').write_text(
                '[main]\nfont=x\n')
            home = Path(directory) / 'home'
            home.mkdir()
            theme = runpy.run_path(str(root / 'alpine/desktop/.local/bin/oldbook-theme'))
            with mock.patch.object(Path, 'home', return_value=home):
                notes = theme['refresh_boot_palette'](GRUVBOX)
            self.assertTrue(any('FAILED' in note for note in notes), notes)


if __name__ == '__main__':
    unittest.main()
