"""The streaming panel helpers release their owned subprocesses."""
import errno
import io
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import importlib.machinery
import importlib.util


SCRIPT = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-panel-status'


def load_script():
    loader = importlib.machinery.SourceFileLoader('oldbook_panel_status', str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class PanelStatusTests(unittest.TestCase):
    def test_every_desktop_has_a_dedicated_remote_watch_card(self):
        configs = [SCRIPT.parents[2] / '.config/conky/panels.json']
        configs.extend((SCRIPT.parents[3] / 'themes/profiles').glob(
            '*/.config/conky/panels.json'))
        self.assertGreater(len(configs), 1)
        for path in configs:
            with self.subTest(path=path):
                panels = json.loads(path.read_text())['panels']
                card = next(panel for panel in panels if panel['id'] == 'remote-watch')
                self.assertIn('oldbook-remote-access conky', card['text'])
                self.assertGreaterEqual(card['height'], 390)
                self.assertEqual(panels[-1]['id'], 'remote-watch')
                self.assertLess(card['priority'], min(
                    panel['priority'] for panel in panels if panel['id'] != 'remote-watch'))
                masthead = next(panel for panel in panels if panel['id'] == 'masthead')
                self.assertNotIn('oldbook-panel-status ssh-desktop', masthead['text'])

    def test_notification_deck_places_ssh_between_wifi_and_next_art(self):
        config = json.loads((SCRIPT.parents[2] / '.config/swaync/config.json').read_text())
        actions = config['widget-config']['buttons-grid']['actions']
        labels = [action['label'] for action in actions]
        wifi = next(index for index, label in enumerate(labels) if 'Wi-Fi' in label)
        ssh = next(index for index, label in enumerate(labels) if 'Remote access' in label)
        art = next(index for index, label in enumerate(labels) if 'Next art' in label)
        self.assertEqual((wifi, ssh, art), (wifi, wifi + 1, wifi + 2))
        self.assertEqual(actions[ssh]['command'],
                         '~/.local/bin/oldbook-remote-access menu')
        self.assertNotIn('type', actions[ssh])
        self.assertNotIn('update-command', actions[ssh])

    def test_notification_reader_is_terminated_and_reaped_with_parent(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-panel-reader-') as directory:
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
