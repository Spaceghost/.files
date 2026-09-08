"""STRATA stays in workspace ten without competing with ordinary Firefox."""
import importlib.machinery
import importlib.util
import fcntl
import errno
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-strata'
loader = importlib.machinery.SourceFileLoader('strata_service', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
strata = importlib.util.module_from_spec(spec)
loader.exec_module(strata)


def tree(number=10, app='oldbook-strata'):
    return {'nodes': [{'type': 'workspace', 'num': number, 'name': f'{number}: STRATA',
                      'nodes': [{'id': 17, 'app_id': app, 'type': 'con'}]}]}


class BackoffTests(unittest.TestCase):
    def test_restart_delays_increase_and_remain_bounded(self):
        retry = strata.Backoff()
        delays = []
        for now in range(10):
            retry.failed(now)
            delays.append(retry.next_attempt - now)
        self.assertEqual(delays[:4], [1, 2, 4, 8])
        self.assertLessEqual(max(delays), 30)

    def test_healthy_service_resets_backoff_only_after_stability(self):
        retry = strata.Backoff()
        retry.failed(0)
        retry.failed(1)
        retry.healthy(10)
        retry.failed(11)
        self.assertEqual(retry.next_attempt, 15)
        retry.healthy(20)
        retry.healthy(51)
        retry.failed(52)
        self.assertEqual(retry.next_attempt, 53)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.service = strata.StrataService(self.directory, Path('/private/sway.sock'), None)
        self.ready = patch.object(strata, 'server_ready', return_value=True).start()
        self.command = patch.dict(strata.IPC, {'command': Mock()})
        self.command.start()
        self.addCleanup(patch.stopall)
        self.browser = Mock()
        self.browser.poll.return_value = None
        self.service.start_browser = Mock(return_value=self.browser)
        self.service.start_server = Mock(return_value=Mock(poll=Mock(return_value=None)))

    def test_adopts_and_pins_only_the_dedicated_window_without_focus(self):
        data = tree(6)
        data['nodes'][0]['nodes'].append({'id': 99, 'type': 'con', 'app_id': 'firefox'})
        self.service.tick(data, 0)
        self.service.start_browser.assert_not_called()
        strata.IPC['command'].assert_called_once_with(
            Path('/private/sway.sock'), '[con_id=17] move container to workspace number "10: Strata"')
        self.service.tick(tree(10), 1)
        self.assertEqual(strata.IPC['command'].call_count, 1)

    def test_scratchpad_is_not_a_way_to_lose_the_review_window(self):
        data = tree(-1)
        data['nodes'][0]['name'] = '__i3_scratch'
        self.service.tick(data, 0)
        strata.IPC['command'].assert_called_once()

    def test_starting_browser_is_not_duplicated_before_its_window_maps(self):
        self.service.tick({'nodes': []}, 0)
        self.service.tick({'nodes': []}, 1)
        self.service.start_browser.assert_called_once()
        self.service.tick(tree(10), 2)
        self.service.tick(tree(10), 3)
        self.service.start_browser.assert_called_once()

    def test_closed_window_restarts_after_backoff(self):
        self.service.tick(tree(10), 0)
        self.service.tick({'nodes': []}, 1)
        self.service.start_browser.assert_not_called()
        self.service.tick({'nodes': []}, 2)
        self.service.start_browser.assert_called_once()

    def test_crashed_browser_retries_without_a_tight_loop(self):
        self.service.tick({'nodes': []}, 0)
        self.browser.poll.return_value = 1
        self.service.tick({'nodes': []}, 1)
        self.service.tick({'nodes': []}, 1.5)
        self.service.start_browser.assert_called_once()
        self.service.tick({'nodes': []}, 2)
        self.assertEqual(self.service.start_browser.call_count, 2)

    def test_server_failure_delays_browser_and_retries_server_once(self):
        self.ready.return_value = False
        self.service.tick({'nodes': []}, 0)
        self.service.tick({'nodes': []}, 1)
        self.service.start_server.assert_called_once()
        self.service.start_browser.assert_not_called()
        self.service.server.poll.return_value = 1
        self.service.tick({'nodes': []}, 2)
        self.service.tick({'nodes': []}, 2.5)
        self.service.start_server.assert_called_once()
        self.service.tick({'nodes': []}, 3)
        self.assertEqual(self.service.start_server.call_count, 2)

    def test_failed_browser_exec_keeps_service_alive_and_waits_before_retry(self):
        self.service.start_browser.side_effect = FileNotFoundError('browser unavailable')
        self.service.tick({'nodes': []}, 0)
        self.service.tick({'nodes': []}, .5)
        self.service.start_browser.assert_called_once()
        self.service.tick({'nodes': []}, 1)
        self.assertEqual(self.service.start_browser.call_count, 2)

    def test_failed_server_exec_keeps_service_alive_and_waits_before_retry(self):
        self.ready.return_value = False
        self.service.start_server.side_effect = OSError('temporarily out of resources')
        self.service.tick({'nodes': []}, 0)
        self.service.tick({'nodes': []}, .5)
        self.service.start_server.assert_called_once()

    def test_stop_waits_and_kills_an_unresponsive_owned_child(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('firefox', 3), 0]
        strata.stop_child(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.socket = Path('/private/sway.sock')

    def test_duplicate_daemon_does_not_create_another_service(self):
        with strata.daemon_lock(self.directory, self.socket).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(strata, 'StrataService') as service:
                strata.daemon(self.directory, self.socket, None)
            service.assert_not_called()

    def test_session_shutdown_stops_owned_server_and_browser(self):
        connection = Mock()
        context = Mock()
        context.__enter__ = Mock(return_value=connection)
        context.__exit__ = Mock(return_value=False)
        service = Mock()
        messages = Mock(side_effect=[(2, {'success': True}), ((1 << 31) | 6, {})])
        with patch.object(strata, 'StrataService', return_value=service), \
                patch.object(strata, 'session_identity', return_value=(1, 2), create=True), \
                patch.object(strata, 'peer_handle', return_value=None, create=True), \
                patch.object(strata.socket, 'socket', return_value=context), \
                patch.object(strata.signal, 'signal'), \
                patch.object(strata.select, 'select', return_value=([connection], [], [])), \
                patch.dict(strata.IPC, {'send': Mock(), 'receive': messages,
                                       'request': Mock(return_value=tree())}):
            strata.daemon(self.directory, self.socket, None)
        service.tick.assert_called_once()
        service.stop.assert_called_once()

    def test_transient_ipc_timeout_reconnects_without_replacing_service(self):
        connection = Mock()
        context = Mock()
        context.__enter__ = Mock(return_value=connection)
        context.__exit__ = Mock(return_value=False)
        service = Mock()
        messages = Mock(side_effect=[(2, {'success': True}), (2, {'success': True}),
                                    ((1 << 31) | 6, {})])
        request = Mock(side_effect=[TimeoutError('Sway is busy'), tree()])
        with patch.object(strata, 'StrataService', return_value=service) as create, \
                patch.object(strata, 'session_identity', return_value=(1, 2), create=True), \
                patch.object(strata, 'peer_handle', return_value=None, create=True), \
                patch.object(strata, 'wait_retry', create=True) as retry, \
                patch.object(strata.socket, 'socket', return_value=context), \
                patch.object(strata.signal, 'signal'), \
                patch.object(strata.select, 'select', return_value=([connection], [], [])), \
                patch.dict(strata.IPC, {'send': Mock(), 'receive': messages, 'request': request}):
            strata.daemon(self.directory, self.socket, None)
        create.assert_called_once()
        retry.assert_called_once()
        service.tick.assert_called_once()
        service.stop.assert_called_once()
        self.assertEqual(connection.connect.call_count, 2)

    def test_dead_compositor_stops_service_even_with_a_stale_socket(self):
        connection = Mock()
        context = Mock()
        context.__enter__ = Mock(return_value=connection)
        context.__exit__ = Mock(return_value=False)
        service = Mock()
        with patch.object(strata, 'StrataService', return_value=service), \
                patch.object(strata, 'session_identity', return_value=(1, 2)), \
                patch.object(strata, 'peer_handle', return_value=55, create=True), \
                patch.object(strata.socket, 'socket', return_value=context), \
                patch.object(strata.signal, 'signal'), \
                patch.object(strata.os, 'close') as close, \
                patch.object(strata.select, 'select', side_effect=[([55], [], [])]), \
                patch.dict(strata.IPC, {'send': Mock(), 'receive': Mock(return_value=(2, {'success': True})),
                                       'request': Mock(return_value=tree())}):
            strata.daemon(self.directory, self.socket, None)
        service.stop.assert_called_once()
        close.assert_called_once_with(55)

    def test_peer_handle_pins_the_compositors_authenticated_process(self):
        connection = Mock()
        connection.getsockopt.return_value = struct.pack('3i', 123, os.getuid(), os.getgid())
        with patch.object(strata.os, 'pidfd_open', return_value=55) as pin:
            self.assertEqual(strata.peer_handle(connection), 55)
        pin.assert_called_once_with(123)

    def test_peer_disappearing_before_pin_does_not_become_an_endless_retry(self):
        connection = Mock()
        connection.getsockopt.return_value = struct.pack('3i', 123, os.getuid(), os.getgid())
        with patch.object(strata.os, 'pidfd_open', side_effect=ProcessLookupError):
            with self.assertRaises(RuntimeError):
                strata.peer_handle(connection)

    def test_initial_refused_connection_exits_without_retrying_a_stale_socket(self):
        connection = Mock()
        connection.connect.side_effect = [ConnectionRefusedError(), AssertionError('Retried dead peer')]
        context = Mock()
        context.__enter__ = Mock(return_value=connection)
        context.__exit__ = Mock(return_value=False)
        service = Mock()
        with patch.object(strata, 'StrataService', return_value=service), \
                patch.object(strata, 'session_identity', return_value=(1, 2)), \
                patch.object(strata.socket, 'socket', return_value=context), \
                patch.object(strata.signal, 'signal'), \
                patch.object(strata, 'wait_retry') as retry:
            strata.daemon(self.directory, self.socket, None)
        service.tick.assert_not_called()
        service.stop.assert_called_once()
        retry.assert_not_called()

    def test_explicit_launch_reuses_daemon_and_focuses_workspace_ten_window(self):
        command = Mock()
        with patch.object(strata, 'daemon_running', return_value=True), \
                patch.object(strata.subprocess, 'Popen') as spawn, \
                patch.dict(strata.IPC, {'request': Mock(return_value=tree(6)), 'command': command}):
            strata.launch(self.directory, self.socket, None)
        spawn.assert_not_called()
        self.assertEqual([call.args[1] for call in command.call_args_list],
                         ['[con_id=17] move container to workspace number "10: Strata"', '[con_id=17] focus'])

    def test_explicit_launch_retries_busy_ipc_requests_and_commands(self):
        request = Mock(side_effect=[BlockingIOError(errno.EAGAIN, 'IPC backlog is full'), tree(), tree()])
        command = Mock(side_effect=[BlockingIOError(errno.EAGAIN, 'IPC backlog is full'), None, None])
        with patch.object(strata, 'daemon_running', return_value=True), \
                patch.object(strata.subprocess, 'Popen') as spawn, \
                patch.object(strata.time, 'sleep') as pause, \
                patch.dict(strata.IPC, {'request': request, 'command': command}):
            strata.launch(self.directory, self.socket, None)
        spawn.assert_not_called()
        self.assertEqual(request.call_count, 3)
        self.assertEqual(pause.call_count, 2)
        self.assertEqual(command.call_count, 3)
        self.assertEqual(command.call_args.args[1], '[con_id=17] focus')

    def test_busy_launcher_stops_at_deadline_with_a_helpful_error(self):
        with patch.object(strata, 'daemon_running', return_value=True), \
                patch.object(strata.time, 'monotonic', side_effect=[0, 0, 31]), \
                patch.object(strata.time, 'sleep'), \
                patch.dict(strata.IPC, {'request': Mock(side_effect=TimeoutError('Sway is busy'))}):
            with self.assertRaisesRegex(RuntimeError, 'strata.log'):
                strata.launch(self.directory, self.socket, None)

    def test_private_firefox_profile_and_exact_app_id_are_retained(self):
        service = strata.StrataService(self.directory, self.socket, None)
        with patch.dict(os.environ, {'HOME': str(self.directory),
                                     'XDG_RUNTIME_DIR': str(self.directory / 'run')}), \
                patch.object(strata.subprocess, 'Popen') as spawn:
            service.start_browser()
        arguments = spawn.call_args.args[0]
        self.assertEqual(arguments[:3], ['firefox', '--no-remote', '--profile'])
        self.assertEqual(arguments[3], str(self.directory / '.local/share/oldbook/strata-firefox'))
        self.assertEqual(spawn.call_args.kwargs['env']['MOZ_APP_REMOTINGNAME'], 'oldbook-strata')
        self.assertTrue(arguments[-1].startswith('http://127.0.0.1:'))

    def test_fossil_is_always_bound_to_loopback(self):
        process = Mock()
        process.poll.return_value = 1
        with patch.object(strata.subprocess, 'Popen', return_value=process) as spawn, \
                patch.object(strata.signal, 'signal'):
            with self.assertRaises(RuntimeError):
                strata.serve(self.directory, self.socket)
        self.assertEqual(spawn.call_args.args[0][:5],
                         ['fossil', 'ui', '--nobrowser', '--port', f'127.0.0.1:{strata.PORT}'])

    def test_port_override_rejects_unusable_values(self):
        for value in ('0', '-1', '65536', '127.0.0.1:8766', 'not a port'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                strata.port_number(value)
        self.assertEqual(strata.port_number('8766'), 8766)


if __name__ == '__main__':
    unittest.main()
