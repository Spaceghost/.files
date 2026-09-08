"""Oldbook Ghost cursors: the Xcursor encoder, the drawn shapes and the theme tree."""
import configparser
import importlib.machinery
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
THEME = REPO / 'alpine/themes/gruvbox-dark.json'
INSTALLED = REPO / 'alpine/desktop/.local/share/icons/Oldbook-Ghost'

loader = importlib.machinery.SourceFileLoader('build_cursor_theme',
                                              str(REPO / 'alpine/bin/build-cursor-theme'))
spec = importlib.util.spec_from_loader(loader.name, loader)
builder = importlib.util.module_from_spec(spec)
loader.exec_module(builder)


def sample(width=4, height=4, xhot=1, yhot=2, delay=28, fill=b'\x11\x22\x33\x44'):
    return (width, height, xhot, yhot, delay, fill * (width * height))


class EncoderTests(unittest.TestCase):
    def test_round_trip_preserves_every_field(self):
        images = [sample(delay=17), sample(width=8, height=8, xhot=4, yhot=4, delay=28)]
        entries = builder.decode(builder.encode(images))
        self.assertEqual(len(entries), 2)
        for original, entry in zip(images, entries):
            width, height, xhot, yhot, delay, pixels = original
            self.assertEqual(entry['nominal'], width)
            self.assertEqual((entry['width'], entry['height']), (width, height))
            self.assertEqual((entry['xhot'], entry['yhot']), (xhot, yhot))
            self.assertEqual(entry['delay'], delay)
            self.assertEqual(entry['pixels'], pixels)

    def test_header_matches_the_xcursor_format(self):
        data = builder.encode([sample(), sample()])
        magic, header, version, count = struct.unpack_from('<4sIII', data, 0)
        self.assertEqual(magic, b'Xcur')
        self.assertEqual((header, version, count), (16, 0x00010000, 2))

    def test_table_positions_address_their_own_chunks(self):
        data = builder.encode([sample(), sample(width=8, height=8)])
        for index in range(2):
            kind, nominal, position = struct.unpack_from('<III', data, 16 + index * 12)
            chunk_nominal = struct.unpack_from('<I', data, position + 8)[0]
            self.assertEqual(kind, builder.IMAGE_TYPE)
            self.assertEqual(chunk_nominal, nominal)

    def test_short_pixel_buffer_is_refused(self):
        with self.assertRaises(ValueError):
            builder.encode([(4, 4, 0, 0, 28, b'\x00' * 12)])

    def test_truncated_file_is_refused(self):
        data = builder.encode([sample()])
        with self.assertRaises(ValueError):
            builder.decode(data[:-16])

    def test_foreign_magic_is_refused(self):
        with self.assertRaises(ValueError):
            builder.decode(b'RIFF' + builder.encode([sample()])[4:])


class ShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palette = builder.load_palette(THEME)

    def test_watch_frames_are_square_and_centred(self):
        for size in builder.SIZES:
            frames = builder.watch_frames(self.palette, size, frames=6)
            self.assertEqual(len(frames), 6)
            for width, height, xhot, yhot, delay, pixels in frames:
                self.assertEqual((width, height), (size, size))
                self.assertEqual((xhot, yhot), (size // 2, size // 2))
                self.assertEqual(delay, builder.FRAME_DELAY_MS)
                self.assertEqual(len(pixels), size * size * 4)

    def test_progress_keeps_the_inherited_pointer_hotspot(self):
        for size, hotspot in builder.POINTER_HOTSPOTS.items():
            frames = builder.progress_frames(self.palette, size, frames=3)
            for _, _, xhot, yhot, _, _ in frames:
                self.assertEqual((xhot, yhot), (hotspot, hotspot))

    def test_frames_differ_so_the_ring_actually_turns(self):
        frames = builder.watch_frames(self.palette, 48, frames=8)
        self.assertEqual(len({frame[5] for frame in frames}), 8)

    def test_every_frame_draws_something(self):
        for frames in (builder.watch_frames(self.palette, 48, frames=4),
                       builder.progress_frames(self.palette, 48, frames=4)):
            for frame in frames:
                self.assertTrue(any(frame[5][3::4]), 'frame is fully transparent')

    def test_breath_returns_to_its_start(self):
        self.assertAlmostEqual(builder.ease_breath(0.0), 0.0, places=9)
        self.assertAlmostEqual(builder.ease_breath(0.5), 1.0, places=9)
        self.assertAlmostEqual(builder.ease_breath(1.0), 0.0, places=9)


class ThemeTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palette = builder.load_palette(THEME)
        cls.directory = tempfile.TemporaryDirectory(prefix='oldbook-cursor-theme-')
        cls.output = Path(cls.directory.name) / 'Oldbook-Ghost'
        cls.written = builder.build(cls.output, cls.palette, sizes=(24, 48), frames=4)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def expected_names(self):
        names = []
        for real, (_, aliases) in builder.SHAPES.items():
            names.append(real)
            names.extend(aliases)
        return names

    def test_every_alias_is_written(self):
        for name in self.expected_names():
            self.assertTrue((self.output / 'cursors' / name).is_file(), name)

    def test_aliases_are_byte_identical_to_their_shape(self):
        for real, (_, aliases) in builder.SHAPES.items():
            reference = (self.output / 'cursors' / real).read_bytes()
            for alias in aliases:
                self.assertEqual((self.output / 'cursors' / alias).read_bytes(), reference,
                                 f'{alias} differs from {real}')

    def test_index_inherits_the_installed_set(self):
        parser = configparser.ConfigParser()
        parser.read(self.output / 'index.theme')
        self.assertEqual(parser['Icon Theme']['Name'], 'Oldbook-Ghost')
        self.assertEqual(parser['Icon Theme']['Inherits'], builder.INHERITS)

    def test_written_files_group_frames_by_nominal_size(self):
        entries = builder.decode((self.output / 'cursors' / 'watch').read_bytes())
        counts = {}
        for entry in entries:
            counts[entry['nominal']] = counts.get(entry['nominal'], 0) + 1
        self.assertEqual(counts, {24: 4, 48: 4})

    def test_deployment_sees_regular_files_only(self):
        # deploy-home skips symlinks, so aliases must be real files to reach HOME.
        for path in (self.output / 'cursors').iterdir():
            self.assertFalse(path.is_symlink(), path.name)


class InstalledThemeTests(unittest.TestCase):
    """The checked-in theme, as the desktop will actually load it."""

    def test_the_theme_is_present_and_complete(self):
        self.assertTrue((INSTALLED / 'index.theme').is_file())
        for real, (_, aliases) in builder.SHAPES.items():
            for name in (real,) + tuple(aliases):
                self.assertTrue((INSTALLED / 'cursors' / name).is_file(), name)

    def test_installed_shapes_carry_every_size_and_frame(self):
        for name in builder.SHAPES:
            entries = builder.decode((INSTALLED / 'cursors' / name).read_bytes())
            counts = {}
            for entry in entries:
                counts[entry['nominal']] = counts.get(entry['nominal'], 0) + 1
            self.assertEqual(counts, {size: builder.FRAMES for size in builder.SIZES},
                             f'{name} is missing sizes or frames')
            self.assertTrue(all(entry['delay'] == builder.FRAME_DELAY_MS for entry in entries))


if __name__ == '__main__':
    unittest.main()
