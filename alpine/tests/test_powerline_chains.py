"""One rounded separator, present and drawable, on every powerline surface.

The chains once shipped with every starship slot empty -- the tool that wrote
them dropped the private-use glyph -- and with the bar's separators set in a
face, Inter, that keeps a subscript digit at that codepoint. These tests read
each file the way its consumer does (TOML, JSON, CSS, tmux's option lines) and
insist on the glyph itself, in a face that has it.
"""
import json
from pathlib import Path
import re
import sys
import tomllib
import unittest

REPO = Path(__file__).resolve().parents[2]
PROFILES = REPO / 'alpine/themes/profiles'
CHAINED = ('gruvbox-dark', 'catppuccin-mocha', 'monochrome-test')
SEPARATOR = ''
NERD_FONT = 'JetBrainsMono Nerd Font'
COLOUR = r'(#[0-9a-f]{6})'
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))


def cap(colour):
    """A separator in one colour over nothing, as starship's format writes it."""
    return re.escape('[' + SEPARATOR + '](fg:') + colour + re.escape(')')


def strip_jsonc(text):
    return re.sub(r'^\s*//.*$', '', text, flags=re.MULTILINE)


class StarshipChain(unittest.TestCase):
    def formats(self):
        for name in CHAINED:
            document = tomllib.loads((PROFILES / name / '.config/starship.toml').read_text())
            yield name, document['format']

    def test_no_separator_slot_is_empty(self):
        for name, fmt in self.formats():
            with self.subTest(profile=name):
                # An empty slot draws nothing at all, and the chips touch.
                self.assertNotIn('[](', fmt)
                self.assertEqual(fmt.count(SEPARATOR), 10)

    def test_the_ribbon_hands_each_colour_to_the_next_chip(self):
        ribbon = re.compile(
            cap(COLOUR) + r'\$username'
            + re.escape('[' + SEPARATOR + '](fg:') + r'\1 bg:' + COLOUR + r'\)\$hostname'
            + re.escape('[' + SEPARATOR + '](fg:') + r'\2 bg:' + COLOUR + r'\)\$directory'
            + cap(r'\3'))
        for name, fmt in self.formats():
            with self.subTest(profile=name):
                self.assertIsNotNone(ribbon.match(fmt), fmt)

    def test_chips_that_come_and_go_carry_their_own_caps(self):
        """An absent module must leave no separator behind as a coloured stub."""
        for name, fmt in self.formats():
            for module in ('${custom.fossil}', '$git_branch$git_status', '$cmd_duration'):
                with self.subTest(profile=name, module=module):
                    pill = re.compile(r'\(' + cap(COLOUR) + re.escape(module) + cap(r'\1') + r'\)')
                    self.assertIsNotNone(pill.search(fmt), fmt)


class TmuxChain(unittest.TestCase):
    def test_every_status_chip_is_capped(self):
        for name in CHAINED:
            text = (PROFILES / name / '.tmux.conf').read_text()
            for option, caps in (('status-left', 2), ('status-right', 3),
                                 ('window-status-current-format', 2)):
                with self.subTest(profile=name, option=option):
                    line = re.search(r'^setw? -g ' + option + r' "(.*)"$', text, re.MULTILINE)
                    self.assertIsNotNone(line, option)
                    self.assertEqual(line.group(1).count(SEPARATOR), caps)


class WaybarChain(unittest.TestCase):
    def test_the_later_plain_bar_design_has_no_separator_modules(self):
        for name in CHAINED:
            bar = json.loads(strip_jsonc((PROFILES / name / '.config/waybar/config.jsonc').read_text()))
            members = bar[0]['group/status']['modules']
            separators = [module for module in members if module.startswith('custom/sep')]
            with self.subTest(profile=name):
                self.assertEqual(separators, [])


class StripChain(unittest.TestCase):
    PALETTE = {'accent': '#dca7ff', 'background_hard': '#13091f', 'surface': '#261631',
               'foreground': '#eaddf5', 'muted': '#816b91'}
    RECORD = {'workspace': '1: Ghost', 'title': 'Pithos'}

    def setUp(self):
        import window_context
        self.context = window_context

    def test_the_strip_wears_the_same_separator_as_the_chains(self):
        self.assertEqual(self.context.POWERLINE, SEPARATOR)

    def test_the_separator_is_set_in_the_named_face_never_the_captions(self):
        found = self.context.strip_markup(self.RECORD, self.PALETTE, font=NERD_FONT)
        spans = re.findall(r'<span([^>]*)>' + SEPARATOR + '</span>', found)
        # Every glyph sits in a span of its own, and every span names the face.
        self.assertEqual(len(spans), found.count(SEPARATOR))
        self.assertEqual(len(spans), len(self.context.strip_segments(self.RECORD)) + 1)
        for attributes in spans:
            self.assertIn('font_family="' + NERD_FONT + '"', attributes)
        self.assertTrue(found.startswith(
            '<span foreground="#dca7ff" font_family="' + NERD_FONT + '">' + SEPARATOR + '</span>'))
        self.assertTrue(found.endswith(SEPARATOR + '</span>'))

    def test_without_a_face_the_markup_is_unchanged_from_before(self):
        found = self.context.strip_markup(self.RECORD, self.PALETTE)
        self.assertNotIn('font_family', found)
        self.assertIn('<span foreground="#dca7ff" background="#261631">' + SEPARATOR, found)

    def test_the_measuring_line_wears_the_same_face(self):
        import decoration_reserve
        reference = decoration_reserve.REFERENCE
        self.assertIn(SEPARATOR, reference)
        self.assertNotIn('', reference)
        markup = self.context.reference_markup(reference, NERD_FONT)
        self.assertIn('<span font_family="' + NERD_FONT + '">' + SEPARATOR + '</span>', markup)
        self.assertEqual(markup.count(SEPARATOR), reference.count(SEPARATOR))
        self.assertEqual(self.context.reference_markup(reference), reference)


if __name__ == '__main__':
    unittest.main()
