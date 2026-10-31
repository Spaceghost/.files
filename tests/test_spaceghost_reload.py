"""Exercise live reload selection and retries without touching real sessions."""
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / '.bin' / 'spaceghost-reload'

class ReloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home, self.repo, self.state = root/'home', root/'repo', root/'state'
        self.bin = self.home/'.bin'
        self.bin.mkdir(parents=True)
        self.repo.mkdir()
        self.log = root/'calls'
        self.sock = root/'nvim.sock'
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(self.sock))
        self.addCleanup(sock.close)
        self.env = dict(os.environ, HOME=str(self.home), SPACEGHOST_SYNC_REPO=str(self.repo),
                        SPACEGHOST_SYNC_STATE=str(self.state), CALLS=str(self.log),
                        TEST_SOCKET=str(self.sock), TMUX_TMPDIR=str(root/'tmux'))
        self.command('nvim-session', 'echo "$TEST_SOCKET"')
        self.command('nvim', '''[ "$2" = "$TEST_SOCKET" ] || exit 1
        case "$*" in
          *"type(Spaceghost)"*) echo 1 ;;
          *) echo nvim >> "$CALLS"; if [ "${FAIL_NVIM:-0}" = 1 ]; then echo 'ERROR: test reload'; else echo reloaded; fi ;;
        esac''')
        self.command('tmux', 'exit 0')
        self.command('systemctl', 'exit 0')
        self.command('gdbus', '''case "$*" in
          *NameHasOwner*) echo "(${GHOSTTY_OWNER:-false},)" ;;
          *) echo ghostty >> "$CALLS" ;;
        esac''')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Reload Test')
        self.git('config', 'user.email', 'reload@example.test')
        self.commit('.config/nvim/init.lua', '-- initial')

    def command(self, name, body):
        p = self.bin/name
        p.write_text('#!/bin/sh\nset -eu\n'+body+'\n')
        p.chmod(0o755)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, name, text):
        p = self.repo/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.git('add', name)
        self.git('commit', '-qm', 'test config')

    def run_reload(self, **env):
        return subprocess.run([str(SCRIPT)], env=dict(self.env, **env),
                              capture_output=True, text=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_reloads_existing_editor_only_when_its_config_changes(self):
        self.assertEqual(self.run_reload().returncode, 0)
        self.assertEqual(self.calls(), ['nvim'])
        self.assertEqual(self.run_reload().returncode, 0)
        self.assertEqual(self.calls(), ['nvim'])
        self.commit('docs/note', 'unrelated')
        self.assertEqual(self.run_reload().returncode, 0)
        self.assertEqual(self.calls(), ['nvim'])
        self.commit('.config/nvim/init.lua', '-- changed')
        self.assertEqual(self.run_reload().returncode, 0)
        self.assertEqual(self.calls(), ['nvim', 'nvim'])

    def test_failed_editor_reload_retries_without_blocking_other_apps(self):
        self.assertNotEqual(self.run_reload(FAIL_NVIM='1', GHOSTTY_OWNER='true').returncode, 0)
        self.assertFalse((self.state/'reloaded-nvim').exists())
        self.assertTrue((self.state/'reloaded-ghostty').exists())
        self.assertEqual(self.calls(), ['nvim', 'ghostty'])
        self.assertEqual(self.run_reload(GHOSTTY_OWNER='true').returncode, 0)
        self.assertEqual(self.calls(), ['nvim', 'ghostty', 'nvim'])

    def test_missing_previous_commit_reloads_instead_of_silently_skipping(self):
        self.run_reload()
        (self.state/'reloaded-nvim').write_text('0'*40+'\n')
        self.assertEqual(self.run_reload().returncode, 0)
        self.assertEqual(self.calls(), ['nvim', 'nvim'])

    def test_stale_and_unmanaged_editor_sockets_are_left_alone(self):
        self.command('nvim', 'echo 0')
        self.assertEqual(self.run_reload().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_reloads_each_existing_tmux_server(self):
        folder = Path(self.env['TMUX_TMPDIR']) / ('tmux-' + str(os.getuid()))
        folder.mkdir(parents=True)
        for name in ('default', 'other'):
            sock = socket.socket(socket.AF_UNIX)
            sock.bind(str(folder/name))
            self.addCleanup(sock.close)
        self.commit('.tmux.conf', 'set -g mouse on')
        self.command('tmux', 'if [ "$3" = source-file ]; then echo "tmux:$2:$4" >> "$CALLS"; fi')
        self.assertEqual(self.run_reload().returncode, 0)
        calls = [line for line in self.calls() if line.startswith('tmux:')]
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(line.endswith(str(self.repo/'.tmux.conf')) for line in calls))

    def test_busy_editor_socket_retries_instead_of_marking_success(self):
        self.command('nvim', 'exit 124')
        self.assertNotEqual(self.run_reload().returncode, 0)
        self.assertFalse((self.state/'reloaded-nvim').exists())

    def test_absent_ghostty_is_not_launched(self):
        self.assertEqual(self.run_reload(GHOSTTY_OWNER='false').returncode, 0)
        self.assertNotIn('ghostty', self.calls())

if __name__ == '__main__':
    unittest.main()
