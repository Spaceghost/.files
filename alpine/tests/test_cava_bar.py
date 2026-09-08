"""The bar visualizer maps cava frames to glyphs and goes quiet with the player."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'alpine/desktop/.local/bin/oldbook-cava-bar'


def load():
    loader = importlib.machinery.SourceFileLoader('cava_bar', str(SCRIPT))
    spec = importlib.util.spec_from_loader('cava_bar', loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FrameTests(unittest.TestCase):
    def test_values_map_to_eight_block_glyphs_and_clamp(self):
        module = load()
        self.assertEqual(module.frame_text('0;3;7;9;\n'), '▁▄██')
        self.assertEqual(module.frame_text('0;0;0'), '▁▁▁')
        self.assertIsNone(module.frame_text('x;1'))
        self.assertIsNone(module.frame_text(''))

    def test_generated_config_is_raw_ascii_mono_at_a_low_frame_rate(self):
        module = load()
        self.assertIn('method = raw', module.CONFIG)
        self.assertIn('data_format = ascii', module.CONFIG)
        self.assertIn('ascii_max_range = 7', module.CONFIG)
        self.assertIn('channels = mono', module.CONFIG)
        self.assertLessEqual(module.FRAMERATE, 20)
        self.assertLessEqual(module.BARS, 12)


class PlayerGateTests(unittest.TestCase):
    def test_bars_follow_the_player_and_collapse_when_silent(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-cava-') as directory:
            root = Path(directory)
            fake_bin = root / 'bin'
            fake_bin.mkdir()
            status = root / 'status'
            status.write_text('Playing\n')
            (fake_bin / 'playerctl').write_text('#!/bin/sh\ncat ' + shlex.quote(str(status)) + '\n')
            # A fake cava: loud frames, then silence, ten frames a second.
            (fake_bin / 'cava').write_text(
                '#!/bin/sh\nn=0\nwhile :; do\n'
                '  if [ "$n" -lt 8 ]; then printf "%s\\n" "1;4;7;2;0;3;5;6;2;1"; '
                'else printf "%s\\n" "0;0;0;0;0;0;0;0;0;0"; fi\n'
                '  n=$((n+1)); sleep 0.1\ndone\n')
            for path in (fake_bin / 'playerctl', fake_bin / 'cava'):
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ['PATH'],
                       XDG_RUNTIME_DIR=directory)
            process = subprocess.Popen([str(SCRIPT)], env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, start_new_session=True)
            lines = []
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    line = process.stdout.readline()
                    if not line:
                        break
                    lines.append(json.loads(line))
                    if lines[-1]['class'] == 'silent' and len(lines) > 2:
                        break
                self.assertEqual(lines[0], {'text': '', 'class': 'silent', 'tooltip': ''})
                playing = [entry for entry in lines if entry['class'] == 'playing']
                self.assertTrue(playing, lines)
                self.assertEqual(playing[0]['text'], '▂▅█▃▁▄▆▇▃▂')
                self.assertEqual(lines[-1], {'text': '', 'class': 'silent', 'tooltip': ''})
                config = Path(directory) / 'oldbook/cava-bar.conf'
                self.assertTrue(config.is_file())
                self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                status.write_text('Paused\n')
                # Once nothing is playing the fake cava must be stopped, not left running.
                time.sleep(2.5)
                remaining = subprocess.run(['pgrep', '-f', str(fake_bin / 'cava')],
                                           capture_output=True, text=True)
                self.assertEqual(remaining.stdout.strip(), '')
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process.stdout.close()
                process.stderr.close()


if __name__ == '__main__':
    unittest.main()
