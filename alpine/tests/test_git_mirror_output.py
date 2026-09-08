import contextlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader(
    'git_mirror_output_test', str(REPO / 'alpine/bin/publish-git-mirror'))
spec = importlib.util.spec_from_loader(loader.name, loader)
publisher = importlib.util.module_from_spec(spec)
loader.exec_module(publisher)


class CommandOutputTests(unittest.TestCase):
    def test_large_stdout_and_stderr_keep_bounded_recent_diagnostics(self):
        code = ('import sys; '
                'sys.stdout.write("x" * (2 * 1024 * 1024) + "stdout-end\\n"); '
                'sys.stderr.write("y" * (2 * 1024 * 1024) + "stderr-end\\n")')
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            result = publisher.run([sys.executable, '-c', code], REPO)
        for actual, ending in ((result.stdout, 'stdout-end\n'),
                               (result.stderr, 'stderr-end\n')):
            with self.subTest(ending=ending):
                self.assertLessEqual(len(actual.encode('utf-8')), 64 * 1024)
                self.assertIn('truncated', actual)
                self.assertTrue(actual.endswith(ending))
        self.assertEqual(output.getvalue(), result.stdout)
        self.assertEqual(error.getvalue(), result.stderr)

    def test_truncated_capture_fails_instead_of_returning_partial_git_data(self):
        code = 'import sys; sys.stdout.write("x" * (2 * 1024 * 1024))'
        with self.assertRaisesRegex(RuntimeError, 'captured stdout.*truncated'):
            publisher.run([sys.executable, '-c', code], REPO, capture=True)

    def test_failed_command_retains_recent_error_without_unbounded_exception(self):
        code = ('import sys; '
                'sys.stderr.write("x" * (2 * 1024 * 1024) + "failure-end\\n"); '
                'sys.exit(7)')
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                publisher.run([sys.executable, '-c', code], REPO)
        self.assertEqual(failure.exception.returncode, 7)
        self.assertLessEqual(len(failure.exception.stderr.encode('utf-8')), 64 * 1024)
        self.assertTrue(failure.exception.stderr.endswith('failure-end\n'))


class ScheduledLogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mirror-output-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / 'state'

    def scheduled(self):
        return publisher.scheduled(self.root, self.root / 'mirror',
                                   '/tmp/unused-output-test-remote', 'alpine-oldbook',
                                   self.state)

    def test_one_verbose_command_keeps_log_and_status_small(self):
        code = ('import sys; '
                'sys.stdout.write("x" * (2 * 1024 * 1024) + "command-end\\n")')

        def noisy_publish(*args, **kwargs):
            publisher.run([sys.executable, '-c', code], self.root)
            return 'verified-commit'

        with mock.patch.object(publisher, 'publish', side_effect=noisy_publish):
            self.assertEqual(self.scheduled(), 0)
        log = self.state / 'sync.log'
        self.assertLessEqual(log.stat().st_size, 1024 * 1024)
        self.assertIn('command-end', log.read_text())
        status = self.state / 'status.json'
        self.assertLess(status.stat().st_size, 8192)
        self.assertEqual(json.loads(status.read_text())['status'], 'ok')

    def test_writes_rotate_during_a_run_and_keep_two_bounded_utf8_logs(self):
        def noisy_publish(*args, **kwargs):
            print('\N{PURPLE HEART}' * (1024 * 1024))
            print('recent-end')
            return 'verified-commit'

        with mock.patch.object(publisher, 'publish', side_effect=noisy_publish):
            self.assertEqual(self.scheduled(), 0)
        for name in ('sync.log', 'sync.log.1'):
            with self.subTest(name=name):
                path = self.state / name
                self.assertTrue(path.exists())
                self.assertLessEqual(path.stat().st_size, 1024 * 1024)
                path.read_text()  # Rotation must not split a UTF-8 character.
        self.assertTrue((self.state / 'sync.log').read_text().endswith('recent-end\n'))
        self.assertEqual(len(list(self.state.glob('sync.log*'))), 2)

    def test_oversized_existing_logs_and_error_status_are_bounded(self):
        self.state.mkdir()
        for name in ('sync.log', 'sync.log.1'):
            (self.state / name).write_text('old-' * (512 * 1024) + 'previous-end\n')
        failure = RuntimeError('x' * (2 * 1024 * 1024) + 'failure-end')
        with mock.patch.object(publisher, 'publish', side_effect=failure):
            self.assertEqual(self.scheduled(), 1)
        for path in self.state.glob('sync.log*'):
            self.assertLessEqual(path.stat().st_size, 1024 * 1024)
        status = self.state / 'status.json'
        self.assertLess(status.stat().st_size, 8192)
        value = json.loads(status.read_text())
        self.assertEqual(value['status'], 'error')
        self.assertTrue(value['error'].endswith('failure-end'))
        self.assertIn('failure-end', (self.state / 'sync.log').read_text())


if __name__ == '__main__':
    unittest.main()
