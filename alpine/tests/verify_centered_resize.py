#!/usr/bin/env python3
"""Exercise centered window resizing in an isolated Sway session."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
if os.environ.get('MBP_INTEL_RESIZE_PRIVATE_BUS') != '1':
    # D-Bus activation inherits its launch environment, so isolate it before
    # starting the bus as well as isolating the compositor and its clients.
    with tempfile.TemporaryDirectory(prefix='centered-resize-') as directory:
        private_env = dict(os.environ)
        for key in ('DBUS_SESSION_BUS_ADDRESS', 'SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            private_env.pop(key, None)
        for key, name in [('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'),
                          ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                          ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')]:
            path = Path(directory) / name
            path.mkdir(mode=0o700)
            private_env[key] = str(path)
        private_env.update(MBP_INTEL_RESIZE_PRIVATE_BUS='1',
                           MBP_INTEL_RESIZE_PRIVATE_BASE=directory,
                           NO_AT_BRIDGE='1', GTK_USE_PORTAL='0')
        result = subprocess.run(['dbus-run-session', '--', sys.executable,
            str(Path(__file__).resolve()), *sys.argv[1:]], env=private_env)
    raise SystemExit(result.returncode)
HELPER = ROOT / 'alpine/desktop/.local/bin/mbp-intel-resize'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=ROOT / 'alpine/verification/centered-resize')
parser.add_argument('--helper', type=Path, default=HELPER)
arguments = parser.parse_args()
HELPER = arguments.helper.resolve()
OUT = arguments.output.resolve()
OUT.mkdir(parents=True, exist_ok=True)


def wait(fn):
    end = time.monotonic() + 10
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


with contextlib.nullcontext(os.environ['MBP_INTEL_RESIZE_PRIVATE_BASE']) as temporary:
    base = Path(temporary)
    runtime = base / 'run'
    runtime.mkdir(mode=0o700, exist_ok=True)
    home = base / 'home'
    (home / '.local/bin').mkdir(parents=True)
    (home / '.local/bin/mbp-intel-resize').symlink_to(HELPER)
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
               XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless',
               WLR_LIBINPUT_NO_DEVICES='1', NO_AT_BRIDGE='1', GTK_USE_PORTAL='0')
    for key, directory in [('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state'),
                           ('XDG_CACHE_HOME', 'cache')]:
        env[key] = str(base / directory)
    for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
        env.pop(key, None)
    config = base / 'sway.conf'
    config.write_text('output HEADLESS-1 mode 1440x900\noutput * bg #352942 solid_color\n'
                      'seat seat0 fallback true\nfocus_follows_mouse no\n'
                      'default_border pixel 0\ndefault_floating_border pixel 0\nset $mod Mod4\n'
                      'include ' + str(ROOT / 'alpine/desktop/.config/sway/local.d/resize.conf') + '\n')
    log = (base / 'runtime.log').open('w')
    sway = subprocess.Popen(['sway', '-c', str(config)], env=env, stdout=log, stderr=log,
                            start_new_session=True)
    children = []
    report = {'isolation': 'private HOME/XDG/runtime, headless Sway and private D-Bus',
              'helper_sha256': hashlib.sha256(HELPER.read_bytes()).hexdigest(),
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

    def act(text, name='centered-target', expected=None):
        response = ipc('command', f'[app_id="^{name}$"] ' + text)
        assert all(item.get('success') for item in response), response
        if expected is not None:
            wait(lambda: app(name)['rect'] == expected)
        else:
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
                                 env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True)
        children.append(child)
        return wait(lambda: app(name))

    try:
        env['SWAYSOCK'] = str(wait(lambda: next(runtime.glob('sway-ipc*.sock'), None)))
        env['WAYLAND_DISPLAY'] = wait(lambda: next((p.name for p in runtime.glob('wayland-*') if p.is_socket()), None))
        launch('centered-target')
        launch('centered-other')
        act('floating enable, resize set 600 400, move absolute position 210 170, focus',
            expected=dict(x=210, y=170, width=600, height=400))
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
        # Keep a real reserved layer-shell strip above the usable workspace.
        bar_config = base / 'waybar.json'
        bar_config.write_text(json.dumps({'layer': 'top', 'position': 'top',
            'height': 40, 'exclusive': True, 'modules-left': ['custom/reserved'],
            'custom/reserved': {'format': 'Private reserved area', 'tooltip': False}}))
        bar_style = base / 'waybar.css'
        bar_style.write_text('* { font-family: sans-serif; font-size: 12px; min-height: 0; }\n'
                             'window#waybar { background: #241a31; color: #eadff5; }\n')
        children.append(subprocess.Popen(['waybar', '-c', str(bar_config), '-s', str(bar_style)],
            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True))

        def usable():
            return next(workspace['rect'] for workspace in ipc('get_workspaces')
                        if workspace.get('focused'))

        wait(lambda: usable()['y'] >= 40)

        def expected_near_full(bounds):
            width = max(1, bounds['width'] - 2 * max(24, round(bounds['width'] * .05)))
            height = max(1, bounds['height'] - 2 * max(24, round(bounds['height'] * .05)))
            return dict(x=bounds['x'] + (bounds['width'] - width) // 2,
                        y=bounds['y'] + (bounds['height'] - height) // 2,
                        width=width, height=height)

        report['near_full'] = {}
        for mode, setup in [('floating', 'floating enable'),
                            ('tiled', 'floating disable'),
                            ('fullscreen', 'floating enable, fullscreen enable')]:
            act(setup + ', focus')
            bounds = usable()
            after = resize('near-full')
            repeated = resize('near-full')
            report['near_full'][mode] = dict(usable=bounds, after=after, repeated=repeated)
            report['checks']['near_full_' + mode] = after == expected_near_full(bounds)
            report['checks']['near_full_' + mode + '_stable'] = repeated == after
            report['checks']['near_full_' + mode + '_floating'] = app()['type'] == 'floating_con' and app()['fullscreen_mode'] == 0
            report['checks']['near_full_' + mode + '_clears_bar'] = after['y'] > bounds['y']
        before_offset_other = app('centered-other')['rect']
        resize('near-full')
        report['checks']['near_full_other_window_unchanged'] = app('centered-other')['rect'] == before_offset_other
        ipc('command', 'output HEADLESS-1 position 1700 240 scale 1.25')
        wait(lambda: usable()['x'] == 1700 and usable()['width'] < 1440)
        bounds = usable()
        after = resize('near-full')
        report['near_full']['offset_scaled_output'] = dict(usable=bounds, after=after)
        report['checks']['near_full_offset_scaled_output'] = after == expected_near_full(bounds)
        command('grim', str(OUT / 'near-full.png'))
        (OUT / 'runtime.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        assert all(report['checks'].values()), report['checks']
    finally:
        if 'SWAYSOCK' in env and sway.poll() is None:
            try:
                report['final_workspace_rects'] = [node['rect'] for node in walk(ipc())
                                                   if node.get('type') == 'workspace']
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                report['final_snapshot_error'] = str(error)
        (OUT / 'runtime.json').write_text(json.dumps(report, indent=2) + '\n')
        # Every process group belongs to this private fixture, including shells
        # whose leader may have exited before its last descendant.
        for child in [*children, sway]:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(.15)
        for child in [*children, sway]:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
        log.close()
        (OUT / 'compositor.log').write_text((base / 'runtime.log').read_text())
