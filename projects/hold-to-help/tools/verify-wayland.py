#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify real layer surfaces on private Sway outputs, without touching a session.

Dependencies: Python 3, PyQt6, built layer-shell bridge, Sway with its headless
backend and pixman renderer, swaymsg, Foot, and grim. Only synthetic text is
rendered. No input device is opened and no command reaches the user's compositor.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


CLIENT = '''from PyQt6.QtCore import QTimer
from hold_to_help.qt_overlay import create_application, QtShortcutOverlay
app = create_application([])
overlay = QtShortcutOverlay()
snapshot = {
    'app': 'Space Ghost editor', 'output': 'HEADLESS-1',
    '_output_rect': {'x': 0, 'y': 0, 'width': 1440, 'height': 900},
    'sections': [
        {'title': 'Editor shortcuts', 'coverage': 'Partial documented baseline',
         'rows': [
             {'key': 'Ctrl+S', 'description': 'Save the universe (and this file)'},
             {'key': 'Ctrl+Z', 'description': 'Undo Zorak’s latest contribution'},
         ]},
        {'title': 'Desktop', 'coverage': 'Configured controls',
         'rows': [
             {'key': 'Super+Enter', 'description': 'Open a terminal'},
             {'key': 'Super (hold)', 'description': 'Show this contextual guide'},
         ]},
    ],
}
overlay.show(snapshot)
def move():
    snapshot.update(output='HEADLESS-2',
                    _output_rect={'x': 1440, 'y': 0, 'width': 1024, 'height': 768})
    overlay.show(snapshot)
QTimer.singleShot(1600, move)
QTimer.singleShot(2800, overlay.hide)
QTimer.singleShot(3200, lambda: overlay.show(snapshot))
QTimer.singleShot(4600, app.quit)
app.exec()
'''


def walk(node):
    yield node
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from walk(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path,
                        help='new private evidence directory')
    parser.add_argument('--library', type=Path,
                        help='built libhold-to-help-layer-shell.so; otherwise use installed lookup')
    parser.add_argument('--sway', default='sway', help='Sway binary with pixman support')
    parser.add_argument('--qt-theme', help='platform theme for this test process only, e.g. qt6ct')
    args = parser.parse_args()
    binaries = {name: shutil.which(value) for name, value in
                [('sway', args.sway), ('swaymsg', 'swaymsg'), ('foot', 'foot'), ('grim', 'grim')]}
    missing = [name for name, path in binaries.items() if path is None]
    if missing:
        parser.error('missing verification dependencies: ' + ', '.join(missing))
    library = args.library.resolve(strict=True) if args.library else None
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    evidence = {'status': 'running', 'live_session_changes': 0, 'checks': [],
                'dependencies': binaries}
    if library:
        evidence['library'] = str(library)
        evidence['library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
    (output / 'sway.conf').write_text('''xwayland disable
output HEADLESS-1 mode 1440x900 pos 0 0
output HEADLESS-2 mode 1024x768 pos 1440 0
output * bg #1d2021 solid_color
seat seat0 fallback true
focus_follows_mouse no
default_border pixel 0
''')
    (output / 'foot.ini').write_text('''[main]
pad=16x16
[colors-dark]
background=282828
foreground=ebdbb2
''')
    (output / 'overlay.py').write_text(CLIENT)
    processes = []
    try:
        with tempfile.TemporaryDirectory(prefix='hold-to-help-wayland-') as runtime:
            env = os.environ.copy()
            env.update(XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
                       WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman')
            for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
                env.pop(key, None)
            with (output / 'sway.log').open('w') as log, (output / 'qt.log').open('w') as qt_log:
                try:
                    sway = subprocess.Popen([binaries['sway'], '--debug', '-c',
                                             str(output / 'sway.conf')],
                                            env=env, stdout=log, stderr=log)
                    processes.append(sway)
                    for _ in range(100):
                        sockets = list(Path(runtime).glob('sway-ipc*.sock'))
                        displays = [path for path in Path(runtime).glob('wayland-*')
                                    if not path.name.endswith('.lock')]
                        if sockets and displays:
                            break
                        if sway.poll() is not None:
                            raise RuntimeError('private compositor exited during startup; see sway.log')
                        time.sleep(.05)
                    else:
                        raise RuntimeError('timed out waiting for private compositor sockets')
                    env.update(SWAYSOCK=str(sockets[0]), WAYLAND_DISPLAY=displays[0].name)
                    foot = subprocess.Popen([
                        binaries['foot'], '--app-id=hold-to-help-focus-proof', '--config',
                        str(output / 'foot.ini'), 'sh', '-c',
                        'printf "Synthetic focus target: keyboard focus stays here.\\n"; sleep 12'],
                        env=env, stdout=log, stderr=log)
                    processes.append(foot)
                    time.sleep(.5)
                    qt_env = env.copy()
                    qt_env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]),
                                  QT_QPA_PLATFORM='wayland', WAYLAND_DEBUG='1',
                                  PYTHONDONTWRITEBYTECODE='1')
                    if library:
                        qt_env['HOLD_TO_HELP_LAYER_SHELL_LIBRARY'] = str(library)
                    if args.qt_theme:
                        qt_env['QT_QPA_PLATFORMTHEME'] = args.qt_theme
                    client = subprocess.Popen(['python3', str(output / 'overlay.py')],
                                              env=qt_env, stdout=qt_log, stderr=qt_log)
                    processes.append(client)
                    for delay, name in ((1.0, 'first-output'), (1.3, 'second-output'),
                                        (1.3, 'repeat-hold')):
                        time.sleep(delay)
                        if client.poll() is not None:
                            raise RuntimeError('overlay exited unexpectedly; see qt.log')
                        tree = json.loads(subprocess.check_output(
                            [binaries['swaymsg'], '-r', '-t', 'get_tree'], env=env, timeout=3))
                        focused = [node.get('app_id') for node in walk(tree)
                                   if node.get('focused') and node.get('app_id')]
                        if focused != ['hold-to-help-focus-proof']:
                            raise AssertionError(f'keyboard focus changed: {focused}')
                        subprocess.run([binaries['grim'], str(output / f'{name}.png')],
                                       env=env, check=True, timeout=3)
                        evidence['checks'].append({'stage': name, 'focused': focused})
                    client.wait(timeout=6)
                    if client.returncode:
                        raise RuntimeError(f'overlay exited with status {client.returncode}')
                    qt_log.flush()
                    trace = (output / 'qt.log').read_text()
                    surfaces = [line for line in trace.splitlines() if 'get_layer_surface(' in line]
                    outputs = set(re.findall(r'wl_output#(\d+)', '\n'.join(surfaces)))
                    if len(surfaces) < 3 or len(outputs) != 2:
                        raise AssertionError('output transition or repeated hold failed to remap layer surface')
                    if not all(', 3, "hold-to-help")' in line for line in surfaces):
                        raise AssertionError('guide did not use the overlay layer')
                    if (trace.count('set_keyboard_interactivity(0)') != len(surfaces)
                            or trace.count('set_exclusive_zone(0)') != len(surfaces)):
                        raise AssertionError('a surface took keyboard focus or reserved desktop space')
                    evidence['checks'].append({'stage': 'wayland-protocol',
                                               'surfaces': surfaces, 'keyboard_interactivity': 0,
                                               'exclusive_zone': 0})
                finally:
                    for process in reversed(processes):
                        if process.poll() is None:
                            process.terminate()
                    for process in reversed(processes):
                        try:
                            process.wait(timeout=4)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
        evidence['status'] = 'passed'
    except BaseException as error:
        evidence.update(status='failed', error=str(error))
        raise
    finally:
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(output / 'evidence.json')


if __name__ == '__main__':
    main()
