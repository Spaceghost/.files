"""Shortcut overlay lifecycle tests; GTK and host input are never opened."""
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest


REPO = Path(__file__).resolve().parents[2]
LIB = REPO / 'alpine/desktop/.local/lib/mbp_intel'
LIB_PARENT = LIB.parent
COMMAND = REPO / 'alpine/desktop/.local/bin/mbp-intel-shortcuts'
sys.path.insert(0, str(LIB))

try:
    from shortcut_overlay import (AlreadyRunning, GraphicalSessionGuard,
                                  ServiceController, SessionLease, SocketWatch,
                                  screen_locked)
except ImportError as error:
    IMPORT_ERROR = error
else:
    IMPORT_ERROR = None


class FakeState:
    def __init__(self):
        self.cancelled = 0

    def cancel(self):
        self.cancelled += 1


class FakeMonitor:
    def __init__(self):
        self.want_overlay = False
        self.device_count = 2
        self.state = FakeState()
        self.closed = False

    def poll(self, now):
        return self.want_overlay

    def close(self):
        self.closed = True


class FakeOverlay:
    def __init__(self):
        self.loading = 0
        self.loading_contexts = []
        self.snapshots = []
        self.hidden = 0
        self.closed = False

    def show_loading(self, context=None):
        self.loading += 1
        self.loading_contexts.append(context)

    def show(self, snapshot):
        self.snapshots.append(snapshot)

    def hide(self):
        self.hidden += 1

    def close(self):
        self.closed = True


class FakeProvider:
    def __init__(self, snapshots=None, gate=None):
        self.snapshots = list(snapshots or [])
        self.gate = gate
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(2)
        if self.snapshots:
            return self.snapshots.pop(0)
        return {'app': 'Unknown', 'output': None, 'sections': []}


class FakeLiveness:
    def __init__(self):
        self.connected = True
        self.closed = False

    def alive(self):
        return self.connected

    def close(self):
        self.closed = True


class FakeGuard:
    def __init__(self):
        self.active = True

    def allows_overlay(self, now):
        return self.active


class RaisingGuard(FakeGuard):
    def allows_overlay(self, now):
        raise RuntimeError('graphical session vanished')


class ShortcutServiceTests(unittest.TestCase):
    def setUp(self):
        if IMPORT_ERROR is not None:
            self.fail(f'shortcut service is unavailable: {IMPORT_ERROR}')

    def controller(self, provider):
        monitor = FakeMonitor()
        overlay = FakeOverlay()
        liveness = FakeLiveness()
        guard = FakeGuard()
        controller = ServiceController(monitor, provider, overlay, liveness, guard,
                                       refresh_seconds=1.0)
        self.addCleanup(controller.close)
        return controller, monitor, overlay, liveness, guard

    def finish_worker(self, controller, now):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            controller.tick(now)
            if controller.snapshot_ready:
                return
            time.sleep(.005)
        self.fail('snapshot worker did not finish')

    def test_slow_snapshot_never_delays_release_or_reappears_stale(self):
        gate = threading.Event()
        snapshot = {'app': 'Terminal', 'output': 'eDP-1', 'sections': []}
        controller, monitor, overlay, _, _ = self.controller(
            FakeProvider([snapshot], gate=gate))
        monitor.want_overlay = True
        self.assertTrue(controller.tick(.500))
        self.assertEqual(overlay.loading, 1)

        monitor.want_overlay = False
        started = time.monotonic()
        self.assertTrue(controller.tick(.525))
        self.assertLess(time.monotonic() - started, .1)
        self.assertGreaterEqual(overlay.hidden, 1)
        gate.set()
        time.sleep(.02)
        controller.tick(.550)
        self.assertEqual(overlay.snapshots, [])

    def test_loading_uses_background_focused_output_before_snapshot(self):
        gate = threading.Event()
        stale = {
            'output': 'HEADLESS-1',
            '_output_rect': {'x': 0, 'y': 0, 'width': 1440, 'height': 900},
        }
        focused = {
            'output': 'HEADLESS-2',
            '_output_rect': {'x': 1440, 'y': 0, 'width': 1280, 'height': 720},
        }
        context = [stale]
        calls = []

        def probe():
            calls.append(True)
            return context[0]

        monitor = FakeMonitor()
        overlay = FakeOverlay()
        controller = ServiceController(
            monitor, FakeProvider(gate=gate), overlay, FakeLiveness(), FakeGuard(),
            loading_probe=probe)
        self.addCleanup(controller.close)
        time.sleep(.02)
        self.assertEqual(calls, [], 'focus must be sampled for the current hold')
        context[0] = focused
        monitor.want_overlay = True
        controller.tick(.5)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not overlay.loading_contexts:
            controller.tick(.51)
            time.sleep(.005)
        self.assertEqual(overlay.loading_contexts, [focused])
        gate.set()

    def test_visible_snapshot_refreshes_only_when_content_changes(self):
        first = {'app': 'Terminal', 'output': 'eDP-1', 'sections': [
            {'title': 'Terminal', 'coverage': 'partial',
             'rows': [{'key': 'Ctrl+Shift+C', 'description': 'Copy'}]}]}
        changed = {'app': 'Editor', 'output': 'eDP-1', 'sections': [
            {'title': 'Editor', 'coverage': 'partial',
             'rows': [{'key': 'Ctrl+S', 'description': 'Save'}]}]}
        provider = FakeProvider([first, first, changed])
        controller, monitor, overlay, _, _ = self.controller(provider)
        monitor.want_overlay = True
        controller.tick(.5)
        self.finish_worker(controller, .51)
        self.assertEqual(overlay.snapshots, [first])

        controller.tick(1.51)
        self.finish_worker(controller, 1.52)
        self.assertEqual(overlay.snapshots, [first],
                         'an unchanged refresh must preserve the scroll position')
        controller.tick(2.52)
        self.finish_worker(controller, 2.53)
        self.assertEqual(overlay.snapshots, [first, changed])

    def test_inactive_graphical_session_hides_and_cancels_hold(self):
        controller, monitor, overlay, _, guard = self.controller(FakeProvider())
        monitor.want_overlay = True
        guard.active = False
        self.assertTrue(controller.tick(.5))
        self.assertEqual(overlay.loading, 0)
        self.assertEqual(monitor.state.cancelled, 1)
        self.assertGreaterEqual(overlay.hidden, 1)

    def test_sway_disconnect_ends_controller_and_closes_resources(self):
        controller, monitor, overlay, liveness, _ = self.controller(FakeProvider())
        liveness.connected = False
        self.assertFalse(controller.tick(.5))
        self.assertTrue(monitor.closed)
        self.assertTrue(overlay.closed)
        self.assertTrue(liveness.closed)

    def test_guard_failure_ends_controller_and_closes_resources(self):
        monitor = FakeMonitor()
        overlay = FakeOverlay()
        liveness = FakeLiveness()
        controller = ServiceController(
            monitor, FakeProvider(), overlay, liveness, RaisingGuard())
        self.assertFalse(controller.tick(.5))
        self.assertTrue(monitor.closed)
        self.assertTrue(overlay.closed)
        self.assertTrue(liveness.closed)

    def test_repeated_cancelled_holds_coalesce_behind_one_bounded_stale_job(self):
        gate = threading.Event()

        class BlockingProvider:
            def __init__(self):
                self.calls = 0

            def snapshot(self):
                self.calls += 1
                call = self.calls
                gate.wait(2)
                return {'app': f'context-{call}', 'output': 'eDP-1', 'sections': []}

        provider = BlockingProvider()
        controller, monitor, overlay, _, _ = self.controller(provider)
        for started in (.5, .6, .7):
            monitor.want_overlay = True
            controller.tick(started)
            monitor.want_overlay = False
            controller.tick(started + .025)
        monitor.want_overlay = True
        controller.tick(.8)
        time.sleep(.03)
        self.assertEqual(provider.calls, 1,
                         'only one obsolete bounded query may occupy the worker')
        gate.set()
        self.finish_worker(controller, .81)
        self.assertEqual(overlay.snapshots[-1]['app'], 'context-2')

    def test_close_is_idempotent(self):
        controller, monitor, overlay, liveness, _ = self.controller(FakeProvider())
        controller.close()
        controller.close()
        self.assertTrue(monitor.closed)
        self.assertTrue(overlay.closed)
        self.assertTrue(liveness.closed)


class RuntimeSafetyTests(unittest.TestCase):
    def setUp(self):
        if IMPORT_ERROR is not None:
            self.fail(f'shortcut service is unavailable: {IMPORT_ERROR}')
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-shortcuts-')
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name)
        self.runtime.chmod(0o700)
        self.sway_socket = self.runtime / 'sway-ipc.test.sock'
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(str(self.sway_socket))
        self.addCleanup(self.listener.close)

    def test_same_sway_session_excludes_duplicate_but_releases_cleanly(self):
        first = SessionLease(self.runtime, self.sway_socket)
        first.acquire()
        second = SessionLease(self.runtime, self.sway_socket)
        with self.assertRaises(AlreadyRunning):
            second.acquire()
        status = json.loads(first.status_path.read_text())
        self.assertEqual(status['version'], 1)
        self.assertEqual(status['state'], 'starting')
        self.assertEqual(status['sway_socket'], str(self.sway_socket))
        self.assertEqual(stat.S_IMODE(first.status_path.stat().st_mode), 0o600)
        first.close()
        second.acquire()
        second.close()

    def test_abandoned_temporary_status_file_does_not_break_startup(self):
        lease = SessionLease(self.runtime, self.sway_socket)
        lease.directory.mkdir(mode=0o700)
        abandoned = lease.status_path.with_name(
            f'.{lease.status_path.name}.{os.getpid()}.tmp')
        abandoned.write_text('partial')
        lease.acquire()
        self.addCleanup(lease.close)
        self.assertEqual(json.loads(lease.status_path.read_text())['state'], 'starting')

    def test_different_sway_sockets_have_distinct_lock_and_status_files(self):
        other_path = self.runtime / 'sway-ipc.other.sock'
        other = socket.socket(socket.AF_UNIX)
        other.bind(str(other_path))
        self.addCleanup(other.close)
        one = SessionLease(self.runtime, self.sway_socket)
        two = SessionLease(self.runtime, other_path)
        self.addCleanup(one.close)
        self.addCleanup(two.close)
        one.acquire()
        two.acquire()
        self.assertNotEqual(one.lock_path, two.lock_path)
        self.assertNotEqual(one.status_path, two.status_path)

    def test_nonprivate_runtime_is_rejected_before_state_is_created(self):
        self.runtime.chmod(0o755)
        lease = SessionLease(self.runtime, self.sway_socket)
        with self.assertRaisesRegex(RuntimeError, 'owned private directory'):
            lease.acquire()
        self.assertFalse((self.runtime / 'mbp-intel-shortcuts').exists())

    def test_socket_watch_detects_peer_shutdown(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        watch = SocketWatch(left)
        self.assertTrue(watch.alive())
        right.close()
        self.assertFalse(watch.alive())

    def test_valid_live_lock_record_suppresses_overlay_but_stale_record_does_not(self):
        wayland_path = self.runtime / 'wayland-test'
        wayland = socket.socket(socket.AF_UNIX)
        wayland.bind(str(wayland_path))
        self.addCleanup(wayland.close)
        process = Path('/proc') / str(os.getpid())
        fields = process.joinpath('stat').read_text().rsplit(')', 1)[1].split()
        identity = {
            'pid': os.getpid(),
            'start_time': fields[19],
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        }
        info = wayland_path.stat()
        record = self.runtime / 'mbp-intel-screen-lock/ready.json'
        record.parent.mkdir(mode=0o700)
        record.write_text(json.dumps({
            'process': identity,
            'compositor': {'socket': str(wayland_path), 'device': info.st_dev,
                           'inode': info.st_ino, 'created_ns': info.st_ctime_ns},
        }))
        self.assertTrue(screen_locked(self.runtime, wayland_path))
        identity['start_time'] = 'stale'
        record.write_text(json.dumps({'process': identity, 'compositor': {}}))
        self.assertFalse(screen_locked(self.runtime, wayland_path))

    def test_missing_wayland_socket_with_live_lock_record_fails_conservative(self):
        missing = self.runtime / 'wayland-gone'
        record = self.runtime / 'mbp-intel-screen-lock/ready.json'
        record.parent.mkdir(mode=0o700)
        record.write_text(json.dumps({
            'process': {'pid': os.getpid(), 'start_time': 'any', 'boot_id': 'any'},
            'compositor': {'socket': str(missing), 'device': 1,
                           'inode': 2, 'created_ns': 3},
        }))
        self.assertTrue(screen_locked(self.runtime, missing))

    def test_graphical_guard_caches_probe_and_always_checks_lock(self):
        calls = []
        locked = [False]
        guard = GraphicalSessionGuard(
            self.runtime, self.runtime / 'wayland-test',
            activity_probe=lambda: calls.append(True) or True,
            lock_probe=lambda runtime, display: locked[0], cache_seconds=.25)
        self.addCleanup(guard.close)
        self.assertFalse(guard.allows_overlay(1.0),
                         'an unknown session state must fail conservative')
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not guard.allows_overlay(1.0):
            time.sleep(.005)
        self.assertTrue(guard.allows_overlay(1.0))
        self.assertTrue(guard.allows_overlay(1.1))
        self.assertEqual(len(calls), 1)
        locked[0] = True
        self.assertFalse(guard.allows_overlay(1.11))

    def test_slow_activity_probe_never_blocks_input_poll_or_release(self):
        quick = [True]

        def activity():
            if quick[0]:
                return True
            time.sleep(.2)
            return True

        guard = GraphicalSessionGuard(
            self.runtime, self.runtime / 'wayland-test', activity_probe=activity,
            lock_probe=lambda runtime, display: False, cache_seconds=.01)
        self.addCleanup(lambda: getattr(guard, 'close', lambda: None)())
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not guard.allows_overlay(0):
            time.sleep(.005)
        self.assertTrue(guard.allows_overlay(0))
        quick[0] = False

        monitor = FakeMonitor()
        overlay = FakeOverlay()
        controller = ServiceController(
            monitor, FakeProvider(), overlay, FakeLiveness(), guard,
            refresh_seconds=1.0)
        self.addCleanup(controller.close)
        monitor.want_overlay = True
        started = time.monotonic()
        controller.tick(.5)
        self.assertLess(time.monotonic() - started, .08)
        monitor.want_overlay = False
        started = time.monotonic()
        controller.tick(.525)
        self.assertLess(time.monotonic() - started, .08)
        self.assertGreaterEqual(overlay.hidden, 1)

    def test_status_command_uses_package_imports_without_loading_gtk(self):
        lease = SessionLease(self.runtime, self.sway_socket)
        lease.acquire()
        self.addCleanup(lease.close)
        env = dict(os.environ, XDG_RUNTIME_DIR=str(self.runtime),
                   PYTHONPATH=str(LIB_PARENT), MBP_INTEL_SHORTCUTS_LEGACY='1')
        result = subprocess.run(
            [str(COMMAND), 'status', '--socket', str(self.sway_socket)],
            env=env, text=True, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual(status['socket_id'], lease.socket_id)
        self.assertTrue(status['live'])
        imported = subprocess.run(
            [sys.executable, '-c',
             'import sys; import mbp_intel.shortcut_overlay; print("gi" in sys.modules)'],
            env=env, text=True, capture_output=True, timeout=3)
        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertEqual(imported.stdout.strip(), 'False')

    def test_status_marks_a_crashed_process_record_stale(self):
        lease = SessionLease(self.runtime, self.sway_socket)
        lease.acquire()
        self.addCleanup(lease.close)
        record = json.loads(lease.status_path.read_text())
        record['state'] = 'running'
        record['process']['start_time'] = 'reused-pid'
        lease.status_path.write_text(json.dumps(record))
        env = dict(os.environ, XDG_RUNTIME_DIR=str(self.runtime),
                   PYTHONPATH=str(LIB_PARENT), MBP_INTEL_SHORTCUTS_LEGACY='1')
        result = subprocess.run(
            [str(COMMAND), 'status', '--socket', str(self.sway_socket)],
            env=env, text=True, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertFalse(status['live'])
        self.assertEqual(status['state'], 'stale')
        self.assertEqual(status['recorded_state'], 'running')


if __name__ == '__main__':
    unittest.main()
