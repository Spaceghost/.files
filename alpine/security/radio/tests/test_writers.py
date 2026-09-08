"""Writer identity checks with temporary proc fixtures; never signal a process."""
from contextlib import ExitStack
from pathlib import Path
import errno
import os
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
from privacyctl_runtime import writers

BOOT = '01234567-89ab-cdef-0123-456789abcdef'


def stat_text(pid=321, start=100):
    # Fields 3..21 precede starttime (field 22); comm can contain ')'.
    return f'{pid} (odd ) name) S ' + ' '.join(['0'] * 18) + f' {start} 0\n'


class WriterTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        (self.root / 'sys/kernel/random').mkdir(parents=True)
        (self.root / 'sys/kernel/random/boot_id').write_text(BOOT + '\n')
        for pid in ('1', '120', '321'):
            (self.root / pid / 'ns').mkdir(parents=True)
        (self.root / 'self').symlink_to('120')
        for namespace in ('pid', 'net'):
            (self.root / '120/ns' / namespace).write_bytes(b'namespace')
            os.link(self.root / '120/ns' / namespace, self.root / '1/ns' / namespace)
        (self.root / '321/ns/pid').write_bytes(b'private namespace')
        os.link(self.root / '120/ns/net', self.root / '321/ns/net')
        (self.root / '321/stat').write_text(stat_text())
        (self.root / '321/status').write_text('Name:\twriter\nNSpid:\t321\t1\n')
        self.stack.enter_context(patch.object(writers, '_PROC', self.root))
        self.stack.enter_context(patch.object(writers.os, 'getpid', return_value=120))
        self.stack.enter_context(patch.object(time, 'monotonic', return_value=10.0))
        self.ready = False
        self.waits = []
        self.stack.enter_context(patch.object(writers.select, 'select', side_effect=self.select))
        self.signals = []
        self.stack.enter_context(patch.object(signal, 'pidfd_send_signal', side_effect=self.send_signal))
        self.stack.enter_context(patch.object(writers.os, 'kill', side_effect=AssertionError('numeric PID signal')))
        self.stack.enter_context(patch.object(writers.os, 'waitpid', side_effect=AssertionError('unrelated waitpid')))
        self.fd = os.open(self.root / '321/stat', os.O_RDONLY)
        self.addCleanup(self.close_borrowed)

    def close_borrowed(self):
        try:
            os.close(self.fd)
        except OSError as error:
            if error.errno != errno.EBADF:
                raise

    def select(self, read, write, exceptional, timeout):
        self.assertEqual(read, [self.fd])
        self.assertEqual((write, exceptional), ([], []))
        self.waits.append(timeout)
        return (read if self.ready else [], [], [])

    def send_signal(self, fd, sig, siginfo=None, flags=0):
        self.signals.append((fd, sig, siginfo, flags))
        self.ready = True

    def record(self):
        info = (self.root / '321/ns/pid').stat()
        return {'pid': 321, 'start_time': 100, 'pidns': {'dev': info.st_dev, 'ino': info.st_ino},
                'nspid': 1, 'operation': 'native-address-add'}

    def test_context_verifies_observer_proc_view_and_namespace_ids(self):
        info = (self.root / '120/ns/pid').stat()
        net = (self.root / '120/ns/net').stat()
        self.assertEqual(writers.current_context(), {
            'boot_id': BOOT, 'observer_pidns': {'dev': info.st_dev, 'ino': info.st_ino},
            'target_netns': {'dev': net.st_dev, 'ino': net.st_ino}})

    def test_context_refuses_ancestor_proc_mount_even_if_self_namespace_matches(self):
        with patch.object(writers.os, 'getpid', return_value=2):
            with self.assertRaises(writers.WriterError):
                writers.current_context()

    def test_context_refuses_proc_init_in_another_pid_namespace(self):
        (self.root / '1/ns/pid').unlink()
        (self.root / '1/ns/pid').write_bytes(b'ancestor')
        with self.assertRaises(writers.WriterError):
            writers.current_context()

    def test_capture_records_actual_init_and_preserves_borrowed_pidfd(self):
        self.assertEqual(writers.capture_writer(321, self.fd, 'native-address-add'), self.record())
        os.fstat(self.fd)
        self.assertEqual(self.signals, [])

    def test_capture_rejects_non_init_shared_pidns_and_wrong_netns(self):
        for change in ('non-init', 'shared-pidns', 'wrong-netns'):
            with self.subTest(change=change):
                status = self.root / '321/status'
                status.write_text('NSpid:\t321\t1\n')
                if change == 'non-init':
                    status.write_text('NSpid:\t321\t2\n')
                if change == 'shared-pidns':
                    (self.root / '321/ns/pid').unlink()
                    os.link(self.root / '120/ns/pid', self.root / '321/ns/pid')
                if change == 'wrong-netns':
                    (self.root / '321/ns/pid').unlink()
                    (self.root / '321/ns/pid').write_bytes(b'private')
                    (self.root / '321/ns/net').unlink()
                    (self.root / '321/ns/net').write_bytes(b'wrong')
                with self.assertRaises(writers.WriterError):
                    writers.capture_writer(321, self.fd, 'native-address-add')
        os.fstat(self.fd)

    def test_capture_rejects_dead_pidfd_before_and_after_metadata(self):
        for readiness in ([([self.fd], [], [])], [([], [], []), ([self.fd], [], [])]):
            with self.subTest(readiness=readiness):
                with patch.object(writers.select, 'select', side_effect=readiness):
                    with self.assertRaises(writers.WriterError):
                        writers.capture_writer(321, self.fd, 'native-address-add')
        os.fstat(self.fd)

    def test_capture_rejects_oversize_and_ambiguous_metadata(self):
        for content in ('NSpid:\t321\t1\n' * 10000, 'NSpid:\t321\t1\nNSpid:\t321\t1\n',
                        'NSpid:\t999\t1\n', 'NSpid:\t1\n', 'NSpid:\t321\t+1\n'):
            with self.subTest(content=content[:50]):
                (self.root / '321/status').write_text(content)
                with self.assertRaises(writers.WriterError):
                    writers.capture_writer(321, self.fd, 'native-address-add')

    def test_writer_schema_rejects_bool_unknown_keys_and_unbounded_tags(self):
        for field, value in (('pid', True), ('pid', 1), ('start_time', 0), ('nspid', True),
                             ('nspid', 2), ('operation', 'x' * 65), ('operation', 'unsafe\n'),
                             ('pidns', {'dev': True, 'ino': 2}), ('pidns', {'dev': 0, 'ino': 2}),
                             ('pidns', {'dev': 1, 'ino': 1 << 63}), ('pid', 1 << 63),
                             ('start_time', 1 << 63), ('operation', 'native.command'),
                             ('operation', 'native1'), ('extra', 0)):
            with self.subTest(field=field, value=value):
                record = self.record()
                record[field] = value
                with self.assertRaises(writers.WriterError):
                    writers.validate_writer(record)


    def drain(self, **changes):
        context = writers.current_context()
        context.update(deadline=100.0)
        context.update(changes)
        with patch.object(writers.os, 'pidfd_open', return_value=self.fd) as opened:
            with patch.object(writers.time, 'monotonic', return_value=10.0):
                result = writers.drain_writer(self.record(), **context)
        opened.assert_called_once_with(321, 0)
        with self.assertRaises(OSError):
            os.fstat(self.fd)
        return result

    def test_drain_matching_live_init_signals_only_held_pidfd_and_waits(self):
        self.assertEqual(self.drain(), 'killed')
        self.assertEqual(self.signals, [(self.fd, signal.SIGKILL, None, 0)])
        self.assertTrue(all(0 <= wait <= 0.025 for wait in self.waits))

    def test_drain_ready_init_needs_no_signal_or_namespace_metadata(self):
        self.ready = True
        (self.root / '321/ns/pid').unlink()
        # Preserve the independently captured record before removing metadata.
        record = {'pid': 321, 'start_time': 100, 'pidns': {'dev': 4, 'ino': 55},
                  'nspid': 1, 'operation': 'native-address-add'}
        with patch.object(self, 'record', return_value=record):
            self.assertEqual(self.drain(), 'dead')
        self.assertEqual(self.signals, [])

    def test_drain_demonstrably_reused_pid_never_signals_replacement(self):
        (self.root / '321/stat').write_text(stat_text(start=101))
        (self.root / '321/status').unlink()
        self.assertEqual(self.drain(), 'reused')
        self.assertEqual(self.signals, [])

    def test_drain_matching_start_wrong_namespace_is_not_reuse(self):
        record = self.record()
        record['pidns']['ino'] += 1
        with patch.object(self, 'record', return_value=record):
            with self.assertRaises(writers.WriterError):
                self.drain()
        self.assertEqual(self.signals, [])
        with self.assertRaises(OSError):
            os.fstat(self.fd)

    def test_drain_matching_start_non_init_refuses(self):
        (self.root / '321/status').write_text('NSpid:\t321\t2\n')
        with self.assertRaises(writers.WriterError):
            self.drain()
        self.assertEqual(self.signals, [])

    def test_drain_metadata_missing_without_completion_refuses(self):
        (self.root / '321/status').unlink()
        with self.assertRaises(writers.WriterError):
            self.drain()
        self.assertEqual(self.signals, [])

    def test_drain_metadata_race_with_positive_readiness_proves_completion(self):
        real_open = os.open
        def disappear(path, flags, *args, **kwargs):
            if path == 'status':
                self.ready = True
                raise FileNotFoundError(errno.ENOENT, 'synthetic proc exit race')
            return real_open(path, flags, *args, **kwargs)
        with patch.object(writers.os, 'open', side_effect=disappear):
            self.assertEqual(self.drain(), 'dead')
        self.assertEqual(self.signals, [])

    def test_drain_only_pidfd_open_esrch_is_verified_absence(self):
        context = writers.current_context()
        with patch.object(writers.os, 'pidfd_open', side_effect=ProcessLookupError(errno.ESRCH, 'gone')):
            self.assertEqual(writers.drain_writer(self.record(), deadline=100.0, **context), 'absent')
        self.assertEqual(self.signals, [])

    def test_drain_pidfd_open_resource_or_permission_errors_are_not_absence(self):
        context = writers.current_context()
        for code in (errno.EPERM, errno.EMFILE, errno.ENOENT, errno.EINVAL):
            with self.subTest(code=code):
                with patch.object(writers.os, 'pidfd_open', side_effect=OSError(code, 'failure')):
                    with self.assertRaises(writers.WriterError):
                        writers.drain_writer(self.record(), deadline=100.0, **context)
        self.assertEqual(self.signals, [])

    def test_drain_boot_view_and_network_mismatch_refuse_before_pid_lookup(self):
        context = writers.current_context()
        for field, value in (('boot_id', '11234567-89ab-cdef-0123-456789abcdef'),
                             ('observer_pidns', {'dev': 0, 'ino': 1}),
                             ('target_netns', {'dev': 0, 'ino': 1})):
            with self.subTest(field=field):
                changed = dict(context, **{field: value})
                with patch.object(writers.os, 'pidfd_open', side_effect=AssertionError('PID lookup before context validation')):
                    with self.assertRaises(writers.WriterError):
                        writers.drain_writer(self.record(), deadline=100.0, **changed)
        self.assertEqual(self.signals, [])

    def test_drain_proc_view_mismatch_refuses_before_pid_lookup(self):
        context = writers.current_context()
        with patch.object(writers.os, 'getpid', return_value=2):
            with patch.object(writers.os, 'pidfd_open', side_effect=AssertionError('wrong PID view lookup')):
                with self.assertRaises(writers.WriterError):
                    writers.drain_writer(self.record(), deadline=100.0, **context)

    def test_drain_deadline_and_cancellation_before_signal_retain_writer(self):
        with self.assertRaises(writers.WriterError):
            self.drain(deadline=9.0)
        self.assertEqual(self.signals, [])
        def cancelled():
            raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.drain(check=cancelled)
        self.assertEqual(self.signals, [])

    def test_drain_wait_timeout_after_kill_is_not_completion(self):
        context = writers.current_context()
        clock = iter([10.0, 10.0, 10.0, 10.0, 101.0])
        with patch.object(writers.os, 'pidfd_open', return_value=self.fd):
            with patch.object(writers.time, 'monotonic', side_effect=lambda: next(clock, 101.0)):
                with patch.object(signal, 'pidfd_send_signal', side_effect=lambda *args: self.signals.append(args)):
                    with self.assertRaises(writers.WriterError):
                        writers.drain_writer(self.record(), deadline=100.0, **context)
        self.assertEqual(len(self.signals), 1)
        self.assertTrue(all(0 <= wait <= 0.025 for wait in self.waits))
        with self.assertRaises(OSError):
            os.fstat(self.fd)

    def test_drain_signal_error_without_readiness_refuses(self):
        with patch.object(signal, 'pidfd_send_signal', side_effect=PermissionError(errno.EPERM, 'denied')):
            with self.assertRaises(writers.WriterError):
                self.drain()


    def test_drain_matching_start_wrong_network_refuses(self):
        (self.root / '321/ns/net').unlink()
        (self.root / '321/ns/net').write_bytes(b'other network')
        with self.assertRaises(writers.WriterError):
            self.drain()
        self.assertEqual(self.signals, [])

    def test_drain_proc_directory_missing_does_not_mean_pidfd_absent(self):
        real_open = os.open
        def missing(path, flags, *args, **kwargs):
            if path == self.root / '321':
                raise FileNotFoundError(errno.ENOENT, 'missing proc metadata')
            return real_open(path, flags, *args, **kwargs)
        with patch.object(writers.os, 'open', side_effect=missing):
            with self.assertRaises(writers.WriterError):
                self.drain()
        self.assertEqual(self.signals, [])

    def test_capture_and_drain_keep_metadata_on_one_process_directory(self):
        record = self.record()
        real_open = os.open
        def replace_after_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if path == self.root / '321':
                (self.root / '321').rename(self.root / 'old-process')
                (self.root / '321').mkdir()
                (self.root / '321/stat').write_text(stat_text(start=200))
                (self.root / '321/status').write_text('NSpid:\t321\t2\n')
            return fd
        with patch.object(writers.os, 'open', side_effect=replace_after_open):
            self.assertEqual(writers.capture_writer(321, self.fd, 'native-address-add'), record)
        (self.root / '321/status').unlink()
        (self.root / '321/stat').unlink()
        (self.root / '321').rmdir()
        (self.root / 'old-process').rename(self.root / '321')
        with patch.object(writers.os, 'open', side_effect=replace_after_open):
            self.assertEqual(self.drain(), 'killed')
        self.assertEqual(self.signals, [(self.fd, signal.SIGKILL, None, 0)])

    def test_drain_cancellation_while_waiting_is_not_completion(self):
        def check():
            if self.signals:
                raise RuntimeError('cancelled during teardown')
        with patch.object(signal, 'pidfd_send_signal', side_effect=lambda *args: self.signals.append(args)):
            with self.assertRaisesRegex(RuntimeError, 'cancelled during teardown'):
                self.drain(check=check)
        self.assertEqual(len(self.signals), 1)
        with self.assertRaises(OSError):
            os.fstat(self.fd)

    def test_drain_signal_exit_race_requires_positive_readiness(self):
        def exited(*args):
            self.ready = True
            raise ProcessLookupError(errno.ESRCH, 'exited during signal')
        with patch.object(signal, 'pidfd_send_signal', side_effect=exited):
            self.assertEqual(self.drain(), 'dead')

    def test_drain_invalid_deadline_refuses_before_pid_lookup(self):
        context = writers.current_context()
        for deadline in (True, float('nan'), float('inf'), '100'):
            with self.subTest(deadline=deadline):
                with patch.object(writers.os, 'pidfd_open', side_effect=AssertionError('invalid deadline PID lookup')):
                    with self.assertRaises(writers.WriterError):
                        writers.drain_writer(self.record(), deadline=deadline, **context)

    def test_capture_refuses_malformed_start_time(self):
        for content in ('321 (writer) S 0\n', stat_text(pid=999), stat_text(start=0), stat_text(start='-1')):
            with self.subTest(content=content):
                (self.root / '321/stat').write_text(content)
                with self.assertRaises(writers.WriterError):
                    writers.capture_writer(321, self.fd, 'native-address-add')


    def test_drain_closes_pidfd_even_when_proc_directory_close_fails(self):
        real_close = os.close
        real_open = os.open
        proc_descriptors = []
        def track_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if path == self.root / '321':
                proc_descriptors.append(fd)
            return fd
        def close_failure(fd):
            real_close(fd)
            if fd in proc_descriptors:
                raise OSError(errno.EIO, 'synthetic close error')
        with patch.object(writers.os, 'open', side_effect=track_open):
            with patch.object(writers.os, 'close', side_effect=close_failure):
                with self.assertRaises(OSError):
                    self.drain()
        with self.assertRaises(OSError):
            os.fstat(self.fd)

    def test_drain_out_of_range_pidfd_argument_is_an_identity_error(self):
        context = writers.current_context()
        with patch.object(writers.os, 'pidfd_open', side_effect=OverflowError('pid_t range')):
            with self.assertRaises(writers.WriterError):
                writers.drain_writer(self.record(), deadline=100.0, **context)
        self.assertEqual(self.signals, [])


if __name__ == '__main__':
    unittest.main()
