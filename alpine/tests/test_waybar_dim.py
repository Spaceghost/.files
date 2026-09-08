"""Fullscreen state tracking must survive transient IPC errors without global reloads."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'alpine/desktop/.local/bin/oldbook-waybar-dim'
EVENT = 1 << 31


def load_helper():
    loader = importlib.machinery.SourceFileLoader('waybar_dim', str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Connection:
    def __init__(self, events):
        self.events = iter([(2, {'success': True}), *events])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def connect(self, path):
        pass

    def settimeout(self, timeout):
        pass


class WaybarDimTests(unittest.TestCase):
    def setUp(self):
        self.module = load_helper()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sway = self.root / 'sway.sock'
        self.sway.touch()
        self.config = self.root / 'config/waybar'
        self.config.mkdir(parents=True)
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(os.environ, XDG_RUNTIME_DIR=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / 'config')).start()
        self.reload = mock.patch.object(self.module, 'reload_style').start()
        mock.patch('time.sleep').start()

    def run_events(self, events, fail_first=False):
        state = {'fullscreen': False, 'requests': 0}

        def receive(connection):
            kind, event = next(connection.events)
            if event.get('change') == 'fullscreen_mode':
                state['fullscreen'] = True
            return kind, event

        def request(path, kind):
            state['requests'] += 1
            if fail_first and state['requests'] == 1:
                raise TimeoutError('synthetic busy compositor')
            if kind == 1:
                return [{'name': '1: Test', 'visible': True}]
            return {'type': 'root', 'nodes': [
                {'type': 'workspace', 'name': '1: Test', 'nodes': [
                    {'type': 'con', 'fullscreen_mode': int(state['fullscreen']),
                     'nodes': [], 'floating_nodes': []}], 'floating_nodes': []}]}

        ipc = {'find_socket': lambda runtime: self.sway, 'send': lambda *args: None,
               'receive': receive, 'request': request}
        mock.patch.object(self.module.runpy, 'run_path', return_value=ipc).start()
        mock.patch.object(self.module.socket, 'socket',
                          side_effect=lambda *args: Connection(events)).start()
        error = None
        try:
            self.module.main()
        except (OSError, RuntimeError) as caught:
            error = caught
        self.assertIsNone(error, 'The helper must recover and process shutdown')
        return state

    def test_title_traffic_does_not_trigger_desktop_queries(self):
        events = [(EVENT | 3, {'change': 'title'}) for _ in range(30)]
        events += [(EVENT | 3, {'change': 'fullscreen_mode'}), (EVENT | 6, {})]
        state = self.run_events(events)
        self.assertEqual(state['requests'], 4)
        self.assertIn('opacity: 0.3', (self.config / 'waybar-state.css').read_text())
        self.reload.assert_not_called()

    def test_transient_snapshot_failure_reconnects_and_updates_state(self):
        state = self.run_events([(EVENT | 3, {'change': 'fullscreen_mode'}),
                                 (EVENT | 6, {})], fail_first=True)
        self.assertEqual(state['requests'], 5)
        self.assertIn('opacity: 0.3', (self.config / 'waybar-state.css').read_text())

    def test_reload_candidates_belong_to_current_wayland_session(self):
        proc = self.root / 'proc'
        proc.mkdir()
        for pid, display in [(101, 'wayland-main'), (102, 'wayland-preview')]:
            entry = proc / str(pid)
            entry.mkdir()
            (entry / 'cmdline').write_bytes(b'waybar\0')
            (entry / 'environ').write_bytes(
                f'XDG_RUNTIME_DIR={self.root}\0WAYLAND_DISPLAY={display}\0'.encode())
        with mock.patch.object(self.module, 'PROC_ROOT', proc, create=True), \
                mock.patch.dict(os.environ, WAYLAND_DISPLAY='wayland-main'):
            self.assertEqual(list(self.module.waybar_processes()), [101])


if __name__ == '__main__':
    unittest.main()
