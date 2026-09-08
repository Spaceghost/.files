#!/usr/bin/env python3
"""Exercise centered window resizing in an isolated Sway session."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'alpine/desktop/.local/bin/oldbook-resize'
OUT = ROOT / 'alpine/verification/centered-resize'
OUT.mkdir(parents=True, exist_ok=True)


def wait(fn):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        result = fn()
        if result:
            return result
        time.sleep(.05)
    raise RuntimeError('Timed out waiting for isolated Sway')


def walk(node):
    yield node
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from walk(child)


def center(rect):
    return [rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2]


with tempfile.TemporaryDirectory(prefix='centered-resize-') as temporary:
    base = Path(temporary)
    runtime = base / 'run'
    runtime.mkdir(mode=0o700)
    home = base / 'home'
    (home / '.local/bin').mkdir(parents=True)
    (home / '.local/bin/oldbook-resize').symlink_to(HELPER)
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
               XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless', WLR_RENDERER='pixman',
               WLR_LIBINPUT_NO_DEVICES='1', DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'no-bus'))
    for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
        env.pop(key, None)
    config = base / 'sway.conf'
    config.write_text('output HEADLESS-1 mode 1440x900\noutput * bg #352942 solid_color\n'
                      'seat seat0 fallback true\nfocus_follows_mouse no\n'
                      'default_border pixel 0\ndefault_floating_border pixel 0\nset $mod Mod4\n'
                      'include ' + str(ROOT / 'alpine/desktop/.config/sway/local.d/resize.conf') + '\n')
    log = (base / 'runtime.log').open('w')
    sway = subprocess.Popen(['sway', '-c', str(config)], env=env, stdout=log, stderr=log)
    children = []
    report = {'isolation': 'private HOME/runtime, headless Sway, no session bus',
              'keyboard_driver': 'wtype single-level symbolic keymap; explicit Shift+plus tested, physical Shift+= mapping unobserved',
              'checks': {}}

    def command(*args):
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError(f'{args}: {result.stdout} {result.stderr}')
        return result.stdout

    def ipc(kind='get_tree', text=None):
        args = ['swaymsg', '-r', '-t', kind]
        if text:
            args.append(text)
        return json.loads(command(*args))

    def app(name='centered-target'):
        return next((node for node in walk(ipc()) if node.get('app_id') == name), None)

    def act(text, name='centered-target'):
        response = ipc('command', f'[app_id="^{name}$"] ' + text)
        assert all(item.get('success') for item in response), response
        time.sleep(.07)
        return app(name)['rect']

    def resize(direction):
        command(str(HELPER), direction)
        time.sleep(.08)
        return app()['rect']

    def launch(name):
        child = subprocess.Popen(['foot', '--app-id=' + name, '--override=resize-by-cells=no',
                                  '--override=initial-window-size-pixels=600x400',
                                  '--override=colors-dark.background=' + ('352046' if name == 'centered-target' else '17131f'),
                                  '--override=colors-dark.foreground=eadff5',
                                  '-e', '/bin/sh', '-c', 'printf \'%s\\n\' \'Centered resize target\'; exec cat'
                                  if name == 'centered-target' else 'printf \'%s\\n\' \'Other window stays unchanged\'; exec cat'],
                                 env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        children.append(child)
        return wait(lambda: app(name))

    try:
        env['SWAYSOCK'] = str(wait(lambda: next(runtime.glob('sway-ipc*.sock'), None)))
        env['WAYLAND_DISPLAY'] = wait(lambda: next((p.name for p in runtime.glob('wayland-*') if p.is_socket()), None))
        launch('centered-target')
        launch('centered-other')
        act('floating enable, resize set 600 400, move absolute position 210 170, focus')
        before = app()['rect']
        other_before = app('centered-other')['rect']
        grow = resize('grow')
        shrink = resize('shrink')
        report['floating'] = dict(before=before, grow=grow, shrink=shrink)
        report['checks']['floating_grow_center'] = grow == dict(x=190, y=150, width=640, height=440)
        report['checks']['floating_shrink_restores'] = shrink == before
        report['checks']['other_window_unchanged'] = app('centered-other')['rect'] == other_before
        act('resize set 75 200')
        limited_before = app()['rect']
        limited = resize('shrink')
        report['minimum'] = dict(before=limited_before, after=limited)
        report['checks']['minimum_width_does_not_block_height'] = limited['width'] == 75 and limited['height'] == 160 and center(limited) == center(limited_before)
        act('resize set 1440 800')
        maximum_before = app()['rect']
        maximum = resize('grow')
        report['maximum'] = dict(before=maximum_before, after=maximum)
        report['checks']['maximum_width_does_not_block_height'] = maximum['width'] == 1440 and maximum['height'] == 840 and center(maximum) == center(maximum_before)
        act('floating disable, focus')
        tiled_before = app()['rect']
        tiled_after = resize('shrink')
        report['tiled'] = dict(before=tiled_before, after=tiled_after)
        report['checks']['tiled_center_retained'] = center(tiled_before) == center(tiled_after) and app()['type'] == 'floating_con'
        act('resize set 600 400, move absolute position 210 170, fullscreen enable')
        fullscreen_before = app()['rect']
        fullscreen_after = resize('shrink')
        report['fullscreen'] = dict(before=fullscreen_before, after=fullscreen_after, mode=app()['fullscreen_mode'])
        report['checks']['fullscreen_disabled'] = app()['fullscreen_mode'] == 0
        report['checks']['fullscreen_center_retained'] = center(fullscreen_before) == center(fullscreen_after)
        act('resize set 600 400, move absolute position 210 170, focus')
        keys = [
            ('super_equal', ['-M','logo','-k','equal','-m','logo'], 40),
            ('super_shift_plus', ['-M','logo','-M','shift','-k','plus','-m','shift','-m','logo'], 40),
            ('super_plus', ['-M','logo','-k','plus','-m','logo'], 40),
            ('super_minus', ['-M','logo','-k','minus','-m','logo'], -40),
            ('super_keypad_add', ['-M','logo','-k','KP_Add','-m','logo'], 40),
            ('super_keypad_subtract', ['-M','logo','-k','KP_Subtract','-m','logo'], -40),
        ]
        report['keys'] = {}
        for name, args, delta in keys:
            act('resize set 600 400, move absolute position 210 170, focus')
            old = app()['rect']
            command('wtype', '-s', '100', *args, '-s', '500')
            try:
                wait(lambda: app()['rect']['width'] == old['width'] + delta and app()['rect']['height'] == old['height'] + delta)
            except RuntimeError:
                pass
            new = app()['rect']
            report['keys'][name] = dict(before=old, after=new)
            report['checks'][name] = new['width'] == old['width'] + delta and new['height'] == old['height'] + delta and center(new) == center(old)
        command('grim', str(OUT / 'floating.png'))
        (OUT / 'runtime.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        assert all(report['checks'].values()), report['checks']
    finally:
        subprocess.run(['swaymsg', 'exit'], env=env, capture_output=True, timeout=5)
        sway.wait(timeout=5)
        for child in children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
        log.close()
