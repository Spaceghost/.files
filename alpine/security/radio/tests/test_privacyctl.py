#!/usr/bin/env python3
"""Protocol and fail-off contracts for the staged controller, no host radio."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys

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
        self.timeline = timeline if timeline is not None else []

    def block_all(self):
        self.calls.append("block-all")
        self.timeline.append("system:block-all")
        self.blocked = True

    def unblock_wifi(self):
        self.calls.append("unblock-wifi")
        self.timeline.append("system:unblock-wifi")
        self.blocked = False

    def prepare_addresses(self, profile):
        self.calls.append("dhcp:" + profile)
        self.timeline.append("system:dhcp:" + profile)

    def states(self, kind):
        return ["0" if self.blocked else "1"]


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
        self.old_read_profile = privacyctl.read_profile
        self.temp = tempfile.TemporaryDirectory()
        privacyctl.PROFILE_FILE = Path(self.temp.name) / "profiles"
        privacyctl.SESSION_FILE = Path(self.temp.name) / "session"
        privacyctl.read_profile = lambda profile, _path=None: (
            (0, "shmecklebucket") if profile == "shmecklebucket" else (1, "Exact iPhone"))

    def tearDown(self):
        privacyctl.PROFILE_FILE = self.old_profile
        privacyctl.SESSION_FILE = self.old_session
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


class ProtocolTests(unittest.TestCase):
    def test_non_ok_reply_is_never_success(self):
        control = object.__new__(privacyctl.WpaControl)
        control.request = lambda _: "FAIL-BUSY"
        with self.assertRaises(privacyctl.PrivacyError): control.expect_ok("RECONNECT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
