#!/usr/bin/env python3
"""Verify centering and raising with native windows in an isolated Sway."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from verify_decoration_attachment import build_pointer, pointer_reply


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'alpine/desktop/.local/bin/mbp-intel-center'
BINDINGS = ROOT / 'alpine/desktop/.config/sway/local.d/center.conf'


def walk(node):
    yield node
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from walk(child)


def wait(fn, message):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError(message)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    sources = [HELPER, BINDINGS, Path(__file__).resolve(),
               ROOT / 'alpine/packages/waybar-art/tests/pointer-input.c',
               ROOT / 'alpine/packages/waybar-art/tests/pointer.xml']
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sources}
    report = {'status': 'running', 'host_changes': 0,
              'isolation': 'private HOME/XDG directories, headless Sway, nonexistent session bus',
              'keyboard': 'wtype virtual keyboard with explicit Mod4 and Shift modifiers',
              'source_sha256': hashes, 'checks': [], 'states': []}
    with tempfile.TemporaryDirectory(prefix='center-window-') as directory:
        base = Path(directory)
        pointer_binary = build_pointer(base)
        env = dict(os.environ)
        for key, folder in [('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'),
                            ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                            ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')]:
            target = base / folder
            target.mkdir(mode=0o700)
            env[key] = str(target)
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        env.update(WLR_BACKENDS='headless', WLR_RENDERER='pixman',
                   WLR_HEADLESS_OUTPUTS='1', WLR_LIBINPUT_NO_DEVICES='1',
                   DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(base / 'no-bus'))
        local_bin = Path(env['HOME']) / '.local/bin'
        local_bin.mkdir(parents=True)
        (local_bin / HELPER.name).symlink_to(HELPER)
        config = output / 'sway.conf'
        config.write_text('xwayland disable\noutput HEADLESS-1 mode 1440x900\n'
                          'output * bg #191324 solid_color\nseat seat0 fallback true\n'
                          'focus_follows_mouse yes\nmouse_warping none\ngaps top 40\n'
                          'default_border pixel 0\ndefault_floating_border pixel 0\n'
                          'for_window [app_id="^center-"] floating enable\n'
                          'set $mod Mod4\ninclude ' + str(BINDINGS) + '\n')
        foot = base / 'foot.ini'
        foot.write_text('[main]\nfont=monospace:size=12\nresize-by-cells=no\n')
        log = (output / 'runtime.log').open('w')
        processes = []

        def spawn(args):
            child = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=log)
            processes.append(child)
            return child

        def command(args):
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise RuntimeError(f'{args!r}: {result.stdout} {result.stderr}')
            return result.stdout

        def ipc(kind='get_tree', text=None):
            args = ['swaymsg', '-r', '-t', kind]
            if text:
                args.append(text)
            data = json.loads(command(args))
            if kind == 'command':
                assert all(item.get('success') for item in data), data
            return data

        def app(name='center-target'):
            return next((item for item in walk(ipc()) if item.get('app_id') == name), None)

        def workspace():
            return next(item for item in ipc('get_workspaces') if item.get('focused'))

        def act(text, name='center-target'):
            ipc('command', f'[app_id="^{name}$"] ' + text)
            time.sleep(.1)

        def press(shift=False):
            args = ['wtype', '-s', '100', '-M', 'logo']
            if shift:
                args.extend(['-M', 'shift'])
            args.extend(['-k', 'c'])
            if shift:
                args.extend(['-m', 'shift'])
            command(args + ['-m', 'logo', '-s', '300'])

        def centered():
            node = app()
            if not node:
                return False
            rect, usable = node['rect'], workspace()['rect']
            return (abs(rect['x'] + rect['width'] / 2 - usable['x'] - usable['width'] / 2) <= .5
                    and abs(rect['y'] + rect['height'] / 2 - usable['y'] - usable['height'] / 2) <= .5)

        def stack():
            return next(item for item in walk(ipc()) if item.get('type') == 'workspace'
                        and item['name'] == workspace()['name'])['floating_nodes']

        def check(name):
            report['checks'].append(name)
            node = app()
            space = workspace()
            report['states'].append({'after': name,
                                     'workspace': {key: space[key] for key in ('id', 'name', 'rect', 'output')},
                                     'target': {key: node[key] for key in
                                                ('id', 'pid', 'rect', 'type', 'focused', 'fullscreen_mode')}
                                     if node else None})

        def capture(name):
            command(['grim', '-o', 'HEADLESS-1', str(output / name)])

        def launch(name, color, label):
            spawn(['foot', '--config=' + str(foot), '--app-id=' + name,
                   '--override=colors-dark.background=' + color,
                   '--override=colors-dark.foreground=eee6fa', '-e', '/bin/sh', '-c',
                   'printf "%s\\n" "$1"; exec cat', 'private-center-fixture', label])
            wait(lambda: app(name), name + ' did not open')

        try:
            sway = spawn(['swayfx', '-c', str(config)])
            runtime = Path(env['XDG_RUNTIME_DIR'])
            env['SWAYSOCK'] = str(wait(lambda: next(runtime.glob('sway-ipc*.sock'), None), 'Sway missing'))
            env['WAYLAND_DISPLAY'] = wait(lambda: next((path.name for path in runtime.glob('wayland-*')
                                                        if path.is_socket()), None), 'Wayland missing')
            launch('center-target', '553377', 'Target: center and bring forward')
            act('floating enable, resize set 600 400, move absolute position 120 160')
            wait(lambda: app()['rect'] == {'x': 120, 'y': 160, 'width': 600, 'height': 400},
                 'initial floating target geometry did not settle')
            launch('center-other', '23485b', 'Control: position and size stay unchanged')
            act('floating enable, resize set 600 400, move absolute position 300 220, focus', 'center-other')
            wait(lambda: app('center-other')['rect'] == {'x': 300, 'y': 220, 'width': 600, 'height': 400},
                 'initial control geometry did not settle')
            other = app('center-other')['rect']
            target_id, target_pid = app()['id'], app()['pid']
            pointer = subprocess.Popen([str(pointer_binary)], env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=log)
            processes.append(pointer)
            pointer_reply(pointer, 'ready')
            pointer.stdin.write(b'move 83 127\n')
            pointer.stdin.flush()
            pointer_reply(pointer, 'ok')
            wait(lambda: app()['focused'], 'pointer did not focus the lower target')
            assert stack()[-1]['id'] != target_id
            check('focused-target-starts-below-overlapping-control')
            capture('before.png')
            press()
            wait(centered, 'Super+c did not center the target')
            assert app()['rect']['width'] == 600 and app()['rect']['height'] == 400
            assert app('center-other')['rect'] == other
            assert stack()[-1]['id'] == target_id and app()['focused']
            check('super-c-centers-preserves-size-and-raises-focused-window')
            capture('centered-raised.png')
            act('move absolute position 120 160, focus')
            press(shift=True)
            wait(centered, 'Super+Shift+c did not center the target')
            assert stack()[-1]['id'] == target_id and app('center-other')['rect'] == other
            check('super-shift-c-centers-and-raises')
            act('kill', 'center-other')
            act('floating disable, focus')
            wait(lambda: app()['type'] == 'con' and app()['focused'], 'tiled fixture did not settle')
            tiled = app()['rect']
            press()
            wait(lambda: app()['type'] == 'floating_con' and centered(), 'tiled target did not center')
            assert app()['type'] == 'floating_con'
            assert app()['rect']['width'] <= round(tiled['width'] * .9)
            assert app()['rect']['height'] <= round(tiled['height'] * .9)
            check('single-tiled-window-becomes-floating-with-visible-margin')
            capture('tiled-to-floating.png')
            act('resize set 620 360, move absolute position 100 140, fullscreen enable, focus')
            assert app()['fullscreen_mode']
            press(shift=True)
            wait(centered, 'fullscreen target did not center')
            assert app()['fullscreen_mode'] == 0
            assert (app()['rect']['width'], app()['rect']['height']) == (620, 360)
            check('fullscreen-exits-and-restores-useful-floating-size')
            act('resize set 1800 1200, focus')
            press()
            wait(centered, 'oversized target did not center')
            usable = workspace()['rect']
            assert app()['rect']['width'] <= usable['width'] and app()['rect']['height'] <= usable['height']
            check('oversized-floating-window-fits-usable-area')
            act('resize set 620 360')
            ipc('command', 'output HEADLESS-1 pos 1440 100')
            act('move absolute position 1480 180, focus')
            press()
            wait(centered, 'offset-output target did not center')
            assert app()['rect']['x'] >= 1440 and app()['rect']['y'] >= 140
            assert app()['id'] == target_id and app()['pid'] == target_pid
            check('offset-output-centers-without-replacing-window')
            capture('offset-output.png')
            previous = app()['rect']
            press()
            assert app()['rect'] == previous
            check('repeated-centering-is-idempotent')
            ipc('command', 'workspace number 2')
            command([str(HELPER)])
            assert not any(item.get('focused') and item.get('app_id') for item in walk(ipc()))
            check('empty-workspace-is-a-no-op')
            assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                       for name, digest in hashes.items()), 'source changed during verification'
            report['status'] = 'passed'
        except BaseException as error:
            report['status'], report['error'] = 'failed', str(error)
            if 'SWAYSOCK' in env:
                capture('failure.png')
            raise
        finally:
            if 'SWAYSOCK' in env:
                subprocess.run(['swaymsg', 'exit'], env=env, stdout=log, stderr=log, timeout=5)
            for child in reversed(processes):
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=5)
            log.close()
            (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve())
