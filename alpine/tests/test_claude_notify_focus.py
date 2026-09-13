"""Clicking a Claude notification lands on the session that sent it, tmux included."""
import json
import os
from pathlib import Path
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-claude-notify-focus'
CLOSE_CALL = ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.Notifications',
             '--object-path', '/org/freedesktop/Notifications', '--method',
             'org.freedesktop.Notifications.CloseNotification']


def record(**extra):
    now = int(time.time())
    base = {'version': 1, 'event': 'attention', 'observed_at': now,
            'valid_until': now + 300, 'tmux_pane': None, 'cwd': None,
            'tty': None, 'id': None}
    base.update(extra)
    return base


class FakeResolver:
    """Stands in for app_identity.ApplicationResolver: no /proc, no real tmux."""

    def __init__(self, identities):
        self.identities = identities

    def resolve_all(self, windows):
        return {window['id']: self.identities[window['id']] for window in windows
               if window['id'] in self.identities}


def window(identifier):
    return {'id': identifier, 'app_id': 'foot', 'name': '', 'nodes': [], 'floating_nodes': []}


@unittest.skipUnless(HELPER.is_file(), 'click handler implementation is missing')
class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(HELPER))
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-claude-focus-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)

    def write_record(self, session_hash, document):
        events = self.runtime / 'oldbook/claude-events'
        events.mkdir(parents=True, mode=0o700, exist_ok=True)
        path = events / f'{session_hash}.json'
        path.write_text(json.dumps(document))
        path.chmod(0o600)
        return path


class ChooseRecordTests(ModuleTests):
    def test_the_swaync_id_wins_when_it_matches_a_live_record(self):
        self.write_record('a' * 64, record(id=1))
        self.write_record('b' * 64, record(id=2, observed_at=int(time.time()) + 1))
        path, document = self.module['choose_record'](self.runtime, 2)
        self.assertEqual(document['id'], 2)
        self.assertEqual(path.name, 'b' * 64 + '.json')

    def test_an_id_matching_nothing_falls_back_to_the_newest_live_record(self):
        self.write_record('a' * 64, record(id=1, observed_at=100))
        self.write_record('b' * 64, record(id=2, observed_at=200))
        path, document = self.module['choose_record'](self.runtime, 999)
        self.assertEqual(document['id'], 2)

    def test_no_id_falls_back_to_the_newest_live_record(self):
        self.write_record('a' * 64, record(id=1, observed_at=100))
        self.write_record('b' * 64, record(id=2, observed_at=200))
        path, document = self.module['choose_record'](self.runtime, None)
        self.assertEqual(document['id'], 2)

    def test_an_expired_record_is_never_chosen(self):
        now = int(time.time())
        self.write_record('a' * 64, record(id=1, observed_at=now - 400, valid_until=now - 100))
        path, document = self.module['choose_record'](self.runtime, None)
        self.assertIsNone(document)

    def test_no_records_at_all_is_a_clean_miss(self):
        path, document = self.module['choose_record'](self.runtime, 5)
        self.assertIsNone(path)
        self.assertIsNone(document)


class MatchingWindowTests(ModuleTests):
    def test_a_controlling_tty_match_wins_even_with_a_pane_present(self):
        tree = {'id': 1, 'nodes': [window(11), window(12)], 'floating_nodes': []}
        resolver = FakeResolver({
            11: {'kind': 'claude', 'tty': '/dev/pts/3', 'tmux_pane': '%1'},
            12: {'kind': 'claude', 'tty': '/dev/pts/9', 'tmux_pane': '%2'},
        })
        found = self.module['matching_window'](
            tree, resolver, record(tty='/dev/pts/9', tmux_pane='%1'))
        self.assertEqual(found, 12)

    def test_a_tmux_pane_match_is_used_when_no_tty_is_recorded(self):
        tree = {'id': 1, 'nodes': [window(11)], 'floating_nodes': []}
        resolver = FakeResolver({11: {'kind': 'claude', 'tty': None, 'tmux_pane': '%7'}})
        found = self.module['matching_window'](tree, resolver, record(tmux_pane='%7'))
        self.assertEqual(found, 11)

    def test_a_non_claude_window_is_never_a_match(self):
        tree = {'id': 1, 'nodes': [window(11)], 'floating_nodes': []}
        resolver = FakeResolver({11: {'kind': 'app', 'tty': '/dev/pts/3', 'tmux_pane': None}})
        found = self.module['matching_window'](tree, resolver, record(tty='/dev/pts/3'))
        self.assertIsNone(found)

    def test_nothing_recorded_to_match_on_is_a_clean_miss(self):
        tree = {'id': 1, 'nodes': [window(11)], 'floating_nodes': []}
        resolver = FakeResolver({11: {'kind': 'claude', 'tty': None, 'tmux_pane': None}})
        self.assertIsNone(self.module['matching_window'](tree, resolver, record()))


class CloseTests(ModuleTests):
    def test_a_recorded_id_is_closed_and_the_file_is_deleted(self):
        path = self.write_record('a' * 64, record(id=7))
        calls = []
        self.module['close'](path, record(id=7),
                             runner=lambda argv, **kw: calls.append(argv))
        self.assertEqual(calls, [[*CLOSE_CALL, '7']])
        self.assertFalse(path.exists())

    def test_no_id_still_deletes_the_file_without_calling_gdbus(self):
        path = self.write_record('a' * 64, record(id=None))
        calls = []
        self.module['close'](path, record(id=None),
                             runner=lambda argv, **kw: calls.append(argv))
        self.assertEqual(calls, [])
        self.assertFalse(path.exists())


class AttachTests(ModuleTests):
    def test_it_opens_the_configured_terminal_attached_to_that_session(self):
        document = {'terminal': ['foot', '--app-id=oldbook-agent', '--title={title}', '-e']}
        calls = []

        def fake_popen(command, **kwargs):
            calls.append((command, kwargs))
        self.module['attach']('agent-claude', document=document, popen=fake_popen)
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertEqual(command, ['foot', '--app-id=oldbook-agent', '--title=agent-claude',
                                   '-e', 'tmux', 'attach-session', '-t', 'agent-claude'])
        self.assertTrue(kwargs.get('start_new_session'))


@unittest.skipUnless(shutil.which('tmux'), 'tmux is required for these tests')
class TmuxBackedTests(ModuleTests):
    """A real, disposable tmux server -- never Jack's own sessions."""

    def setUp(self):
        super().setUp()
        self.tmux_root = self.root / 'tmux'
        self.tmux_root.mkdir()
        self.tmux_env = dict(os.environ, TMUX_TMPDIR=str(self.tmux_root))
        self.addCleanup(self.kill_server)

    def kill_server(self):
        subprocess.run(['tmux', 'kill-server'], env=self.tmux_env,
                       capture_output=True, timeout=5)

    def tmux(self, *args):
        return subprocess.run(['tmux', *args], env=self.tmux_env,
                              capture_output=True, text=True, timeout=5)

    def pane_ids(self, session):
        result = self.tmux('list-panes', '-s', '-t', session, '-F', '#{pane_id}')
        return result.stdout.split()

    def test_session_for_pane_finds_the_session_that_owns_it(self):
        self.tmux('new-session', '-d', '-s', 'agent-claude', '-x', '80', '-y', '24')
        self.addCleanup(lambda: self.tmux('kill-session', '-t', 'agent-claude'))
        pane = self.pane_ids('agent-claude')[0]
        runner = lambda argv, **kw: subprocess.run(argv, env=self.tmux_env, **kw)
        self.assertEqual(self.module['session_for_pane'](pane, runner=runner), 'agent-claude')

    def test_an_unknown_pane_id_finds_no_session(self):
        runner = lambda argv, **kw: subprocess.run(argv, env=self.tmux_env, **kw)
        self.assertIsNone(self.module['session_for_pane']('%999999', runner=runner))

    def test_select_pane_brings_a_background_window_to_the_front(self):
        """The task this exists for: a pane sitting in a background window."""
        self.tmux('new-session', '-d', '-s', 'multi', '-x', '80', '-y', '24')
        self.addCleanup(lambda: self.tmux('kill-session', '-t', 'multi'))
        self.tmux('new-window', '-t', 'multi', '-d')
        panes = self.pane_ids('multi')
        self.assertEqual(len(panes), 2)
        background_pane = panes[1]
        # The session's active window starts on the first window, not the one
        # holding the pane a notification points at.
        active_before = self.tmux('display-message', '-p', '-t', 'multi',
                                  '-F', '#{pane_id}').stdout.strip()
        self.assertNotEqual(active_before, background_pane)
        runner = lambda argv, **kw: subprocess.run(argv, env=self.tmux_env, **kw)
        self.module['select_pane'](background_pane, runner=runner)
        active_after = self.tmux('display-message', '-p', '-t', 'multi',
                                 '-F', '#{pane_id}').stdout.strip()
        self.assertEqual(active_after, background_pane)

    def test_locate_focuses_a_window_the_resolver_already_sees(self):
        self.tmux('new-session', '-d', '-s', 'agent-claude', '-x', '80', '-y', '24')
        self.addCleanup(lambda: self.tmux('kill-session', '-t', 'agent-claude'))
        pane = self.pane_ids('agent-claude')[0]
        tree = {'id': 1, 'nodes': [window(11)], 'floating_nodes': []}
        resolver = FakeResolver({11: {'kind': 'claude', 'tty': None, 'tmux_pane': pane}})
        workspaces = {
            'find_socket': lambda runtime: 'fake-socket',
            'request': lambda sway, kind: tree,
        }
        plan = self.module['locate'](record(tmux_pane=pane), workspaces, self.runtime,
                                     resolver=resolver)
        self.assertEqual(plan, {'action': 'focus', 'sway': 'fake-socket', 'target': 11})

    def test_locate_falls_back_to_attaching_when_the_pane_is_not_on_any_window(self):
        self.tmux('new-session', '-d', '-s', 'agent-claude', '-x', '80', '-y', '24')
        self.addCleanup(lambda: self.tmux('kill-session', '-t', 'agent-claude'))
        pane = self.pane_ids('agent-claude')[0]

        def no_sway(runtime):
            raise RuntimeError('no owned Sway session socket')
        workspaces = {'find_socket': no_sway}
        with mock.patch.dict(os.environ, {'TMUX_TMPDIR': str(self.tmux_root)}):
            plan = self.module['locate'](record(tmux_pane=pane), workspaces, self.runtime,
                                         resolver=FakeResolver({}))
        self.assertEqual(plan, {'action': 'attach', 'session': 'agent-claude'})

    def test_locate_gives_up_cleanly_when_the_session_is_gone(self):
        workspaces = {'find_socket': lambda runtime: (_ for _ in ()).throw(
            RuntimeError('no owned Sway session socket'))}
        with mock.patch.dict(os.environ, {'TMUX_TMPDIR': str(self.tmux_root)}):
            plan = self.module['locate'](record(tmux_pane='%404'), workspaces, self.runtime,
                                         resolver=FakeResolver({}))
        self.assertEqual(plan, {'action': None})


if __name__ == '__main__':
    unittest.main()
