import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
import thumbnails


def painting(path, width=160, height=100):
    """A small opaque test painting; the cache must round its corners."""
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, height)
    pixbuf.fill(0xfabd2fff)
    pixbuf.savev(str(path), 'png', [], [])
    return path


def corner_alpha(path):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
    pixels = pixbuf.get_pixels()
    stride, channels = pixbuf.get_rowstride(), pixbuf.get_n_channels()
    width, height = pixbuf.get_width(), pixbuf.get_height()
    corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    centre = pixels[(height // 2) * stride + (width // 2) * channels + 3]
    return [pixels[y * stride + x * channels + 3] for x, y in corners], centre


class ThumbnailCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.source = painting(self.root / 'painting.png')

    def test_renders_scaled_rounded_png_into_the_cache(self):
        path = thumbnails.thumbnail(self.source, height=48, cache=self.cache)
        self.assertIsNotNone(path)
        self.assertEqual(path.parent, self.cache / thumbnails.CACHE_NAME)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
        self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (76, 48))
        corners, centre = corner_alpha(path)
        self.assertEqual(corners, [0, 0, 0, 0])
        self.assertEqual(centre, 255)
        self.assertEqual(oct(path.stat().st_mode & 0o777), '0o600')
        self.assertEqual(oct(path.parent.stat().st_mode & 0o777), '0o700')
        self.assertFalse(list(path.parent.glob('*.tmp')))

    def test_square_shape_crops_to_the_centre(self):
        path = thumbnails.thumbnail(self.source, height=40, shape='square', cache=self.cache)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
        self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (40, 40))
        self.assertTrue(path.name.endswith('-square.png'))

    def test_cache_key_uses_supplied_digest_height_and_radius(self):
        digest = 'a' * 64
        path = thumbnails.thumbnail(self.source, height=96, radius=12, digest=digest, cache=self.cache)
        self.assertEqual(path.name, 'a' * 32 + '-h96-r12-fit.png')
        hashed = thumbnails.thumbnail(self.source, height=96, radius=12, cache=self.cache)
        self.assertEqual(hashed.name, thumbnails.file_digest(self.source)[:32] + '-h96-r12-fit.png')
        self.assertNotEqual(path, hashed)
        self.assertEqual(thumbnails.icon_name(path), 'a' * 32 + '-h96-r12-fit')

    def test_second_request_reuses_the_cached_file(self):
        first = thumbnails.thumbnail(self.source, height=48, cache=self.cache)
        os.utime(first, (1, 1))
        second = thumbnails.thumbnail(self.source, height=48, cache=self.cache)
        self.assertEqual(first, second)
        self.assertEqual(second.stat().st_mtime, 1)
        self.assertEqual(thumbnails.cached(self.source, height=48, cache=self.cache), first)
        self.assertIsNone(thumbnails.cached(self.source, height=64, cache=self.cache))

    def test_unreadable_or_missing_paintings_yield_no_thumbnail(self):
        broken = self.root / 'broken.png'
        broken.write_bytes(b'not a png')
        self.assertIsNone(thumbnails.thumbnail(broken, cache=self.cache))
        self.assertIsNone(thumbnails.thumbnail(self.root / 'missing.png', cache=self.cache))
        self.assertFalse(list((self.cache / thumbnails.CACHE_NAME).glob('*')))

    def test_warm_renders_every_readable_painting(self):
        other = painting(self.root / 'other.png', 120, 120)
        count = thumbnails.warm([self.source, other, self.root / 'missing.png'], height=32, cache=self.cache)
        self.assertEqual(count, 2)
        self.assertEqual(len(list((self.cache / thumbnails.CACHE_NAME).glob('*.png'))), 2)

    def test_icon_theme_links_the_cache_and_inherits_the_desktop_theme(self):
        data = self.root / 'data'
        name = thumbnails.icon_theme(cache=self.cache, data=data, inherits=['Oldbook-Gruvbox'])
        self.assertEqual(name, thumbnails.THEME)
        theme = data / 'icons' / thumbnails.THEME
        self.assertEqual((theme / 'thumbnails').resolve(), (self.cache / thumbnails.CACHE_NAME).resolve())
        index = (theme / 'index.theme').read_text()
        self.assertIn('Inherits=Oldbook-Gruvbox,Papirus,hicolor', index)
        self.assertIn('Directories=thumbnails', index)
        path = thumbnails.thumbnail(self.source, height=96, cache=self.cache)
        self.assertTrue((theme / 'thumbnails' / path.name).is_file())
        # Re-running is idempotent and keeps the same link and index.
        before = (theme / 'index.theme').stat().st_mtime_ns
        thumbnails.icon_theme(cache=self.cache, data=data, inherits=['Oldbook-Gruvbox'])
        self.assertEqual((theme / 'index.theme').stat().st_mtime_ns, before)

    def test_desktop_icon_theme_reads_gtk_settings(self):
        settings = self.root / 'settings.ini'
        settings.write_text('[Settings]\ngtk-icon-theme-name=Oldbook-Gruvbox\n')
        self.assertEqual(thumbnails.desktop_icon_theme(settings), 'Oldbook-Gruvbox')
        self.assertIsNone(thumbnails.desktop_icon_theme(self.root / 'absent.ini'))

    def test_command_line_prints_cache_paths(self):
        environment = dict(os.environ, XDG_CACHE_HOME=str(self.cache))
        with mock.patch.dict(os.environ, environment):
            import contextlib
            import io
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = thumbnails.main(['--height', '24', str(self.source)])
        self.assertEqual(code, 0)
        printed = Path(output.getvalue().strip())
        self.assertTrue(printed.is_file())
        self.assertTrue(printed.name.endswith('-h24-r3-fit.png'))


if __name__ == '__main__':
    unittest.main()
