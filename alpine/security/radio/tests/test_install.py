"""Exercise permissions preparation and rollback without host device access."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / 'install'
LOADER = importlib.machinery.SourceFileLoader('radio_install', str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
install = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(install)


class FakeHost:
    def __init__(self):
        self.saved = {'mode': 0o664, 'acl_base64': 'cHJpdmF0ZSBhY2w='}
        self.current = dict(self.saved)
        self.calls = []
        self.failure = None
        self.changed = False

    def state(self):
        return {'rfkill0': {'type': 'wlan', 'soft': '1' if self.changed else '0', 'hard': '0'}}

    def permissions(self):
        return dict(self.current)

    def link_identity(self):
        return {'interface': 'wlan0', 'ssid': 'synthetic trusted network',
                'bssid': '02:00:00:00:00:01', 'addresses': []}

    def apply_permissions(self, saved=None):
        self.calls.append('restore' if saved else 'prepare')
        self.current = dict(saved) if saved else {'mode': 0o644, 'acl_base64': None}

    def udev(self):
        self.calls.append('udev')
        if self.failure == 'udev' and self.calls.count('udev') == 1:
            raise RuntimeError('fake udev failure')

    def verify(self):
        self.calls.append('verify')
        if self.failure == 'verify':
            raise RuntimeError('fake retained uaccess tag')
        if self.failure == 'changed':
            self.changed = True


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source.rules'
        self.source.write_text('synthetic reviewed rule\n')
        self.target = self.root / 'installed.rules'
        self.journal = self.root / 'journal'
        self.journal.mkdir()
        self.host = FakeHost()

    def run_prepare(self):
        return install.prepare(self.source, self.target, self.journal, self.host)

    def test_success_records_exact_private_backup_and_keeps_radio_state(self):
        result = self.run_prepare()
        before = json.loads((result / 'before.json').read_text())
        after = json.loads((result / 'result.json').read_text())
        self.assertEqual(before['device_permissions'], self.host.saved)
        self.assertIsNone(before['rule_before'])
        self.assertEqual(after['status'], 'prepared')
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertEqual(self.host.calls, ['prepare', 'udev', 'verify'])
        self.assertEqual(self.host.current, {'mode': 0o644, 'acl_base64': None})
        self.assertTrue(after['jack_can_read_rfkill'])
        self.assertTrue(after['jack_cannot_write_rfkill'])
        self.assertTrue(after['wifi_link_unchanged'])
        self.assertEqual(stat.S_IMODE(result.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in result.iterdir()))

    def test_udev_or_verification_failure_restores_mode_acl_and_removes_only_new_rule(self):
        for failure in ('udev', 'verify'):
            with self.subTest(failure=failure):
                self.host = FakeHost()
                self.host.failure = failure
                with self.assertRaises(RuntimeError):
                    self.run_prepare()
                self.assertEqual(self.host.current, self.host.saved)
                self.assertFalse(self.target.exists())
                self.assertEqual(self.host.calls[-1], 'restore')

    def test_failure_preserves_preexisting_matching_rule(self):
        self.target.write_bytes(self.source.read_bytes())
        self.target.chmod(0o640)
        self.host.failure = 'verify'
        with self.assertRaises(RuntimeError):
            self.run_prepare()
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertEqual(self.host.current, self.host.saved)

    def test_different_rule_and_symlink_refused_before_permissions_change(self):
        self.target.write_text('existing custom policy\n')
        with self.assertRaises(RuntimeError):
            self.run_prepare()
        self.assertEqual(self.target.read_text(), 'existing custom policy\n')
        self.target.unlink()
        self.target.symlink_to(self.source)
        with self.assertRaises(RuntimeError):
            self.run_prepare()
        self.assertEqual(self.host.calls, [])
        self.assertEqual(list(self.journal.iterdir()), [])

    def test_radio_change_fails_verification_without_manipulating_radios(self):
        self.host.failure = 'changed'
        with self.assertRaises(RuntimeError):
            self.run_prepare()
        self.assertEqual(self.host.current, self.host.saved)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.host.changed)  # No permission to change radio state.

    def test_wifi_identity_change_rolls_permissions_back(self):
        original = self.host.link_identity()
        changed = dict(original, ssid='unexpected new network')
        with mock.patch.object(self.host, 'link_identity', side_effect=[original, changed, changed]):
            with self.assertRaises(RuntimeError):
                self.run_prepare()
        self.assertEqual(self.host.current, self.host.saved)
        self.assertFalse(self.target.exists())

    def test_radio_device_rule_keeps_status_readable_without_write_grants(self):
        rule = SCRIPT.parent / 'root/etc/udev/rules.d/72-privacy-rfkill.rules'
        content = rule.read_text()
        self.assertIn('MODE="0644"', content)
        self.assertIn('TAG-="uaccess"', content)
        self.assertNotIn('GROUP="netdev"', content)

    def test_unknown_activation_mode_is_rejected_before_any_host_work(self):
        result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--activate'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)

    def test_privileged_path_rejects_symlinks_and_writable_source(self):
        self.target.symlink_to(self.source)
        with self.assertRaises(RuntimeError):
            install.owned_path(self.target)
        self.source.chmod(0o666)
        with self.assertRaises(RuntimeError):
            install.owned_path(self.source)


if __name__ == '__main__':
    unittest.main()
