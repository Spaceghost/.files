"""Scheduling must stay confined to the desktop and stop at child processes."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'bin/mbp-intel-ui-priority'


def load_helper():
    loader = importlib.machinery.SourceFileLoader('ui_priority', str(SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class PriorityTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.is_file(), 'The bounded desktop priority helper is missing')
        self.helper = load_helper()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / 'home'
        self.proc = Path(self.temporary.name) / 'proc'
        self.uid = os.getuid()

    def process(self, executable='/usr/bin/waybar', argv=None, uid=None):
        pid = self.proc / '123'
        pid.mkdir(parents=True, exist_ok=True)
        exe = pid / 'exe'
        exe.unlink(missing_ok=True)
        exe.symlink_to(executable)
        (pid / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in
                                    (argv or [executable])) + b'\0')
        owner = self.uid if uid is None else uid
        (pid / 'status').write_text(f'Name:\twaybar\nUid:\t{owner}\t{owner}\t{owner}\t{owner}\nTgid:\t123\n')
        (pid / 'stat').write_text('123 (waybar) S ' + '0 ' * 18 + '321 0\n')
        return pid

    def identify(self):
        return self.helper.identify(123, self.uid, self.home, self.proc)

    def test_accepts_system_ui_but_not_spoofed_name(self):
        self.process()
        self.assertEqual(self.identify()['name'], 'waybar')
        self.process(executable=sys.executable, argv=['waybar'])
        self.assertIsNone(self.identify())

    def test_ignores_other_users_and_non_ui_executables(self):
        self.process(uid=self.uid + 1)
        self.assertIsNone(self.identify())
        for command in ('/bin/sh', '/usr/bin/foot', '/usr/bin/ollama'):
            self.process(executable=command)
            self.assertIsNone(self.identify())

    def test_python_is_limited_to_exact_desktop_daemon_path(self):
        script = self.home / '.files/alpine/desktop/.local/bin/mbp-intel-carousel'
        script.parent.mkdir(parents=True)
        script.write_text('# daemon fixture\n')
        deployed = self.home / '.local/bin/mbp-intel-carousel'
        deployed.parent.mkdir(parents=True)
        deployed.symlink_to(script)
        self.process(executable=sys.executable, argv=[sys.executable, str(deployed), 'daemon'])
        self.assertEqual(self.identify()['name'], 'mbp-intel-carousel')
        self.process(executable=sys.executable, argv=[sys.executable, '-S', str(deployed), 'daemon'])
        self.assertIsNotNone(self.identify(), 'The approved daemon -S startup must be recognized')
        self.assertEqual(self.identify()['name'], 'mbp-intel-carousel')
        for argv in ([sys.executable, str(deployed), 'show'],
                     [sys.executable, str(deployed), 'daemon', '--extra'],
                     [sys.executable, '/tmp/mbp-intel-carousel', 'daemon'],
                     [sys.executable, '-c', str(deployed)]):
            self.process(executable=sys.executable, argv=argv)
            self.assertIsNone(self.identify())

    def test_reads_real_self_scheduler_on_musl(self):
        # Alpine's libc scheduler wrappers return ENOSYS; the Linux adapter
        # must still read the real kernel policy, as /proc reports it.
        fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
        policy = int(fields[38])
        self.assertTrue(callable(getattr(self.helper, 'scheduler_policy', None)),
                        'The Linux scheduling adapter must support musl')
        self.assertEqual(self.helper.scheduler_policy(0) & ~os.SCHED_RESET_ON_FORK, policy)

    def test_accepts_versioned_superhold_daemon_only(self):
        script = self.home / '.local/share/superhold/versions/0.2.0.dev1-abc/bin/superhold'
        script.parent.mkdir(parents=True)
        script.write_text('# launcher fixture\n')
        self.process(executable=sys.executable, argv=[sys.executable, str(script), 'daemon'])
        self.assertEqual(self.identify()['name'], 'superhold')
        self.process(executable=sys.executable, argv=[sys.executable, str(script), 'show'])
        self.assertIsNone(self.identify())

    def test_session_scope_uses_exact_socket_environment_or_compositor_pid(self):
        self.assertTrue(callable(getattr(self.helper, 'in_session', None)),
                        'Session scans must exclude other desktop sessions')
        process = self.process()
        (process / 'environ').write_bytes(b'SWAYSOCK=/run/user/1000/private.sock\0')
        private = '/run/user/1000/private.sock'
        live = '/run/user/1000/live.sock'
        self.assertTrue(self.helper.in_session(123, private, 999, self.proc))
        self.assertFalse(self.helper.in_session(123, live, 999, self.proc))
        self.assertTrue(self.helper.in_session(123, live, 123, self.proc))
        (process / 'environ').write_bytes(b'OTHER_SWAYSOCK=/run/user/1000/live.sock\0')
        self.assertFalse(self.helper.in_session(123, live, 999, self.proc))

    def test_session_socket_requires_caller_ownership_and_real_peer_credentials(self):
        self.assertTrue(callable(getattr(self.helper, 'session_owner', None)),
                        'Session PID must come from a caller-owned compositor socket')
        path = Path(self.temporary.name) / 'sway.sock'
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(path))
            server.listen(2)
            self.assertEqual(self.helper.session_owner(str(path), self.uid), os.getpid())
            with self.assertRaises(ValueError):
                self.helper.session_owner(str(path), self.uid + 1)
            alias = path.with_name('alias.sock')
            alias.symlink_to(path)
            with self.assertRaises(ValueError):
                self.helper.session_owner(str(alias), self.uid)

    def test_boost_requires_reset_before_negative_nice_and_keeps_realtime(self):
        # System calls are the privileged boundary; this recorder models state,
        # including the dangerous ordering where nice changes before reset.
        class Scheduler:
            policy = os.SCHED_OTHER
            nice = 0

            def getscheduler(self, tid):
                return self.policy

            def setscheduler(self, tid, policy, parameter):
                self.policy = policy

            def setpriority(self, kind, tid, nice):
                if not self.policy & os.SCHED_RESET_ON_FORK:
                    raise AssertionError('Children would inherit negative nice')
                self.nice = nice

        state = Scheduler()
        with patch.object(self.helper.os, 'sched_getscheduler', state.getscheduler), \
                patch.object(self.helper.os, 'sched_setscheduler', state.setscheduler), \
                patch.object(self.helper.os, 'setpriority', state.setpriority):
            self.assertTrue(self.helper.boost_thread(123, -5))
            self.assertEqual(state.nice, -5)
            state.policy, state.nice = os.SCHED_FIFO, -11
            self.assertFalse(self.helper.boost_thread(123, -5))
            self.assertEqual((state.policy, state.nice), (os.SCHED_FIFO, -11))

    def test_failed_reset_never_applies_negative_nice(self):
        with patch.object(self.helper.os, 'sched_getscheduler', return_value=os.SCHED_OTHER), \
                patch.object(self.helper.os, 'sched_setscheduler', side_effect=PermissionError), \
                patch.object(self.helper.os, 'setpriority', side_effect=AssertionError('unsafe nice')):
            with self.assertRaises(PermissionError):
                self.helper.boost_thread(123, -5)


if __name__ == '__main__':
    unittest.main()
