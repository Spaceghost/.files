"""Startup priority requests must return immediately and reap their own child."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


LIBRARY = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/mbp_intel'
sys.path.insert(0, str(LIBRARY))
import ui_priority


class PriorityRequestTests(unittest.TestCase):
    def test_request_returns_before_helper_exits_and_reaps_it_afterward(self):
        # Redirect only the external privileged executable to a real private
        # child whose lifetime the fixture controls through stdin.
        native_popen = subprocess.Popen
        children, errors = [], []
        returned = threading.Event()

        def launch(*_args, **_kwargs):
            child = native_popen(['/bin/sh', '-c', 'read -r value'], stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(child)
            return child

        def request():
            try:
                ui_priority.request_priority()
            except Exception as error:
                errors.append(error)
            finally:
                returned.set()

        with tempfile.TemporaryDirectory(prefix='ui-priority-request-') as directory:
            sway = Path(directory) / 'sway.sock'
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(sway))
                with patch.dict(os.environ, XDG_RUNTIME_DIR=directory, SWAYSOCK=str(sway)), \
                        patch.object(ui_priority.Path, 'is_file', return_value=True), \
                        patch.object(ui_priority.subprocess, 'Popen', side_effect=launch):
                    caller = threading.Thread(target=request, daemon=True)
                    caller.start()
                    try:
                        self.assertTrue(returned.wait(2), 'Startup waited for the priority helper')
                        self.assertFalse(errors)
                        self.assertEqual(len(children), 1)
                        child = children[0]
                        self.assertTrue((Path('/proc') / str(child.pid)).exists())
                        child.stdin.write(b'finish\n')
                        child.stdin.close()
                        # Do not poll/wait on Popen here: that would reap the
                        # child in the fixture and conceal the production bug.
                        deadline = time.monotonic() + 3
                        while (Path('/proc') / str(child.pid)).exists() and time.monotonic() < deadline:
                            time.sleep(.01)
                        self.assertFalse((Path('/proc') / str(child.pid)).exists(),
                                         'Exited priority helper was left as a zombie')
                        with self.assertRaises(ChildProcessError):
                            os.waitpid(child.pid, os.WNOHANG)
                    finally:
                        for child in children:
                            if not child.stdin.closed:
                                child.stdin.close()
                            child.wait(timeout=3)
                        caller.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
