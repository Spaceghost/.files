"""The real GTK Scripture bar follows theme changes in an isolated compositor."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from theme_fixtures import theme_descriptor


REPO = Path(__file__).resolve().parents[2]
BAR = REPO / 'alpine/desktop/.local/bin/oldbook-scripture-bar'
PROBE = r'''
import json
from pathlib import Path
import runpy
import sys
import time

api = runpy.run_path(sys.argv[1])
root = Path(sys.argv[2])
themes = root / 'alpine/themes'
initial = sys.argv[3]
(themes / 'current').write_text(initial)
scope = api['SearchBar'].__init__.__globals__
scope['REPO'] = root
scope['STATE'] = root / 'state'
scope['FINDER'] = root / 'noop-scripture'
scope['FINDER'].write_text('raise SystemExit(0)\n')
from overlay_theme import read_palette
scope['read_palette'] = lambda: read_palette(themes)
bar = api['SearchBar']()
Gtk, GLib = api['Gtk'], api['GLib']
shortcut = bar.button.get_child().get_children()[-1]

def color(widget, property_name):
    value = widget.get_style_context().get_property(property_name, Gtk.StateFlags.NORMAL)
    return '#%02x%02x%02x' % tuple(round(channel * 255)
                                 for channel in (value.red, value.green, value.blue))

def sample():
    return {'background': color(bar.button, 'background-color'),
            'hint': color(bar.label, 'color'),
            'shortcut': color(shortcut, 'color')}

def settle(changed_from=None):
    deadline = time.monotonic() + (3.5 if changed_from else .2)
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if changed_from and sample() != changed_from:
            return
        time.sleep(.02)

settle()
samples = [sample()]
if initial == 'spaceghost':
    (themes / 'current').write_text('gruvbox-dark')
    settle(samples[-1])
    samples.append(sample())
    document = json.loads((themes / 'gruvbox-dark.json').read_text())
    document['palette'].update(background='#192b34', muted='#8eaab8', accent='#69ccb8')
    (themes / 'gruvbox-dark.json').write_text(json.dumps(document))
    settle(samples[-1])
    samples.append(sample())
bar.window.destroy()
print(json.dumps(samples))
'''


@unittest.skipUnless(shutil.which('sway'), 'native theme tests require Sway')
class ScriptureBarThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='scripture-bar-theme-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        runtime = cls.root / 'run'
        runtime.mkdir(mode=0o700)
        # A private state directory as well: oldbook-palette records the accent
        # the painting on screen elected under XDG_STATE_HOME, and read_palette
        # honours it for the matching theme. Inheriting the user's would let the
        # live desktop's amber overrule the descriptor this test just edited.
        state = cls.root / 'state'
        state.mkdir(mode=0o700)
        cls.env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), GDK_BACKEND='wayland',
                       XDG_STATE_HOME=str(state),
                       WLR_BACKENDS='headless', WLR_RENDERER='pixman',
                       WLR_LIBINPUT_NO_DEVICES='1')
        for name in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            cls.env.pop(name, None)
        config = cls.root / 'sway.conf'
        config.write_text('output HEADLESS-1 mode 1280x800\nseat seat0 fallback true\n')
        log = (cls.root / 'sway.log').open('w')
        cls.addClassCleanup(log.close)
        cls.sway = subprocess.Popen(['sway', '-c', str(config)], env=cls.env,
                                    stdout=log, stderr=log)
        cls.addClassCleanup(cls.stop_compositor)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
            if displays:
                cls.env['WAYLAND_DISPLAY'] = displays[0].name
                return
            if cls.sway.poll() is not None:
                break
            time.sleep(.05)
        raise RuntimeError((cls.root / 'sway.log').read_text())

    @classmethod
    def stop_compositor(cls):
        cls.sway.terminate()
        try:
            cls.sway.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.sway.kill()
            cls.sway.wait()

    def render(self, initial):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root = Path(directory)
            themes = root / 'alpine/themes'
            themes.mkdir(parents=True)
            for name in ('spaceghost', 'gruvbox-dark'):
                shutil.copyfile(theme_descriptor(name), themes / (name + '.json'))
            result = subprocess.run([sys.executable, '-c', PROBE, str(BAR), str(root), initial],
                                    env=self.env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_gruvbox_uses_the_active_background_text_and_gold_accent(self):
        self.assertEqual(self.render('gruvbox-dark')[0], {
            'background': '#282828', 'hint': '#928374', 'shortcut': '#fabd2f'})

    def test_running_bar_follows_theme_switch_and_descriptor_edits(self):
        samples = self.render('spaceghost')
        self.assertEqual(samples[0], {
            'background': '#13091f', 'hint': '#816b91', 'shortcut': '#dca7ff'})
        self.assertEqual(samples[1], {
            'background': '#282828', 'hint': '#928374', 'shortcut': '#fabd2f'})
        self.assertEqual(samples[2], {
            'background': '#192b34', 'hint': '#8eaab8', 'shortcut': '#69ccb8'})


if __name__ == '__main__':
    unittest.main()
