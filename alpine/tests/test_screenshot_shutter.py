"""Screenshot shutter tests: the flash, click and annotator follow the capture.

Every tool is a stub in a private PATH; nothing here touches the live outputs.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-screenshot'


class ShutterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-shutter-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stubs = self.root / 'bin'
        self.stubs.mkdir()
        self.log = self.root / 'calls.log'
        # /bin supplies the BusyBox basics; everything else must be a stub.
        self.env = dict(os.environ, HOME=str(self.root), XDG_RUNTIME_DIR=str(self.root),
                        PATH=str(self.stubs) + os.pathsep + '/bin')
        self.stub('grim', 'for target do :; done\nprintf \'png\' > "$target"\n')
        self.stub('wl-copy', 'cat >/dev/null\n')
        self.stub('notify-send', '')

    def stub(self, name, body):
        path = self.stubs / name
        path.write_text('#!/bin/sh\nprintf \'%s\\n\' "' + name + ' $*" >> '
                        + shlex.quote(str(self.log)) + '\n' + body)
        path.chmod(0o755)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def capture(self, **extra):
        result = subprocess.run([str(HELPER), 'full'], env=dict(self.env, **extra),
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        pictures = list((self.root / 'Pictures/Screenshots').glob('spaceghost-*.png'))
        self.assertEqual(len(pictures), 1)
        return pictures[0]

    def test_flash_click_and_annotator_follow_the_capture(self):
        for name in ('pw-play', 'oldbook-osd', 'satty', 'swappy'):
            self.stub(name, '')
        sound = self.root / 'shutter.oga'
        sound.write_bytes(b'OggS')
        picture = self.capture(OLDBOOK_SHUTTER_SOUND=str(sound))
        calls = self.calls()
        order = [line.split()[0] for line in calls]
        self.assertLess(order.index('grim'), order.index('oldbook-osd'))
        self.assertLess(order.index('grim'), order.index('pw-play'))
        self.assertIn('oldbook-osd flash', calls)
        self.assertIn('pw-play ' + str(sound), calls)
        self.assertIn('wl-copy --type image/png', calls)
        self.assertTrue(any(line.startswith('satty --filename ' + str(picture)
                                            + ' --output-filename ' + str(picture))
                            for line in calls))
        self.assertFalse(any(line.startswith('swappy') for line in calls))
        self.assertTrue(any(line.startswith('notify-send') for line in calls))

    def test_missing_sound_daemon_and_satty_never_fail_the_capture(self):
        self.stub('swappy', '')
        self.capture(OLDBOOK_SHUTTER_SOUND=str(self.root / 'missing.oga'))
        calls = self.calls()
        self.assertTrue(any(line.startswith('swappy -f') for line in calls))
        self.assertFalse(any(line.startswith(('pw-play', 'oldbook-osd', 'satty')) for line in calls))

    def test_a_failing_flash_or_player_is_ignored(self):
        self.stub('oldbook-osd', 'exit 1\n')
        self.stub('pw-play', 'exit 1\n')
        self.stub('satty', 'exit 1\n')
        sound = self.root / 'shutter.oga'
        sound.write_bytes(b'OggS')
        self.capture(OLDBOOK_SHUTTER_SOUND=str(sound))
        self.assertIn('oldbook-osd flash', self.calls())

    def test_unknown_mode_is_rejected_before_anything_runs(self):
        result = subprocess.run([str(HELPER), 'everything'], env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 64)
        self.assertEqual(self.calls(), [])


if __name__ == '__main__':
    unittest.main()
