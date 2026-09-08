import runpy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

API = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-wallpaper'))


class GalleryPickerTests(unittest.TestCase):
    def test_newest_first_pages_select_the_original_artwork_id(self):
        entries = [dict(id=str(i), title='Painting ' + str(i),
                        generated_utc=f'2026-09-07T{i:02d}:00:00+00:00') for i in range(14)]
        pages = []
        def menu(command, **kwargs):
            rows = kwargs['input'].splitlines()
            pages.append(rows)
            self.assertLessEqual(int(command[command.index('--lines') + 1]), 9)
            if len(pages) == 1:
                self.assertIn('Painting 13', rows[0])
                self.assertFalse(any('Painting 9' in row for row in rows))
                return SimpleNamespace(returncode=0, stdout='Older images →\n')
            self.assertIn('Painting 9', rows[0])
            return SimpleNamespace(returncode=0, stdout=rows[0] + '\n')
        function = API['pick']
        with mock.patch.dict(function.__globals__, load_gallery=lambda: (entries, 1200),
                             available_themes=lambda _: [], update=mock.Mock()) as scope:
            with mock.patch('subprocess.run', side_effect=menu):
                function()
            scope['update'].assert_called_once_with('pick', '9')
        self.assertEqual(len(pages), 2)

    def test_cancel_does_not_change_wallpaper(self):
        function = API['pick']
        update = mock.Mock()
        with mock.patch.dict(function.__globals__, load_gallery=lambda: ([dict(id='a', title='A')], 1200),
                             available_themes=lambda _: [], update=update):
            with mock.patch('subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='')):
                function()
        update.assert_not_called()


class FakeThumbnails:
    """Stand-in for the cache: paintings whose path is known get an icon name."""
    THEME = 'Oldbook-Thumbnails'
    __file__ = '/nonexistent/thumbnails.py'

    def __init__(self):
        self.rendered = []
        self.theme_requests = 0

    def thumbnail(self, path, height=48, radius=None, digest=None, shape='fit', cache=None):
        self.rendered.append((str(path), height, digest))
        return Path('/cache') / (f'{digest or "hash"}-h{height}.png')

    def cached(self, path, height=48, radius=None, digest=None, shape='fit', cache=None):
        return Path('/cache') / (f'{digest or "hash"}-h{height}.png')

    @staticmethod
    def icon_name(path):
        return Path(path).stem

    def icon_theme(self):
        self.theme_requests += 1
        return self.THEME


class GalleryThumbnailTests(unittest.TestCase):
    def entries(self, count):
        return [dict(id=str(i), title='Painting ' + str(i), path=f'/art/{i}.png', sha256='ab' * 32,
                     generated_utc=f'2026-09-07T{i:02d}:00:00+00:00') for i in range(count)]

    def test_painting_rows_carry_thumbnail_icons_and_selection_ignores_the_suffix(self):
        fake = FakeThumbnails()
        calls = []

        def menu(command, **kwargs):
            calls.append((command, kwargs['input'].split('\n')))
            # Fuzzel echoes the row text; a client that echoed the icon field too must still match.
            return SimpleNamespace(returncode=0, stdout=calls[-1][1][0] + '\n')
        function = API['pick']
        with mock.patch.dict(function.__globals__, load_gallery=lambda: (self.entries(6), 1200),
                             available_themes=lambda _: [], update=mock.Mock(),
                             thumbnails=fake, warm_thumbnails=mock.Mock()) as scope:
            with mock.patch('subprocess.run', side_effect=menu):
                function()
            scope['update'].assert_called_once_with('pick', '5')
        command, rows = calls[0]
        self.assertIn('--icon-theme', command)
        self.assertEqual(command[command.index('--icon-theme') + 1], 'Oldbook-Thumbnails')
        self.assertEqual(command[command.index('--line-height') + 1], '40')
        painting_rows = [row for row in rows if row.startswith(('01', '02', '03', '04'))]
        self.assertEqual(len(painting_rows), 4)
        for row in painting_rows:
            self.assertRegex(row, r'\x00icon\x1f' + 'ab' * 32 + r'-h96$')
        self.assertTrue(all('\x00' not in row for row in rows if row.startswith(('Older', '✦', 'Gallery'))))
        # Only the four rows on screen are rendered before the menu opens.
        self.assertEqual(len(fake.rendered), 4)
        self.assertEqual(fake.theme_requests, 1)

    def test_rows_without_thumbnails_keep_the_plain_menu(self):
        calls = []

        def menu(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=1, stdout='')
        function = API['pick']
        entries = [dict(id='a', title='A')]  # no path, so nothing to render
        with mock.patch.dict(function.__globals__, load_gallery=lambda: (entries, 1200),
                             available_themes=lambda _: [], update=mock.Mock(),
                             warm_thumbnails=mock.Mock()):
            with mock.patch('subprocess.run', side_effect=menu):
                function()
        self.assertNotIn('--icon-theme', calls[0])
        self.assertNotIn('--line-height', calls[0])

    def test_gallery_menu_returns_plain_text_for_iconed_rows(self):
        menu = API['gallery_menu']
        with mock.patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='Row\x00icon\x1fname\n')) as run:
            self.assertEqual(menu('P ❯ ', ['Row', 'Other'], {'Row': 'name'}), 'Row')
        self.assertEqual(run.call_args.kwargs['input'], 'Row\x00icon\x1fname\nOther\n')
        with mock.patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='Row\n')):
            self.assertEqual(menu('P ❯ ', ['Row', 'Other'], {'Row': 'name'}), 'Row')
            self.assertEqual(menu('P ❯ ', ['Row', 'Other']), 'Row')

    def test_status_reports_a_thumbnail_only_when_a_height_is_requested(self):
        import io
        import json
        import contextlib
        status = API['status']
        fake = FakeThumbnails()
        current = Path(__file__).resolve()
        with mock.patch.dict(status.__globals__, read_state=lambda: {'title': 'T'}, generation_status=lambda: None,
                             thumbnails=fake, CURRENT=current):
            plain, sized = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(plain):
                status()
            with contextlib.redirect_stdout(sized):
                status(44)
        self.assertNotIn('thumbnail', json.loads(plain.getvalue()))
        self.assertEqual(json.loads(sized.getvalue())['thumbnail'], '/cache/hash-h44.png')
        self.assertEqual(fake.rendered, [(str(current), 44, None)])
