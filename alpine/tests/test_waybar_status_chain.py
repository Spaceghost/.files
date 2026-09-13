"""The bar's status chain is flush chips joined by drawn caps, in every theme."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO = Path(__file__).resolve().parents[2]
PROFILES = REPO / 'alpine/themes/profiles'
PALETTE = REPO / 'alpine/desktop/.local/bin/oldbook-palette'


def bar_config(path):
    document = json.loads(re.sub(r'^\s*//.*$', '', path.read_text(), flags=re.M))
    return document[0] if isinstance(document, list) else document


def rules(style):
    """The stylesheet without its comments, which may name selectors in prose."""
    return re.sub(r'/\*.*?\*/', '', style.read_text(), flags=re.S)


def chained_themes():
    for style in sorted(PROFILES.glob('*/.config/waybar/style.css')):
        if '#custom-sep0' in style.read_text():
            yield style.parents[2].name, style, bar_config(style.with_name('config.jsonc'))


class StatusChainTests(unittest.TestCase):
    def test_the_active_themes_carry_a_chain(self):
        self.assertLessEqual({'gruvbox-dark', 'catppuccin-mocha', 'monochrome-test'},
                             {name for name, _, _ in chained_themes()})

    def test_every_chip_is_styled_by_the_name_waybar_gives_its_group(self):
        # Waybar names the box of group/<name> #<name>, as #status is group/status.
        # #group-<name> matches nothing, which left every chip unpainted.
        for name, style, bar in chained_themes():
            css = rules(style)
            self.assertNotRegex(css, r'#group-[a-z]', name)
            groups = [module[len('group/'):] for module in bar['group/status']['modules']
                      if module.startswith('group/')]
            self.assertTrue(groups, name)
            for group in groups:
                self.assertRegex(css, rf'(?m)^#{re.escape(group)} {{ background: ', (name, group))

    def test_every_separator_draws_its_cap_instead_of_sizing_a_glyph(self):
        # A glyph is only as tall as its line; the chip is taller, and the next
        # chip's colour showed above and below it as a strip.
        for name, style, bar in chained_themes():
            css = rules(style)
            separators = [module for module in bar['group/status']['modules']
                          if module.startswith('custom/sep')]
            self.assertGreaterEqual(len(separators), 2, name)
            for module in separators:
                selector = re.escape('#' + module.replace('/', '-'))
                self.assertRegex(css, rf'(?m)^{selector} {{[^}}]*radial-gradient\(ellipse farthest-side',
                                 (name, module))

    def test_the_caps_beside_the_clock_wear_the_tint_the_palette_gives_it(self):
        self.assertIn('#clock {{ background: alpha(@oldbook_accent, .18); }}', PALETTE.read_text())
        for name, style, _ in chained_themes():
            css = rules(style)
            self.assertRegex(css, r'(?m)^#custom-sep5 \{ background-color: alpha\(@oldbook_accent, \.18\);', name)
            self.assertRegex(css, r'(?m)^#custom-sep6 \{ background-image: radial-gradient\(ellipse '
                                  r'farthest-side at left, alpha\(@oldbook_accent, \.18\)', name)

    def test_every_chain_stylesheet_parses_in_gtk3(self):
        # One property GTK3 refuses takes the whole bar down, so parse each file
        # the way waybar loads it, beside the two files it imports, off-screen.
        probe = textwrap.dedent('''
            import sys
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, GLib
            try:
                Gtk.CssProvider().load_from_path(sys.argv[1])
            except GLib.Error as error:
                print(error.message)
                sys.exit(1)
        ''')
        environment = {key: value for key, value in os.environ.items()
                       if key not in ('WAYLAND_DISPLAY', 'DISPLAY', 'SWAYSOCK')}
        for name, style, _ in chained_themes():
            with tempfile.TemporaryDirectory() as directory:
                copy = Path(directory) / 'style.css'
                copy.write_text(style.read_text())
                (Path(directory) / 'waybar-accent.css').write_text('@define-color oldbook_accent #fabd2f;\n')
                (Path(directory) / 'waybar-state.css').write_text('')
                result = subprocess.run([sys.executable, '-c', probe, str(copy)], capture_output=True,
                                        text=True, env=environment, timeout=60)
                if 'gi' in result.stderr and ('No module named' in result.stderr
                                              or 'not available' in result.stderr):
                    self.skipTest('GTK3 introspection is not installed')
                self.assertEqual(result.returncode, 0, (name, result.stdout, result.stderr))


if __name__ == '__main__':
    unittest.main()
