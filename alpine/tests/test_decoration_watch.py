"""Exercise persistent decoration IPC against a private Unix socket server."""

import importlib.util
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest


MODEL = (Path(__file__).resolve().parents[1]
         / 'desktop/.local/lib/oldbook/decoration_watch.py')
SPEC = importlib.util.spec_from_file_location('decoration_watch', MODEL)
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)
HEADER = struct.Struct('=6sII')


def receive_exact(connection, size):
    data = bytearray()
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            raise ConnectionError('peer closed')
        data.extend(part)
    return bytes(data)


class SwayServer:
    def __init__(self, path, fragmented=False):
        self.path = str(path)
        self.fragmented = fragmented
        self.condition = threading.Condition()
        self.send_lock = threading.Lock()
        self.connections = set()
        self.subscribers = set()
        self.workers = []
        self.requests = []
        self.request_times = []
        self.subscriptions = []
        self.tree = {'id': 1, 'name': 'initial', 'nodes': []}
        self.stall = False
        self.reply_delay = 0
        self.stopped = threading.Event()
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.path)
        self.listener.listen()
        self.listener.settimeout(0.05)
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        while not self.stopped.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self.condition:
                self.connections.add(connection)
            worker = threading.Thread(target=self._serve,
                                      args=(connection,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def _send(self, connection, kind, value):
        body = json.dumps(value).encode()
        frame = HEADER.pack(b'i3-ipc', len(body), kind) + body
        with self.send_lock:
            if self.fragmented:
                for index in range(0, len(frame), 3):
                    connection.sendall(frame[index:index + 3])
            else:
                connection.sendall(frame)

    def _serve(self, connection):
        try:
            while not self.stopped.is_set():
                magic, length, kind = HEADER.unpack(
                    receive_exact(connection, HEADER.size))
                if magic != b'i3-ipc':
                    return
                body = receive_exact(connection, length)
                if kind == 2:
                    with self.condition:
                        self.subscriptions.append(json.loads(body))
                    self._send(connection, kind, {'success': True})
                    with self.condition:
                        self.subscribers.add(connection)
                        self.condition.notify_all()
                elif kind == 4:
                    with self.condition:
                        self.requests.append(connection)
                        self.request_times.append(time.monotonic())
                        tree = self.tree
                        stall = self.stall
                        self.condition.notify_all()
                    if not stall:
                        if self.reply_delay:
                            time.sleep(self.reply_delay)
                        self._send(connection, kind, tree)
                else:
                    return
        except (OSError, ValueError):
            pass
        finally:
            with self.condition:
                self.connections.discard(connection)
                self.subscribers.discard(connection)
                self.condition.notify_all()
            connection.close()

    def wait_for(self, predicate, timeout=2):
        with self.condition:
            return self.condition.wait_for(predicate, timeout)

    def event(self, number=3):
        with self.condition:
            subscribers = tuple(self.subscribers)
        for connection in subscribers:
            self._send(connection, (1 << 31) | number, {'change': 'fixture'})

    def disconnect(self):
        with self.condition:
            connections = tuple(self.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close(self):
        self.stopped.set()
        self.listener.close()
        self.thread.join(timeout=1)
        self.disconnect()
        for worker in self.workers:
            worker.join(timeout=1)


class DecorationWatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='decoration-watch-')
        self.addCleanup(self.directory.cleanup)
        self.server = SwayServer(Path(self.directory.name) / 'sway.sock',
                                 fragmented=True)
        self.addCleanup(self.server.close)
        self.delivered = []
        self.condition = threading.Condition()
        self.watcher = watch.TreeWatch(self.server.path, self.deliver)
        self.addCleanup(self.watcher.close)

    def deliver(self, tree):
        with self.condition:
            self.delivered.append(tree)
            self.condition.notify_all()

    def wait_delivered(self, count):
        with self.condition:
            self.assertTrue(self.condition.wait_for(
                lambda: len(self.delivered) >= count, timeout=2),
                'watcher did not deliver the requested tree')

    def test_partial_frames_reuse_connection_and_suppress_unchanged_trees(self):
        self.watcher.set_attached(True)
        self.watcher.start()
        self.watcher.start()  # Starting twice must not create another worker.
        self.wait_delivered(1)
        self.assertTrue(self.server.wait_for(lambda: len(self.server.requests) >= 5))
        self.assertEqual(len(set(self.server.requests)), 1)
        self.assertEqual(self.server.subscriptions,
                         [['window', 'workspace', 'output', 'shutdown']])
        self.assertEqual(len(self.delivered), 1)
        with self.server.condition:
            self.server.tree = {'id': 1, 'name': 'moved', 'nodes': []}
        self.wait_delivered(2)
        self.assertEqual(self.delivered[-1]['name'], 'moved')

    def test_semantic_event_refreshes_before_long_idle_poll(self):
        self.watcher.IDLE_INTERVAL = 30
        self.watcher.start()
        self.wait_delivered(1)
        self.assertTrue(self.server.wait_for(lambda: bool(self.server.subscribers)))
        with self.server.condition:
            self.server.tree = {'id': 2, 'name': 'fullscreen', 'nodes': []}
        self.server.event()
        self.wait_delivered(2)
        self.assertEqual(self.delivered[-1]['id'], 2)
        self.assertEqual(len(set(self.server.requests)), 1)

    def test_request_processing_does_not_add_another_poll_interval(self):
        # A busy compositor still has enough time to reply within a 60 Hz
        # frame. Sleeping a full interval afterward would halve that cadence.
        self.server.reply_delay = 0.010
        self.watcher.set_attached(True)
        self.watcher.start()
        self.assertTrue(self.server.wait_for(lambda: len(self.server.requests) >= 18))
        with self.server.condition:
            times = self.server.request_times[2:18]
        mean_interval = (times[-1] - times[0]) / (len(times) - 1)
        self.assertLessEqual(mean_interval, 1 / 60)
        self.assertEqual(len(set(self.server.requests)), 1)

    def test_attaching_wakes_idle_poll_and_detaching_stops_fast_poll(self):
        self.watcher.IDLE_INTERVAL = 30
        self.watcher.start()
        self.wait_delivered(1)
        with self.server.condition:
            self.server.tree = {'id': 3, 'name': 'floating', 'nodes': []}
        self.watcher.set_attached(True)
        self.wait_delivered(2)
        self.assertTrue(self.server.wait_for(lambda: len(self.server.requests) >= 4))
        self.watcher.set_attached(False)
        # The wakeup may cause one final refresh. No further motion polls remain.
        time.sleep(0.08)
        with self.server.condition:
            count = len(self.server.requests)
        self.assertFalse(self.server.wait_for(
            lambda: len(self.server.requests) > count, timeout=0.15))

    def test_disconnect_reconnects_and_shutdown_closes_both_connections(self):
        self.watcher.start()
        self.wait_delivered(1)
        with self.server.condition:
            self.server.tree = {'id': 4, 'name': 'reconnected', 'nodes': []}
        self.server.disconnect()
        self.wait_delivered(2)
        self.assertGreaterEqual(len(self.server.subscriptions), 2)
        self.assertEqual(self.delivered[-1]['name'], 'reconnected')
        self.server.event(number=6)
        self.assertTrue(self.server.wait_for(lambda: not self.server.connections))
        self.watcher._thread.join(timeout=1)
        self.assertFalse(self.watcher._thread.is_alive())
        self.assertFalse(self.watcher._connections)
        self.assertIsNone(self.watcher._wake_read)
        self.assertIsNone(self.watcher._wake_write)

    def test_close_interrupts_blocked_tree_read_and_does_not_restart(self):
        self.server.stall = True
        self.watcher.start()
        self.assertTrue(self.server.wait_for(lambda: bool(self.server.requests)))
        started = time.monotonic()
        self.watcher.close()
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertFalse(self.watcher._thread.is_alive())
        self.assertTrue(self.server.wait_for(lambda: not self.server.connections))
        self.assertEqual(self.delivered, [])
        self.watcher.close()
        self.watcher.start()
        self.assertFalse(self.watcher._thread.is_alive())
        self.assertFalse(self.watcher._connections)

    def test_oversized_frame_is_rejected_without_reading_its_body(self):
        left, right = socket.socketpair()
        try:
            left.sendall(HEADER.pack(b'i3-ipc', 33 * 1024 * 1024, 4))
            with self.assertRaisesRegex(ValueError, 'invalid Sway IPC frame'):
                watch._receive(right)
        finally:
            left.close()
            right.close()


if __name__ == '__main__':
    unittest.main()
