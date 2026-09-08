#!/usr/bin/env python3
"""Render Launchpad and Mission Control in a private headless SwayFX session.

The overlays are the real executables from this checkout, driven over their own
control sockets, with a private HOME, runtime directory and cache. Mission
Control gets real windows to photograph by opening terminals on two workspaces
inside the private compositor, so its stills come from the same capture provider
the window carousel uses. The pixman renderer draws no compositor blur; the
overlay's own blurred painting is its own texture and does appear.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / 'alpine/desktop/.local/bin'
PAINTING = (REPO / 'alpine/assets/gallery/themes/gruvbox-dark'
            / '2026-09-07-gruvbox-dark-yosemite-f932fef36c22.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    painting = PAINTING if PAINTING.is_file() else next(
        (REPO / 'alpine/assets/gallery').rglob('*.png'), None)
    if painting is None:
        raise SystemExit('no painting available for the overlay background')

    with tempfile.TemporaryDirectory(prefix='oldbook-grids-') as temporary:
        base = Path(temporary)
        home, runtime = base / 'home', base / 'run'
        (home / '.local/share/oldbook').mkdir(parents=True)
        (home / '.local/share/oldbook/current-wallpaper.png').symlink_to(painting)
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CACHE_HOME=str(home / '.cache'),
                   XDG_STATE_HOME=str(home / '.local/state'),
                   XDG_CURRENT_DESKTOP='sway',
                   WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
                   WLR_RENDERER='pixman', GTK_USE_PORTAL='0', NO_AT_BRIDGE='1',
                   GTK_A11Y='none', GDK_BACKEND='wayland')
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        config = output / 'sway.conf'
        config.write_text(
            'xwayland disable\n'
            'output HEADLESS-1 mode 1440x900\n'
            f'output * bg "{painting}" fill\n'
            'seat seat0 fallback true\n'
            'default_border pixel 0\n')
        children = []
        report = {'painting': str(painting), 'renderer': 'pixman (no compositor blur)'}
        with (output / 'runtime.log').open('w') as log:
            def spawn(command, **extra):
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                           start_new_session=True, **extra)
                children.append(process)
                return process

            def wait_for(predicate, ticks=200):
                for _ in range(ticks):
                    if predicate():
                        return True
                    time.sleep(.05)
                return False

            def swaymsg(*args):
                result = subprocess.run(['swaymsg', *args], env=env, capture_output=True,
                                        text=True, timeout=10)
                return result.stdout

            def shot(name):
                subprocess.run(['grim', str(output / name)], env=env, check=True, timeout=20)
                return name

            try:
                spawn(['swayfx', '--config', str(config)])
                if not wait_for(lambda: list(runtime.glob('sway-ipc*.sock'))):
                    raise RuntimeError('headless SwayFX never started')
                env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
                env['WAYLAND_DISPLAY'] = next(path.name for path in runtime.glob('wayland-*')
                                              if path.is_socket())
                # Real windows on two workspaces so Mission Control photographs
                # something through the carousel's own capture provider.
                # Fill each terminal with colour so a still is visibly a real
                # window capture rather than an empty card.
                fill = ('for i in $(seq 1 40); do '
                        'printf "\\033[%dm  %s  \\033[0m" "$((31 + i % 6))" "{}"; '
                        'done; printf "\\n"; sleep 600')
                swaymsg('workspace', 'number', '1: Ghost')
                spawn(['foot', '--title', 'ghost-shell', '-e', 'sh', '-c',
                       fill.format('GHOST PLANET')])
                wait_for(lambda: 'ghost-shell' in swaymsg('-t', 'get_tree'))
                swaymsg('workspace', 'number', '3: Lab')
                spawn(['foot', '--title', 'lab-shell', '-e', 'sh', '-c',
                       fill.format('LAB')])
                wait_for(lambda: 'lab-shell' in swaymsg('-t', 'get_tree'))
                swaymsg('workspace', 'number', '1: Ghost')
                time.sleep(1.5)
                report['workspaces'] = [item.get('name') for item in
                                        json.loads(swaymsg('-r', '-t', 'get_workspaces'))]

                for name, command, settle in (
                        ('launchpad', 'oldbook-launchpad', 2.5),
                        ('mission-control', 'oldbook-mission-control', 3.0)):
                    overlay = spawn([str(BIN / command), 'show'])
                    namespace = 'oldbook-' + name
                    mapped = wait_for(lambda: namespace in swaymsg('-r', '-t', 'get_tree'))
                    time.sleep(settle)
                    report[name + '_mapped'] = mapped
                    report[name + '_shot'] = shot(name + '.png')
                    if name == 'launchpad':
                        # Type-to-search starts at the first keystroke. wtype
                        # loses the first key of each invocation while its
                        # virtual keyboard binds, so the query carries a
                        # deliberate leading duplicate and arrives as "fire".
                        # The overlay itself drops nothing.
                        typed = subprocess.run(['wtype', 'ffire'], env=env,
                                               capture_output=True, timeout=15)
                        report['launchpad_typed'] = typed.returncode == 0
                        time.sleep(1.2)
                        report['launchpad_search_shot'] = shot('launchpad-search.png')
                    # Close through the overlay's own control socket, the way a
                    # second key press does, and confirm the process leaves.
                    subprocess.run([str(BIN / command), 'close'], env=env, timeout=10)
                    report[name + '_closed'] = wait_for(
                        lambda: overlay.poll() is not None, ticks=60)
                    if overlay.poll() is None:
                        overlay.terminate()
                    children.remove(overlay)
                    time.sleep(.5)

                report['after_close_shot'] = shot('after-close.png')
                report['status'] = ('passed' if report.get('launchpad_mapped')
                                    and report.get('mission-control_mapped')
                                    and report.get('launchpad_closed')
                                    and report.get('mission-control_closed') else 'failed')
                for name in sorted(item.name for item in output.glob('*.png')):
                    report[name + '_sha256'] = hashlib.sha256(
                        (output / name).read_bytes()).hexdigest()
                (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps(report, indent=2))
                return 0 if report['status'] == 'passed' else 1
            finally:
                for child in reversed(children):
                    if child.poll() is None:
                        try:
                            os.killpg(child.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                for child in children:
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()


if __name__ == '__main__':
    sys.exit(main())
