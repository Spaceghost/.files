"""Desktop presentation for remote access."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "alpine/desktop/.local/bin/oldbook-remote-access"


def load_ui():
    loader = importlib.machinery.SourceFileLoader("oldbook_remote_access_ui", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class RemoteAccessUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = load_ui()

    def snapshot(self, **changes):
        value = {
            "mode": "tailnet", "desired": "tailnet", "trust": "untrusted",
            "network": {"ssid": "Cafe"}, "password": True, "keys": [],
            "degraded": False, "sessions": [],
            "fleet": {"online": 4, "total": 26, "peers": []},
            "hatches": {"known": [], "unexpected": [], "serve": False, "funnel": False},
            "recovery": {"state": "AT RISK", "gap": "No off-machine backup."},
        }
        value.update(changes)
        return value

    def test_waybar_distinguishes_all_three_modes_and_degraded(self):
        states = {}
        for mode in ("off", "tailnet", "lan"):
            states[mode] = self.ui.waybar(self.snapshot(mode=mode))["class"]
        self.assertEqual(states, {"off": "disabled", "tailnet": "tailnet", "lan": "lan"})
        self.assertEqual(self.ui.waybar(self.snapshot(degraded=True))["class"], "warning")

    def test_menu_exposes_mode_trust_password_keys_and_diagnostics(self):
        rows = self.ui.menu_rows(self.snapshot(keys=[{
            "label": "work", "fingerprint": "SHA256:abc", "kind": "ssh-ed25519"}]))
        text = "\n".join(rows)
        self.assertIn("Mode · Tailnet only", text)
        self.assertIn("Network · Cafe · Untrusted", text)
        self.assertIn("LAN password · On", text)
        self.assertIn("Keys · 1 enrolled", text)
        self.assertIn("24-hour activity", text)
        self.assertIn("Fleet · 4/26 online", text)
        self.assertIn("Open hatches", text)
        self.assertIn("Recovery Beacon · AT RISK", text)

    def test_report_contains_session_process_and_security_sections(self):
        snapshot = self.snapshot(sessions=[{
            "live": True, "account": "jack", "identity": "alice@example.com",
            "source": "tailnet · laptop", "auth": "Tailscale identity",
            "started": 100.0, "processes": ["zsh", "tmux", "codex"],
        }])
        report = self.ui.report(snapshot, now=200.0)
        self.assertIn("24-HOUR ACTIVITY", report)
        self.assertIn("alice@example.com", report)
        self.assertIn("zsh → tmux → codex", report)
        self.assertIn("TAILNET FLEET", report)
        self.assertIn("OPEN HATCHES", report)
        self.assertIn("RECOVERY BEACON", report)

    def test_conky_delegates_to_bounded_twelve_row_renderer(self):
        rows = [{"id": str(index), "live": True, "started": float(index),
                 "account": "jack", "identity": f"peer-{index}",
                 "source": "tailnet", "auth": "Tailscale identity", "processes": []}
                for index in range(13)]
        rendered = self.ui.conky(self.snapshot(sessions=rows), now=20.0)
        self.assertIn("+ 1 MORE", rendered)

    def test_session_announcements_fire_once_for_connect_and_disconnect(self):
        notices = []
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "sessions.json"
            empty = self.snapshot(sessions=[])
            live = self.snapshot(sessions=[{
                "id": "one", "live": True, "started": 100.0, "account": "jack",
                "identity": "alice@example.com", "source": "tailnet · laptop",
                "auth": "Tailscale identity", "processes": ["zsh"]}])
            ended = self.snapshot(sessions=[dict(live["sessions"][0], live=False,
                                                  ended=160.0)])
            tell = lambda title, body: notices.append((title, body))
            self.ui.announce(empty, marker=marker, tell=tell)
            self.ui.announce(live, marker=marker, tell=tell)
            self.ui.announce(live, marker=marker, tell=tell)
            self.ui.announce(ended, marker=marker, tell=tell)
        self.assertEqual([title for title, _body in notices],
                         ["Remote session connected", "Remote session ended"])
        self.assertIn("alice@example.com", notices[0][1])

    def test_authentication_failure_warnings_are_rate_limited(self):
        notices = []
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "failures.json"
            tell = lambda title, body: notices.append((title, body))
            self.ui.announce_failures([], marker=marker, tell=tell, now=0)
            self.ui.announce_failures(
                [{"id": "a", "account": "jack", "source": "192.0.2.8",
                  "method": "password"}], marker=marker, tell=tell, now=301)
            self.ui.announce_failures(
                [{"id": "a"}, {"id": "b", "account": "jack",
                  "source": "192.0.2.9", "method": "password"}],
                marker=marker, tell=tell, now=302)
            self.ui.announce_failures(
                [{"id": "a"}, {"id": "b"}, {"id": "c", "account": "jack",
                  "source": "192.0.2.10", "method": "key"}],
                marker=marker, tell=tell, now=602)
        self.assertEqual(len(notices), 2)
        self.assertEqual(notices[0][0], "Remote authentication failed")
        self.assertIn("2 attempts", notices[1][1])


if __name__ == "__main__":
    unittest.main()
