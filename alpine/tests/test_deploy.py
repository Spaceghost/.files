import importlib.machinery
import importlib.util
import errno
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import types
import socket
import subprocess
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

    def test_database_backup_manifest_does_not_block_deployment_or_rollback(self):
        backup = self.home / '.local/state/mbp-intel/backups/scripture-hourly'
        backup.mkdir(parents=True)
        manifest = backup / 'manifest.json'
        body = json.dumps({'databases': ['history.sqlite3'],
                           'note': 'Scripture history backup'}) + '\n'
        manifest.write_text(body)
        database = backup / 'history.sqlite3'
        database.write_bytes(b'preserved database backup')
        original = self.home / '.config/app/config'
        original.parent.mkdir(parents=True)
        original.write_text('my original')

        try:
            deployed = m.deploy(self.home, self.overlay)
        except RuntimeError as error:
            self.fail(f'An unrelated database backup blocked deployment: {error}')
        self.assertTrue(original.is_symlink())
        self.assertEqual(original.read_text(), 'new')
        m.rollback(self.home, deployed)
        self.assertEqual(original.read_text(), 'my original')
        self.assertEqual(manifest.read_text(), body)
        self.assertEqual(database.read_bytes(), b'preserved database backup')

    def test_malformed_deployment_headers_block_before_replacing_user_files(self):
        backup = self.home / '.local/state/mbp-intel/backups/1788840000000000000'
        backup.mkdir(parents=True)
        manifest = backup / 'manifest.json'
        original = self.home / '.config/app/config'
        original.parent.mkdir(parents=True)
        original.write_text('my original')
        for document in (
                None,
                False,
                'damaged journal',
                {},
                {'status': 'complete'},
                {'version': 2},
                {'entries': []},
                {'version': 3, 'status': 'complete', 'entries': []},
                {'version': 2, 'status': 'complete', 'entries': None},
                {'version': 2, 'status': 'unexpected', 'entries': []}):
            with self.subTest(document=document):
                original.unlink(missing_ok=True)
                original.write_text('my original')
                manifest.write_text(json.dumps(document))
                with self.assertRaisesRegex(RuntimeError, 'deployment journal'):
                    m.deploy(self.home, self.overlay)
                self.assertFalse(original.is_symlink())
                self.assertEqual(original.read_text(), 'my original')

    def test_reject_parent_symlink_without_external_write(self):
        external = self.root / 'external'
        external.mkdir()
        (self.home / '.config').symlink_to(external)
        with self.assertRaises(RuntimeError):
            m.deploy(self.home, self.overlay)
        self.assertEqual(list(external.iterdir()), [])

    def test_superhold_config_alias_shares_edits_and_restores_legacy_file(self):
        source = self.overlay / '.config/superhold/config.toml'
        source.parent.mkdir(parents=True)
        source.write_text('trigger = "super"\n')
        old = self.home / '.config/hold-to-help/config.toml'
        old.parent.mkdir(parents=True)
        old.write_text('trigger = "capslock"\n')
        new = self.home / '.config/superhold/config.toml'
        saved = m.deploy(self.home, self.overlay)
        self.assertEqual(old.resolve(), new.resolve())
        old.write_text('hold_seconds = 0.7\n')
        self.assertEqual(new.read_text(), source.read_text())
        self.assertIsNone(m.deploy(self.home, self.overlay))
        m.rollback(self.home, saved)
        self.assertEqual(old.read_text(), 'trigger = "capslock"\n')
        self.assertFalse(new.exists())

    def test_only_selects_exact_config_pair_and_excludes_unrelated_files(self):
        source = self.overlay / '.config/superhold/config.toml'
        source.parent.mkdir(parents=True)
        source.write_text('trigger = "super"\n')
        wallpaper = self.root / 'wallpaper.png'
        wallpaper.write_bytes(b'wallpaper')
        selected = ['.config/superhold/config.toml', '.config/hold-to-help/config.toml']
        saved = m.deploy(self.home, self.overlay, wallpaper, only=selected)
        self.assertEqual({entry['path'] for entry in json.loads(
            (saved / 'manifest.json').read_text())['entries']}, set(selected))
        for relative in selected:
            self.assertEqual((self.home / relative).resolve(), source)
        self.assertFalse((self.home / '.config/app').exists())
        self.assertFalse((self.home / '.local/share').exists())

    def test_only_rejects_missing_and_unsafe_selections_before_target_changes(self):
        for selected in ([], ['missing'], ['.config/app'], ['/absolute'], ['../escape'],
                         [''], ['.'], ['.config/app/../app/config'],
                         ['.config/app/config', 'missing']):
            with self.subTest(selected=selected):
                with self.assertRaisesRegex(ValueError, 'selection'):
                    m.deploy(self.home, self.overlay, only=selected)
                self.assertEqual(list(self.home.iterdir()), [])

    def test_explicit_legacy_overlay_config_is_not_replaced_by_alias(self):
        for name in ('superhold', 'hold-to-help'):
            source = self.overlay / '.config' / name / 'config.toml'
            source.parent.mkdir(parents=True)
            source.write_text(name)
        m.deploy(self.home, self.overlay)
        self.assertEqual((self.home / '.config/hold-to-help/config.toml').read_text(),
                         'hold-to-help')

    def test_existing_legacy_overlay_symlink_does_not_create_alias(self):
        source = self.overlay / '.config/superhold/config.toml'
        source.parent.mkdir(parents=True)
        source.write_text('new')
        legacy = self.overlay / '.config/hold-to-help/config.toml'
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'selection'):
            m.deploy(self.home, self.overlay, only=['.config/hold-to-help/config.toml'])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_cli_repeated_only_is_forwarded_and_cannot_limit_rollback(self):
        with mock.patch.object(sys, 'argv', ['deploy-home', '--target', str(self.home),
                '--only', '.config/app/config', '--only', '.config/other/config']), \
                mock.patch.object(m, 'deploy', return_value=None) as deploy, \
                mock.patch.object(sys, 'stdout', io.StringIO()):
            m.main()
        self.assertEqual(deploy.call_args.kwargs['only'],
                         ['.config/app/config', '.config/other/config'])
        with mock.patch.object(sys, 'argv', ['deploy-home', '--only', '.config/app/config',
                '--rollback', str(self.root / 'backup')]), \
                mock.patch.object(m, 'rollback') as rollback, \
                mock.patch.object(sys, 'stderr', io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                m.main()
        self.assertEqual(error.exception.code, 2)
        rollback.assert_not_called()

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
        backups = list((self.home / '.local/state/mbp-intel/backups').iterdir())
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
        backup = next((self.home / '.local/state/mbp-intel/backups').iterdir())
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
        backup = self.home / '.local/state/mbp-intel/backups/legacy'
        saved = backup / 'home/.config/app/config'
        saved.parent.mkdir(parents=True)
        saved.write_text('legacy original')
        (backup / 'manifest.json').write_text(json.dumps([
            {'path': '.config/app/config', 'source': str(source), 'saved': True}]))
        m.rollback(self.home, backup)
        self.assertEqual(dest.read_text(), 'legacy original')


class WrapperMigrationTest(unittest.TestCase):
    def test_portable_profiles_precede_mbp_intel_with_legacy_fallback(self):
        wrapper_loader = importlib.machinery.SourceFileLoader('shortcut_wrapper',
            str(Path(__file__).parents[1] / 'desktop/.local/bin/mbp-intel-shortcuts'))
        wrapper_spec = importlib.util.spec_from_loader(wrapper_loader.name, wrapper_loader)
        wrapper = importlib.util.module_from_spec(wrapper_spec)
        wrapper_loader.exec_module(wrapper)
        for portable in ('superhold', 'hold-to-help', 'dangling', None):
            with self.subTest(portable=portable), tempfile.TemporaryDirectory() as directory:
                config = Path(directory)
                legacy = config / 'mbp-intel/shortcuts.json'
                legacy.parent.mkdir(parents=True)
                legacy.write_text('{}')
                if portable:
                    path = config / ('superhold' if portable == 'dangling' else portable) / 'profiles.json'
                    path.parent.mkdir(parents=True)
                    if portable == 'dangling':
                        path.symlink_to(config / 'missing')
                    else:
                        path.write_text('{}')
                cli = types.SimpleNamespace(main=lambda arguments: arguments)
                with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}, clear=True), \
                        mock.patch.dict(sys.modules, {'superhold.cli': cli, 'hold_to_help.cli': cli}), \
                        mock.patch.object(sys, 'path', [str(Path(__file__).parents[2] /
                            'projects/superhold'), *sys.path]), \
                        mock.patch.object(sys, 'argv', ['mbp-intel-shortcuts', 'status']):
                    expected = ['status'] if portable else ['--profiles', str(legacy), 'status']
                    self.assertEqual(wrapper.main(), expected)

    def test_wrapper_reads_superhold_runtime_status_without_a_display(self):
        repo = Path(__file__).parents[2]
        with mock.patch.object(sys, 'path', [str(repo / 'projects/superhold'), *sys.path]):
            from superhold.service import SessionLease
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            config.chmod(0o700)
            session = config / 'sway-ipc.test.sock'
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(session))
                lease = SessionLease(config, session)
                lease.acquire()
                try:
                    result = subprocess.run([str(repo / 'alpine/desktop/.local/bin/mbp-intel-shortcuts'),
                        'status', '--socket', str(session)],
                        env={'PATH': os.environ['PATH'], 'HOME': directory,
                             'XDG_CONFIG_HOME': directory, 'XDG_RUNTIME_DIR': directory},
                        capture_output=True, text=True, timeout=3)
                finally:
                    lease.close()
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads(result.stdout)
            self.assertTrue(status['live'])
            self.assertEqual(status['socket_id'], lease.socket_id)


if __name__ == '__main__':
    unittest.main()
