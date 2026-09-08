"""Gallery theme picks must surface results and allow repairing the active theme."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_wallpapers import REPO, load


art = load('theme_picker_wallpaper', REPO / 'alpine/desktop/.local/bin/oldbook-wallpaper')


class ThemePickerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        themes = self.repo / 'alpine/themes'
        themes.mkdir(parents=True)
        for identity, name in (('active-theme', 'Active theme'),
                               ('moon-books', 'Moon books; $(not-a-command)')):
            (themes / (identity + '.json')).write_text(json.dumps({
                'id': identity, 'name': name, 'image_style': 'Fixture moonlight.'}))
        (themes / 'current').write_text('active-theme\n')
        patch = mock.patch.object(art, 'REPO', self.repo)
        patch.start()
        self.addCleanup(patch.stop)

    def test_selected_theme_requests_visible_result_with_literal_identity(self):
        with mock.patch.object(art, 'gallery_menu',
                               return_value='○  Moon books; $(not-a-command)'), \
                mock.patch.object(art.subprocess, 'Popen') as launch:
            self.assertEqual(art.switch_theme(), 0)
        launch.assert_called_once_with(
            ['/usr/bin/python3', str(REPO / 'alpine/desktop/.local/bin/oldbook-theme'),
             'use', 'moon-books', '--notify'], start_new_session=True)

    def test_active_theme_can_be_reapplied_after_incomplete_refresh(self):
        with mock.patch.object(art, 'gallery_menu', return_value='●  Active theme'), \
                mock.patch.object(art.subprocess, 'Popen') as launch:
            self.assertEqual(art.switch_theme(), 0)
        launch.assert_called_once_with(
            ['/usr/bin/python3', str(REPO / 'alpine/desktop/.local/bin/oldbook-theme'),
             'use', 'active-theme', '--notify'], start_new_session=True)

    def test_cancel_back_or_unknown_selection_never_launches(self):
        for selection in (None, '← Back to the gallery', 'unknown'):
            with self.subTest(selection=selection), \
                    mock.patch.object(art, 'gallery_menu', return_value=selection), \
                    mock.patch.object(art.subprocess, 'Popen') as launch:
                self.assertEqual(art.switch_theme(), 0)
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
