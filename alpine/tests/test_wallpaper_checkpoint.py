import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('wallpaper_generator_checkpoint', REPO / 'alpine/wallpapers/generate.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class WallpaperCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='art-checkpoint-test-')
        self.base = Path(self.temporary.name)
        self.repo = self.base / 'checkout'
        self.repo.mkdir()
        self.fossil('init', str(self.base / 'test.fossil'), '--admin-user', 'art-test')
        self.fossil('open', str(self.base / 'test.fossil'))
        self.fossil('settings', 'autosync', 'off')
        self.fossil('user', 'default', 'art-test')
        (self.repo / 'unrelated.txt').write_text('original\n')
        self.fossil('add', 'unrelated.txt')
        self.fossil('commit', '--nosync', '--nosign', '--no-prompt', '-m', 'test: baseline')
        (self.repo / 'unrelated.txt').write_text('user work in progress\n')
        self.gallery = self.repo / 'alpine/assets/gallery'
        self.gallery.mkdir(parents=True)
        self.image = self.gallery / '2026-09-07-test.png'
        self.image.write_bytes(b'\x89PNG\r\n\x1a\n' + b'validated bitmap fixture' * 100)
        self.sidecar = self.image.with_suffix('.json')
        self.sidecar.write_text(json.dumps({'file': str(self.image.relative_to(self.repo)),
                                           'sha256': hashlib.sha256(self.image.read_bytes()).hexdigest()}))

    def tearDown(self):
        self.temporary.cleanup()

    def fossil(self, *args):
        return subprocess.run(['fossil', *args], cwd=self.repo, capture_output=True,
                              text=True, check=True, timeout=30).stdout

    def test_checkpoint_commits_pair_only_and_preserves_unrelated_edits(self):
        (self.repo / 'another-new.txt').write_text('another task\n')
        self.fossil('add', 'another-new.txt')
        checkin = generator.checkpoint_generated(self.image, self.sidecar, self.repo)
        self.assertRegex(checkin, r'^[0-9a-f]{40,64}$')
        changes = self.fossil('changes', '--classify', '--rel-paths')
        self.assertIn('EDITED', changes)
        self.assertIn('unrelated.txt', changes)
        self.assertIn('ADDED', changes)
        self.assertIn('another-new.txt', changes)
        self.assertNotIn(self.image.name, changes)
        self.assertNotIn(self.sidecar.name, changes)
        self.assertEqual(self.fossil('cat', 'unrelated.txt', '-r', checkin), 'original\n')
        self.assertEqual((self.repo / 'unrelated.txt').read_text(), 'user work in progress\n')
        committed = subprocess.check_output(['fossil', 'cat', str(self.image.relative_to(self.repo)), '-r', checkin], cwd=self.repo)
        self.assertEqual(committed, self.image.read_bytes())

    def test_checkpoint_accepts_themed_and_general_pairs_without_other_changes(self):
        for folder in ('general', 'themes/gruvbox-dark'):
            with self.subTest(folder=folder):
                directory = self.gallery / folder
                directory.mkdir(parents=True)
                image = directory / 'new.png'
                image.write_bytes(self.image.read_bytes())
                sidecar = image.with_suffix('.json')
                sidecar.write_text(json.dumps({'file': str(image.relative_to(self.repo)),
                                               'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}))
                checkin = generator.checkpoint_generated(image, sidecar, self.repo)
                committed = subprocess.check_output(['fossil', 'cat', str(image.relative_to(self.repo)),
                                                     '-r', checkin], cwd=self.repo)
                self.assertEqual(committed, image.read_bytes())
                self.assertIn('unrelated.txt', self.fossil('changes', '--rel-paths'))

    def test_checkpoint_rejects_arbitrary_subdirectories_and_symlinked_theme_directory(self):
        for folder in ('elsewhere', 'themes/Bad Name', 'themes/gruvbox-dark/deeper'):
            directory = self.gallery / folder
            directory.mkdir(parents=True, exist_ok=True)
            image = directory / 'bad.png'
            image.write_bytes(self.image.read_bytes())
            sidecar = image.with_suffix('.json')
            sidecar.write_text('{}')
            with self.subTest(folder=folder), self.assertRaisesRegex(RuntimeError, 'gallery'):
                generator.checkpoint_generated(image, sidecar, self.repo)
        linked = self.gallery / 'themes/linked'
        linked.symlink_to(self.gallery, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            generator.checkpoint_generated(linked / self.image.name, linked / self.sidecar.name, self.repo)
        self.assertNotIn(self.image.name, self.fossil('ls'))

    def test_checkpoint_failure_keeps_files_and_daily_reservation(self):
        self.fossil('settings', 'autosync', 'on')
        state = self.base / 'state'
        state.mkdir()
        record = state / (generator.dt.date.today().isoformat() + '.json')
        metadata = {'status': 'checkpoint-pending', 'file': str(self.image.relative_to(self.repo))}
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(generator.checkpoint_record(record, metadata, self.repo), 1)
        self.assertEqual(json.loads(record.read_text())['status'], 'checkpoint-pending')
        self.assertTrue(self.image.is_file())
        self.assertTrue(self.sidecar.is_file())
        with mock.patch.object(generator, 'STATE', state), mock.patch.object(generator, 'REPO', self.repo):
            native_popen = subprocess.Popen
            with mock.patch.object(generator.subprocess, 'Popen', wraps=native_popen) as processes, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(generator.run_once(), 1)
                self.assertTrue(processes.call_args_list)
                self.assertTrue(all(call.args[0][0] == 'fossil' for call in processes.call_args_list))
        self.fossil('settings', 'autosync', 'off')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(generator.checkpoint_record(record, metadata, self.repo), 0)
        self.assertEqual(json.loads(record.read_text())['status'], 'complete')

    def test_configured_hooks_are_refused_without_running_or_bypassing(self):
        marker = self.base / 'hook-ran'
        self.fossil('hook', 'add', '--type', 'before-commit', '--command', 'touch ' + str(marker))
        with self.assertRaisesRegex(RuntimeError, 'hooks are configured'):
            generator.checkpoint_generated(self.image, self.sidecar, self.repo)
        self.assertFalse(marker.exists())
        self.assertNotIn(self.image.name, self.fossil('ls'))


if __name__ == '__main__':
    unittest.main()
