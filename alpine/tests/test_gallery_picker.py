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
