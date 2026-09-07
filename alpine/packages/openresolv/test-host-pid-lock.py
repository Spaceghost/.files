#!/usr/bin/env python3
"""Build a private resolver fixture; no host DNS, services or root access."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(sys.argv.pop(1)).resolve()


class HostPidLockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='openresolv-lock-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        shutil.copytree(SOURCE, self.source)
        self.config = self.root / 'etc'
        self.config.mkdir()
        self.state = self.root / 'run/resolvconf'
        subscribers = self.root / 'subscribers'
        subscribers.mkdir()
        subprocess.run(['./configure', '--prefix=/usr', '--sysconfdir=' + str(self.config),
                        '--rundir=' + str(self.root / 'run'), '--libexecdir=' + str(subscribers)],
                       cwd=self.source, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['make', '-B', 'resolvconf'], cwd=self.source, check=True,
                       stdout=subprocess.DEVNULL)
        self.script = self.source / 'resolvconf'
        configured = self.script.read_text().splitlines()
        for line in ('SYSCONFDIR=' + str(self.config), 'VARDIR=' + str(self.state),
                     'LIBEXECDIR=' + str(subscribers)):
            if line not in configured:
                raise RuntimeError('refusing resolver fixture with nonprivate configured paths')
        self.script.chmod(0o755)
        self.proc = os.open('/proc', os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.proc)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith('OPENRESOLV_HOST_')}

    def invoke(self, *args, environment=None, fd=None, current_pid=False):
        env = dict(self.env, **(environment or {}))
        fds = () if fd is None else (fd,)
        command = [str(self.script), *args]
        if current_pid:
            command = ['/bin/sh', '-c',
                       'OPENRESOLV_HOST_PID=$$; export OPENRESOLV_HOST_PID; exec "$@"',
                       'fixture', *command]
        return subprocess.run(command, env=env, pass_fds=fds,
                              input='nameserver 192.0.2.53\n', capture_output=True,
                              text=True, timeout=3)

    def test_capability_probe_is_read_only(self):
        result = self.invoke('--host-pid-lock-version')
        self.assertEqual((result.returncode, result.stdout), (0, '1\n'))
        self.assertFalse(self.state.exists())

    def test_ordinary_add_and_delete_keep_native_provider_behavior(self):
        self.assertEqual(self.invoke('-a', 'synthetic0').returncode, 0)
        self.assertEqual((self.state / 'keys/synthetic0').read_text(), 'nameserver 192.0.2.53\n')
        self.assertEqual(self.invoke('-d', 'synthetic0').returncode, 0)
        self.assertFalse((self.state / 'keys/synthetic0').exists())

    def test_complete_valid_bridge_can_add_without_host_dns(self):
        env = {'OPENRESOLV_HOST_PROC_FD': str(self.proc)}
        result = self.invoke('-a', 'synthetic0', environment=env, fd=self.proc, current_pid=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.state / 'keys/synthetic0').is_file())

    def test_invalid_requested_context_never_creates_state(self):
        valid = {'OPENRESOLV_HOST_PID': str(os.getpid()), 'OPENRESOLV_HOST_PROC_FD': str(self.proc)}
        cases = [{'OPENRESOLV_HOST_PID': '1'}, {'OPENRESOLV_HOST_PROC_FD': str(self.proc)},
                 {'OPENRESOLV_HOST_PID': '', 'OPENRESOLV_HOST_PROC_FD': ''},
                 dict(valid, OPENRESOLV_HOST_PID='-1'), dict(valid, OPENRESOLV_HOST_PID='01'),
                 dict(valid, OPENRESOLV_HOST_PID='x'), dict(valid, OPENRESOLV_HOST_PID='2147483648'),
                 dict(valid, OPENRESOLV_HOST_PROC_FD='-1'), dict(valid, OPENRESOLV_HOST_PROC_FD='0'),
                 dict(valid, OPENRESOLV_HOST_PROC_FD='2147483648'), valid]
        for env in cases:
            with self.subTest(environment=env):
                result = self.invoke('-a', 'synthetic0', environment=env, fd=self.proc)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.state.exists())

    def test_nonproc_and_closed_descriptor_are_rejected_before_state(self):
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            env = {'OPENRESOLV_HOST_PROC_FD': str(descriptor)}
            result = self.invoke('-a', 'synthetic0', environment=env, fd=descriptor, current_pid=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.state.exists())
        finally:
            os.close(descriptor)
        env = {'OPENRESOLV_HOST_PROC_FD': '99999'}
        self.assertNotEqual(self.invoke('-a', 'synthetic0', environment=env, current_pid=True).returncode, 0)
        self.assertFalse(self.state.exists())

    def test_readonly_child_may_inherit_its_parent_context(self):
        self.assertEqual(self.invoke('-a', 'synthetic0').returncode, 0)
        env = dict(self.env, OPENRESOLV_HOST_PROC_FD=str(self.proc))
        result = subprocess.run(['/bin/sh', '-c',
            'OPENRESOLV_HOST_PID=$$; export OPENRESOLV_HOST_PID; '
            '/bin/sh -c \'exec "$1" -i\' child "$1"; status=$?; exit "$status"',
            'fixture', str(self.script)], env=env, pass_fds=(self.proc,),
            capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('synthetic0', result.stdout)


if __name__ == '__main__':
    unittest.main()
