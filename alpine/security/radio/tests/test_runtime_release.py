"""Deterministic, explicit runtime releases; temporary files only."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / 'make-runtime-release'
LOADER = importlib.machinery.SourceFileLoader('radio_runtime_release', str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
release = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(release)


class RuntimeReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / 'source'
        for name in release.SOURCE_FILES:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic source: ' + name + '\n')
        self.manifest = self.source / release.MANIFEST
        self.manifest.write_text('\n'.join(release.SOURCE_FILES) + '\n')
        self.archive = self.directory / 'release.tar.gz'

    def test_exact_regular_manifest_and_payload_modes(self):
        release.make_release(self.source, self.archive)
        with tarfile.open(self.archive) as archive:
            members = archive.getmembers()
            expected = [f'{release.PACKAGE}-{release.VERSION}/{name}'
                        for name in sorted(release.SOURCE_FILES)]
            self.assertEqual([member.name for member in members], expected)
            for member in members:
                name = member.name.split('/', 1)[1]
                self.assertTrue(member.isfile())
                self.assertEqual(member.mode, release.file_mode(name))
                self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, release.EPOCH))
            self.assertEqual(len(release.RUNTIME_FILES), 17)
            self.assertEqual(sum(mode == 0o750 for mode in release.RUNTIME_FILES.values()), 3)
            self.assertTrue(all(name.startswith('root/usr/local/') for name in release.RUNTIME_FILES))

    def test_mtimes_source_modes_and_output_name_do_not_change_bytes(self):
        release.make_release(self.source, self.archive)
        first = self.archive.read_bytes()
        for name in release.SOURCE_FILES:
            path = self.source / name
            os.utime(path, (42, 42))
            path.chmod(0o600)
        other = self.directory / 'other.tar.gz'
        release.make_release(self.source, other)
        self.assertEqual(first, other.read_bytes())

    def test_unlisted_private_policy_cache_and_fixture_are_never_copied(self):
        for name in ('auth.json', 'root/etc/privacyctl/profiles',
                     'root/etc/wpa_supplicant/wpa_supplicant.conf',
                     'root/usr/local/lib/privacyctl_runtime/__pycache__/lease.pyc',
                     'tests/fixtures/private-output.json', 'tests/.secret'):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('must remain outside the release')
        release.make_release(self.source, self.archive)
        with tarfile.open(self.archive) as archive:
            self.assertEqual(len(archive.getmembers()), len(release.SOURCE_FILES))

    def test_new_runtime_module_requires_explicit_release_review(self):
        extra = self.source / 'root/usr/local/lib/privacyctl_runtime/new_module.py'
        extra.write_text('new runtime implementation')
        with self.assertRaisesRegex(ValueError, 'runtime module'):
            release.make_release(self.source, self.archive)

    def test_manifest_additions_duplicates_omissions_and_unsafe_paths_refuse(self):
        original = self.manifest.read_text()
        for name in ('auth.json', 'tests/.secret', '../outside', '/etc/passwd',
                     'tests/../auth.json', release.SOURCE_FILES[0]):
            with self.subTest(name=name):
                self.manifest.write_text(original + name + '\n')
                with self.assertRaises(ValueError):
                    release.make_release(self.source, self.archive)
        self.manifest.write_text('\n'.join(release.SOURCE_FILES[1:]) + '\n')
        with self.assertRaises(ValueError):
            release.make_release(self.source, self.archive)
        self.assertFalse(self.archive.exists())

    def test_symlink_file_and_parent_and_special_file_refuse_without_replacing_output(self):
        self.archive.write_bytes(b'previous release')
        target = self.source / 'tests/test_lease.py'
        target.unlink()
        target.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            release.make_release(self.source, self.archive)
        target.unlink()
        os.mkfifo(target)
        with self.assertRaises(ValueError):
            release.make_release(self.source, self.archive)
        target.unlink()
        target.write_text('restored')
        tests = self.source / 'tests'
        tests.rename(self.source / 'elsewhere')
        tests.symlink_to(self.source / 'elsewhere', target_is_directory=True)
        with self.assertRaises(ValueError):
            release.make_release(self.source, self.archive)
        self.assertEqual(self.archive.read_bytes(), b'previous release')

    def test_hardlinked_source_and_source_output_refuse(self):
        target = self.source / 'tests/test_lease.py'
        os.link(target, self.directory / 'outside')
        with self.assertRaises(ValueError):
            release.make_release(self.source, self.archive)
        (self.directory / 'outside').unlink()
        original = target.read_bytes()
        with self.assertRaises(ValueError):
            release.make_release(self.source, target)
        self.assertEqual(target.read_bytes(), original)

    def test_file_and_manifest_size_limits_preserve_existing_archive(self):
        self.archive.write_bytes(b'previous release')
        source = self.source / 'tests/test_lease.py'
        with source.open('wb') as stream:
            stream.truncate(release.FILE_LIMIT + 1)
        with self.assertRaises(ValueError):
            release.make_release(self.source, self.archive)
        source.write_text('restored')
        self.manifest.write_text('#' * (release.MANIFEST_LIMIT + 1))
        with self.assertRaises(ValueError):
            release.make_release(self.source, self.archive)
        self.assertEqual(self.archive.read_bytes(), b'previous release')


if __name__ == '__main__':
    unittest.main()
