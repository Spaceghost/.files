"""Ghost Planet GRUB theme: the PF2 font writer, theme.txt and the GRUB defaults."""
import json
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
GRUB = REPO / 'alpine/system/grub'
sys.path.insert(0, str(GRUB))
import grub_theme as gt  # noqa: E402

THEME = GRUB / 'theme'


def glyph(code, rows, x_ofs=0, y_ofs=0, device_width=None):
    width = len(rows[0]) if rows else 0
    height = len(rows)
    return {'code': code, 'width': width, 'height': height, 'x_ofs': x_ofs, 'y_ofs': y_ofs,
            'device_width': device_width if device_width is not None else width,
            'bitmap': gt.pack_bitmap(rows)}


class BitmapTests(unittest.TestCase):
    def test_packs_most_significant_bit_first(self):
        self.assertEqual(gt.pack_bitmap([[1, 0, 0, 0, 0, 0, 0, 0]]), b'\x80')
        self.assertEqual(gt.pack_bitmap([[0, 0, 0, 0, 0, 0, 0, 1]]), b'\x01')

    def test_rows_are_a_continuous_stream_without_padding(self):
        # Three three-pixel rows are nine bits (101 010 111): two bytes, not
        # three, and the ninth bit lands at the top of the second byte.
        packed = gt.pack_bitmap([[1, 0, 1], [0, 1, 0], [1, 1, 1]])
        self.assertEqual(len(packed), 2)
        self.assertEqual(packed, bytes([0b10101011, 0b10000000]))

    def test_round_trips_through_unpack(self):
        rows = [[(column + row) % 3 == 0 for column in range(13)] for row in range(7)]
        packed = gt.pack_bitmap(rows)
        restored = gt.unpack_bitmap(packed, 13, 7)
        self.assertEqual([[bool(pixel) for pixel in row] for row in rows], restored)


class Pf2Tests(unittest.TestCase):
    def sample(self):
        return [glyph(0x41, [[1, 1, 0], [1, 0, 1], [1, 1, 1]]),
                glyph(0x67, [[0, 1], [1, 1]], x_ofs=1, y_ofs=-2, device_width=4),
                glyph(0x20, [], device_width=9)]

    def test_round_trips_metadata_and_glyphs(self):
        data = gt.build_pf2(self.sample(), 'Ghost Mono Regular 32', 'Ghost Mono', 32, 26, 7)
        document = gt.parse_pf2(data)
        self.assertEqual(document['name'], 'Ghost Mono Regular 32')
        self.assertEqual(document['fami'], 'Ghost Mono')
        self.assertEqual(document['weig'], 'normal')
        self.assertEqual((document['ptsz'], document['asce'], document['desc']), (32, 26, 7))
        self.assertEqual(document['maxw'], 3)
        self.assertEqual(document['maxh'], 3)
        self.assertEqual(sorted(document['glyphs']), [0x20, 0x41, 0x67])
        descender = document['glyphs'][0x67]
        self.assertEqual((descender['x_ofs'], descender['y_ofs'], descender['device_width']), (1, -2, 4))
        self.assertEqual(gt.unpack_bitmap(document['glyphs'][0x41]['bitmap'], 3, 3),
                         [[True, True, False], [True, False, True], [True, True, True]])

    def test_starts_with_the_pff2_magic(self):
        data = gt.build_pf2(self.sample(), 'n', 'f', 16, 12, 4)
        self.assertEqual(data[:12], b'FILE' + struct.pack('>I', 4) + b'PFF2')

    def test_character_index_offsets_point_at_the_glyphs(self):
        data = gt.build_pf2(self.sample(), 'n', 'f', 16, 12, 4)
        document = gt.parse_pf2(data)
        for code, entry in document['glyphs'].items():
            self.assertEqual(entry['code'], code)
        # The parser follows the recorded offsets, so a wrong offset would have
        # produced different bitmaps above; assert the sentinel is present too.
        self.assertIn(b'DATA' + struct.pack('>I', 0xFFFFFFFF), data)

    def test_index_is_sorted_by_code_point(self):
        data = gt.build_pf2(self.sample(), 'n', 'f', 16, 12, 4)
        start = data.index(b'CHIX')
        length = struct.unpack('>I', data[start + 4:start + 8])[0]
        payload = data[start + 8:start + 8 + length]
        codes = [struct.unpack_from('>I', payload, offset)[0]
                 for offset in range(0, length, gt.CHIX_ENTRY.size)]
        self.assertEqual(codes, sorted(codes))

    def test_rejects_a_bitmap_of_the_wrong_size(self):
        broken = glyph(0x41, [[1, 1], [1, 1]])
        broken['bitmap'] = b'\x00\x00\x00'
        with self.assertRaises(ValueError):
            gt.build_pf2([broken], 'n', 'f', 16, 12, 4)

    def test_rejects_duplicate_code_points(self):
        with self.assertRaises(ValueError):
            gt.build_pf2([glyph(0x41, [[1]]), glyph(0x41, [[0]])], 'n', 'f', 16, 12, 4)

    def test_rejects_an_empty_font(self):
        with self.assertRaises(ValueError):
            gt.build_pf2([], 'n', 'f', 16, 12, 4)


class ThemeDocumentTests(unittest.TestCase):
    def specification(self):
        return {
            'globals': {'desktop-image': 'background.png', 'desktop-color': '#282828',
                        'terminal-font': 'Ghost Mono Regular 20'},
            'components': [
                {'type': 'label', 'text': 'GHOST PLANET', 'top': '13%', 'font': 'Ghost Mono Regular 32'},
                {'type': 'boot_menu', 'left': '22%', 'scrollbar': False, 'item_height': 46,
                 'selected_item_pixmap_style': 'select_*.png'},
                {'type': 'progress_bar', 'id': '__timeout__', 'show_text': True},
            ],
        }

    def test_renders_booleans_and_percentages_unquoted(self):
        text = gt.render_theme(self.specification())
        self.assertIn('scrollbar = false', text)
        self.assertIn('show_text = true', text)
        self.assertIn('left = 22%', text)
        self.assertIn('item_height = 46', text)
        self.assertIn('font = "Ghost Mono Regular 32"', text)

    def test_validates_against_shipped_fonts_and_images(self):
        text = gt.render_theme(self.specification())
        self.assertTrue(gt.validate_theme(text, fonts=['Ghost Mono Regular 32', 'Ghost Mono Regular 20'],
                                          images=['background.png', 'select_c.png', 'select_nw.png']))

    def test_rejects_a_font_that_was_not_shipped(self):
        text = gt.render_theme(self.specification())
        with self.assertRaises(ValueError):
            gt.validate_theme(text, fonts=['Ghost Mono Regular 20'], images=['background.png', 'select_c.png'])

    def test_rejects_a_pixmap_set_that_was_not_shipped(self):
        text = gt.render_theme(self.specification())
        with self.assertRaises(ValueError):
            gt.validate_theme(text, fonts=['Ghost Mono Regular 32', 'Ghost Mono Regular 20'],
                              images=['background.png'])

    def test_requires_the_menu_components(self):
        specification = self.specification()
        specification['components'] = [specification['components'][0]]
        with self.assertRaises(ValueError):
            gt.validate_theme(gt.render_theme(specification))


class GrubDefaultsTests(unittest.TestCase):
    ORIGINAL = ('GRUB_TIMEOUT=1\n'
                'GRUB_DISABLE_SUBMENU=y\n'
                'GRUB_DISABLE_RECOVERY=true\n'
                'GRUB_CMDLINE_LINUX_DEFAULT="quiet vt.color=0x0F"\n')

    VALUES = {'GRUB_TIMEOUT': 3, 'GRUB_TIMEOUT_STYLE': 'menu',
              'GRUB_THEME': '/boot/grub/themes/ghost-planet/theme.txt',
              'GRUB_GFXMODE': 'auto', 'GRUB_GFXPAYLOAD_LINUX': 'keep'}

    def test_rewrites_an_existing_key_in_place(self):
        result = gt.rewrite_grub_keys(self.ORIGINAL, self.VALUES)
        self.assertIn('GRUB_TIMEOUT=3\n', result)
        self.assertNotIn('GRUB_TIMEOUT=1', result)
        # Exactly one GRUB_TIMEOUT line; GRUB_TIMEOUT_STYLE is a separate key.
        self.assertEqual(result.count('GRUB_TIMEOUT='), 1)
        self.assertEqual(result.count('GRUB_TIMEOUT_STYLE='), 1)

    def test_keeps_every_unmanaged_line(self):
        result = gt.rewrite_grub_keys(self.ORIGINAL, self.VALUES)
        self.assertIn('GRUB_DISABLE_SUBMENU=y\n', result)
        self.assertIn('GRUB_CMDLINE_LINUX_DEFAULT="quiet vt.color=0x0F"\n', result)

    def test_appends_absent_keys_under_one_banner(self):
        result = gt.rewrite_grub_keys(self.ORIGINAL, self.VALUES)
        self.assertEqual(result.count('# Ghost Planet boot menu'), 1)
        self.assertIn('GRUB_GFXPAYLOAD_LINUX=keep\n', result)
        self.assertIn('GRUB_THEME=/boot/grub/themes/ghost-planet/theme.txt\n', result)

    def test_is_idempotent(self):
        once = gt.rewrite_grub_keys(self.ORIGINAL, self.VALUES)
        twice = gt.rewrite_grub_keys(once, self.VALUES)
        self.assertEqual(once, twice)

    def test_reads_the_managed_keys_back(self):
        result = gt.rewrite_grub_keys(self.ORIGINAL, self.VALUES)
        found = gt.grub_key_values(result)
        self.assertEqual(found['GRUB_TIMEOUT'], '3')
        self.assertEqual(found['GRUB_THEME'], '/boot/grub/themes/ghost-planet/theme.txt')

    def test_refuses_a_duplicated_key(self):
        with self.assertRaises(ValueError):
            gt.rewrite_grub_keys('GRUB_TIMEOUT=1\nGRUB_TIMEOUT=2\n', {'GRUB_TIMEOUT': 3})

    def test_refuses_shell_metacharacters(self):
        with self.assertRaises(ValueError):
            gt.rewrite_grub_keys(self.ORIGINAL, {'GRUB_THEME': '/tmp/$(reboot)/theme.txt'})

    def test_quotes_a_value_with_spaces(self):
        result = gt.rewrite_grub_keys(self.ORIGINAL, {'GRUB_GFXMODE': '1280x800 auto'})
        self.assertIn('GRUB_GFXMODE="1280x800 auto"\n', result)


class MenuConfigTests(unittest.TestCase):
    THEME_PATH = '/boot/grub/themes/ghost-planet/theme.txt'
    GOOD = ('set timeout_style=menu\n'
            'set timeout=3\n'
            'insmod gfxmenu\n'
            'loadfont ($root)/grub/themes/ghost-planet/ghost-32.pf2\n'
            'loadfont ($root)/grub/themes/ghost-planet/ghost-20.pf2\n'
            'insmod png\n'
            'set theme=($root)/grub/themes/ghost-planet/theme.txt\n'
            'export theme\n'
            'terminal_output gfxterm\n')

    # What grub-mkconfig actually writes: the timeout sits indented inside the
    # feature test and is repeated in the fallback branch below it.
    REAL = ('terminal_output gfxterm\n'
            'if [ x$feature_timeout_style = xy ] ; then\n'
            '  set timeout_style=menu\n'
            '  set timeout=3\n'
            'else\n'
            '  set timeout=3\n'
            'fi\n'
            'insmod gfxmenu\n'
            'loadfont ($root)/grub/themes/ghost-planet/ghost-32.pf2\n'
            'insmod png\n'
            'set theme=($root)/grub/themes/ghost-planet/theme.txt\n')

    def test_accepts_a_generated_menu(self):
        found = gt.validate_menu_cfg(self.GOOD, self.THEME_PATH, 3)
        self.assertEqual(len(found['fonts']), 2)

    def test_accepts_the_indented_lines_grub_mkconfig_writes(self):
        found = gt.validate_menu_cfg(self.REAL, self.THEME_PATH, 3)
        self.assertEqual(found['fonts'], ['/grub/themes/ghost-planet/ghost-32.pf2'])

    def test_still_rejects_the_wrong_timeout_when_indented(self):
        with self.assertRaises(ValueError):
            gt.validate_menu_cfg(self.REAL, self.THEME_PATH, 1)

    def test_rejects_a_missing_theme_selection(self):
        with self.assertRaises(ValueError):
            gt.validate_menu_cfg(self.GOOD.replace('set theme=', 'set nothing='), self.THEME_PATH, 3)

    def test_rejects_a_hidden_menu(self):
        with self.assertRaises(ValueError):
            gt.validate_menu_cfg(self.GOOD.replace('set timeout_style=menu', 'set timeout_style=hidden'),
                                 self.THEME_PATH, 3)

    def test_rejects_the_wrong_timeout(self):
        with self.assertRaises(ValueError):
            gt.validate_menu_cfg(self.GOOD, self.THEME_PATH, 5)

    def test_rejects_a_text_only_terminal(self):
        with self.assertRaises(ValueError):
            gt.validate_menu_cfg(self.GOOD.replace('terminal_output gfxterm', 'terminal_output console'),
                                 self.THEME_PATH, 3)

    def test_rejects_a_theme_without_its_own_font(self):
        without = '\n'.join(line for line in self.GOOD.splitlines() if 'loadfont' not in line) + '\n'
        with self.assertRaises(ValueError):
            gt.validate_menu_cfg(without, self.THEME_PATH, 3)


class ShippedThemeTests(unittest.TestCase):
    """The committed theme has to be self-consistent without running the generator."""

    def setUp(self):
        if not (THEME / 'theme.txt').is_file():
            self.skipTest('the theme has not been generated yet')
        self.provenance = json.loads((THEME / 'provenance.json').read_text())

    def test_fonts_parse_and_carry_their_declared_names(self):
        for record in self.provenance['fonts']:
            document = gt.parse_pf2((THEME / record['file']).read_bytes())
            self.assertEqual(document['name'], record['name'])
            self.assertEqual(len(document['glyphs']), record['glyphs'])
            self.assertGreater(document['maxh'], 16, 'the point of a custom font is a bigger one')

    def test_fonts_carry_the_printable_ascii_range_and_the_ghost(self):
        document = gt.parse_pf2((THEME / self.provenance['fonts'][0]['file']).read_bytes())
        for code in range(0x20, 0x7F):
            self.assertIn(code, document['glyphs'], 'missing U+%04X' % code)
        ghost = document['glyphs'].get(0xF02A0)
        self.assertIsNotNone(ghost, 'the Nerd Font ghost is the wordmark')
        self.assertTrue(ghost['width'] and ghost['height'], 'the ghost glyph has no ink')

    def test_letters_have_ink_and_space_has_none(self):
        document = gt.parse_pf2((THEME / self.provenance['fonts'][0]['file']).read_bytes())
        for character in 'AGhostPlanet0123':
            entry = document['glyphs'][ord(character)]
            self.assertTrue(any(entry['bitmap']), 'no ink for ' + character)
        self.assertEqual(document['glyphs'][0x20]['bitmap'], b'')
        self.assertGreater(document['glyphs'][0x20]['device_width'], 0)

    def test_theme_only_names_shipped_fonts_and_images(self):
        text = (THEME / 'theme.txt').read_text()
        fonts = [record['name'] for record in self.provenance['fonts']]
        images = [path.name for path in THEME.glob('*.png')]
        self.assertTrue(gt.validate_theme(text, fonts=fonts, images=images))

    def test_every_selection_tile_is_present(self):
        for corner in ('c', 'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'):
            self.assertTrue((THEME / ('select_%s.png' % corner)).is_file(), corner)

    def test_the_background_stays_small_enough_to_decode_at_boot(self):
        size = (THEME / 'background.png').stat().st_size
        self.assertLess(size, 600_000, 'GRUB decodes this PNG on the CPU before the menu appears')

    def test_provenance_hashes_match_the_committed_files(self):
        import hashlib
        for record in self.provenance['fonts'] + [self.provenance['background']]:
            data = (THEME / record['file']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'], record['file'])


if __name__ == '__main__':
    unittest.main()
