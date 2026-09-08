"""Different-boot store transitions, using only disposable files."""
import copy
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from test_journal import active_record, record, writer
from privacyctl_runtime import journal

CONTEXT = {'boot_id': '22345678-1234-1234-1234-123456789abc',
           'observer_pidns': {'dev': 4, 'ino': 300},
           'target_netns': {'dev': 4, 'ino': 301}}


def retired(value=None):
    value = active_record() if value is None else copy.deepcopy(value)
    value.update(version=2, phase='reboot-dns', recovery_context=copy.deepcopy(CONTEXT))
    value['resources']['addresses'] = []
    value['resources']['routes'] = []
    value['writers'] = {'native': None, 'dhcp': None}
    return value


class RebootValidationTests(unittest.TestCase):
    def test_v2_preserves_provenance_and_only_dns_candidates(self):
        value = retired()
        self.assertEqual(journal.validate_record(value), value)
        for field, wrong in [('version', 1), ('phase', 'active'), ('phase', 'clean'),
                             ('recovery_context', {}), ('recovery_context', dict(CONTEXT, extra=1))]:
            with self.subTest(field=field, wrong=wrong), self.assertRaises(journal.JournalError):
                journal.validate_record(dict(value, **{field: wrong}))
        for key in ('addresses', 'routes'):
            bad = retired(); bad['resources'][key] = active_record()['resources'][key]
            with self.assertRaises(journal.JournalError): journal.validate_record(bad)
        bad = retired(); bad['writers']['dhcp'] = writer()
        with self.assertRaises(journal.JournalError): journal.validate_record(bad)

    def test_v2_cannot_claim_same_boot_as_original_writers(self):
        bad = retired(); bad['recovery_context']['boot_id'] = bad['boot_id']
        with self.assertRaises(journal.JournalError): journal.validate_record(bad)

    def test_reboot_clean_rejects_resources_and_writers(self):
        value = retired(); value['phase'] = 'reboot-clean'
        with self.assertRaises(journal.JournalError): journal.validate_record(value)
        value['resources'] = record()['resources']
        self.assertEqual(journal.validate_record(value), value)
        value['writers']['native'] = writer()
        with self.assertRaises(journal.JournalError): journal.validate_record(value)


@unittest.skipUnless(os.geteuid() == 0, 'root-owned disposable journal directories required')
class RebootStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name); self.path.chmod(0o700)
        self.store = journal.Journal(self.path)
        self.original = active_record()
        self.store.write(self.original)

    def test_rollover_preserves_dns_and_original_identity_and_sequence(self):
        value = self.store.rollover_boot(CONTEXT)
        expected = retired(self.original); expected['sequence'] += 1
        self.assertEqual(value, expected)
        self.assertEqual(journal.Journal(self.path).read(), expected)
        self.assertEqual(stat.S_IMODE((self.path / 'lease.json').stat().st_mode), 0o600)
        with self.assertRaises(journal.JournalError): self.store.rollover_boot(CONTEXT)
        value['sequence'] += 1; value['writers']['native'] = writer()
        self.store.write(value)
        newer = dict(CONTEXT, boot_id='32345678-1234-1234-1234-123456789abc')
        self.assertIsNone(self.store.rollover_boot(newer)['writers']['native'])

    def test_normal_write_cannot_rollover_or_change_recovery_context(self):
        value = retired(self.original); value['sequence'] += 1
        with self.assertRaises(journal.JournalError): self.store.write(value)
        self.store.rollover_boot(CONTEXT)
        value = self.store.read(); value['sequence'] += 1
        value['recovery_context']['observer_pidns']['ino'] += 1
        with self.assertRaises(journal.JournalError): self.store.write(value)

    def test_rollover_rejects_same_boot_namespace_change_and_unread_or_replaced_disk(self):
        context = dict(CONTEXT, boot_id=self.original['boot_id'])
        with self.assertRaises(journal.JournalError): self.store.rollover_boot(context)
        with self.assertRaises(journal.JournalError): journal.Journal(self.path).rollover_boot(CONTEXT)
        destination = self.path / 'lease.json'
        data = destination.read_bytes(); destination.unlink(); destination.write_bytes(data); destination.chmod(0o600)
        with self.assertRaises(journal.JournalError): self.store.rollover_boot(CONTEXT)
        self.assertEqual(destination.read_bytes(), data)

    def test_rollover_fsync_failures_recover_exact_old_or_new_disk(self):
        for after in (False, True):
            with self.subTest(after=after):
                self.store = journal.Journal(self.path); previous = self.store.read()
                context = dict(CONTEXT, boot_id=('4' if after else '3') + CONTEXT['boot_id'][1:])
                sync = os.fsync
                def fail(fd):
                    if stat.S_ISDIR(os.fstat(fd).st_mode) == after:
                        raise OSError('injected rollover fsync')
                    sync(fd)
                with patch.object(journal.os, 'fsync', fail), self.assertRaises(OSError):
                    self.store.rollover_boot(context)
                disk = journal.Journal(self.path).read()
                self.assertEqual(disk['version'], 2 if after else previous['version'])
                if after:
                    self.assertEqual(disk['recovery_context'], context)
                else:
                    self.assertEqual(disk, previous)
                self.assertEqual(disk['resources']['provider'], previous['resources']['provider'])

    def test_reboot_clean_exact_instance_removal(self):
        value = self.store.rollover_boot(CONTEXT)
        with self.assertRaises(journal.JournalError): self.store.remove()
        value.update(phase='reboot-clean', sequence=value['sequence'] + 1,
                     resources=record()['resources'])
        self.store.write(value); self.store.remove()
        self.assertIsNone(journal.Journal(self.path).read())
