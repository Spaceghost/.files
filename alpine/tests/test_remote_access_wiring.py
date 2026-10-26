"""Deployment wiring for the remote-access controller."""
import json
from pathlib import Path
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]


class RemoteAccessWiringTests(unittest.TestCase):
    def test_firewall_policy_has_a_dedicated_dynamic_chain(self):
        policy = REPO / "alpine/security/firewall/oldbook.nft"
        subprocess.run(["doas", "-n", "nft", "--check", "--file", str(policy)], check=True,
                       capture_output=True, text=True)
        text = policy.read_text()
        self.assertIn("chain remote_access", text)
        self.assertIn("tcp dport 22 jump remote_access", text)

    def test_openrc_service_starts_the_fail_closed_observer(self):
        service = REPO / "alpine/security/remote-access/oldbook-remote-access.initd"
        self.assertTrue(service.is_file())
        text = service.read_text()
        self.assertIn("command=/usr/local/sbin/oldbook-remote-access", text)
        self.assertIn('command_args="watch"', text)
        self.assertIn("need tailscale oldbook-firewall", text)

    def test_observer_and_ui_transitions_share_one_process_lock(self):
        controller = (REPO / "alpine/bin/oldbook-remote-access").read_text()
        self.assertIn("fcntl.flock", controller)
        self.assertIn("with operation_lock(paths.lock):", controller)
        self.assertGreaterEqual(controller.count("with operation_lock(paths.lock):"), 2)

    def test_installer_grants_only_named_controller_operations(self):
        installer = (REPO / "alpine/bin/install-desktop-system").read_text()
        self.assertIn("oldbook-remote-access", installer)
        for command in ("reconcile", "mode", "trust", "password", "key-add", "key-remove"):
            self.assertIn(f"args {command}", installer)
        self.assertNotIn("permit nopass jack as root cmd /usr/local/sbin/oldbook-sshd-toggle",
                         installer)
        self.assertNotIn("alpine/bin/oldbook-sshd-toggle').read_text", installer)
        self.assertIn("remote_was_running", installer)
        self.assertIn("if not remote_was_running:", installer)

    def test_swaync_remote_control_stays_between_wifi_and_art(self):
        config = json.loads((REPO / "alpine/desktop/.config/swaync/config.json").read_text())
        actions = config["widget-config"]["buttons-grid"]["actions"]
        labels = [row["label"] for row in actions]
        wifi = next(index for index, label in enumerate(labels) if "Wi-Fi" in label)
        remote = next(index for index, label in enumerate(labels) if "Remote access" in label)
        art = next(index for index, label in enumerate(labels) if "Next art" in label)
        self.assertEqual((remote, art), (wifi + 1, wifi + 2))


if __name__ == "__main__":
    unittest.main()
