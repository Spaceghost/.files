"""Lock acquisition regression tests; never connect to the live compositor."""
import json
import os
import signal
import socket
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
LOCK = REPO / 'alpine/desktop/.local/bin/oldbook-lock'


class LockRegressionTests(unittest.TestCase):
    def test_process_name_alone_never_proves_readiness(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-test-') as directory:
            root = Path(directory)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            fake_bin = root / 'bin'
            fake_bin.mkdir()
            helper = fake_bin / 'swaylockd'
            helper.write_text('#!/bin/sh\nexit 1\n')
            helper.chmod(0o755)
            env = dict(os.environ, HOME=directory, XDG_RUNTIME_DIR=directory, WAYLAND_DISPLAY='wayland-test',
                       PATH=str(fake_bin) + ':/usr/bin:/bin')
            fake = subprocess.Popen(['swaylock', '-c', 'import time; time.sleep(20)'],
                                    executable='/usr/bin/python3')
            try:
                time.sleep(0.05)
                result = subprocess.run([str(LOCK)], env=env, capture_output=True,
                                        text=True, timeout=3)
                self.assertNotEqual(result.returncode, 0,
                                    'a matching process has never sent lock readiness')
            finally:
                fake.terminate()
                fake.wait()

    def test_concurrent_calls_wait_for_one_real_readiness_event(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-test-') as directory:
            root = Path(directory)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            helper = root / 'swaylockd'
            helper.write_text("#!/usr/bin/python3\nimport os,sys,time\n"
                              f"with open({str(root / 'starts')!r}, 'a') as f: f.write(str(os.getpid())+'\\n')\n"
                              "time.sleep(.3)\n"
                              "os.write(int(sys.argv[sys.argv.index('-R')+1]), b'\\n')\n"
                              "time.sleep(20)\n")
            helper.chmod(0o755)
            env = dict(os.environ, HOME=directory, XDG_RUNTIME_DIR=directory, WAYLAND_DISPLAY='wayland-test',
                       PATH=directory + ':/usr/bin:/bin')
            clients = []
            try:
                started = time.monotonic()
                clients = [subprocess.Popen([str(LOCK)], env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, text=True) for _ in range(2)]
                for client in clients:
                    output, error = client.communicate(timeout=3)
                    self.assertEqual(client.returncode, 0, error)
                self.assertGreaterEqual(time.monotonic() - started, .3)
                self.assertEqual(len((root / 'starts').read_text().splitlines()), 1)
                ready = json.loads((root / 'oldbook-screen-lock/ready.json').read_text())
                # A fresh call reuses the proven, live process without another launch.
                result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=2)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len((root / 'starts').read_text().splitlines()), 1)
                # A stale identity must never be accepted as proof of a current lock.
                original = json.loads(json.dumps(ready))
                ready['process']['start_time'] = 'invalid'
                (root / 'oldbook-screen-lock/ready.json').write_text(json.dumps(ready))
                helper.write_text('#!/bin/sh\nexit 1\n')
                result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=2)
                self.assertNotEqual(result.returncode, 0)
                # The still-live supervisor cannot authorize a different compositor.
                (root / 'oldbook-screen-lock/ready.json').write_text(json.dumps(original))
                wayland.close()
                (root / 'wayland-test').unlink()
                replacement = socket.socket(socket.AF_UNIX)
                self.addCleanup(replacement.close)
                replacement.bind(str(root / 'wayland-test'))
                result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=2)
                self.assertNotEqual(result.returncode, 0)
            finally:
                for client in clients:
                    if client.poll() is None:
                        client.kill()
                        client.wait()
                if (root / 'starts').exists():
                    for pid in (root / 'starts').read_text().splitlines():
                        try:
                            os.killpg(int(pid), signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    def test_unready_helper_is_killed_and_never_records_success(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-test-') as directory:
            root = Path(directory)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            helper = root / 'swaylockd'
            helper.write_text("#!/usr/bin/python3\nimport os,time\n"
                              f"open({str(root / 'started')!r}, 'w').write(str(os.getpid()))\n"
                              "time.sleep(20)\n")
            helper.chmod(0o755)
            code = ("import runpy; from pathlib import Path; "
                    f"m=runpy.run_path({str(LOCK)!r}); "
                    f"m['acquire_lock'](Path({directory!r}), {str(helper)!r}, timeout=.2)")
            result = subprocess.run(['/usr/bin/python3', '-c', code], env=dict(os.environ, WAYLAND_DISPLAY='wayland-test'), capture_output=True, text=True, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('did not report readiness', result.stderr)
            self.assertFalse((root / 'oldbook-screen-lock/ready.json').exists())
            with self.assertRaises(ProcessLookupError):
                os.kill(int((root / 'started').read_text()), 0)

    def test_nonprivate_runtime_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-test-') as directory:
            Path(directory).chmod(0o755)
            result = subprocess.run([str(LOCK)], env=dict(os.environ, XDG_RUNTIME_DIR=directory),
                                    capture_output=True, text=True, timeout=2)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('owned private directory', result.stderr)


if __name__ == '__main__':
    unittest.main()
