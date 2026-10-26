"""Remote access policy, session history, and display behavior."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "alpine/security/remote_access.py"


def load_module():
    spec = importlib.util.spec_from_file_location("remote_access", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Machine:
    """Stateful boundary that exposes unsafe intermediate transitions."""

    def __init__(self, tailscale=True, sshd=True, lan=True):
        self.tailscale = tailscale
        self.sshd = sshd
        self.lan = lan
        self.snapshots = []

    def _record(self, operation):
        self.snapshots.append((operation, self.tailscale, self.sshd, self.lan))

    def remove_lan(self):
        self.lan = False
        self._record("remove-lan")

    def stop_sshd(self):
        self.sshd = False
        self._record("stop-sshd")

    def set_tailnet(self, enabled):
        self.tailscale = enabled
        self._record("tailnet-on" if enabled else "tailnet-off")

    def validate_sshd(self):
        self._record("validate-sshd")

    def start_sshd(self):
        self.sshd = True
        self._record("start-sshd")

    def add_lan(self, interface, subnets):
        self.lan = True
        self._record(("add-lan", interface, tuple(subnets)))


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = load_module()

    def context(self, **changes):
        value = {
            "trust": "home",
            "security": "WPA3",
            "interface": "wlan0",
            "subnets": ["192.0.2.0/24", "2001:db8:1::/64"],
            "password": False,
            "keys": 1,
        }
        value.update(changes)
        return value

    def test_unknown_network_forces_a_lan_request_to_tailnet(self):
        machine = Machine()
        result = self.remote.apply_mode(machine, "lan", self.context(trust="untrusted"))
        self.assertEqual(result["effective"], "tailnet")
        self.assertFalse(machine.lan)
        self.assertFalse(machine.sshd)
        self.assertTrue(machine.tailscale)
        self.assertIn("untrusted", result["reason"].lower())

    def test_friend_network_can_open_lan_after_sshd_is_ready(self):
        machine = Machine(tailscale=False, sshd=False, lan=False)
        result = self.remote.apply_mode(machine, "lan", self.context(trust="friend"))
        self.assertEqual(result["effective"], "lan")
        self.assertEqual([event[0] for event in machine.snapshots],
                         ["remove-lan", "tailnet-on", "validate-sshd",
                          "start-sshd", ("add-lan", "wlan0",
                                          ("192.0.2.0/24", "2001:db8:1::/64"))])
        self.assertTrue(machine.lan)

    def test_lan_needs_a_key_or_password(self):
        machine = Machine()
        result = self.remote.apply_mode(
            machine, "lan", self.context(password=False, keys=0))
        self.assertEqual(result["effective"], "tailnet")
        self.assertIn("authentication", result["reason"].lower())
        self.assertFalse(machine.lan)

    def test_open_network_can_never_open_lan(self):
        machine = Machine()
        result = self.remote.apply_mode(
            machine, "lan", self.context(trust="home", security="Open"))
        self.assertEqual(result["effective"], "tailnet")
        self.assertFalse(machine.lan)

    def test_turning_everything_off_closes_lan_before_stopping_services(self):
        machine = Machine()
        result = self.remote.apply_mode(machine, "off", self.context())
        self.assertEqual(result["effective"], "off")
        self.assertEqual([row[0] for row in machine.snapshots],
                         ["remove-lan", "stop-sshd", "tailnet-off"])
        self.assertFalse(machine.lan)
        self.assertFalse(machine.sshd)
        self.assertFalse(machine.tailscale)

    def test_firewall_fragment_is_scoped_to_interface_subnets_and_port(self):
        text = self.remote.firewall_fragment(
            "wlan0", ["192.0.2.0/24", "2001:db8:1::/64"])
        self.assertIn('iifname "wlan0"', text)
        self.assertIn("ip saddr 192.0.2.0/24", text)
        self.assertIn("ip6 saddr 2001:db8:1::/64", text)
        self.assertEqual(text.count("tcp dport 22"), 2)
        self.assertNotIn("0.0.0.0/0", text)
        self.assertNotIn("::/0", text)


class KeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = load_module()

    def test_valid_public_key_is_normalized_without_comment(self):
        key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKcqbziAdFY7FhE8r8J7nmDx7/oYLptrwKBIohuV5SAR laptop"
        kind, payload = self.remote.validate_public_key(key)
        self.assertEqual(kind, "ssh-ed25519")
        self.assertEqual(payload, key.split()[1])

    def test_private_key_and_options_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "public key"):
            self.remote.validate_public_key("-----BEGIN OPENSSH PRIVATE KEY-----")
        with self.assertRaisesRegex(ValueError, "type"):
            self.remote.validate_public_key(
                'command="id" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKcqbziAdFY7FhE8r8J7nmDx7/oYLptrwKBIohuV5SAR')

    def test_sshd_config_disables_password_but_keeps_keys(self):
        config = self.remote.sshd_config("jack", password=False,
                                         authorized_keys="/etc/oldbook/remote-access/authorized_keys")
        self.assertIn("PasswordAuthentication no", config)
        self.assertIn("KbdInteractiveAuthentication no", config)
        self.assertIn("PubkeyAuthentication yes", config)
        self.assertIn("Match User jack", config)
        self.assertIn("AuthorizedKeysFile .ssh/authorized_keys /etc/oldbook/remote-access/authorized_keys", config)
        self.assertIn("AllowTcpForwarding no", config)
        self.assertIn("PermitRootLogin no", config)


class NetworkTrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = load_module()

    def network(self, **changes):
        value = {"uuid": "network-uuid", "ssid": "Client House",
                 "bssid": "aa:bb:cc:dd:ee:ff", "security": "WPA2-PSK"}
        value.update(changes)
        return value

    def test_unknown_and_unapproved_access_points_are_untrusted(self):
        registry = {"network-uuid": {"trust": "friend", "ssid": "Client House",
                                     "security": "WPA2-PSK",
                                     "bssids": ["aa:bb:cc:dd:ee:ff"]}}
        self.assertEqual(self.remote.network_trust(self.network(), registry), "friend")
        self.assertEqual(self.remote.network_trust(
            self.network(bssid="11:22:33:44:55:66"), registry), "untrusted")
        self.assertEqual(self.remote.network_trust(
            self.network(uuid="unknown"), registry), "untrusted")

    def test_trusting_a_second_mesh_access_point_preserves_the_first(self):
        registry = {}
        registry = self.remote.remember_network_trust(
            registry, self.network(), "friend")
        registry = self.remote.remember_network_trust(
            registry, self.network(bssid="11:22:33:44:55:66"), "friend")
        self.assertEqual(registry["network-uuid"]["bssids"],
                         ["11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff"])

    def test_open_network_cannot_be_promoted(self):
        with self.assertRaisesRegex(ValueError, "Open"):
            self.remote.remember_network_trust(
                {}, self.network(security="Open"), "home")

    def test_marking_untrusted_does_not_need_an_access_point_identity(self):
        registry = self.remote.remember_network_trust(
            {}, self.network(bssid=""), "untrusted")
        self.assertEqual(registry["network-uuid"]["trust"], "untrusted")


class SessionLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = load_module()

    def test_missing_live_session_is_ended_and_expires_after_24_hours(self):
        existing = [{"id": "a", "live": True, "started": 100.0,
                     "identity": "alice", "processes": ["zsh"]},
                    {"id": "old", "live": False, "started": 1.0,
                     "ended": 100.0, "identity": "old"}]
        merged = self.remote.merge_sessions(existing, [], now=200.0)
        self.assertEqual(len(merged), 2)
        self.assertFalse(next(row for row in merged if row["id"] == "a")["live"])
        self.assertEqual(next(row for row in merged if row["id"] == "a")["ended"], 200.0)
        expired = self.remote.merge_sessions(merged, [], now=200.0 + 86400.0)
        self.assertEqual(expired, [])

    def test_observed_session_updates_processes_without_losing_start_time(self):
        existing = [{"id": "a", "live": True, "started": 100.0,
                     "identity": "alice", "processes": ["zsh"]}]
        observed = [{"id": "a", "live": True, "started": 190.0,
                     "identity": "alice", "processes": ["zsh", "tmux", "codex"]}]
        merged = self.remote.merge_sessions(existing, observed, now=200.0)
        self.assertEqual(merged[0]["started"], 100.0)
        self.assertEqual(merged[0]["processes"], ["zsh", "tmux", "codex"])

    def test_later_log_rotation_does_not_erase_proven_authentication(self):
        existing = [{"id": "a", "live": True, "started": 100.0,
                     "identity": "192.0.2.5", "auth": "key · work · SHA256:abc"}]
        observed = [{"id": "a", "live": True, "started": 150.0,
                     "identity": "192.0.2.5", "auth": "unknown"}]
        merged = self.remote.merge_sessions(existing, observed, now=200.0)
        self.assertEqual(merged[0]["auth"], "key · work · SHA256:abc")

    def test_conky_shows_twelve_sessions_then_more_count(self):
        sessions = []
        for number in range(15):
            sessions.append({
                "id": str(number), "live": number < 2,
                "started": 1000.0 - number, "ended": None if number < 2 else 1100.0 - number,
                "account": "jack", "identity": f"person-{number}",
                "source": "tailnet", "auth": "Tailscale identity",
                "processes": ["zsh", "tmux"] if number == 0 else [],
            })
        output = self.remote.render_conky(
            {"mode": "tailnet", "trust": "untrusted", "sessions": sessions},
            now=1200.0)
        self.assertIn("person-0", output)
        self.assertIn("zsh → tmux", output)
        self.assertIn("+ 3 MORE", output)
        self.assertNotIn("person-12", output)

    def test_conky_neutralizes_dynamic_conky_markup(self):
        output = self.remote.render_conky({
            "mode": "tailnet", "trust": "untrusted",
            "sessions": [{"id": "x", "live": True, "started": 10.0,
                          "identity": "${exec touch /tmp/bad}", "source": "tailnet",
                          "auth": "unknown", "processes": []}],
        }, now=20.0)
        self.assertNotIn("${exec", output)
        self.assertIn("＄", output)

    def test_process_chain_keeps_names_only_and_is_bounded(self):
        chain = self.remote.safe_process_chain([
            "/bin/zsh", "tmux: server", "/opt/codex/bin/codex --secret", "python3", "extra"])
        self.assertEqual(chain, ["zsh", "tmux", "codex", "python3"])

    def test_live_sessions_attribute_tailnet_identity_and_lan_key(self):
        processes = [
            {"pid": 20, "ppid": 10, "started": 100.0, "comm": "zsh",
             "account": "jack", "connection": "100.64.0.8 4555 100.95.0.1 22"},
            {"pid": 21, "ppid": 20, "started": 101.0, "comm": "tmux: server",
             "account": "jack", "connection": "100.64.0.8 4555 100.95.0.1 22"},
            {"pid": 30, "ppid": 11, "started": 105.0, "comm": "sftp-server",
             "account": "jack", "connection": "192.0.2.44 5666 192.0.2.2 22"},
        ]
        peers = {"100.64.0.8": {"device": "field-laptop", "user": "alice@example.com"}}
        auth = {("192.0.2.44", "5666"): {"method": "key", "fingerprint": "SHA256:abc"}}
        sessions = self.remote.sessions_from_processes(
            processes, peers, auth, {"SHA256:abc": "Alice work key"})
        self.assertEqual(len(sessions), 2)
        tailnet = next(row for row in sessions if row["source"] == "tailnet · field-laptop")
        self.assertEqual(tailnet["identity"], "alice@example.com")
        self.assertEqual(tailnet["auth"], "Tailscale identity")
        self.assertEqual(tailnet["processes"], ["zsh", "tmux"])
        lan = next(row for row in sessions if row["source"] == "LAN · 192.0.2.44")
        self.assertEqual(lan["auth"], "key · Alice work key · SHA256:abc")
        self.assertEqual(lan["processes"], ["sftp-server"])

    def test_password_and_unknown_auth_are_never_reported_as_keys(self):
        processes = [{"pid": 10, "ppid": 1, "started": 5.0, "comm": "zsh",
                      "account": "jack", "connection": "192.0.2.5 99 192.0.2.2 22"}]
        password = self.remote.sessions_from_processes(
            processes, {}, {("192.0.2.5", "99"): {"method": "password"}}, {})[0]
        unknown = self.remote.sessions_from_processes(processes, {}, {}, {})[0]
        self.assertEqual(password["auth"], "LAN password")
        self.assertEqual(unknown["auth"], "unknown")


class FleetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = load_module()

    def test_tailnet_summary_maps_users_and_sorts_online_first(self):
        document = {
            "User": {"1": {"LoginName": "alice@example.com"}},
            "Peer": {
                "node-b": {"HostName": "offline", "Online": False,
                           "TailscaleIPs": ["100.64.0.9"], "UserID": 1,
                           "LastSeen": "2026-10-25T01:00:00Z"},
                "node-a": {"HostName": "online", "Online": True,
                           "TailscaleIPs": ["100.64.0.8"], "UserID": 1,
                           "OS": "linux", "ExitNodeOption": True},
            },
        }
        summary = self.remote.summarize_tailnet(document)
        self.assertEqual(summary["online"], 1)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["peers"][0]["device"], "online")
        self.assertEqual(summary["peers"][0]["user"], "alice@example.com")
        self.assertTrue(summary["peers"][0]["exit_node"])

    def test_hatches_flag_only_non_loopback_unexpected_listeners(self):
        listeners = [
            {"address": "127.0.0.1", "port": 8766, "process": "fossil"},
            {"address": "0.0.0.0", "port": 22, "process": "sshd"},
            {"address": "0.0.0.0", "port": 8080, "process": "mystery"},
        ]
        hatches = self.remote.classify_hatches(
            listeners, {"mode": "lan", "observed": {"lan": True}}, serve=False, funnel=False)
        self.assertEqual([row["port"] for row in hatches["unexpected"]], [8080])
        self.assertEqual([row["port"] for row in hatches["known"]], [22])
        self.assertFalse(hatches["funnel"])


class PersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = load_module()

    def test_atomic_json_round_trip_has_private_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            self.remote.atomic_json(path, {"mode": "tailnet"}, mode=0o600)
            self.assertEqual(json.loads(path.read_text()), {"mode": "tailnet"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
