import importlib.machinery
import importlib.util
import errno
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

loader = importlib.machinery.SourceFileLoader('deploy', str(Path(__file__).parents[1] / 'bin/deploy-home'))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class DeployTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.overlay = self.root / 'overlay'
        (self.overlay / '.config/app').mkdir(parents=True)
        (self.overlay / '.config/app/config').write_text('new')

    def test_idempotence_and_rollback_preserve_original(self):
        old = self.home / '.config/app/config'
        old.parent.mkdir(parents=True)
        old.write_text('my original')
        saved = m.deploy(self.home, self.overlay)
        self.assertEqual(old.read_text(), 'new')
        self.assertIsNone(m.deploy(self.home, self.overlay))
        m.rollback(self.home, saved)
        self.assertEqual(old.read_text(), 'my original')
        self.assertFalse(old.is_symlink())

    def test_reject_parent_symlink_without_external_write(self):
        external = self.root / 'external'
        external.mkdir()
        (self.home / '.config').symlink_to(external)
        with self.assertRaises(RuntimeError):
            m.deploy(self.home, self.overlay)
        self.assertEqual(list(external.iterdir()), [])

    def test_rollback_refuses_changed_destination(self):
        backup = m.deploy(self.home, self.overlay)
        dest = self.home / '.config/app/config'
        dest.unlink()
        dest.write_text('user edit')
        with self.assertRaises(RuntimeError):
            m.rollback(self.home, backup)
        self.assertEqual(dest.read_text(), 'user edit')

    def test_full_journal_is_durable_before_any_user_file_moves(self):
        dest = self.home / '.config/app/config'
        dest.parent.mkdir(parents=True)
        dest.write_text('irreplaceable original')
        with mock.patch.object(m.json, 'dump', side_effect=OSError(errno.ENOSPC, 'simulated full journal write')):
            with self.assertRaises(OSError):
                m.deploy(self.home, self.overlay)
        self.assertEqual(dest.read_text(), 'irreplaceable original')
        self.assertFalse(dest.is_symlink())

    def test_crash_after_move_is_recoverable_and_blocks_new_deployment(self):
        dest = self.home / '.config/app/config'
        dest.parent.mkdir(parents=True)
        dest.write_text('original')
        rename = os.replace
        def crash_after_move(source, target):
            result = rename(source, target)
            if Path(source) == dest:
                raise OSError('simulated crash immediately after original moved')
            return result
        with mock.patch.object(m.os, 'replace', crash_after_move):
            with self.assertRaises(OSError):
                m.deploy(self.home, self.overlay)
        backups = list((self.home / '.local/state/oldbook/backups').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / 'manifest.json').is_file())
        with self.assertRaisesRegex(RuntimeError, 'Interrupted deployment'):
            m.deploy(self.home, self.overlay)
        m.rollback(self.home, backups[0])
        self.assertEqual(dest.read_text(), 'original')
        self.assertFalse(dest.is_symlink())
        m.rollback(self.home, backups[0])
        self.assertEqual(dest.read_text(), 'original')

    def test_partial_deployment_rolls_back_all_originals(self):
        first = self.home / '.config/app/config'
        second = self.home / '.config/app/second'
        first.parent.mkdir(parents=True)
        first.write_text('first original')
        second.write_text('second original')
        (self.overlay / '.config/app/second').write_text('new second')
        create_link = Path.symlink_to
        def fail_second(path, source, **kwargs):
            if path == second:
                raise OSError('simulated failure after second backup')
            return create_link(path, source, **kwargs)
        with mock.patch.object(Path, 'symlink_to', fail_second):
            with self.assertRaises(OSError):
                m.deploy(self.home, self.overlay)
        backup = next((self.home / '.local/state/oldbook/backups').iterdir())
        m.rollback(self.home, backup)
        self.assertEqual(first.read_text(), 'first original')
        self.assertEqual(second.read_text(), 'second original')

    def test_interrupted_rollback_can_resume_without_losing_originals(self):
        dest = self.home / '.config/app/config'
        dest.parent.mkdir(parents=True)
        dest.write_text('original')
        backup = m.deploy(self.home, self.overlay)
        saved = backup / 'home/.config/app/config'
        rename = os.replace
        def crash_after_restore(source, target):
            result = rename(source, target)
            if Path(source) == saved:
                raise OSError('simulated crash after original restored')
            return result
        with mock.patch.object(m.os, 'replace', crash_after_restore):
            with self.assertRaises(OSError):
                m.rollback(self.home, backup)
        self.assertEqual(dest.read_text(), 'original')
        m.rollback(self.home, backup)
        self.assertEqual(dest.read_text(), 'original')
        self.assertTrue((backup / 'restored').is_file())

    def test_rollback_refuses_modified_backup_before_touching_deployed_link(self):
        dest = self.home / '.config/app/config'
        dest.parent.mkdir(parents=True)
        dest.write_text('original')
        backup = m.deploy(self.home, self.overlay)
        (backup / 'home/.config/app/config').write_text('changed backup')
        with self.assertRaisesRegex(RuntimeError, 'Saved original changed'):
            m.rollback(self.home, backup)
        self.assertTrue(dest.is_symlink())
        self.assertEqual(dest.read_text(), 'new')

    def test_generated_python_caches_are_never_deployed(self):
        cache = self.overlay / '.local/bin/__pycache__/helper.cpython-314.pyc'
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b'compiled')
        (self.overlay / '.local/bin/loose.pyc').write_bytes(b'compiled')
        m.deploy(self.home, self.overlay)
        self.assertFalse((self.home / '.local/bin/__pycache__').exists())
        self.assertFalse((self.home / '.local/bin/loose.pyc').exists())

    def test_legacy_list_manifest_can_still_restore(self):
        dest = self.home / '.config/app/config'
        dest.parent.mkdir(parents=True)
        source = self.overlay / '.config/app/config'
        dest.symlink_to(source)
        backup = self.home / '.local/state/oldbook/backups/legacy'
        saved = backup / 'home/.config/app/config'
        saved.parent.mkdir(parents=True)
        saved.write_text('legacy original')
        (backup / 'manifest.json').write_text(json.dumps([
            {'path': '.config/app/config', 'source': str(source), 'saved': True}]))
        m.rollback(self.home, backup)
        self.assertEqual(dest.read_text(), 'legacy original')


if __name__ == '__main__':
    unittest.main()
