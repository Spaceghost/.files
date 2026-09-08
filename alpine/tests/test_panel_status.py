"""The streaming panel helpers release their owned subprocesses."""
import errno
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/mbp-intel-panel-status'


class PanelStatusTests(unittest.TestCase):
    def test_notification_reader_is_terminated_and_reaped_with_parent(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-panel-reader-') as directory:
            root = Path(directory)
            child_pid = root / 'child.pid'
            stopped = root / 'child.stopped'
            stub = root / 'swaync-client'
            stub.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
import signal
import sys

root = Path(os.environ["PANEL_READER_TEST"])
root.joinpath("child.pid").write_text(str(os.getpid()))
def stop(_number, _frame):
    root.joinpath("child.stopped").write_text("terminated\\n")
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
print("[]", flush=True)
print('{"text":"1","alt":"notification","class":"notification"}', flush=True)
signal.pause()
''')
            stub.chmod(0o755)
            environment = dict(os.environ)
            environment['PATH'] = str(root) + os.pathsep + environment['PATH']
            environment['PANEL_READER_TEST'] = str(root)
            parent = subprocess.Popen(
                [str(SCRIPT), 'notifications'], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, env=environment)
            try:
                deadline = time.monotonic() + 3
                while not child_pid.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(child_pid.exists(), 'stub notification reader did not start')
                ready, _, _ = select.select([parent.stdout], [], [], 2)
                self.assertTrue(ready, 'panel helper emitted no valid status')
                report = json.loads(parent.stdout.readline())
                self.assertEqual((report['text'], report['alt']), ('1', 'notification'))

                parent.terminate()
                parent.communicate(timeout=4)
                self.assertEqual(parent.returncode, 128 + signal.SIGTERM)
                self.assertEqual(stopped.read_text(), 'terminated\n')
                pid = int(child_pid.read_text())
                try:
                    os.kill(pid, 0)
                except OSError as error:
                    self.assertEqual(error.errno, errno.ESRCH)
                else:
                    self.fail('notification reader remains after its parent exited')
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=2)


if __name__ == '__main__':
    unittest.main()
