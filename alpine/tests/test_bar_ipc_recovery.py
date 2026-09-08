"""Exercise actual helper subprocesses against a disconnecting private IPC socket."""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / 'alpine/desktop/.local/bin'
HEADER = struct.Struct('=6sII')


class IpcFixture:
    def __init__(self, directory, failed_kind):
        self.path = directory / 'sway.sock'
        self.failed_kind = failed_kind
        self.failures = 0
        self.subscriptions = []
        self.running = True
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(self.path))
        self.server.listen(8)
        self.server.settimeout(.1)
        self.thread = threading.Thread(target=self.serve)
        self.thread.start()

    def send(self, connection, kind, value):
        body = json.dumps(value).encode()
        connection.sendall(HEADER.pack(b'i3-ipc', len(body), kind) + body)

    def serve(self):
        while self.running:
            try:
                connection, _ = self.server.accept()
            except (TimeoutError, OSError):
                continue
            connection.settimeout(2)
            try:
                header = connection.recv(HEADER.size, socket.MSG_WAITALL)
                _, length, kind = HEADER.unpack(header)
                connection.recv(length, socket.MSG_WAITALL) if length else None
                if kind == self.failed_kind and not self.failures:
                    self.failures += 1
                    # A truncated frame must be discarded before reconnecting.
                    connection.sendall(b'i3-')
                    connection.close()
                    continue
                if kind == 2:
                    self.send(connection, kind, {'success': True})
                    self.subscriptions.append(connection)
                    continue
                if kind == 4:
                    value = {'type': 'root', 'nodes': [{
                        'id': 10, 'type': 'workspace', 'num': 1,
                        'name': '1: Personal notes', 'nodes': [], 'floating_nodes': [],
                    }], 'floating_nodes': []}
                elif kind == 1:
                    value = [{'name': '1: Personal notes', 'visible': True}]
                else:
                    value = [{'success': True}]
                self.send(connection, kind, value)
            except (OSError, struct.error):
                pass
            connection.close()

    def shutdown_event(self):
        for connection in self.subscriptions:
            try:
                self.send(connection, (1 << 31) | 6, {'change': 'exit'})
            except OSError:
                pass

    def close(self):
        self.running = False
        self.server.close()
        for connection in self.subscriptions:
            connection.close()
        self.thread.join(3)


class BarIpcRecoveryTests(unittest.TestCase):
    def wait(self, predicate, process):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if predicate():
                return
            if process.poll() is not None:
                self.fail('Helper stopped instead of reconnecting: ' + process.stderr.read())
            time.sleep(.05)
        self.fail('Helper did not recover within eight seconds')

    def exercise(self, helper, failed_kind):
        with tempfile.TemporaryDirectory(prefix='bar-ipc-recovery-') as temporary:
            root = Path(temporary)
            runtime = root / 'run'
            runtime.mkdir(mode=0o700)
            config = root / '.config/waybar'
            config.mkdir(parents=True)
            fixture = IpcFixture(runtime, failed_kind)
            env = dict(os.environ, HOME=str(root), XDG_RUNTIME_DIR=str(runtime),
                       XDG_CONFIG_HOME=str(root / '.config'), SWAYSOCK=str(fixture.path))
            if helper == 'oldbook-workspaces':
                command = [str(BIN / helper), 'daemon']
            else:
                # Keep native IPC/state behavior, but never signal the host bar.
                runner = ('import runpy; ns=runpy.run_path(' + repr(str(BIN / helper)) + '); '
                          'ns["main"].__globals__["reload_style"]=lambda: None; ns["main"]()')
                command = ['python3', '-c', runner]
            process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, text=True)
            try:
                if helper == 'oldbook-workspaces':
                    state = runtime / 'oldbook/workspaces/state.json'

                    def recovered():
                        try:
                            data = json.loads(state.read_text())
                        except (OSError, ValueError):
                            return False
                        return (data.get('updated_at', 0) > 0 and data['records']['10']['base']
                                == '1: Personal notes')

                    self.wait(recovered, process)
                else:
                    self.wait(lambda: len(fixture.subscriptions) == 1, process)
                    self.assertIn('Written by oldbook-waybar-dim',
                                  (config / 'waybar-state.css').read_text())
                self.assertEqual(fixture.failures, 1)
                self.assertIsNone(process.poll())
                fixture.shutdown_event()
                self.assertEqual(process.wait(5), 0)
                self.assertIn('reconnecting', process.stderr.read())
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(5)
                process.stderr.close()
                fixture.close()

    def test_workspace_snapshot_disconnect_recovers_without_losing_custom_name(self):
        self.exercise('oldbook-workspaces', 4)

    def test_workspace_subscription_disconnect_recovers(self):
        self.exercise('oldbook-workspaces', 2)

    def test_bar_style_snapshot_disconnect_recovers(self):
        self.exercise('oldbook-waybar-dim', 1)


if __name__ == '__main__':
    unittest.main()
