import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


def load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(REPO / 'alpine/bin' / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


publisher = load('publication_test', 'publish-git-mirror')
backup = load('backup_test', 'backup-repository')


@unittest.skipUnless(shutil.which('git') and shutil.which('fossil'), 'needs git and fossil')
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-publication-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checkout = self.root / 'checkout'
        self.checkout.mkdir()
        self.database = self.root / 'source.fossil'
        self.command('fossil', 'init', '-A', 'tester', self.database)
        self.command('fossil', 'open', self.database, '--nosync')
        self.command('fossil', 'user', 'default', 'tester')
        (self.checkout / 'config').write_text('first\n')
        self.command('fossil', 'add', 'config')
        self.command('fossil', 'commit', '--nosync', '--no-warnings', '--branch',
                     'alpine-oldbook', '-m', 'Initial desktop')
        self.mirror = self.root / 'mirror'
        self.remote = self.root / 'remote.git'
        self.command('git', 'init', '--bare', self.remote)

    def command(self, *args, cwd=None):
        result = subprocess.run([str(x) for x in args], cwd=cwd or self.checkout,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def test_publish_retry_and_incremental_preserve_other_branch(self):
        first = publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        self.command('git', 'update-ref', 'refs/heads/base', first, cwd=self.remote)
        again = publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        self.assertEqual(first, again)
        (self.checkout / 'config').write_text('second\n')
        self.command('fossil', 'commit', '--nosync', '--no-warnings', '-m', 'Change desktop')
        second = publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        self.assertNotEqual(first, second)
        self.assertEqual(self.command('git', 'show', 'alpine-oldbook:config', cwd=self.remote), 'second\n')
        self.assertEqual(self.command('git', 'rev-parse', 'base', cwd=self.remote).strip(), first)
        self.assertTrue((self.mirror / '.mirror_state').is_dir())

    def test_diverged_remote_is_not_overwritten(self):
        publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        other = self.root / 'other'
        self.command('git', 'clone', '--branch', 'alpine-oldbook', self.remote, other)
        self.command('git', 'config', 'user.name', 'Test', cwd=other)
        self.command('git', 'config', 'user.email', 'test@example.invalid', cwd=other)
        (other / 'remote-change').write_text('keep me\n')
        self.command('git', 'add', 'remote-change', cwd=other)
        self.command('git', 'commit', '-m', 'Remote edit', cwd=other)
        self.command('git', 'push', 'origin', 'alpine-oldbook', cwd=other)
        before = self.command('git', 'rev-parse', 'alpine-oldbook', cwd=self.remote)
        with self.assertRaises(subprocess.CalledProcessError):
            publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        self.assertEqual(before, self.command('git', 'rev-parse', 'alpine-oldbook', cwd=self.remote))

    def test_separate_push_destination_is_rejected(self):
        publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        unintended = self.root / 'unintended.git'
        self.command('git', 'init', '--bare', unintended)
        self.command('git', 'config', 'remote.github.pushurl', unintended, cwd=self.mirror)
        with self.assertRaisesRegex(ValueError, 'push destination differs'):
            publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        self.assertEqual(self.command('git', 'for-each-ref', cwd=unintended), '')

    def test_mirror_symlink_into_checkout_is_rejected(self):
        alias = self.root / 'mirror-alias'
        destination = self.checkout / 'nested-mirror'
        alias.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'mirror separate'):
            publisher.publish(self.checkout, alias, str(self.remote), 'alpine-oldbook')
        self.assertFalse(destination.exists())

    def test_backup_dangling_metadata_symlink_is_not_followed(self):
        destination = self.root / 'public.fossil'
        unintended = self.root / 'untouched'
        destination.with_suffix('.fossil.json').symlink_to(unintended)
        with self.assertRaises(SystemExit):
            backup.backup(self.checkout, destination, public=True)
        self.assertFalse(unintended.exists())
        self.assertFalse(destination.exists())

    def test_public_backup_retains_history_uv_and_identity_without_passwords(self):
        (self.checkout / 'artifact').write_bytes(b'exact package bytes\x00')
        self.command('fossil', 'uv', 'add', 'artifact', '--as', 'archive/package.apk')
        self.command('fossil', 'user', 'password', 'tester', 'disposable-test-password')
        destination = self.root / 'public.fossil'
        backup.backup(self.checkout, destination, public=True)
        with sqlite3.connect(self.database) as source, sqlite3.connect(destination) as copy:
            self.assertGreater(source.execute("SELECT count(*) FROM user WHERE pw != ''").fetchone()[0], 0)
            self.assertEqual(copy.execute("SELECT count(*) FROM user WHERE pw != ''").fetchone()[0], 0)
            self.assertEqual(source.execute("SELECT value FROM config WHERE name='project-code'").fetchone(),
                             copy.execute("SELECT value FROM config WHERE name='project-code'").fetchone())
            self.assertEqual(source.execute('SELECT name, hash FROM unversioned').fetchall(),
                             copy.execute('SELECT name, hash FROM unversioned').fetchall())
        metadata = json.loads(destination.with_suffix('.fossil.json').read_text())
        self.assertTrue(metadata['public_scrubbed'])
        self.assertEqual(metadata['sha256'], hashlib.sha256(destination.read_bytes()).hexdigest())
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        restored = self.root / 'restored'
        restored.mkdir()
        self.command('fossil', 'open', destination, 'alpine-oldbook', '--nosync', cwd=restored)
        self.assertEqual((restored / 'config').read_text(), 'first\n')
        with self.assertRaises((FileExistsError, SystemExit)):
            backup.backup(self.checkout, destination, public=True)


if __name__ == '__main__':
    unittest.main()
