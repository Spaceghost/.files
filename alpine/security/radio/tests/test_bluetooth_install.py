"""Bluetooth preparation/rollback tests; no host radios or udev commands run."""
import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).parents[1]


def load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / filename))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


install = load('bluetooth_install', 'install-bluetooth')
permissions = load('permissions_base', 'install')
parser_check = load('bluetooth_parser_check', 'verify-bluetooth-rule')


class FakeHost:
    def __init__(self):
        device = lambda kind, inode: {'type': kind, 'name': kind, 'soft': '0', 'hard': '0',
                                      'syspath': '/synthetic/' + kind, 'inode': inode, 'device': 7}
        self.current = {'radios': {'rfkill0': device('bluetooth', 31), 'rfkill1': device('wlan', 32)},
                        'wifi': {'ssid': 'synthetic home', 'bssid': '02:00:00:00:00:01',
                                 'addresses': ['192.0.2.2/24']},
                        'routes': {'-4': [{'gateway': '192.0.2.1'}], '-6': []}}
        self.calls = []
        self.fail = None

    def snapshot(self):
        return copy.deepcopy(self.current)

    def no_active_peripherals(self):
        if self.fail == 'peripheral':
            raise RuntimeError('synthetic Bluetooth input present')
        return {'bluetooth_inputs': False}

    def reload(self):
        self.calls.append('reload')
        if self.fail == 'reload':
            raise RuntimeError('synthetic reload failure')

    def apply(self):
        self.calls.append('apply-bluetooth')
        self.current['radios']['rfkill0']['soft'] = '1'
        if self.fail == 'apply':
            raise RuntimeError('synthetic apply failure')
        if self.fail == 'wifi':
            self.current['wifi']['ssid'] = 'unexpected network'

    def restore(self, name, saved):
        self.calls.append('restore:' + name)
        current = self.current['radios'].get(name)
        if current is None or any(current[key] != saved[key] for key in
                                  ('type', 'name', 'syspath', 'inode', 'device')):
            raise RuntimeError('synthetic device registration changed')
        self.current['radios'][name]['soft'] = saved['soft']


class BluetoothTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / 'source.rules'
        self.source.write_text('synthetic rule\n')
        self.target = self.directory / 'target.rules'
        self.journals = self.directory / 'journals'
        self.journals.mkdir()
        self.host = FakeHost()
        self.before = self.host.snapshot()

    def prepare(self):
        return install.prepare(self.source, self.target, self.journals, self.host,
                               permissions.write_private)

    def rollback(self, result):
        return install.rollback(Path(result['journal']), self.target, self.source.read_bytes(),
                                self.host, permissions.write_private)

    def test_prepare_then_explicit_rollback_preserves_wlan_and_restores_bluetooth(self):
        result = self.prepare()
        self.assertTrue(install.TOKEN.fullmatch(result['token']))
        self.assertEqual(self.host.current['radios']['rfkill0']['soft'], '1')
        install.wlan_unchanged(self.before, self.host.snapshot())
        self.assertEqual(self.rollback(result)['status'], 'rolled_back')
        self.assertEqual(self.host.snapshot(), self.before)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.host.calls, ['apply-bluetooth', 'reload', 'restore:rfkill0'])
        self.assertEqual(stat.S_IMODE(Path(result['journal']).stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600
                            for path in Path(result['journal']).iterdir()))

    def test_apply_failure_rolls_back_before_returning_failure(self):
        self.host.fail = 'apply'
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertEqual(self.host.snapshot(), self.before)
        self.assertFalse(self.target.exists())

    def test_wifi_change_aborts_without_attempting_to_reconnect_it(self):
        self.host.fail = 'wifi'
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertEqual(self.host.current['radios']['rfkill0']['soft'], '0')
        self.assertEqual(self.host.current['wifi']['ssid'], 'unexpected network')
        self.assertEqual(self.host.calls, ['apply-bluetooth', 'reload', 'restore:rfkill0'])

    def test_preexisting_rule_is_never_owned_or_modified(self):
        for matching in (False, True):
            with self.subTest(matching=matching):
                original = self.source.read_bytes() if matching else b'previous custom policy\n'
                self.target.write_bytes(original)
                self.target.chmod(0o640)
                with self.assertRaises(RuntimeError):
                    self.prepare()
                self.assertEqual(self.target.read_bytes(), original)
                self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
                self.assertEqual(self.host.calls, [])
        self.assertEqual(list(self.journals.iterdir()), [])

    def test_rollback_refuses_reused_rfkill_index_without_touching_new_device(self):
        result = self.prepare()
        self.host.current['radios']['rfkill0']['inode'] = 99
        with self.assertRaises(RuntimeError):
            self.rollback(result)
        self.assertEqual(self.host.current['radios']['rfkill0']['soft'], '1')
        self.assertTrue(self.target.exists())
        self.assertEqual(self.host.calls, ['apply-bluetooth'])

    def test_changed_inventory_is_rejected_before_removing_rule(self):
        result = self.prepare()
        self.host.current['radios']['rfkill2'] = dict(
            self.host.current['radios']['rfkill0'], inode=91, soft='0')
        with self.assertRaises(RuntimeError):
            install.bluetooth_matches(self.before, self.host.snapshot())
        with self.assertRaises(RuntimeError):
            self.rollback(result)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.host.calls, ['apply-bluetooth'])

    def test_recreated_identical_rule_is_not_removed_by_old_token(self):
        result = self.prepare()
        old = self.target.with_name('retained-old-rule')
        self.target.rename(old)
        self.target.write_bytes(self.source.read_bytes())
        with self.assertRaises(RuntimeError):
            self.rollback(result)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.host.calls, ['apply-bluetooth'])

    def test_rule_instance_metadata_change_is_not_claimed_by_old_token(self):
        result = self.prepare()
        self.target.chmod(0o640)
        with self.assertRaises(RuntimeError):
            self.rollback(result)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.host.calls, ['apply-bluetooth'])

    def test_failed_old_rollback_cannot_remove_a_new_successful_preparation(self):
        first = self.prepare()
        self.host.fail = 'reload'
        with self.assertRaises(RuntimeError):
            self.rollback(first)
        self.host.fail = None
        second = self.prepare()
        calls = list(self.host.calls)
        with self.assertRaises(RuntimeError):
            self.rollback(first)
        self.assertTrue(self.target.exists())
        self.assertEqual(self.host.calls, calls)
        self.assertEqual(self.host.current['radios']['rfkill0']['soft'], '1')
        self.assertEqual(self.rollback(second)['status'], 'rolled_back')
        self.assertEqual(self.host.current['radios']['rfkill0']['soft'], '1')

    def test_overlapping_preparation_is_rejected_by_nonblocking_lock(self):
        with install.transaction_lock(self.journals):
            with self.assertRaises(BlockingIOError):
                with install.transaction_lock(self.journals):
                    self.fail('a second transaction acquired the same lock')

    def test_rollback_refuses_concurrently_modified_rule(self):
        result = self.prepare()
        self.target.write_text('another reviewed policy\n')
        with self.assertRaises(RuntimeError):
            self.rollback(result)
        self.assertEqual(self.target.read_text(), 'another reviewed policy\n')
        self.assertEqual(self.host.calls, ['apply-bluetooth'])

    def test_repeated_successful_rollback_is_a_noop(self):
        result = self.prepare()
        self.rollback(result)
        previous = list(self.host.calls)
        self.host.current['radios']['rfkill0']['soft'] = '1'
        self.assertEqual(self.rollback(result)['status'], 'rolled_back')
        self.assertEqual(self.host.calls, previous)
        self.assertEqual(self.host.current['radios']['rfkill0']['soft'], '1')

    def test_reloading_failure_does_not_attempt_to_unblock_bluetooth(self):
        result = self.prepare()
        self.host.fail = 'reload'
        with self.assertRaises(RuntimeError):
            self.rollback(result)
        self.assertNotIn('restore:rfkill0', self.host.calls)
        self.assertEqual(self.host.current['radios']['rfkill0']['soft'], '1')

    def test_existing_blocked_state_stays_blocked_after_rollback(self):
        self.host.current['radios']['rfkill0']['soft'] = '1'
        result = self.prepare()
        self.rollback(result)
        self.assertEqual(self.host.current['radios']['rfkill0']['soft'], '1')

    def test_peripheral_preflight_and_invalid_tokens_have_no_actions(self):
        self.host.fail = 'peripheral'
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertEqual(self.host.calls, [])
        for token in ('../escape', '/var/lib/other', 'a' * 31, 'a' * 33, 'A' * 32, 'x' * 32):
            self.assertIsNone(install.TOKEN.fullmatch(token))


class ParserNamespaceTests(unittest.TestCase):
    def test_live_or_partly_isolated_namespaces_are_rejected_before_mount(self):
        for mount_same, network_same in ((True, True), (True, False), (False, True)):
            with self.subTest(mount_same=mount_same, network_same=network_same):
                def identity(path):
                    kind = path.rsplit('/', 1)[-1]
                    same = mount_same if kind == 'mnt' else network_same
                    return kind + (':1' if '/1/' in path or same else ':2')
                with mock.patch.object(parser_check.os, 'readlink', side_effect=identity), mock.patch.object(
                        parser_check, 'run') as run:
                    with self.assertRaises(RuntimeError):
                        parser_check.isolated(Path('/unused'), Path('/unused/rule'))
                run.assert_not_called()


class BoundedRestoreTests(unittest.TestCase):
    def test_snapshot_state_and_identity_come_from_one_held_registration(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            device = root / 'rfkill0'
            device.mkdir()
            for key, value in {'type': 'bluetooth', 'name': 'original', 'soft': '0', 'hard': '0'}.items():
                (device / key).write_text(value)
            original_inode = device.stat().st_ino
            original_open = install.os.open
            replaced = False

            def raced_open(path, flags, *args, **options):
                nonlocal replaced
                if path == 'type' and options.get('dir_fd') is not None and not replaced:
                    replaced = True
                    device.rename(root / 'old-registration')
                    device.mkdir()
                    for key, value in {'type': 'wlan', 'name': 'replacement', 'soft': '1', 'hard': '0'}.items():
                        (device / key).write_text(value)
                return original_open(path, flags, *args, **options)

            with mock.patch.object(install.os, 'open', side_effect=raced_open):
                with self.assertRaises(RuntimeError):
                    install.radio_snapshot(root)
            self.assertTrue(replaced)
            self.assertEqual((root / 'old-registration/soft').read_text(), '0')
            self.assertEqual((device / 'soft').read_text(), '1')
            self.assertNotEqual(original_inode, device.stat().st_ino)

    def test_real_child_refuses_replacement_wlan_directory_after_parent_snapshot(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            device = root / 'rfkill0'
            device.mkdir()
            for key, value in {'type': 'bluetooth', 'name': 'synthetic', 'soft': '1'}.items():
                (device / key).write_text(value)
            info = device.stat()
            saved = {'type': 'bluetooth', 'name': 'synthetic', 'soft': '0', 'hard': '0',
                     'syspath': str(device), 'inode': info.st_ino, 'device': info.st_dev}
            current = dict(saved, soft='1')
            host = object.__new__(install.Host)
            original_run = install.run

            def raced_run(arguments, **options):
                device.rename(root / 'original-registration')
                device.mkdir()
                for key, value in {'type': 'wlan', 'name': 'replacement', 'soft': '1'}.items():
                    (device / key).write_text(value)
                return original_run(arguments, **options)

            with mock.patch.object(host, 'snapshot', return_value={'radios': {'rfkill0': current}}), mock.patch.object(
                    install, 'run', side_effect=raced_run):
                with self.assertRaises(subprocess.CalledProcessError):
                    host.restore('rfkill0', saved)
            self.assertEqual((device / 'soft').read_text(), '1')
            self.assertEqual((root / 'original-registration/soft').read_text(), '1')

    def test_real_child_restores_only_matching_private_bluetooth_device(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)
            for key, value in {'type': 'bluetooth', 'name': 'synthetic', 'soft': '1'}.items():
                (path / key).write_text(value)
            info = path.stat()
            saved = {'type': 'bluetooth', 'name': 'synthetic', 'soft': '0', 'hard': '0',
                     'syspath': str(path), 'inode': info.st_ino, 'device': info.st_dev}
            host = object.__new__(install.Host)
            with mock.patch.object(host, 'snapshot', return_value={'radios': {'rfkill0': dict(saved, soft='1')}}):
                host.restore('rfkill0', saved)
            self.assertEqual((path / 'soft').read_text(), '0')


if __name__ == '__main__':
    unittest.main()
