#!/usr/bin/env python3
"""Protocol and fail-off contracts for the staged controller, no host radio."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys
import os
import stat
from unittest import mock

sys.dont_write_bytecode = True

SCRIPT = Path(__file__).parents[1] / "root/usr/local/sbin/privacyctl"
loader = importlib.machinery.SourceFileLoader("privacyctl", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
privacyctl = importlib.util.module_from_spec(spec)
loader.exec_module(privacyctl)


class FakeSystem:
    def __init__(self, timeline=None):
        self.calls = []
        self.blocked = True
        self.bluetooth_blocked = True
        self.timeline = timeline if timeline is not None else []

    def block_all(self):
        self.calls.append("block-all")
        self.timeline.append("system:block-all")
        self.blocked = True
        self.bluetooth_blocked = True

    def block_bluetooth(self):
        self.calls.append("block-bluetooth")
        self.timeline.append("system:block-bluetooth")
        self.bluetooth_blocked = True

    def unblock_wifi(self):
        self.calls.append("unblock-wifi")
        self.timeline.append("system:unblock-wifi")
        self.blocked = False

    def prepare_addresses(self, profile):
        self.calls.append("dhcp:" + profile)
        self.timeline.append("system:dhcp:" + profile)

    def states(self, kind):
        blocked = self.bluetooth_blocked if kind == "bluetooth" else self.blocked
        return ["0" if blocked else "1"]

    def hard_states(self, kind):
        return ["0"]


class FakeWpa:
    def __init__(self, replies=None, identity=("0", "shmecklebucket"), status=None, event=True, timeline=None):
        self.replies = replies or {}
        self.identity = identity
        self.status_value = status or {"wpa_state": "COMPLETED", "id": "0", "ssid": "shmecklebucket"}
        self.event = event
        self.calls = []
        self.timeline = timeline if timeline is not None else []

    def __enter__(self): return self
    def __exit__(self, *_): pass
    def expect_ok(self, command):
        self.calls.append(command)
        self.timeline.append("wpa:" + command)
        if self.replies.get(command, "OK") != "OK":
            raise privacyctl.PrivacyError("wpa rejected " + command.split()[0])
    def network_ssid(self, network_id):
        self.calls.append("LIST_NETWORKS")
        self.timeline.append("wpa:LIST_NETWORKS")
        if str(network_id) != self.identity[0]:
            raise privacyctl.PrivacyError("configured network id is absent or ambiguous")
        return self.identity[1]
    def status(self):
        self.calls.append("STATUS")
        self.timeline.append("wpa:STATUS")
        return self.status_value
    def wait_event(self, fragment, _deadline):
        self.calls.append("WAIT:" + fragment)
        self.timeline.append("wpa:WAIT:" + fragment)
        if not self.event:
            raise privacyctl.PrivacyError("expected wpa event did not arrive")
    def request(self, command):
        self.calls.append(command)
        self.timeline.append("wpa:" + command)
        return "bssid / frequency / signal level / flags / ssid\n"


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.timeline = []
        self.system = FakeSystem(self.timeline)
        self.wpa = FakeWpa(timeline=self.timeline)
        self.controller = privacyctl.Controller(self.system, lambda: self.wpa)
        self.old_profile = privacyctl.PROFILE_FILE
        self.old_session = privacyctl.SESSION_FILE
        self.old_lock = privacyctl.LOCK_FILE
        self.old_read_profile = privacyctl.read_profile
        self.temp = tempfile.TemporaryDirectory()
        privacyctl.PROFILE_FILE = Path(self.temp.name) / "profiles"
        privacyctl.SESSION_FILE = Path(self.temp.name) / "session"
        privacyctl.LOCK_FILE = Path(self.temp.name) / "lock"
        privacyctl.read_profile = lambda profile, _path=None: (
            (0, "shmecklebucket") if profile == "shmecklebucket" else (1, "Exact iPhone"))

    def tearDown(self):
        privacyctl.PROFILE_FILE = self.old_profile
        privacyctl.SESSION_FILE = self.old_session
        privacyctl.LOCK_FILE = self.old_lock
        privacyctl.read_profile = self.old_read_profile
        self.temp.cleanup()

    def profile(self, text="profile|shmecklebucket|0|shmecklebucket"):
        privacyctl.PROFILE_FILE.write_text(text + "\n")
        privacyctl.PROFILE_FILE.chmod(0o600)

    def test_failed_wpa_reply_fails_off_before_wifi_unblocks(self):
        self.profile()
        self.wpa.replies["DISABLE_NETWORK all"] = "FAIL-BUSY"
        with self.assertRaises(privacyctl.PrivacyError): self.controller.connect("shmecklebucket")
        self.assertTrue(self.system.blocked)
        self.assertNotIn("unblock-wifi", self.system.calls)

    def test_identity_mismatch_fails_off(self):
        self.profile()
        self.wpa.identity = ("0", "other")
        with self.assertRaises(privacyctl.PrivacyError): self.controller.connect("shmecklebucket")
        self.assertTrue(self.system.blocked)
        self.assertNotIn("unblock-wifi", self.system.calls)

    def test_completed_wrong_network_fails_off(self):
        self.profile()
        self.wpa.status_value = {"wpa_state": "COMPLETED", "id": "9", "ssid": "other"}
        old = privacyctl.CONNECT_DEADLINE; privacyctl.CONNECT_DEADLINE = 0
        try:
            with self.assertRaises(privacyctl.PrivacyError): self.controller.connect("shmecklebucket")
        finally: privacyctl.CONNECT_DEADLINE = old
        self.assertTrue(self.system.blocked)

    def test_connect_selects_while_blocked_then_acquires_dhcp(self):
        self.profile()
        self.controller.connect("shmecklebucket")
        self.assertLess(self.timeline.index("system:block-all"), self.timeline.index("wpa:SELECT_NETWORK 0"))
        self.assertLess(self.timeline.index("wpa:ENABLE_NETWORK 0"), self.timeline.index("system:unblock-wifi"))
        self.assertIn("dhcp:shmecklebucket", self.system.calls)
        self.assertTrue(privacyctl.SESSION_FILE.exists())

    def test_scan_requires_fresh_event_and_fails_off(self):
        self.wpa.event = False
        with self.assertRaises(privacyctl.PrivacyError): self.controller.scan()
        self.assertTrue(self.system.blocked)
        self.assertIn("DISABLE_NETWORK all", self.wpa.calls)

    def test_scan_rejects_fail_reply(self):
        self.wpa.replies["SCAN"] = "FAIL"
        with self.assertRaises(privacyctl.PrivacyError): self.controller.scan()
        self.assertTrue(self.system.blocked)

    def test_hotspot_clears_inherited_ipv6_before_dhcp(self):
        self.profile("profile|iphone-hotspot|1|Exact iPhone")
        self.wpa.identity = ("1", "Exact iPhone")
        self.wpa.status_value = {"wpa_state": "COMPLETED", "id": "1", "ssid": "Exact iPhone"}
        self.controller.connect("iphone-hotspot")
        self.assertIn("dhcp:iphone-hotspot", self.system.calls)

    def one_supervisor_cycle(self):
        with mock.patch.object(privacyctl.time, "sleep", side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                self.controller.supervise()

    def test_idle_missing_session_reblocks_unowned_radio_state(self):
        self.system.blocked = False
        self.one_supervisor_cycle()
        self.assertTrue(self.system.blocked)

    def test_malformed_or_incomplete_session_fails_off(self):
        for content in ('{', '[]', '{}', '{"id": 0, "ssid": "other"}'):
            with self.subTest(content=content):
                privacyctl.SESSION_FILE.write_text(content)
                privacyctl.SESSION_FILE.chmod(0o600)
                self.system.blocked = False
                self.one_supervisor_cycle()
                self.assertTrue(self.system.blocked)
                self.assertFalse(privacyctl.SESSION_FILE.exists())

    def test_failed_control_socket_fails_off(self):
        privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.system.blocked = False

        def unavailable():
            raise privacyctl.PrivacyError("control socket unavailable")

        self.controller.wpa_factory = unavailable
        self.one_supervisor_cycle()
        self.assertTrue(self.system.blocked)
        self.assertFalse(privacyctl.SESSION_FILE.exists())

    def test_valid_trusted_session_keeps_wifi_enabled(self):
        privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.system.blocked = False
        self.one_supervisor_cycle()
        self.assertFalse(self.system.blocked)
        self.assertTrue(privacyctl.SESSION_FILE.exists())
        self.assertEqual(self.wpa.calls, ["STATUS"])

    def test_trusted_session_reblocks_bluetooth_without_disconnecting_wifi(self):
        privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.system.blocked = False
        self.system.bluetooth_blocked = False
        self.one_supervisor_cycle()
        self.assertTrue(self.system.bluetooth_blocked)
        self.assertFalse(self.system.blocked)
        self.assertTrue(privacyctl.SESSION_FILE.exists())
        self.assertEqual(self.system.calls, ["block-bluetooth"])

    def test_failed_bluetooth_reblock_fails_trusted_session_off(self):
        privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.system.blocked = False
        self.system.bluetooth_blocked = False
        with mock.patch.object(self.system, "block_bluetooth",
                               side_effect=privacyctl.PrivacyError("Bluetooth block failed")):
            self.one_supervisor_cycle()
        self.assertTrue(self.system.blocked)
        self.assertFalse(privacyctl.SESSION_FILE.exists())

    def test_session_read_os_error_still_attempts_radio_block(self):
        privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.system.blocked = False
        original = privacyctl.os.open

        def cannot_read(path, flags, *args, **kwargs):
            if path == privacyctl.SESSION_FILE.name and (flags & os.O_ACCMODE) == os.O_RDONLY:
                raise PermissionError("test unreadable session")
            return original(path, flags, *args, **kwargs)

        with mock.patch.object(privacyctl.os, "open", cannot_read):
            self.one_supervisor_cycle()
        self.assertTrue(self.system.blocked)

    def test_supervisor_does_not_interrupt_command_holding_radio_lock(self):
        # A scan/connect may temporarily have no session or an older session.
        for has_session in (False, True):
            with self.subTest(has_session=has_session):
                if has_session:
                    privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
                self.system.blocked = False
                self.wpa.calls.clear()
                with privacyctl.RadioLock():
                    self.one_supervisor_cycle()
                self.assertFalse(self.system.blocked)
                self.assertEqual(self.wpa.calls, [])

    def test_off_blocks_radios_even_if_session_cannot_be_removed(self):
        self.system.blocked = False
        with mock.patch.object(privacyctl, "clear_session", side_effect=PermissionError("test cleanup failure")):
            with self.assertRaises((OSError, privacyctl.PrivacyError)):
                self.controller.off()
        self.assertTrue(self.system.blocked)


class RuntimeDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old_session = privacyctl.SESSION_FILE
        self.addCleanup(setattr, privacyctl, "SESSION_FILE", self.old_session)
        privacyctl.SESSION_FILE = self.root / "runtime" / "session.json"

    def test_first_session_creates_private_runtime_directory_and_file(self):
        privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.assertEqual(stat.S_IMODE(privacyctl.SESSION_FILE.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(privacyctl.SESSION_FILE.stat().st_mode), 0o600)
        self.assertEqual(privacyctl.SESSION_FILE.stat().st_uid, os.geteuid())

    def test_symlink_runtime_directory_is_rejected_without_writing_through(self):
        destination = self.root / "elsewhere"
        destination.mkdir()
        privacyctl.SESSION_FILE.parent.symlink_to(destination, target_is_directory=True)
        with self.assertRaises(privacyctl.PrivacyError):
            privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.assertEqual(list(destination.iterdir()), [])

    def test_shared_runtime_directory_is_rejected(self):
        privacyctl.SESSION_FILE.parent.mkdir(mode=0o777)
        privacyctl.SESSION_FILE.parent.chmod(0o777)
        with self.assertRaises(privacyctl.PrivacyError):
            privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.assertFalse(privacyctl.SESSION_FILE.exists())

    def test_runtime_directory_owned_by_someone_else_is_rejected(self):
        privacyctl.SESSION_FILE.parent.mkdir(mode=0o700)
        original = privacyctl.os.fstat

        def different_owner(descriptor):
            result = original(descriptor)
            fields = list(result)
            fields[4] = os.geteuid() + 1
            return os.stat_result(fields)

        with mock.patch.object(privacyctl.os, "fstat", side_effect=different_owner):
            with self.assertRaises(privacyctl.PrivacyError):
                privacyctl.write_session("shmecklebucket", 0, "shmecklebucket")
        self.assertFalse(privacyctl.SESSION_FILE.exists())


class ProtocolTests(unittest.TestCase):
    def test_non_ok_reply_is_never_success(self):
        control = object.__new__(privacyctl.WpaControl)
        control.request = lambda _: "FAIL-BUSY"
        with self.assertRaises(privacyctl.PrivacyError): control.expect_ok("RECONNECT")


class BluetoothEnforcementTests(unittest.TestCase):
    def test_bluetooth_only_block_verifies_every_device_without_touching_wifi(self):
        system = privacyctl.System()
        calls = []
        with mock.patch.object(privacyctl, "run_checked", side_effect=lambda command: calls.append(command)):
            with mock.patch.object(system, "states", return_value=["0", "0"]):
                system.block_bluetooth()
        self.assertEqual(calls, [["/usr/sbin/rfkill", "block", "bluetooth"]])

    def test_bluetooth_block_rejects_an_unblocked_device_after_successful_command(self):
        system = privacyctl.System()
        with mock.patch.object(privacyctl, "run_checked", return_value=""):
            with mock.patch.object(system, "states", return_value=["0", "1"]):
                with self.assertRaises(privacyctl.PrivacyError):
                    system.block_bluetooth()


class DeadlineAndCleanupTests(unittest.TestCase):
    def test_rejected_attach_removes_its_private_socket(self):
        import socket
        import threading
        with tempfile.TemporaryDirectory() as directory:
            endpoint = str(Path(directory) / 'wpa')
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
                server.bind(endpoint)
                def reject():
                    _request, peer = server.recvfrom(1024)
                    server.sendto(b'FAIL\n', peer)
                worker = threading.Thread(target=reject)
                worker.start()
                with self.assertRaises(privacyctl.PrivacyError):
                    privacyctl.WpaControl(endpoint, directory)
                worker.join(timeout=1)
                self.assertFalse(worker.is_alive())
                self.assertEqual(list(Path(directory).glob('.privacyctl-*')), [])

    def test_full_wpa_send_queue_is_covered_by_the_request_deadline(self):
        import socket
        import threading
        import time
        with tempfile.TemporaryDirectory() as directory:
            endpoint = str(Path(directory) / 'wpa')
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server, \
                    socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                server.bind(endpoint)
                client.bind(str(Path(directory) / 'client'))
                client.connect(endpoint)
                client.setblocking(False)
                while True:
                    try:
                        client.send(b'fill')
                    except BlockingIOError:
                        break
                client.setblocking(True)
                control = object.__new__(privacyctl.WpaControl)
                control.sock = client
                failures = []
                def request():
                    try:
                        control.request('PING', deadline=.05)
                    except BaseException as error:
                        failures.append(error)
                worker = threading.Thread(target=request, daemon=True)
                started = time.monotonic()
                worker.start()
                worker.join(timeout=.3)
                timed_out_without_draining = not worker.is_alive()
                # Release old implementations safely before asserting failure.
                server.settimeout(.01)
                while True:
                    try:
                        server.recv(1024)
                    except socket.timeout:
                        break
                worker.join(timeout=.3)
                self.assertTrue(timed_out_without_draining, 'first send blocked before its deadline')
                self.assertLess(time.monotonic() - started, .3)
                self.assertEqual(len(failures), 1)
                self.assertIsInstance(failures[0], privacyctl.PrivacyError)

    def test_command_timeout_kills_dhcp_style_hook_process_group(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / 'hook.pid'
            code = ('import subprocess,sys,time; from pathlib import Path; '
                    'hook=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); '
                    'Path(sys.argv[1]).write_text(str(hook.pid)); time.sleep(30)')
            started = time.monotonic()
            with self.assertRaises(privacyctl.PrivacyError):
                privacyctl.run_checked([sys.executable, '-c', code, str(pid_file)], timeout=.2)
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertTrue(pid_file.exists(), 'the synthetic DHCP hook did not start')
            process = Path('/proc') / pid_file.read_text() / 'stat'
            deadline = time.monotonic() + 1
            while process.exists() and time.monotonic() < deadline:
                try:
                    if process.read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                        break
                except FileNotFoundError:
                    break
                time.sleep(.01)
            if process.exists():
                self.assertEqual(process.read_text().rsplit(')', 1)[1].split()[0], 'Z',
                                 'a timed-out hook is still running')

    def test_timeout_kills_stdout_holding_hook_after_its_leader_exits(self):
        import signal
        import time
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / 'hook.pid'
            code = ('import subprocess,sys; from pathlib import Path; '
                    'hook=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); '
                    'Path(sys.argv[1]).write_text(str(hook.pid))')
            original_stop = privacyctl.stop_process_group
            observations = []
            groups = []
            def stop_group(process):
                groups.append(process.pid)
                observations.append(process.returncode)
                original_stop(process)
                observations.append(process.returncode)
            try:
                with mock.patch.object(privacyctl, 'stop_process_group', side_effect=stop_group):
                    with self.assertRaises(privacyctl.PrivacyError):
                        privacyctl.run_checked([sys.executable, '-c', code, str(pid_file)], timeout=.2)
                # communicate waits for the hook-held pipe without reaping the
                # exited leader. Therefore the cleanup's early return is not
                # taken; reaping afterwards confirms that the leader exited 0.
                self.assertEqual(observations, [None, 0])
                process = Path('/proc') / pid_file.read_text() / 'stat'
                deadline = time.monotonic() + 1
                while process.exists() and time.monotonic() < deadline:
                    try:
                        if process.read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                            break
                    except FileNotFoundError:
                        break
                    time.sleep(.01)
                if process.exists():
                    self.assertEqual(process.read_text().rsplit(')', 1)[1].split()[0], 'Z')
            finally:
                # Only the freshly created synthetic group can still contain
                # its recorded hook if a regression made cleanup skip it.
                if pid_file.exists():
                    pid = int(pid_file.read_text())
                    try:
                        if os.getpgid(pid) in groups:
                            os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_contended_lock_has_a_finite_wait(self):
        import time
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                privacyctl, 'LOCK_FILE', Path(directory) / 'lock'):
            with privacyctl.RadioLock():
                started = time.monotonic()
                with self.assertRaisesRegex(privacyctl.PrivacyError, 'lock'):
                    with privacyctl.RadioLock(timeout=.05):
                        self.fail('contended lock unexpectedly acquired')
                self.assertLess(time.monotonic() - started, .3)

    def test_absolute_transaction_deadline_interrupts_and_restores_alarm(self):
        import signal
        import time
        previous = signal.getsignal(signal.SIGALRM)
        started = time.monotonic()
        with self.assertRaisesRegex(privacyctl.PrivacyError, 'deadline'):
            with privacyctl.operation_deadline(.05):
                time.sleep(1)
        self.assertLess(time.monotonic() - started, .3)
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_expired_connect_reblocks_both_radios_before_releasing_lock(self):
        import time
        case = ControllerTests()
        case.setUp()
        self.addCleanup(case.tearDown)
        original_deadline = privacyctl.operation_deadline
        with mock.patch.object(case.system, 'prepare_addresses', side_effect=lambda _: time.sleep(1)), \
                mock.patch.object(privacyctl, 'operation_deadline', side_effect=lambda: original_deadline(.05)):
            with self.assertRaisesRegex(privacyctl.PrivacyError, 'deadline'):
                privacyctl.run_locked(case.controller, 'connect', 'shmecklebucket')
        self.assertIn('unblock-wifi', case.system.calls)
        self.assertTrue(case.system.blocked)
        self.assertTrue(case.system.bluetooth_blocked)
        self.assertFalse(privacyctl.SESSION_FILE.exists())
        with privacyctl.RadioLock(blocking=False):
            self.assertTrue(case.system.blocked)


class RfkillStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        actual_path = privacyctl.Path
        self.paths = mock.patch.object(privacyctl, 'Path', side_effect=lambda path: (
            self.root if str(path) == '/sys/class/rfkill' else actual_path(path)))
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.system = privacyctl.System()
        self.command = mock.patch.object(privacyctl, 'run_checked', return_value='')
        self.command.start()
        self.addCleanup(self.command.stop)

    def adapter(self, number, kind, soft, hard):
        path = self.root / f'rfkill{number}'
        path.mkdir(exist_ok=True)
        for name, value in {'type': kind, 'soft': soft, 'hard': hard,
                            'state': 2 if hard else 0 if soft else 1}.items():
            (path / name).write_text(str(value) + '\n')
        return path

    def test_status_reports_soft_and_hard_independently_for_all_combinations(self):
        for soft in (0, 1):
            for hard in (0, 1):
                with self.subTest(soft=soft, hard=hard):
                    self.adapter(0, 'wlan', soft, hard)
                    self.adapter(1, 'bluetooth', soft, hard)
                    status = privacyctl.Controller(self.system).status()
                    for radio in ('wifi', 'bluetooth'):
                        self.assertEqual(status[radio]['soft_blocked'], bool(soft))
                        self.assertEqual(status[radio]['hard_blocked'], bool(hard))

    def test_persistent_soft_block_verification_accepts_either_hard_state(self):
        for hard in (0, 1):
            with self.subTest(hard=hard):
                self.adapter(0, 'wlan', 1, hard)
                self.adapter(1, 'bluetooth', 1, hard)
                self.system.block_all()
                self.system.block_bluetooth()

    def test_hard_block_alone_cannot_pass_persistent_soft_block_verification(self):
        self.adapter(0, 'wlan', 1, 0)
        self.adapter(1, 'bluetooth', 0, 1)
        with self.assertRaises(privacyctl.PrivacyError):
            self.system.block_all()
        with self.assertRaises(privacyctl.PrivacyError):
            self.system.block_bluetooth()
        status = privacyctl.Controller(self.system).status()
        self.assertFalse(status['bluetooth']['soft_blocked'])
        self.assertTrue(status['bluetooth']['hard_blocked'])

    def test_unreadable_adapter_soft_state_cannot_be_silently_ignored(self):
        self.adapter(0, 'bluetooth', 1, 0)
        broken = self.adapter(1, 'bluetooth', 1, 0)
        (broken / 'soft').unlink()
        with self.assertRaises(privacyctl.PrivacyError):
            self.system.block_bluetooth()

    def test_invalid_soft_value_is_not_a_verified_block(self):
        self.adapter(0, 'bluetooth', 3, 1)
        with self.assertRaises(privacyctl.PrivacyError):
            self.system.block_bluetooth()


if __name__ == "__main__":
    unittest.main(verbosity=2)
