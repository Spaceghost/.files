import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO / 'alpine/bin/bootstrap-fossil-from-github'


class FossilBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mbp-intel-fossil-bootstrap-')
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source.git'
        self.repository = self.root / 'files.fossil'
        self.checkout = self.root / 'checkout'
        self.git('init', '-q', '-b', 'base', str(self.source), cwd=self.root)
        self.git('config', 'user.name', 'Bootstrap Test', cwd=self.source)
        self.git('config', 'user.email', 'bootstrap@example.invalid', cwd=self.source)
        (self.source / 'README.md').write_text('base\n')
        executable = self.source / 'hello'
        executable.write_text('#!/bin/sh\necho hello\n')
        executable.chmod(0o755)
        self.git('add', 'README.md', 'hello', cwd=self.source)
        self.git('commit', '-q', '-m', 'base', cwd=self.source)
        self.git('checkout', '-q', '-b', 'alpine-oldbook', cwd=self.source)
        (self.source / 'branch.txt').write_text('alpine\n')
        self.git('add', 'branch.txt', cwd=self.source)
        self.git('commit', '-q', '-m', 'alpine', cwd=self.source)

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *arguments, cwd):
        subprocess.run(['git', *arguments], cwd=cwd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    def bootstrap(self, *extra):
        return subprocess.run([
            str(BOOTSTRAP), '--source', str(self.source),
            '--repository', str(self.repository), '--checkout', str(self.checkout),
            *extra,
        ], capture_output=True, text=True, timeout=30)

    def test_bootstrap_command_is_executable(self):
        self.assertTrue(BOOTSTRAP.is_file())
        self.assertTrue(os.access(BOOTSTRAP, os.X_OK))

    def test_help_documents_safe_defaults(self):
        result = subprocess.run([str(BOOTSTRAP), '--help'], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('https://github.com/Spaceghost/.files.git', result.stdout)
        self.assertIn('alpine-oldbook', result.stdout)
        self.assertIn('--repository', result.stdout)
        self.assertIn('--checkout', result.stdout)

    def test_imports_git_history_and_opens_requested_branch(self):
        result = self.bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.repository.is_file())
        self.assertEqual(stat.S_IMODE(self.repository.stat().st_mode), 0o600)
        self.assertEqual((self.checkout / 'README.md').read_text(), 'base\n')
        self.assertEqual((self.checkout / 'branch.txt').read_text(), 'alpine\n')
        self.assertTrue((self.checkout / 'hello').stat().st_mode & stat.S_IXUSR)
        branch = subprocess.run(['fossil', 'branch', 'current'], cwd=self.checkout,
                                capture_output=True, text=True, check=True)
        self.assertEqual(branch.stdout.strip(), 'alpine-oldbook')
        info = subprocess.run(['fossil', 'info', '-R', str(self.repository)],
                              capture_output=True, text=True, check=True)
        self.assertIn('check-ins:    2', info.stdout)
        self.assertIn('new Fossil identity', result.stdout)

    def test_refuses_an_existing_repository_or_checkout(self):
        for existing in ('repository', 'checkout'):
            with self.subTest(existing=existing):
                repository = self.root / (existing + '.fossil')
                checkout = self.root / (existing + '-checkout')
                if existing == 'repository':
                    repository.write_text('keep repository\n')
                else:
                    checkout.mkdir()
                    (checkout / 'keep').write_text('keep checkout\n')
                result = subprocess.run([
                    str(BOOTSTRAP), '--source', str(self.source),
                    '--repository', str(repository), '--checkout', str(checkout),
                ], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('already exists', result.stderr)
                if existing == 'repository':
                    self.assertEqual(repository.read_text(), 'keep repository\n')
                    self.assertFalse(checkout.exists())
                else:
                    self.assertFalse(repository.exists())
                    self.assertEqual((checkout / 'keep').read_text(), 'keep checkout\n')

    def test_failure_removes_partial_repository_and_checkout(self):
        result = self.bootstrap('--branch', 'missing-branch')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing-branch', result.stderr)
        self.assertFalse(self.repository.exists())
        self.assertFalse(self.checkout.exists())


if __name__ == '__main__':
    unittest.main()
