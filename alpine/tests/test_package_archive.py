import copy
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader(
    'package_archive', str(Path(__file__).parents[1] / 'bin/package-archive'))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class PackageArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cache = self.base / 'cache'
        self.cache.mkdir()
        self.payload = b'signed APK fixture'
        digest = hashlib.sha256(self.payload).hexdigest()
        self.pkg = {
            'name': 'theme', 'version': '1-r0', 'arch': 'x86_64',
            'artifact_arch': 'noarch', 'apk_identity': 'Q1fixture=',
            'filename': 'theme-1-r0.apk', 'sha256': digest,
            'artifact': f'sha256/{digest}/theme-1-r0.apk',
        }
        key = 'public key fixture\n'
        self.manifest = {
            'schema': 2, 'arch': 'x86_64', 'packages': [self.pkg],
            'world': 'theme\n', 'repositories': 'https://example.invalid/edge/main\n',
            'keys': [{'name': 'builder.rsa.pub', 'content': key,
                      'sha256': hashlib.sha256(key.encode()).hexdigest()}],
        }

    def write_lock(self, manifest=None):
        data = (json.dumps(manifest or self.manifest, sort_keys=True, indent=2)+'\n').encode()
        path = self.base / (hashlib.sha256(data).hexdigest()[:20]+'.json')
        path.write_bytes(data)
        return path

    def write_database(self, root, arch='noarch', identity='Q1fixture='):
        database = root / 'lib/apk/db/installed'
        database.parent.mkdir(parents=True, exist_ok=True)
        database.write_text(f'C:{identity}\nP:theme\nV:1-r0\nA:{arch}\n\n')

    def test_lock_rejects_modified_metadata_even_with_valid_json(self):
        lock = self.write_lock()
        lock.write_text(lock.read_text().replace('theme\\n', 'attacker\\n'))
        with self.assertRaisesRegex(RuntimeError, 'immutable filename'):
            m.load_lock(lock)

    def test_lock_rejects_path_traversal_before_restore(self):
        self.manifest['keys'][0]['name'] = '../escape.pub'
        with self.assertRaisesRegex(RuntimeError, 'public key name'):
            m.load_lock(self.write_lock())

    def test_lock_rejects_corrupt_key_before_restore(self):
        self.manifest['keys'][0]['content'] = 'different key'
        with self.assertRaisesRegex(RuntimeError, 'Public key checksum'):
            m.load_lock(self.write_lock())

    def test_lock_rejects_duplicate_package(self):
        self.manifest['packages'].append(copy.deepcopy(self.pkg))
        with self.assertRaisesRegex(RuntimeError, 'Duplicate package'):
            m.load_lock(self.write_lock())

    def test_missing_fetch_does_not_resolve_cached_custom_package(self):
        (self.cache / self.pkg['filename']).write_bytes(self.payload)
        installed = [self.pkg, {'name': 'official', 'version': '2-r1'}]
        with patch.object(m, 'run') as run:
            m.fetch_missing(installed, self.cache,
                            'https://example.invalid/main\n@testing https://example.invalid/testing\n')
        args = run.call_args.args[0]
        self.assertIn('official=2-r1', args)
        self.assertNotIn('theme=1-r0', args)

    def test_snapshot_rejects_same_version_from_different_signed_build(self):
        native = {k: self.pkg[k] for k in ('name', 'version', 'arch', 'apk_identity')}
        native['apk_identity'] = 'Q1different-build='
        with self.assertRaisesRegex(RuntimeError, 'differs from installed identity: theme'):
            m.validate_artifacts([self.pkg], [native])

    def test_snapshot_accepts_noarch_only_when_control_identity_matches(self):
        native = {k: self.pkg[k] for k in ('name', 'version', 'arch', 'apk_identity')}
        native['arch'] = 'noarch'
        m.validate_artifacts([self.pkg], [native])

    def test_corrupt_cached_apk_is_rejected_without_overwrite(self):
        archive = self.cache / self.pkg['filename']
        archive.write_bytes(b'tampered')
        with patch.object(m, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Checksum mismatch'):
                m.export(self.manifest, self.cache)
        run.assert_not_called()
        self.assertEqual(archive.read_bytes(), b'tampered')

    def test_corrupt_fossil_export_is_not_published_and_retry_succeeds(self):
        def corrupt(args, **kwargs):
            Path(args[-1]).write_bytes(b'corrupt Fossil bytes')

        with patch.object(m, 'run', side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError, 'Corrupt Fossil artifact'):
                m.export(self.manifest, self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])

        def correct(args, **kwargs):
            Path(args[-1]).write_bytes(self.payload)

        with patch.object(m, 'run', side_effect=correct):
            m.export(self.manifest, self.cache)
        self.assertEqual((self.cache / self.pkg['filename']).read_bytes(), self.payload)

    def test_cache_symlink_is_rejected(self):
        outside = self.base / 'outside'
        outside.write_bytes(self.payload)
        (self.cache / self.pkg['filename']).symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'symlink'):
            m.export(self.manifest, self.cache)

    def test_noarch_restore_matches_identity_despite_original_index_arch(self):
        root = self.base / 'root'
        self.write_database(root)
        m.verify_closure(m.load_lock(self.write_lock()), root)

    def test_same_name_version_and_arch_with_wrong_identity_is_rejected(self):
        root = self.base / 'root'
        self.write_database(root, identity='Q1different=')
        with self.assertRaisesRegex(RuntimeError, 'differs.*theme'):
            m.verify_closure(self.manifest, root)

    def test_wrong_native_architecture_is_rejected(self):
        root = self.base / 'root'
        self.write_database(root, arch='aarch64')
        with self.assertRaisesRegex(RuntimeError, 'differs.*theme'):
            m.verify_closure(self.manifest, root)

    def test_missing_or_extra_package_is_rejected(self):
        root = self.base / 'root'
        self.write_database(root)
        database = root / 'lib/apk/db/installed'
        database.write_text(database.read_text()+'C:Q1extra=\nP:extra\nV:1-r0\nA:noarch\n\n')
        with self.assertRaisesRegex(RuntimeError, 'differs.*extra'):
            m.verify_closure(self.manifest, root)

    def test_failed_install_preserves_evidence_and_target_can_retry(self):
        root = self.base / 'root'
        (self.cache / self.pkg['filename']).write_bytes(self.payload)

        def fail_install(args, **kwargs):
            stage = Path(args[args.index('--root')+1])
            (stage / 'failure-evidence').write_text('package script failed')
            raise subprocess.CalledProcessError(1, args)

        with patch.object(m.os, 'geteuid', return_value=0), \
                patch.object(m, 'output', return_value='x86_64\n'), \
                patch.object(m, 'run', side_effect=fail_install):
            with self.assertRaisesRegex(RuntimeError, 'evidence retained.*safe to retry'):
                m.restore(self.manifest, self.cache, root)
        self.assertFalse(root.exists())
        stages = list(self.base.glob('.root.restore-*'))
        self.assertEqual(len(stages), 1)
        self.assertTrue((stages[0] / 'failure-evidence').is_file())

        def install(args, **kwargs):
            self.assertIn('--no-network', args)
            self.assertEqual(args[args.index('--repositories-file')+1], '/dev/null')
            stage = Path(args[args.index('--root')+1])
            self.write_database(stage)

        with patch.object(m.os, 'geteuid', return_value=0), \
                patch.object(m, 'output', return_value='x86_64\n'), \
                patch.object(m, 'run', side_effect=install):
            m.restore(self.manifest, self.cache, root)
        self.assertEqual((root / 'etc/apk/world').read_text(), self.manifest['world'])
        self.assertEqual((root / 'etc/apk/repositories').read_text(), self.manifest['repositories'])
        self.assertTrue((stages[0] / 'failure-evidence').is_file())

    def test_nonempty_target_is_never_modified(self):
        root = self.base / 'root'
        root.mkdir()
        marker = root / 'user-data'
        marker.write_text('keep me')
        with patch.object(m.os, 'geteuid', return_value=0), patch.object(m, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'new or empty'):
                m.restore(self.manifest, self.cache, root)
        run.assert_not_called()
        self.assertEqual(marker.read_text(), 'keep me')

    def prepare_host(self):
        root = self.base / 'host'
        self.write_database(root, arch='x86_64')
        (root / 'etc/apk').mkdir(parents=True)
        (root / 'etc/apk/world').write_text('original-world\n')
        (root / 'etc/apk/repositories').write_text('original-repositories\n')
        (root / 'etc/private-config').write_text('local machine configuration')
        (self.cache / self.pkg['filename']).write_bytes(self.payload)
        return root

    def host_patches(self, execute):
        native = {k: self.pkg[k] for k in ('name', 'version', 'arch', 'apk_identity')}
        native['arch'] = 'noarch'
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(m.os, 'geteuid', return_value=0))
        stack.enter_context(patch.object(m, 'output', return_value='x86_64\n'))
        stack.enter_context(patch.object(m, 'artifact_packages', return_value=[native]))
        stack.enter_context(patch.object(m, 'run', side_effect=execute))
        return stack

    def test_host_install_requires_root_before_export(self):
        with patch.object(m.os, 'geteuid', return_value=1000), patch.object(m, 'export') as export:
            with self.assertRaisesRegex(RuntimeError, 'requires root'):
                m.install_host(self.manifest, self.cache)
        export.assert_not_called()

    def test_host_signature_failure_leaves_configuration_and_database_untouched(self):
        root = self.prepare_host()
        before = (root / 'lib/apk/db/installed').read_bytes()

        def reject_signature(args, **kwargs):
            self.assertIn('verify', args)
            raise subprocess.CalledProcessError(1, args)

        with self.host_patches(reject_signature):
            with self.assertRaises(subprocess.CalledProcessError):
                m.install_host(self.manifest, self.cache, root)
        self.assertEqual((root / 'lib/apk/db/installed').read_bytes(), before)
        self.assertEqual((root / 'etc/apk/world').read_text(), 'original-world\n')
        self.assertFalse((root / 'var/backups').exists())

    def test_host_simulation_rejects_removals_before_install(self):
        root = self.prepare_host()
        installed = []

        def simulate_removal(args, **kwargs):
            if '--simulate' in args:
                return subprocess.CompletedProcess(args, 0, '( 1/2) Purging other-package (1-r0)\n')
            if 'add' in args:
                installed.append(args)
            return subprocess.CompletedProcess(args, 0, '')

        with self.host_patches(simulate_removal):
            with self.assertRaisesRegex(RuntimeError, 'would remove existing packages'):
                m.install_host(self.manifest, self.cache, root)
        self.assertEqual(installed, [])
        self.assertFalse((root / 'var/backups').exists())

    def test_host_preserves_extras_and_private_backup_and_applies_locked_world(self):
        root = self.prepare_host()
        db = root / 'lib/apk/db/installed'
        db.write_text(db.read_text()+'C:Q1extra=\nP:extra\nV:1-r0\nA:noarch\n\n')
        installed = []

        def install(args, **kwargs):
            if 'add' in args:
                self.assertIn('--no-network', args)
                self.assertEqual(args[args.index('--repositories-file')+1], '/dev/null')
                if '--simulate' not in args:
                    installed.append(args)
            return subprocess.CompletedProcess(args, 0, '(1/1) Reinstalling theme (1-r0)\n')

        with self.host_patches(install):
            extras = m.install_host(self.manifest, self.cache, root)
        self.assertEqual(extras, ['extra'])
        self.assertEqual(len(installed), 1)
        self.assertEqual((root / 'etc/apk/world').read_text(), self.manifest['world'])
        self.assertEqual((root / 'etc/apk/repositories').read_text(), self.manifest['repositories'])
        self.assertEqual((root / 'etc/private-config').read_text(), 'local machine configuration')
        backups = list((root / 'var/backups/oldbook').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.assertEqual((backups[0] / 'apk-db/installed').read_bytes(), db.read_bytes())
        with m.tarfile.open(backups[0] / 'etc.tar') as archive:
            self.assertEqual(archive.extractfile('etc/apk/world').read(), b'original-world\n')
            self.assertEqual(archive.extractfile('etc/private-config').read(), b'local machine configuration')

    def test_host_identity_failure_retains_backup_and_does_not_publish_locked_world(self):
        root = self.prepare_host()

        def wrong_install(args, **kwargs):
            if 'add' in args and '--simulate' not in args:
                self.write_database(root, identity='Q1wrong=')
            return subprocess.CompletedProcess(args, 0, '')

        with self.host_patches(wrong_install):
            with self.assertRaisesRegex(RuntimeError, 'partial changes may remain.*Do not restore'):
                m.install_host(self.manifest, self.cache, root)
        self.assertEqual(len(list((root / 'var/backups/oldbook').iterdir())), 1)
        self.assertEqual((root / 'etc/apk/world').read_text(), 'original-world\n')


if __name__ == '__main__':
    unittest.main()
