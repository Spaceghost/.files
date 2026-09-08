"""Synthetic guard/barrier checks; never execute the native fixture."""
import copy
import os
from pathlib import Path
import stat
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
import verify_radio_owner_failures as fixture


class SurvivorFixtureTests(unittest.TestCase):
    def setUp(self):
        self.host = {'net': 'net:[1]', 'mnt': 'mnt:[2]', 'pid': 'pid:[3]'}
        self.outer = {'net': 'net:[4]', 'mnt': 'mnt:[5]', 'pid': 'pid:[6]'}
        self.inner = {'net': 'net:[4]', 'mnt': 'mnt:[7]', 'pid': 'pid:[8]'}

    def test_parent_death_change_requires_guard_before_loading_libc(self):
        with patch.object(fixture, 'survivor_guard', side_effect=RuntimeError('unsafe')), \
             patch('ctypes.CDLL', side_effect=AssertionError('libc reached')):
            with self.assertRaisesRegex(RuntimeError, 'unsafe'):
                fixture.allow_survival(self.host, self.outer)

    def test_only_guarded_init_parent_death_signal_is_cleared_and_verified(self):
        calls = []
        def prctl(option, value, *_args):
            calls.append(option)
            if option == 2:
                value._obj.value = 0
            return 0
        with patch.object(fixture, 'survivor_guard', return_value=(17, self.inner)) as guard, \
             patch.object(fixture.os, 'readlink', return_value='30'), \
             patch.dict(os.environ, {'OPENRESOLV_HOST_PID': '30'}), \
             patch('ctypes.CDLL', return_value=types.SimpleNamespace(prctl=prctl)):
            self.assertEqual(fixture.allow_survival(self.host, self.outer), (17, self.inner))
        guard.assert_called_once_with(self.host, self.outer, require_init=True)
        self.assertEqual(calls, [1, 2])

    def test_parent_death_setup_error_is_not_reported_as_survival(self):
        with patch.object(fixture, 'survivor_guard', return_value=(17, self.inner)), \
             patch.object(fixture.os, 'readlink', return_value='30'), \
             patch.dict(os.environ, {'OPENRESOLV_HOST_PID': '30'}), \
             patch('ctypes.CDLL', return_value=types.SimpleNamespace(prctl=lambda *_: -1)):
            with self.assertRaises(OSError):
                fixture.allow_survival(self.host, self.outer)

    def test_wrong_original_gate_pid_refuses_before_parent_death_change(self):
        with patch.object(fixture, 'survivor_guard', return_value=(17, self.inner)), \
             patch.object(fixture.os, 'readlink', return_value='30'), \
             patch.dict(os.environ, {'OPENRESOLV_HOST_PID': '31'}), \
             patch('ctypes.CDLL', side_effect=AssertionError('libc reached')):
            with self.assertRaisesRegex(RuntimeError, 'gate PID'):
                fixture.allow_survival(self.host, self.outer)

    def guard_context(self, *, current=None, mount_override=None, self_link='1'):
        mounts = {name: ('tmpfs', 'privacyctl-dhcp-fixture')
                  for name in ('/etc', '/run', '/var', '/dev', '/sys')}
        mounts.update(mount_override or {})
        text = '\n'.join(f'{i} 0 0:1 / {name} rw - {kind} {source} rw'
                         for i, (name, (kind, source)) in enumerate(mounts.items(), 1))
        links = {'/proc/self': self_link, '/proc/1/ns/pid': self.inner['pid'],
                 '/proc/self/fd/17/1/ns/pid': self.outer['pid'],
                 '/proc/self/fd/17/self/ns/net': self.outer['net']}
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(fixture.guards, 'guard_private', return_value=current or self.inner))
        stack.enter_context(patch.object(fixture.os, 'getpid', return_value=1))
        stack.enter_context(patch.object(fixture.os, 'readlink', side_effect=lambda p: links[str(p)]))
        stack.enter_context(patch.object(fixture.Path, 'lstat', return_value=types.SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0)))
        stack.enter_context(patch.object(fixture, 'read_json', return_value={'host': self.host, 'expected': self.outer}))
        stack.enter_context(patch.object(fixture.Path, 'read_text', return_value=text))
        stack.enter_context(patch.object(fixture.Path, 'exists', return_value=False))
        stack.enter_context(patch.dict(os.environ, {'OPENRESOLV_HOST_PROC_FD': '17'}))
        stack.enter_context(patch.object(fixture.os, 'fstat', return_value=types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o500)))
        stack.enter_context(patch('fcntl.fcntl', return_value=os.O_RDONLY))
        return stack

    def test_guard_accepts_only_private_child_namespaces_and_original_proc_view(self):
        with self.guard_context():
            self.assertEqual(fixture.survivor_guard(self.host, self.outer, require_init=True), (17, self.inner))
        for key in ('net', 'mnt', 'pid'):
            changed = dict(self.inner)
            changed[key] = self.host[key] if key == 'net' else self.outer[key]
            with self.guard_context(current=changed), self.assertRaises(RuntimeError):
                fixture.survivor_guard(self.host, self.outer, require_init=True)
        with self.guard_context(self_link='99'), self.assertRaises(RuntimeError):
            fixture.survivor_guard(self.host, self.outer, require_init=True)

    def test_guard_rejects_missing_wrong_and_subordinate_var_mounts(self):
        for override in ({'/var': ('ext4', 'host')}, {'/var': ('tmpfs', 'wrong')},
                         {'/var/lib': ('tmpfs', 'privacyctl-dhcp-fixture')}):
            with self.guard_context(mount_override=override), self.assertRaises(RuntimeError):
                fixture.survivor_guard(self.host, self.outer, require_init=True)

    def barrier(self, *, dead_index=None, same_observer=False):
        rows = [{'pid': value, 'start_time': str(value + 100), 'namespaces': dict(self.inner)}
                for value in (30, 31, 32, 33)]
        rows[3]['namespaces']['pid'] = 'pid:[9]'
        rows[3]['namespaces']['mnt'] = 'mnt:[10]'
        proof = {'writer': {'pid': 30, 'operation': 'native-survivor'}, 'init': rows[0],
                 'descendants': rows[1:], 'old_owner': {'pid': 20, 'start_time': '120'}}
        handles = []
        class Handle:
            def __init__(self, record, *_):
                self.fd = record['pid']
                self.closed = False
                self.ready = len(handles) == dead_index
                handles.append(self)
            def dead(self): return self.ready
            def close(self): self.closed = True
        observer = proof['old_owner'] if same_observer else {'pid': 21, 'start_time': '121'}
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(fixture.base, 'fixture_guard'))
        stack.enter_context(patch.object(fixture, 'process_record', return_value=observer))
        stack.enter_context(patch.object(fixture, 'Handle', Handle))
        stack.enter_context(patch('privacyctl_runtime.writers.capture_writer', return_value=copy.deepcopy(proof['writer'])))
        stack.enter_context(patch.object(fixture, 'append_event'))
        return stack, proof, handles

    def test_wrong_init_or_duplicate_descendant_refuses_before_capture(self):
        for change in ('init', 'duplicate'):
            stack, proof, handles = self.barrier()
            if change == 'init':
                proof['init']['pid'] = 39
            else:
                proof['descendants'][0]['pid'] = proof['init']['pid']
            with stack, self.assertRaisesRegex(RuntimeError, 'distinct original identities'):
                fixture.SurvivorBarrier(proof, self.host, self.outer, 'invocation')
            self.assertEqual(handles, [])

    def test_new_observer_requires_every_original_process_live_at_entry(self):
        for index in range(4):
            stack, proof, handles = self.barrier(dead_index=index)
            with stack, self.assertRaisesRegex(RuntimeError, 'alive'):
                fixture.SurvivorBarrier(proof, self.host, self.outer, 'invocation')
            self.assertTrue(all(h.closed for h in handles))
        stack, proof, handles = self.barrier(same_observer=True)
        with stack, self.assertRaisesRegex(RuntimeError, 'new observer'):
            fixture.SurvivorBarrier(proof, self.host, self.outer, 'invocation')

    def test_real_drain_result_and_all_ready_pidfds_precede_cleanup(self):
        stack, proof, handles = self.barrier()
        with stack:
            barrier = fixture.SurvivorBarrier(proof, self.host, self.outer, 'invocation')
            with self.assertRaisesRegex(RuntimeError, 'before'):
                barrier.require_drained()
            def drain(record, **kwargs):
                self.assertEqual(record, proof['writer'])
                self.assertEqual(kwargs, {'deadline': 7})
                for handle in handles: handle.ready = True
                return 'killed'
            self.assertEqual(barrier.drain(proof['writer'], drain, deadline=7), 'killed')
            barrier.require_drained()
            barrier.close()
        self.assertTrue(all(h.closed for h in handles))

    def test_early_death_wrong_result_or_remaining_child_never_opens_cleanup(self):
        for result, survivor in [('dead', False), ('killed', True)]:
            stack, proof, handles = self.barrier()
            with stack:
                barrier = fixture.SurvivorBarrier(proof, self.host, self.outer, 'invocation')
                def drain(*args, **kwargs):
                    for h in handles: h.ready = True
                    if survivor: handles[-1].ready = False
                    return result
                with self.assertRaises(RuntimeError): barrier.drain(proof['writer'], drain)
                with self.assertRaises(RuntimeError): barrier.require_drained()
                barrier.close()


if __name__ == '__main__':
    unittest.main()
