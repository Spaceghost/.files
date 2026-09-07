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


if __name__ == "__main__":
    unittest.main(verbosity=2)
