"""Pure schema and disposable-file journal tests; no kernel network effects."""
import base64
import importlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
try:
    journal = importlib.import_module('privacyctl_runtime.journal')
except ModuleNotFoundError as error:
    if error.name != 'privacyctl_runtime.journal':
        raise
    journal = None


def record(phase='alias-intent', sequence=1):
    return {
        'version': 1, 'sequence': sequence, 'generation': 'a' * 32,
        'boot_id': '12345678-1234-1234-1234-123456789abc',
        'observer_pidns': {'dev': 4, 'ino': 100},
        'target_netns': {'dev': 4, 'ino': 101},
        'interface': 'wlan0', 'ifindex': 7, 'phase': phase,
        'cookie': 'privacyctl:' + 'a' * 32,
        'previous_alias': base64.b64encode(b'prior\xff alias').decode('ascii'),
        'resources': {'addresses': [], 'routes': [], 'provider': None,
                      'dns_contents': []},
        'writers': {'native': None, 'dhcp': None},
    }


def writer():
    return {'pid': 9876, 'start_time': 50, 'pidns': {'dev': 4, 'ino': 200},
            'nspid': 1, 'operation': 'set-alias'}


def active_record():
    value = record('active')
    value['resources'] = {
        'addresses': [{'family': 4, 'cidr': '192.0.2.10/24', 'protocol': 196},
                      {'family': 6, 'cidr': '2001:db8::10/64', 'protocol': 196}],
        'routes': [{'family': 4, 'destination': 'default', 'gateway': '192.0.2.1',
                    'protocol': 196, 'metric': 42701, 'source': '192.0.2.10'},
                   {'family': 6, 'destination': '2001:db8::/64', 'gateway': None,
                    'protocol': 196, 'metric': 42700, 'source': '2001:db8::10'}],
        'provider': 'privacyctl.' + 'a' * 32 + '.wlan0',
        'dns_contents': ['nameserver 192.0.2.53\nnameserver 2001:db8::53\n'],
    }
    value['writers']['native'] = writer()
    return value


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(journal, 'bounded journal implementation is missing')

    def test_valid_record_is_independent_deep_copy_with_exact_alias(self):
        value = active_record()
        normalized = journal.validate_record(value)
        self.assertEqual(normalized, value)
        normalized['resources']['addresses'].clear()
        self.assertEqual(len(value['resources']['addresses']), 2)
        self.assertEqual(base64.b64decode(normalized['previous_alias']), b'prior\xff alias')

    def test_rejects_missing_extra_and_non_json_top_fields(self):
        values = [None, [], {'version': 1}, dict(record(), extra='x')]
        for key in record():
            value = record()
            del value[key]
            values.append(value)
        for value in values:
            with self.subTest(value=value), self.assertRaises(journal.JournalError):
                journal.validate_record(value)

    def test_rejects_invalid_identity_and_scalar_types(self):
        cases = {'version': [True, 2, 1.0], 'sequence': [True, 0, -1, 2**63],
                 'generation': ['A' * 32, 'a' * 31],
                 'boot_id': ['12345678-1234-1234-1234-123456789ABC', 'bad'],
                 'observer_pidns': [{'dev': True, 'ino': 1}, {'dev': 1, 'ino': 0}],
                 'target_netns': [{'dev': 1, 'ino': 2, 'extra': 3}],
                 'ifindex': [True, 0], 'interface': ['', '.', '..', '../wlan0',
                                                       'x' * 16, 'wl an0'],
                 'cookie': ['privacyctl:' + 'b' * 32], 'phase': ['unknown']}
        for key, invalids in cases.items():
            for invalid in invalids:
                value = record()
                value[key] = invalid
                with self.subTest(key=key, invalid=invalid), self.assertRaises(journal.JournalError):
                    journal.validate_record(value)

    def test_alias_rejects_noncanonical_base64_nul_and_oversize(self):
        for alias in ['!', 'YQ', 'YQ===', 'YR==', 'YQ==\n',
                      base64.b64encode(b'\x00').decode(),
                      base64.b64encode(b'x' * 256).decode()]:
            value = record()
            value['previous_alias'] = alias
            with self.subTest(alias=alias), self.assertRaises(journal.JournalError):
                journal.validate_record(value)

    def test_resource_selectors_reject_broad_wrong_or_noncanonical_values(self):
        cases = [('addresses', 'protocol', 195), ('addresses', 'family', True),
                 ('addresses', 'cidr', '192.0.2.10'),
                 ('addresses', 'cidr', '2001:db8::1/64'),
                 ('routes', 'protocol', 0), ('routes', 'metric', 42699),
                 ('routes', 'metric', 42956), ('routes', 'metric', True),
                 ('routes', 'destination', '192.0.2.1/24'),
                 ('routes', 'gateway', '2001:db8::1'),
                 ('routes', 'source', '192.0.2.01')]
        for collection, key, invalid in cases:
            value = active_record()
            value['resources'][collection][0][key] = invalid
            with self.subTest(collection=collection, key=key), self.assertRaises(journal.JournalError):
                journal.validate_record(value)

    def test_resource_limits_and_duplicate_candidates(self):
        value = active_record()
        value['resources']['addresses'] *= 2
        value['resources']['routes'] *= 2
        value['resources']['dns_contents'] *= 2
        normalized = journal.validate_record(value)
        self.assertEqual(len(normalized['resources']['addresses']), 2)
        self.assertEqual(len(normalized['resources']['routes']), 2)
        self.assertEqual(len(normalized['resources']['dns_contents']), 1)
        for key, count in [('addresses', 17), ('routes', 65), ('dns_contents', 5)]:
            value = active_record()
            value['resources'][key] = [value['resources'][key][0]] * count
            with self.subTest(key=key), self.assertRaises(journal.JournalError):
                journal.validate_record(value)

    def test_dns_provider_and_contents_are_constrained(self):
        for content in ['search example.com\n', 'nameserver invalid\n',
                        'nameserver 192.0.2.53 # comment\n', 'nameserver café\n',
                        'nameserver 192.0.2.53\n' * 110, 'nameserver fe80::1%wlan0\n']:
            value = active_record()
            value['resources']['dns_contents'] = [content]
            with self.subTest(content=content), self.assertRaises(journal.JournalError):
                journal.validate_record(value)
        for provider in [None, 'privacyctl.' + 'b' * 32 + '.wlan0', '../provider']:
            value = active_record()
            value['resources']['provider'] = provider
            with self.subTest(provider=provider), self.assertRaises(journal.JournalError):
                journal.validate_record(value)

    def test_writer_identity_requires_namespace_init_without_executable_fields(self):
        cases = [('pid', True), ('pid', 1), ('start_time', 0), ('nspid', True),
                 ('nspid', 2), ('operation', '/bin/sh'), ('operation', 'x' * 65),
                 ('pidns', {'dev': 1, 'ino': 0}), ('executable', '/bin/sh')]
        for key, invalid in cases:
            value = active_record()
            value['writers']['native'][key] = invalid
            with self.subTest(key=key), self.assertRaises(journal.JournalError):
                journal.validate_record(value)

    def test_phases_cannot_claim_clean_with_resources_or_live_writers(self):
        for phase in ['alias-intent', 'alias-restore-intent', 'clean']:
            value = active_record()
            value['phase'] = phase
            with self.subTest(phase=phase), self.assertRaises(journal.JournalError):
                journal.validate_record(value)
        for phase, slot in [('alias-restore-intent', 'dhcp'), ('clean', 'native'),
                            ('clean', 'dhcp')]:
            value = record(phase)
            value['writers'][slot] = writer()
            with self.subTest(phase=phase, slot=slot), self.assertRaises(journal.JournalError):
                journal.validate_record(value)
        value = record()
        value['writers']['native'] = writer()
        self.assertEqual(journal.validate_record(value), value)


@unittest.skipUnless(os.geteuid() == 0, 'root-owned journal fixtures require root')
class JournalTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(journal, 'bounded journal implementation is missing')
        self.temporary = tempfile.TemporaryDirectory(prefix='privacyctl-journal-', dir='/root')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / 'lease.json'
        self.store = journal.Journal(self.directory)

    def put_bytes(self, data):
        self.path.write_bytes(data)
        self.path.chmod(0o600)

    def test_durable_create_increment_reload_and_clean_remove(self):
        self.assertIsNone(self.store.read())
        self.store.write(record())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)
        second = journal.Journal(self.directory)
        self.assertEqual(second.read(), record())
        second.write(record('clean', 2))
        second.remove()
        self.assertFalse(self.path.exists())
        self.assertIsNone(second.read())

    def test_write_validates_before_creating_any_file(self):
        value = record()
        value['cookie'] = 'wrong'
        with self.assertRaises(journal.JournalError):
            self.store.write(value)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_sequence_and_unread_existing_record_are_rejected(self):
        with self.assertRaises(journal.JournalError):
            self.store.write(record(sequence=2))
        self.store.write(record())
        before = self.path.read_bytes()
        for value in [record(), record(sequence=3)]:
            with self.assertRaises(journal.JournalError):
                self.store.write(value)
        with self.assertRaises(journal.JournalError):
            journal.Journal(self.directory).write(record(sequence=2))
        self.assertEqual(self.path.read_bytes(), before)

    def test_loaded_record_and_returned_write_copy_cannot_grant_remove(self):
        result = self.store.write(record())
        result['phase'] = 'clean'
        loaded = self.store.read()
        loaded['phase'] = 'clean'
        with self.assertRaises(journal.JournalError):
            self.store.remove()
        self.assertTrue(self.path.exists())

    def test_changed_generation_is_refused_even_at_next_sequence(self):
        self.store.write(record())
        value = record(sequence=2)
        value['generation'] = 'b' * 32
        value['cookie'] = 'privacyctl:' + 'b' * 32
        with self.assertRaises(journal.JournalError):
            self.store.write(value)
        self.assertEqual(self.store.read()['generation'], 'a' * 32)

    def test_replacement_same_bytes_or_in_place_change_blocks_mutation(self):
        for change in ['replacement', 'in-place', 'missing']:
            with self.subTest(change=change):
                self.store = journal.Journal(self.directory)
                self.store.write(record('clean'))
                original = self.path.read_bytes()
                if change == 'replacement':
                    other = self.directory / 'replacement'
                    other.write_bytes(original)
                    other.chmod(0o600)
                    other.replace(self.path)
                elif change == 'in-place':
                    self.put_bytes(original + b' ')
                else:
                    self.path.unlink()
                with self.assertRaises(journal.JournalError):
                    self.store.remove()
                with self.assertRaises(journal.JournalError):
                    self.store.write(record('clean', 2))
                self.path.unlink(missing_ok=True)

    def test_malformed_json_is_never_repaired_or_deleted(self):
        good = json.dumps(record()).encode()
        malformed = [b'{', good[:-1] + b', "version": 1}', b'[' * 1000 + b']' * 1000,
                     b' ' * 65537, good + b'\x00', b'\xff', b'{"version":NaN}']
        for data in malformed:
            with self.subTest(data=data[:50]):
                self.put_bytes(data)
                store = journal.Journal(self.directory)
                with self.assertRaises(journal.JournalError):
                    store.read()
                with self.assertRaises(journal.JournalError):
                    store.write(record())
                with self.assertRaises(journal.JournalError):
                    store.remove()
                self.assertEqual(self.path.read_bytes(), data)

    def test_rejects_symlink_hardlink_fifo_wrong_mode_and_owner(self):
        for unsafe in ['symlink', 'hardlink', 'fifo', 'mode', 'owner']:
            with self.subTest(unsafe=unsafe):
                other = self.directory / 'other'
                other.write_bytes(json.dumps(record()).encode())
                other.chmod(0o600)
                if unsafe == 'symlink':
                    self.path.symlink_to(other)
                elif unsafe == 'hardlink':
                    os.link(other, self.path)
                elif unsafe == 'fifo':
                    os.mkfifo(self.path, 0o600)
                else:
                    self.put_bytes(other.read_bytes())
                    if unsafe == 'mode':
                        self.path.chmod(0o640)
                    else:
                        os.chown(self.path, 1000, 1000)
                with self.assertRaises((journal.JournalError, OSError)):
                    self.store.read()
                self.path.unlink()
                other.unlink()

    def test_rejects_unsafe_path_components_and_directory_replacement(self):
        private = self.directory / 'private'
        private.mkdir(mode=0o700)
        link = self.directory / 'link'
        link.symlink_to(private, target_is_directory=True)
        for directory in [link, self.directory / '..' / self.directory.name]:
            with self.subTest(directory=directory), self.assertRaises((journal.JournalError, OSError)):
                journal.Journal(directory).read()
        for mode in [0o755, 0o770]:
            private.chmod(mode)
            with self.subTest(mode=mode), self.assertRaises(journal.JournalError):
                journal.Journal(private).read()
        private.chmod(0o700)
        self.store.write(record('clean'))
        moved = self.directory / 'old'
        self.path.rename(moved)
        self.put_bytes(moved.read_bytes())
        with self.assertRaises(journal.JournalError):
            self.store.remove()

    def test_invalid_filenames_never_escape_directory(self):
        for filename in ['', '.', '..', '../lease.json', '/lease.json', 'a/b', 'x\x00']:
            with self.subTest(filename=filename), self.assertRaises(journal.JournalError):
                journal.Journal(self.directory, filename).read()

    def test_failed_file_fsync_or_rename_preserves_original(self):
        self.store.write(record())
        before = self.path.read_bytes()
        for syscall in ['fsync', 'rename']:
            with self.subTest(syscall=syscall):
                with patch.object(journal.os, syscall, side_effect=OSError('injected ' + syscall)):
                    with self.assertRaises(OSError):
                        self.store.write(record('active', 2))
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.directory.iterdir()), [self.path])
        self.store.write(record('active', 2))

    def test_directory_fsync_failure_surfaces_and_requires_reload(self):
        self.store.write(record())
        real_fsync = os.fsync

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('injected directory fsync')
            real_fsync(fd)

        with patch.object(journal.os, 'fsync', side_effect=fail_directory):
            with self.assertRaises(OSError):
                self.store.write(record('active', 2))
        self.assertEqual(json.loads(self.path.read_bytes())['sequence'], 2)
        with self.assertRaises(journal.JournalError):
            self.store.write(record('clean', 3))
        self.assertEqual(self.store.read()['sequence'], 2)
        self.store.write(record('clean', 3))
        with patch.object(journal.os, 'fsync', side_effect=fail_directory):
            with self.assertRaises(OSError):
                self.store.remove()
        self.assertFalse(self.path.exists())

    def test_same_content_foreign_replacement_after_rename_is_not_adopted(self):
        self.store.write(record())
        real_rename = os.rename

        def replace_after_rename(*args, **kwargs):
            real_rename(*args, **kwargs)
            foreign = self.directory / 'foreign'
            foreign.write_bytes(self.path.read_bytes())
            foreign.chmod(0o600)
            real_rename(foreign, self.path)

        with patch.object(journal.os, 'rename', side_effect=replace_after_rename):
            with self.assertRaises(journal.JournalError):
                self.store.write(record('active', 2))
        self.assertEqual(json.loads(self.path.read_bytes())['sequence'], 2)
        with self.assertRaises(journal.JournalError):
            self.store.write(record('clean', 3))

    def test_root_sticky_ancestor_is_safe_but_foreign_or_unprotected_is_not(self):
        with tempfile.TemporaryDirectory(prefix='privacyctl-journal-', dir='/tmp') as directory:
            store = journal.Journal(directory)
            store.write(record())
            self.assertEqual(store.read(), record())
        ancestor = self.directory / 'ancestor'
        ancestor.mkdir(mode=0o700)
        private = ancestor / 'private'
        private.mkdir(mode=0o700)
        for mode, uid in [(0o777, 0), (0o700, 1000)]:
            ancestor.chmod(mode)
            os.chown(ancestor, uid, uid)
            with self.subTest(mode=mode, uid=uid), self.assertRaises(journal.JournalError):
                journal.Journal(private).read()
            os.chown(ancestor, 0, 0)

    def test_partial_writes_complete_and_zero_write_preserves_old_record(self):
        real_write = os.write

        def short_write(fd, data):
            return real_write(fd, data[:17])

        with patch.object(journal.os, 'write', side_effect=short_write):
            self.store.write(record())
        self.assertEqual(self.store.read(), record())
        before = self.path.read_bytes()
        with patch.object(journal.os, 'write', return_value=0):
            with self.assertRaises(OSError):
                self.store.write(record('active', 2))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.directory.iterdir()), [self.path])

    def test_failed_read_revokes_old_clean_removal_permission(self):
        self.store.write(record('clean'))
        with patch.object(journal.os, 'read', side_effect=OSError('injected read error')):
            with self.assertRaises(OSError):
                self.store.read()
        with self.assertRaises(journal.JournalError):
            self.store.remove()
        self.assertTrue(self.path.exists())

    def test_unlink_failure_retains_clean_record(self):
        self.store.write(record('clean'))
        with patch.object(journal.os, 'unlink', side_effect=OSError('injected unlink error')):
            with self.assertRaises(OSError):
                self.store.remove()
        self.assertEqual(self.store.read(), record('clean'))


if __name__ == '__main__':
    unittest.main()
