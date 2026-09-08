"""Theme process selection leaves other HOME and compositor sessions alone."""
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
THEME = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/mbp-intel-theme'))


class ThemeSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='theme-session-')
        self.addCleanup(self.directory.cleanup)
        self.session = {'HOME': self.directory.name,
                        'SWAYSOCK': '/run/user/1000/sway-ipc.1000.fixture.sock'}
        self.enterContext(mock.patch.dict(os.environ, self.session))

    def process(self, environment):
        # Real /proc command line and initial environment, with no compositor or
        # application launched and no signals sent through the code under test.
        child = subprocess.Popen(['mbp-intel-theme-test-app', '-c',
                                  'import time; time.sleep(30)'], executable='/usr/bin/python3',
                                 env=environment, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop, child)
        return child.pid

    @staticmethod
    def stop(child):
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=3)

    def test_only_same_home_and_compositor_are_selected(self):
        expected = self.process(self.session)
        foreign_home = self.process({**self.session, 'HOME': self.directory.name + '/private'})
        foreign_session = self.process({**self.session, 'SWAYSOCK': '/tmp/private-sway.sock'})
        no_session = self.process({'HOME': self.directory.name})
        children = {expected, foreign_home, foreign_session, no_session}
        selected = set(THEME['owned_processes']('mbp-intel-theme-test-app'))
        self.assertEqual(selected & children, {expected})

    def test_unknown_caller_session_cannot_select_any_application(self):
        child = self.process(self.session)
        with mock.patch.dict(os.environ, {'HOME': self.directory.name}, clear=True):
            selected = set(THEME['owned_processes']('mbp-intel-theme-test-app'))
        self.assertNotIn(child, selected)


if __name__ == '__main__':
    unittest.main()
