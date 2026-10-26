"""Privileged remote-access controller behavior."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "alpine/bin/oldbook-remote-access"
PUBLIC_KEY = ("ssh-ed25519 "
              "AAAAC3NzaC1lZDI1NTE5AAAAIKcqbziAdFY7FhE8r8J7nmDx7/oYLptrwKBIohuV5SAR")


def load_controller():
    loader = importlib.machinery.SourceFileLoader("oldbook_remote_access", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeSystem:
    """Real state transitions with external command boundaries removed."""

    def __init__(self):
        self.tailscale = True
        self.sshd = True
        self.lan = True
        self.ssh_config = ""
        self.authorized_keys = ""
        self.network = {
            "uuid": "home-uuid", "ssid": "Home", "bssid": "aa:bb:cc:dd:ee:ff",
            "security": "WPA2-PSK", "interface": "wlan0",
            "subnets": ["192.0.2.0/24"],
        }
        self.events = []
        self.external = []

    def current_network(self):
        return dict(self.network)

    def remove_lan(self):
        self.lan = False
        self.events.append("remove-lan")

    def stop_sshd(self):
        self.sshd = False
        self.events.append("stop-sshd")

    def set_tailnet(self, enabled):
        self.tailscale = enabled
        self.events.append("tailnet-on" if enabled else "tailnet-off")

    def validate_sshd(self):
        self.events.append("validate-sshd")

    def start_sshd(self):
        self.sshd = True
        self.events.append("start-sshd")

    def add_lan(self, interface, subnets):
        self.lan = True
        self.events.append("add-lan")

    def install_sshd_config(self, text):
        self.ssh_config = text

    def install_authorized_keys(self, text):
        self.authorized_keys = text

    def fingerprint(self, _kind, _payload):
        return "SHA256:testfingerprint"

    def external_keys(self, _account):
        return list(self.external)

    def observed(self):
        return {"tailnet": self.tailscale, "sshd": self.sshd, "lan": self.lan}

    def remote_data(self, _state):
        return {
            "processes": [{"pid": 20, "ppid": 10, "started": 100.0,
                           "comm": "zsh", "account": "jack",
                           "connection": "100.64.0.8 4555 100.95.0.1 22"}],
            "authentication": {},
            "fleet": {"online": 1, "total": 2, "peers": [],
                      "addresses": {"100.64.0.8": {
                          "device": "field-laptop", "user": "alice@example.com"}}},
            "listeners": [], "serve": False, "funnel": False,
            "recovery": {"off_machine_backup": False, "package_archive": 90.0},
        }


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_controller()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        base = Path(self.folder.name)
        self.paths = self.module.Paths(base)
        self.system = FakeSystem()
        self.controller = self.module.Controller(self.paths, self.system)

    def test_first_reconcile_migrates_safely_to_tailnet_only(self):
        result = self.controller.reconcile()
        self.assertEqual(result["desired"], "tailnet")
        self.assertEqual(result["mode"], "tailnet")
        self.assertFalse(self.system.sshd)
        self.assertFalse(self.system.lan)
        self.assertTrue(self.system.tailscale)
        stored = json.loads(self.paths.config.read_text())
        self.assertEqual(stored["desired"], "tailnet")

    def test_lan_mode_is_refused_until_current_network_is_trusted(self):
        with self.assertRaisesRegex(ValueError, "trusted"):
            self.controller.set_mode("lan")
        self.assertEqual(self.controller.state()["desired"], "tailnet")
        self.assertFalse(self.system.lan)

    def test_friend_trust_then_lan_mode_persists_and_opens_narrowly(self):
        self.controller.set_trust("friend")
        result = self.controller.set_mode("lan")
        self.assertEqual(result["mode"], "lan")
        self.assertTrue(self.system.lan)
        self.assertTrue(self.system.sshd)
        stored = json.loads(self.paths.config.read_text())
        self.assertEqual(stored["desired"], "lan")
        self.assertEqual(stored["networks"]["home-uuid"]["trust"], "friend")

    def test_network_roam_closes_lan_but_keeps_desired_mode_for_return(self):
        self.controller.set_trust("home")
        self.controller.set_mode("lan")
        self.system.network["bssid"] = "11:22:33:44:55:66"
        result = self.controller.reconcile()
        self.assertEqual(result["desired"], "lan")
        self.assertEqual(result["mode"], "tailnet")
        self.assertFalse(self.system.lan)

    def test_marking_current_network_untrusted_cancels_lan_desire(self):
        self.controller.set_trust("home")
        self.controller.set_mode("lan")
        result = self.controller.set_trust("untrusted")
        self.assertEqual(result["desired"], "tailnet")
        self.assertFalse(self.system.lan)

    def test_key_enrollment_writes_public_material_and_metadata(self):
        result = self.controller.add_key("work laptop", PUBLIC_KEY)
        self.assertEqual(result["fingerprint"], "SHA256:testfingerprint")
        self.assertIn(PUBLIC_KEY, self.system.authorized_keys)
        self.assertIn("oldbook:work-laptop", self.system.authorized_keys)
        state = self.controller.state()
        self.assertEqual(state["keys"][0]["label"], "work laptop")

    def test_password_cannot_be_disabled_before_a_key_exists(self):
        with self.assertRaisesRegex(ValueError, "key"):
            self.controller.set_password(False)
        self.assertTrue(self.controller.state()["password"])

    def test_ssh_copy_id_key_allows_password_to_be_disabled_and_is_visible(self):
        self.system.external = [{"label": "field laptop", "kind": "ssh-ed25519",
                                 "fingerprint": "SHA256:external", "managed": False}]
        snapshot = self.controller.set_password(False)
        self.assertFalse(snapshot["password"])
        self.assertEqual(snapshot["keys"][0]["fingerprint"], "SHA256:external")
        self.assertFalse(snapshot["keys"][0]["managed"])

    def test_last_key_cannot_be_removed_while_password_is_disabled(self):
        enrolled = self.controller.add_key("work", PUBLIC_KEY)
        self.controller.set_password(False)
        with self.assertRaisesRegex(ValueError, "password"):
            self.controller.remove_key(enrolled["fingerprint"])
        self.assertEqual(len(self.controller.state()["keys"]), 1)

    def test_snapshot_permissions_allow_read_only_status_consumers(self):
        self.controller.reconcile()
        self.assertEqual(self.paths.snapshot.stat().st_mode & 0o777, 0o644)
        snapshot = json.loads(self.paths.snapshot.read_text())
        self.assertNotIn("public_key", json.dumps(snapshot))

    def test_reconcile_publishes_fleet_hatches_recovery_and_session_ledger(self):
        snapshot = self.controller.reconcile()
        self.assertEqual(snapshot["fleet"]["online"], 1)
        self.assertEqual(snapshot["sessions"][0]["identity"], "alice@example.com")
        self.assertEqual(snapshot["hatches"]["unexpected"], [])
        self.assertEqual(snapshot["recovery"]["state"], "AT RISK")
        self.assertTrue(self.paths.sessions.is_file())

    def test_failed_authentication_log_is_sanitized_and_deduplicated(self):
        system = self.module.System()
        system._recent_log = lambda path=Path("/var/log/messages"), limit=5000: [
            "Oct 26 host auth.info sshd-session[1]: Failed password for jack from 192.0.2.8 port 55 ssh2",
            "Oct 26 host auth.info sshd-session[1]: Failed password for jack from 192.0.2.8 port 55 ssh2",
            "Oct 26 host auth.info sshd-session[2]: Failed publickey for invalid user bad from 192.0.2.9 port 56 ssh2",
        ]
        failures = system._authentication_failures()
        self.assertEqual(len(failures), 2)
        self.assertEqual(failures[0]["account"], "jack")
        self.assertEqual(failures[1]["account"], "bad")
        self.assertEqual(failures[1]["method"], "key")
        self.assertNotIn("line", failures[0])


if __name__ == "__main__":
    unittest.main()
