"""Application identity tests use disposable process and tmux snapshots."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

LIB = Path(__file__).resolve().parents[1] / 'desktop/.local/lib'
sys.path.insert(0, str(LIB))

from oldbook.app_identity import ApplicationResolver


class TmuxRunner:
    def __init__(self, clients='', panes=''):
        self.clients = clients
        self.panes = panes
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[1] == 'list-clients':
            return self.clients
        if argv[1] == 'list-panes':
            return self.panes
        raise AssertionError(f'unexpected command: {argv!r}')


class ApplicationResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-proc-test-')
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name)

    def process(self, pid, comm, ppid=1, pgrp=None, tty=0, tpgid=-1):
        pgrp = pid if pgrp is None else pgrp
        node = self.proc / str(pid)
        node.mkdir()
        (node / 'comm').write_text(comm + '\n')
        (node / 'stat').write_text(
            f'{pid} ({comm}) S {ppid} {pgrp} {pgrp} {tty} {tpgid} 0\n')

    def resolver(self, runner=None):
        return ApplicationResolver(
            proc_root=self.proc,
            command_runner=runner or TmuxRunner(),
            uid=os.getuid(),
        )

    def test_terminal_uses_foreground_process_and_ignores_background_codex(self):
        self.process(100, 'foot')
        self.process(101, 'sh', ppid=100, tty=34818, tpgid=102)
        self.process(102, 'btop', ppid=101, pgrp=102, tty=34818, tpgid=102)
        self.process(103, 'codex', ppid=101, pgrp=103, tty=34818, tpgid=102)

        result = self.resolver().resolve_all([
            {'id': 5, 'pid': 100, 'app_id': 'foot', 'name': 'foot'},
        ])

        self.assertEqual(result, {
            5: {'name': 'btop', 'kind': 'app', 'state': None},
        })

    def test_tmux_uses_largest_pane_in_clients_displayed_window(self):
        self.process(100, 'foot')
        self.process(101, 'sh', ppid=100, tty=34818, tpgid=110)
        self.process(110, 'tmux: client', ppid=101, tty=34818, tpgid=110)
        runner = TmuxRunner(
            clients='110\t$0\t@0\n',
            panes=(
                '$0\t@0\t0\t%1\t1001\t/dev/pts/1\tnvim\t80\t40\t1\toldbook\n'
                '$0\t@0\t0\t%2\t1002\t/dev/pts/2\tcodex\t120\t40\t0\t'
                r'\⠸\ jack\ \|\ codex\ \|\ ~/.files\ \|\ Working\ \|\ Context\ 22\%\ left'
                '\n'
                '$0\t@1\t0\t%3\t1003\t/dev/pts/3\tcodex\t200\t60\t1\t'
                r'\⠸\ hidden\ \|\ codex\ \|\ /tmp\ \|\ Working'
                '\n'
                '$9\t@9\t0\t%9\t1009\t/dev/pts/9\tcodex\t300\t80\t1\t'
                r'\⠸\ detached\ \|\ codex\ \|\ /tmp\ \|\ Working'
                '\n'
            ),
        )

        result = self.resolver(runner).resolve_all([
            {'id': 5, 'pid': 100, 'app_id': 'foot', 'name': 'foot'},
        ])

        self.assertEqual(result, {
            5: {
                'name': 'Codex',
                'kind': 'codex',
                'state': 'Working',
                'tmux_pane': '%2',
                'tty': '/dev/pts/2',
            },
        })

    def test_tmux_zoom_uses_active_pane_even_if_fixture_reports_smaller_geometry(self):
        self.process(100, 'foot')
        self.process(110, 'tmux: client', ppid=100, tty=34818, tpgid=110)
        runner = TmuxRunner(
            clients='110\t$0\t@0\n',
            panes=(
                '$0\t@0\t1\t%1\t1001\t/dev/pts/1\tnvim\t80\t30\t1\toldbook\n'
                '$0\t@0\t1\t%2\t1002\t/dev/pts/2\tcodex\t200\t60\t0\t'
                r'\⠸\ jack\ \|\ codex\ \|\ ~\ \|\ Working'
                '\n'
            ),
        )

        result = self.resolver(runner).resolve_all([
            {'id': 5, 'pid': 100, 'app_id': 'foot', 'name': 'foot'},
        ])

        self.assertEqual(result[5], {
            'name': 'Neovim',
            'kind': 'app',
            'state': None,
            'tmux_pane': '%1',
            'tty': '/dev/pts/1',
        })

    def test_tmux_title_with_encoded_newline_cannot_inject_codex_state(self):
        self.process(100, 'foot')
        self.process(110, 'tmux: client', ppid=100, tty=34818, tpgid=110)
        runner = TmuxRunner(
            clients='110\t$0\t@0\n',
            panes=(
                '$0\t@0\t0\t%2\t1002\t/dev/pts/2\tcodex\t120\t40\t1\t'
                r'jack\ \|\ codex\ \|\ ~\ \|\ Working\nsecret\ \|\ Context\ 22\%\ left'
                '\n'
            ),
        )

        result = self.resolver(runner).resolve_all([
            {'id': 5, 'pid': 100, 'app_id': 'foot', 'name': 'foot'},
        ])

        self.assertEqual(result[5]['name'], 'Codex')
        self.assertIsNone(result[5]['state'])
        self.assertNotRegex(str(result[5]), r'[\x00-\x1f\x7f]')

    def test_tmux_is_queried_once_per_snapshot_instead_of_per_terminal(self):
        self.process(100, 'foot')
        self.process(200, 'foot')
        runner = TmuxRunner()

        result = self.resolver(runner).resolve_all([
            {'id': 5, 'pid': 100, 'app_id': 'foot', 'name': 'foot'},
            {'id': 6, 'pid': 200, 'app_id': 'foot', 'name': 'foot'},
        ])

        self.assertEqual(result[5]['name'], 'Foot')
        self.assertEqual(result[6]['name'], 'Foot')
        self.assertEqual(len(runner.calls), 2)
        self.assertTrue(all(call[0] == 'tmux' for call in runner.calls))

    def test_browser_chatgpt_requires_a_clear_app_or_title_signal(self):
        result = self.resolver().resolve_all([
            {'id': 1, 'pid': 10, 'app_id': 'firefox', 'name': 'ChatGPT — Mozilla Firefox'},
            {'id': 2, 'pid': 11, 'app_id': 'firefox', 'name': 'Private project — Mozilla Firefox'},
            {'id': 3, 'pid': 12, 'app_id': 'com.openai.chatgpt', 'name': 'OpenAI'},
            {'id': 4, 'pid': 13, 'app_id': 'chromium', 'name': 'Docs — Chromium'},
        ])

        self.assertEqual(result, {
            1: {'name': 'ChatGPT', 'kind': 'chatgpt', 'state': None},
            2: {'name': 'Firefox', 'kind': 'app', 'state': None},
            3: {'name': 'ChatGPT', 'kind': 'chatgpt', 'state': None},
            4: {'name': 'Chromium', 'kind': 'app', 'state': None},
        })

    def test_native_codex_title_supplies_state_but_process_name_alone_does_not(self):
        self.process(100, 'foot')
        self.process(101, 'codex', ppid=100, pgrp=101, tty=34818, tpgid=101)

        result = self.resolver().resolve_all([
            {
                'id': 5,
                'pid': 100,
                'app_id': 'foot',
                'name': '⠸ jack | codex | ~/.files | Working | main | Context 22% left',
            },
            {'id': 6, 'pid': 101, 'app_id': 'codex', 'name': 'codex'},
        ])

        self.assertEqual(result[5], {
            'name': 'Codex', 'kind': 'codex', 'state': 'Working', 'tty': '/dev/pts/2'})
        self.assertEqual(result[6], {
            'name': 'Codex', 'kind': 'codex', 'state': None, 'tty': '/dev/pts/2'})

    def test_codex_launcher_app_id_uses_foreground_descendant_tty(self):
        self.process(200, 'foot')
        self.process(201, 'codex', ppid=200, pgrp=201, tty=34821, tpgid=201)

        result = self.resolver().resolve_all([
            {'id': 7, 'pid': 200, 'app_id': 'codex', 'name': 'Codex'},
        ])

        self.assertEqual(result[7], {
            'name': 'Codex', 'kind': 'codex', 'state': None, 'tty': '/dev/pts/5'})

    def test_ghostty_resolves_foreground_codex_and_claude(self):
        self.process(300, 'ghostty')
        self.process(301, 'codex', ppid=300, pgrp=301, tty=34822, tpgid=301)
        self.process(400, 'ghostty')
        self.process(401, 'claude', ppid=400, pgrp=401, tty=34823, tpgid=401)

        result = self.resolver().resolve_all([
            {'id': 8, 'pid': 300, 'app_id': 'com.mitchellh.ghostty', 'name': 'Codex'},
            {'id': 9, 'pid': 400, 'app_id': 'com.mitchellh.ghostty', 'name': 'Claude'},
        ])

        self.assertEqual(result[8], {
            'name': 'Codex', 'kind': 'codex', 'state': None, 'tty': '/dev/pts/6'})
        self.assertEqual(result[9], {
            'name': 'Claude', 'kind': 'claude', 'state': None, 'tty': '/dev/pts/7'})

    def test_browser_claude_requires_a_clear_title_signal(self):
        result = self.resolver().resolve_all([
            {'id': 10, 'pid': 10, 'app_id': 'firefox', 'name': 'Claude — Mozilla Firefox'},
            {'id': 11, 'pid': 11, 'app_id': 'firefox', 'name': 'Private project — Firefox'},
        ])

        self.assertEqual(result[10], {'name': 'Claude', 'kind': 'claude', 'state': None})
        self.assertEqual(result[11], {'name': 'Firefox', 'kind': 'app', 'state': None})

    def test_control_characters_are_removed_and_missing_pids_are_harmless(self):
        result = self.resolver().resolve_all([
            {'id': 1, 'pid': 999999, 'app_id': 'foot', 'name': 'secret prompt\npassword'},
            {'id': 2, 'pid': 999998, 'app_id': 'odd\n\tapplication', 'name': 'ignored title'},
        ])

        self.assertEqual(result[1], {'name': 'Foot', 'kind': 'app', 'state': None})
        self.assertEqual(result[2], {'name': 'odd application', 'kind': 'app', 'state': None})
        for identity in result.values():
            self.assertNotRegex(identity['name'], r'[\x00-\x1f\x7f]')


if __name__ == '__main__':
    unittest.main()
