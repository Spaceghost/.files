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


SOURCE = Path(__file__).resolve().parents[1] / 'bin/oldbook-ui-priority'


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
        script = self.home / '.files/alpine/desktop/.local/bin/oldbook-carousel'
        script.parent.mkdir(parents=True)
        script.write_text('# daemon fixture\n')
        deployed = self.home / '.local/bin/oldbook-carousel'
        deployed.parent.mkdir(parents=True)
        deployed.symlink_to(script)
        self.process(executable=sys.executable, argv=[sys.executable, str(deployed), 'daemon'])
        self.assertEqual(self.identify()['name'], 'oldbook-carousel')
        self.process(executable=sys.executable, argv=[sys.executable, '-S', str(deployed), 'daemon'])
        self.assertIsNotNone(self.identify(), 'The approved daemon -S startup must be recognized')
        self.assertEqual(self.identify()['name'], 'oldbook-carousel')
        for argv in ([sys.executable, str(deployed), 'show'],
                     [sys.executable, str(deployed), 'daemon', '--extra'],
                     [sys.executable, '/tmp/oldbook-carousel', 'daemon'],
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

    def test_desktop_threads_sit_well_below_zero_and_the_compositor_lowest(self):
        self.process()
        self.assertEqual(self.identify()['nice'], -15)
        self.process(executable='/usr/bin/swayfx')
        self.assertEqual(self.identify()['nice'], -10)
        self.process(executable='/usr/bin/conky')
        self.assertEqual(self.identify()['nice'], -15)

    def test_the_compositor_render_thread_goes_round_robin_with_children_reset(self):
        # Jack: "I need animation to take absolute priority." The one thread
        # that renders every frame runs realtime; anything it forks does not.
        class Scheduler:
            policy = os.SCHED_OTHER
            calls = []

            def getscheduler(self, tid):
                return self.policy

            def setscheduler(self, tid, policy, parameter):
                self.calls.append((tid, policy, parameter.sched_priority))
                self.policy = policy

        state = Scheduler()
        with patch.object(self.helper.os, 'sched_getscheduler', state.getscheduler), \
                patch.object(self.helper.os, 'sched_setscheduler', state.setscheduler):
            self.assertTrue(self.helper.realtime_thread(123, 1))
            self.assertEqual(state.calls, [(123, os.SCHED_RR | os.SCHED_RESET_ON_FORK, 1)])
            # Running again is harmless: round-robin from an earlier run is renewed.
            self.assertTrue(self.helper.realtime_thread(123, 1))
            state.policy = os.SCHED_FIFO
            self.assertFalse(self.helper.realtime_thread(123, 1))
            self.assertEqual(len(state.calls), 2)
        self.assertEqual(self.helper.COMPOSITOR_REALTIME, 1)

    def member(self, pid, group, leader, comm, executable='/usr/bin/waybar', argv=None,
               uid=None, environ=b'SWAYSOCK=/run/user/1000/live.sock\0'):
        """A process in the fake /proc, in a session group with a leader."""
        path = self.proc / str(pid)
        path.mkdir(parents=True, exist_ok=True)
        exe = path / 'exe'
        exe.unlink(missing_ok=True)
        exe.symlink_to(executable)
        (path / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in
                                      (argv or [executable])) + b'\0')
        owner = self.uid if uid is None else uid
        (path / 'status').write_text(f'Name:\t{comm}\nUid:\t{owner}\t{owner}\t{owner}\t{owner}\nTgid:\t{pid}\n')
        (path / 'stat').write_text(f'{pid} ({comm}) S 1 {pid} {leader} ' + '0 ' * 16 + '321 0\n')
        (path / 'comm').write_text(comm + '\n')
        (path / 'autogroup').write_text(f'/autogroup-{group} nice 0\n')
        (path / 'environ').write_bytes(environ)
        return path

    def test_only_the_desktops_own_session_groups_are_weighted(self):
        live = '/run/user/1000/live.sock'
        # The compositor's group, whoever leads it (greetd's worker is root's).
        self.member(300, 16, 299, 'swayfx', executable='/usr/bin/swayfx')
        # The session script's group: the daemons it started, under its shell,
        # and a panel module's own sh child -- script interpreters, not shells.
        self.member(310, 24, 305, 'sh', executable='/bin/busybox',
                    argv=['/bin/sh', '/home/jack/.local/bin/oldbook-session'])
        self.member(311, 24, 305, 'swaync', executable='/usr/bin/swaync')
        self.member(312, 24, 305, 'sh', executable='/bin/busybox',
                    argv=['sh', '-c', 'oldbook-waybar-ghost-class'])
        # A daemon that is its own session leader.
        self.member(320, 27, 320, 'superhold', executable='/usr/bin/superhold')
        # A terminal group: a shell, an agent and a panel started by hand in it.
        self.member(330, 64, 330, 'zsh', executable='/bin/zsh')
        self.member(331, 64, 330, 'claude', executable='/usr/bin/claude')
        self.member(332, 64, 330, 'waybar', executable='/usr/bin/waybar')
        # A group with no desktop process at all.
        self.member(340, 70, 340, 'firefox', executable='/usr/bin/firefox')
        # A desktop process from another session's environment.
        self.member(350, 80, 349, 'waybar', executable='/usr/bin/waybar',
                    environ=b'SWAYSOCK=/run/user/1000/other.sock\0')
        groups = self.helper.desktop_groups(self.uid, self.home, live, 300, self.proc)
        self.assertEqual(groups, {'16', '24', '27'})
        self.helper.weight_group(311, self.helper.GROUP_NICE, self.proc)
        self.assertEqual((self.proc / '311/autogroup').read_text().strip(), '-20')
        self.assertEqual(self.helper.GROUP_NICE, -20)

    def test_failed_reset_never_applies_negative_nice(self):
        with patch.object(self.helper.os, 'sched_getscheduler', return_value=os.SCHED_OTHER), \
                patch.object(self.helper.os, 'sched_setscheduler', side_effect=PermissionError), \
                patch.object(self.helper.os, 'setpriority', side_effect=AssertionError('unsafe nice')):
            with self.assertRaises(PermissionError):
                self.helper.boost_thread(123, -5)


if __name__ == '__main__':
    unittest.main()
