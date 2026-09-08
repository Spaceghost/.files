import hashlib
import fcntl
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]


def load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(REPO / 'alpine/bin' / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


publisher = load('publication_test', 'publish-git-mirror')
backup = load('backup_test', 'backup-repository')


class CommandTimeoutTests(unittest.TestCase):
    def test_timeout_stops_helpers_before_a_later_retry(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-timeout-test-') as directory:
            marker = Path(directory) / 'surviving-helper'
            child = ('import time; from pathlib import Path; time.sleep(1); '
                     f'Path({str(marker)!r}).touch()')
            parent = ('import subprocess, sys, time; '
                      f'subprocess.Popen([sys.executable, "-c", {child!r}]); time.sleep(10)')
            with mock.patch.object(publisher, 'COMMAND_TIMEOUT', 0.2):
                with self.assertRaises(subprocess.TimeoutExpired):
                    publisher.run([sys.executable, '-c', parent], directory)
            time.sleep(1.1)
            self.assertFalse(marker.exists(), 'Timed-out helper continued after releasing the lock')


@unittest.skipUnless(shutil.which('git') and shutil.which('fossil'), 'needs git and fossil')
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-publication-test-')
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

    def test_remote_branch_publishes_beside_a_diverged_branch_of_the_same_name(self):
        publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        other = self.root / 'other'
        self.command('git', 'clone', '--branch', 'alpine-oldbook', self.remote, other)
        self.command('git', 'config', 'user.name', 'Test', cwd=other)
        self.command('git', 'config', 'user.email', 'test@example.invalid', cwd=other)
        (other / 'remote-change').write_text('another line\n')
        self.command('git', 'add', 'remote-change', cwd=other)
        self.command('git', 'commit', '-m', 'Remote edit', cwd=other)
        self.command('git', 'push', 'origin', 'alpine-oldbook', cwd=other)
        diverged = self.command('git', 'rev-parse', 'alpine-oldbook', cwd=self.remote)
        (self.checkout / 'config').write_text('ours\n')
        self.command('fossil', 'commit', '--nosync', '--no-warnings', '-m', 'Our change')
        commit = publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook',
                                   remote_branch='alpine-oldbook-live')
        self.assertEqual(self.command('git', 'rev-parse', 'alpine-oldbook-live',
                                      cwd=self.remote).strip(), commit)
        self.assertEqual(self.command('git', 'show', 'alpine-oldbook-live:config',
                                      cwd=self.remote), 'ours\n')
        self.assertEqual(diverged, self.command('git', 'rev-parse', 'alpine-oldbook',
                                                cwd=self.remote))
        receipt = json.loads((self.mirror / '.git/oldbook-published.json').read_text())
        self.assertEqual(receipt['branch'], 'alpine-oldbook')
        self.assertEqual(receipt['remote_branch'], 'alpine-oldbook-live')

    def test_publishing_the_same_commit_under_a_new_name_is_not_skipped(self):
        state = self.root / 'scheduler-state'
        self.assertEqual(publisher.scheduled(self.checkout, self.mirror, str(self.remote),
                                             'alpine-oldbook', state), 0)
        commit = self.command('git', 'rev-parse', 'alpine-oldbook', cwd=self.remote).strip()
        # The receipt records the destination too, so an unchanged commit still
        # publishes when it has never been sent under this name.
        self.assertEqual(publisher.scheduled(self.checkout, self.mirror, str(self.remote),
                                             'alpine-oldbook', state, 'alpine-oldbook-live'), 0)
        self.assertEqual(self.command('git', 'rev-parse', 'alpine-oldbook-live',
                                      cwd=self.remote).strip(), commit)
        status = json.loads((state / 'status.json').read_text())
        self.assertEqual(status['remote_branch'], 'alpine-oldbook-live')

    def test_separate_push_destination_is_rejected(self):
        publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        unintended = self.root / 'unintended.git'
        self.command('git', 'init', '--bare', unintended)
        self.command('git', 'config', 'remote.github.pushurl', unintended, cwd=self.mirror)
        with self.assertRaisesRegex(ValueError, 'push destination differs'):
            publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        self.assertEqual(self.command('git', 'for-each-ref', cwd=unintended), '')

    def test_inherited_follow_tags_cannot_publish_unrequested_tags(self):
        publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook',
                          export_only=True)
        self.command('git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                     'tag', '-a', 'local-only', 'alpine-oldbook', '-m', 'Keep local', cwd=self.mirror)
        self.command('git', 'config', 'push.followTags', 'true', cwd=self.mirror)
        publisher.publish(self.checkout, self.mirror, str(self.remote), 'alpine-oldbook')
        self.assertEqual(self.command('git', 'tag', '--list', cwd=self.remote), '')

    def test_mirror_symlink_into_checkout_is_rejected(self):
        alias = self.root / 'mirror-alias'
        destination = self.checkout / 'nested-mirror'
        alias.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'mirror separate'):
            publisher.publish(self.checkout, alias, str(self.remote), 'alpine-oldbook')
        self.assertFalse(destination.exists())

    def test_scheduled_retry_skips_network_only_after_verified_publication(self):
        state = self.root / 'scheduler-state'
        unavailable = self.root / 'remote-offline.git'
        self.remote.rename(unavailable)
        self.assertEqual(publisher.scheduled(self.checkout, self.mirror,
                         str(self.remote), 'alpine-oldbook', state), 1)
        self.assertEqual(json.loads((state / 'status.json').read_text())['status'], 'error')
        unavailable.rename(self.remote)
        self.assertEqual(publisher.scheduled(self.checkout, self.mirror,
                         str(self.remote), 'alpine-oldbook', state), 0)
        first = self.command('git', 'rev-parse', 'alpine-oldbook', cwd=self.remote).strip()
        self.assertEqual(json.loads((state / 'status.json').read_text())['commit'], first)
        self.remote.rename(unavailable)
        # A confirmed unchanged commit needs no network, even with the remote offline.
        self.assertEqual(publisher.scheduled(self.checkout, self.mirror,
                         str(self.remote), 'alpine-oldbook', state), 0)
        (self.checkout / 'config').write_text('new committed setup\n')
        self.command('fossil', 'commit', '--nosync', '--no-warnings', '-m', 'Next setup')
        self.assertEqual(publisher.scheduled(self.checkout, self.mirror,
                         str(self.remote), 'alpine-oldbook', state), 1)
        unavailable.rename(self.remote)
        self.assertEqual(publisher.scheduled(self.checkout, self.mirror,
                         str(self.remote), 'alpine-oldbook', state), 0)
        self.assertEqual(self.command('git', 'show', 'alpine-oldbook:config', cwd=self.remote),
                         'new committed setup\n')
        self.assertEqual((state / 'status.json').stat().st_mode & 0o777, 0o600)

    def test_busy_mirror_is_skipped_without_exporting_or_pushing(self):
        lock = self.root / '.mirror.publish.lock'
        with lock.open('w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIsNone(publisher.publish(self.checkout, self.mirror,
                              str(self.remote), 'alpine-oldbook'))
        self.assertFalse(self.mirror.exists())
        self.assertEqual(self.command('git', 'for-each-ref', cwd=self.remote), '')

    def test_scheduled_log_rotation_preserves_recent_failure_and_previous_log(self):
        state = self.root / 'scheduler-state'
        state.mkdir()
        (state / 'sync.log').write_text('x' * (1024 * 1024 + 1))
        shutil.rmtree(self.remote)
        self.assertEqual(publisher.scheduled(self.checkout, self.mirror,
                         str(self.remote), 'alpine-oldbook', state), 1)
        self.assertTrue((state / 'sync.log.1').exists())
        self.assertLess((state / 'sync.log').stat().st_size, 1024 * 1024)
        self.assertIn('error', (state / 'sync.log').read_text().lower())

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
