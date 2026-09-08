"""Preservation review finds overlapping behaviors and never hides uncovered work."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CHECK = runpy.run_path(str(REPO / 'alpine/bin/check-features'))


class FeatureImpact(unittest.TestCase):
    def setUp(self):
        self.features = CHECK['load_index']()

    def ids(self, paths):
        return {item['id'] for item in CHECK['affected'](self.features, paths)}

    def test_theme_template_change_reviews_brand_lock_and_caption_contracts(self):
        changes = ['alpine/wallpapers/desktop_theme.py', 'alpine/themes/example.json']
        self.assertTrue({'THEME-COMPLETE', 'GHOST-BRAND', 'LOCK-THEME', 'DECORATION-STYLE',
                         'GALLERY-ACTIVATION', 'CONKY-READING'} <= self.ids(changes))

    def test_mode_binding_change_reviews_keys_and_window_switching_together(self):
        self.assertTrue({'WINDOW-SWITCHING', 'APPLE-KEYS', 'SHORTCUT-HELP',
                         'SESSION-OWNERSHIP'} <= self.ids([
                             'alpine/desktop/.config/sway/local.d/apple-overview.conf']))

    def test_installed_guide_source_is_in_scope_across_project_directories(self):
        self.assertTrue({'SHORTCUT-HELP', 'THEME-COMPLETE'} <= self.ids([
            'projects/superhold-guide/src/superhold/theme.py']))

    def test_deleted_profile_still_has_impact_without_an_existing_file(self):
        self.assertTrue({'GHOST-BRAND', 'BAR-LAYOUT', 'DEPLOY-RECOVERY'} <= self.ids([
            'alpine/themes/profiles/deleted-theme/.config/waybar/style.css']))

    def test_unknown_feature_is_rejected_instead_of_running_nothing(self):
        result = subprocess.run([sys.executable, str(REPO / 'alpine/bin/check-features'),
                                 '--feature', 'TYPO'], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unknown feature', result.stderr)

    def test_unmapped_change_is_reported_without_claiming_coverage(self):
        result = subprocess.run([sys.executable, str(REPO / 'alpine/bin/check-features'),
                                 '--json', 'alpine/new-component/unknown.py'], text=True,
                                capture_output=True, check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report['features'], [])
        self.assertEqual(report['unmapped_paths'], ['alpine/new-component/unknown.py'])

    def test_path_normalization_keeps_hidden_files_and_rejects_escape(self):
        self.assertEqual(CHECK['normalize_path'](str(REPO / 'alpine/desktop/.config/sway/config')),
                         'alpine/desktop/.config/sway/config')
        with self.assertRaises(ValueError):
            CHECK['normalize_path']('../unrelated/config')

    def test_all_checks_are_existing_files_and_ids_are_unique(self):
        self.assertEqual(len(self.features), len({item['id'] for item in self.features}))
        for item in self.features:
            for test in item.get('tests', []):
                self.assertTrue((REPO / 'alpine/tests' / test).is_file())

    def test_shared_checks_run_once_and_a_failure_fails_the_review(self):
        fixtures = [
            {'id': 'FEATURE-A', 'paths': ['alpine/a/*'], 'tests': ['test_carousel.py']},
            {'id': 'FEATURE-B', 'paths': ['alpine/b/*'],
             'tests': ['test_carousel.py', 'test_deploy.py']},
        ]
        main = CHECK['main']
        with mock.patch.dict(main.__globals__, {'load_index': lambda: fixtures}), \
                mock.patch.object(subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)]) as run, \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--all', '--run']), 1)
        self.assertEqual([call.args[0][-2] for call in run.call_args_list],
                         ['test_carousel.py', 'test_deploy.py'])


if __name__ == '__main__':
    unittest.main()
