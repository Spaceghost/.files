from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]


class PublicationMergeTests(unittest.TestCase):
    def test_publishing_preserves_remote_history_and_the_fossil_export_ref(self):
        api = runpy.run_path(str(REPO / 'alpine/bin/publish-git-mirror'))
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            mirror, remote = root / 'mirror', root / 'remote.git'
            subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
            subprocess.run(['git', 'init', '-q', str(mirror)], check=True)

            def git(*args):
                return subprocess.run(['git', *args], cwd=mirror, check=True,
                                      capture_output=True, text=True).stdout.strip()

            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            (mirror / 'base').write_text('base')
            git('add', 'base')
            git('commit', '-qm', 'base')
            git('branch', 'alpine-oldbook')
            (mirror / 'remote-only').write_text('preserve me')
            git('add', 'remote-only')
            git('commit', '-qm', 'remote addition')
            old_remote = git('rev-parse', 'HEAD')
            git('push', str(remote), 'HEAD:refs/heads/live')
            git('checkout', '-q', 'alpine-oldbook')
            (mirror / 'local-only').write_text('new work')
            git('add', 'local-only')
            git('commit', '-qm', 'local addition')
            export = git('rev-parse', 'HEAD')
            actual_run = api['run']

            def without_export(args, cwd, capture=False):
                if args[:3] == ['fossil', 'git', 'export']:
                    return subprocess.CompletedProcess(args, 0, '', '')
                return actual_run(args, cwd, capture)

            with patch.dict(api['publish_locked'].__globals__, {'run': without_export}):
                published = api['publish_locked'](mirror, mirror, str(remote),
                                                   'alpine-oldbook', False, False, 'live')
            self.assertEqual(git('rev-parse', 'alpine-oldbook'), export)
            self.assertEqual(git('show', published + ':remote-only'), 'preserve me')
            self.assertEqual(git('show', published + ':local-only'), 'new work')
            git('merge-base', '--is-ancestor', old_remote, published)
            self.assertEqual(git('ls-remote', str(remote), 'refs/heads/live').split()[0], published)


if __name__ == '__main__':
    unittest.main()
