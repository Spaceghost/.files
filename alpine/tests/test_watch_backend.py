"""Native backend selection without mapping a guard on the user's desktop."""
import os
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]


class WatchDiagnosticsTests(unittest.TestCase):
    def test_lock_preserves_the_startup_error_in_a_private_log(self):
        lock = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-lock'))
        with tempfile.TemporaryDirectory(prefix='watch-diagnostics-') as root:
            runtime = Path(root)
            with patch.dict(os.environ, {'SWAYSOCK': str(runtime / 'sway.sock')}), \
                    patch.dict(lock['begin_catbed_mode'].__globals__, {
                        '_watch_command': lambda *args: [sys.executable, '-c',
                            'import sys; sys.stderr.write("backend diagnosis\\n")']}):
                self.assertFalse(lock['begin_catbed_mode'](runtime))
            log = runtime / 'oldbook/watch-startup.log'
            self.assertIn('backend diagnosis', log.read_text())
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)


@unittest.skipUnless(Path('/usr/bin/sway').exists() and shutil.which('wtype'),
                     'requires native Sway and its isolated virtual keyboard tool')
class WatchBackendTests(unittest.TestCase):
    def test_inherited_x11_preference_cannot_select_an_x11_guard(self):
        with tempfile.TemporaryDirectory(prefix='watch-backend-') as root:
            root = Path(root)
            runtime = root / 'run'
            runtime.mkdir(mode=0o700)
            config = root / 'sway.conf'
            config.write_text('output HEADLESS-1 resolution 800x600\nseat seat0 fallback true\n'
                              'mode "watch" {\n bindsym F24 nop\n}\n')
            env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless',
                       WLR_RENDERER='pixman', WLR_LIBINPUT_NO_DEVICES='1', GSK_RENDERER='cairo')
            for key in ('WAYLAND_DISPLAY', 'SWAYSOCK', 'DISPLAY', 'GDK_BACKEND'):
                env.pop(key, None)
            with (root / 'sway.log').open('w') as log:
                sway = subprocess.Popen(['/usr/bin/sway', '-c', str(config)], env=env,
                                        stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 10
                    displays = []
                    while time.monotonic() < deadline and sway.poll() is None:
                        displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
                        if displays:
                            break
                        time.sleep(.05)
                    self.assertTrue(displays, (root / 'sway.log').read_text())
                    env.update(WAYLAND_DISPLAY=displays[0].name,
                               GDK_BACKEND='x11', DISPLAY=':65530')
                    program = (
                        'import runpy\n'
                        f'm = runpy.run_path({str(REPO / "alpine/desktop/.local/bin/oldbook-watch")!r})\n'
                        'from gi.repository import GLib\n'
                        'loop = GLib.MainLoop()\n'
                        'guard = m["watch_mode"].Guard(m["read_palette"](m["THEMES"]), '
                        'lambda: None, lambda *args: None, lambda: None)\n'
                        'print(type(guard.Gdk.Display.get_default()).__name__)\n'
                        'guard.close()\n')
                    result = subprocess.run(['/usr/bin/python3', '-c', program], env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('WaylandDisplay', result.stdout)
                    holds = root / 'catbed.json'
                    holds.write_text('{"version":1,"keys":[],"sysrq":{"guard":false}}')
                    env.update(SWAYSOCK=str(next(runtime.glob('sway-ipc.*.sock'))),
                               CATBED_GUARD_CONFIG=str(holds),
                               XDG_STATE_HOME=str(root / 'state'),
                               XDG_CONFIG_HOME=str(root / 'config'),
                               DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'no-bus'))
                    with (root / 'guard.log').open('w') as output:
                        guard = subprocess.Popen([str(REPO / 'alpine/desktop/.local/bin/oldbook-watch'),
                                                  'start'], env=env, stdout=output, stderr=output)
                        keyboard = subprocess.Popen(['wtype', '-M', 'shift', '-s', '10000', '-m', 'shift'],
                                                    env=env, stdout=output, stderr=output)
                        try:
                            state = runtime / 'oldbook/watch.json'
                            deadline = time.monotonic() + 10
                            while time.monotonic() < deadline and guard.poll() is None and not state.exists():
                                time.sleep(.05)
                            self.assertTrue(state.exists(), (root / 'guard.log').read_text())
                            self.assertEqual(json.loads(state.read_text())['mode'], 'watch')
                            self.assertIsNone(guard.poll())
                        finally:
                            keyboard.terminate()
                            keyboard.wait(timeout=5)
                            guard.terminate()
                            guard.wait(timeout=5)
                finally:
                    sway.terminate()
                    sway.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
