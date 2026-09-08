#!/usr/bin/env python3
"""Render the restored ghost in private Waybar with two actual stylesheets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from verify_apple_overview import require, wait_for
from verify_carousel import stop_private
from verify_decoration_attachment import SwayIPC


ROOT = Path(__file__).resolve().parents[2]


def purple_pixels(path):
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    image = GdkPixbuf.Pixbuf.new_from_file(str(path))
    data = memoryview(image.get_pixels())
    channels, stride = image.get_n_channels(), image.get_rowstride()
    count = 0
    for y in range(min(36, image.get_height())):
        for x in range(min(45, image.get_width())):
            offset = y * stride + x * channels
            red, green, blue = data[offset:offset + 3]
            count += red > 75 and blue > red and blue > green + 30
    return count


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    sources = [('base', ROOT / 'alpine/desktop/.config/waybar/style.css'),
               ('waxen-meridian', ROOT / 'alpine/themes/profiles/waxen-meridian-373c11cb12f0/.config/waybar/style.css')]
    evidence = {'status': 'running', 'checks': [], 'host_changes': 0,
                'scope': 'Real private Waybar custom/ghost; synthetic context only; no live input or helpers.',
                'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for _, path in sources},
                'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    processes = []
    ipc = None
    with tempfile.TemporaryDirectory(prefix='ghost-badge-') as directory:
        base = Path(directory)
        env = dict(os.environ)
        for key, name in (('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'),
                          ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                          ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')):
            path = base / name
            path.mkdir(mode=0o700)
            env[key] = str(path)
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        env.update(WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', NO_AT_BRIDGE='1',
                   GTK_A11Y='none', XDG_CURRENT_DESKTOP='sway',
                   DBUS_SESSION_BUS_ADDRESS=f'unix:path={base / "bus"}')
        config = output / 'sway.conf'
        config.write_text('xwayland disable\noutput HEADLESS-1 mode 500x160\n'
                          'output * bg #19151e solid_color\nseat seat0 fallback true\n')
        production = json.loads((ROOT / 'alpine/desktop/.config/waybar/config.jsonc').read_text())[0]
        bar = {'name': 'top', 'layer': 'overlay', 'position': 'top', 'height': 32,
               'modules-left': ['custom/ghost', 'custom/fixture'],
               'custom/ghost': {'format': production['custom/ghost']['format'], 'tooltip': False},
               'custom/fixture': {'format': '  PRIVATE GHOST BADGE PREVIEW  ', 'tooltip': False}}
        bar_config = output / 'waybar.json'
        bar_config.write_text(json.dumps(bar, indent=2) + '\n')
        (output / 'waybar-state.css').write_text('/* Private preview: no fullscreen window. */\n')
        log = (output / 'runtime.log').open('w')

        def spawn(argv):
            process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=log, start_new_session=True)
            processes.append(process)
            return process

        def layers():
            # Waybar uses its configured name as the layer namespace.
            return [surface for item in ipc.requests([(3, '')])[0]
                    for surface in item.get('layer_shell_surfaces', [])
                    if surface.get('namespace') == 'top']

        try:
            spawn(['dbus-daemon', '--session', '--nofork', f'--address={env["DBUS_SESSION_BUS_ADDRESS"]}'])
            wait_for(lambda: (base / 'bus').is_socket(), 'private D-Bus did not start')
            spawn(['/usr/bin/swayfx', '--config', str(config)])

            def ready():
                sockets = list(Path(env['XDG_RUNTIME_DIR']).glob('sway-ipc.*.sock'))
                displays = [path for path in Path(env['XDG_RUNTIME_DIR']).glob('wayland-*') if path.is_socket()]
                return (sockets[0], displays[0]) if sockets and displays else None

            sway, display = wait_for(ready, 'private Sway did not start')
            env.update(SWAYSOCK=str(sway), WAYLAND_DISPLAY=display.name)
            subprocess.run(['dbus-update-activation-environment', 'SWAYSOCK', 'WAYLAND_DISPLAY'],
                           env=env, check=True, stdout=log, stderr=log, timeout=4)
            ipc = SwayIPC(sway)
            for name, source in sources:
                style = output / (name + '.css')
                style.write_bytes(source.read_bytes())
                process = spawn(['waybar', '--config', str(bar_config), '--style', str(style)])
                wait_for(layers, 'private Waybar did not map')
                image = output / (name + '.png')

                def painted():
                    subprocess.run(['grim', '-g', '0,0 500x64', str(image)], env=env,
                                   check=True, stdout=log, stderr=log, timeout=4)
                    return purple_pixels(image) > 150

                wait_for(painted, 'restored purple badge did not paint')
                evidence['checks'].append({'name': name + '-renders-original-purple-badge',
                                           'passed': True, 'purple_pixels': purple_pixels(image),
                                           'layers': layers()})
                process.terminate()
                process.wait(timeout=4)
                wait_for(lambda: not layers(), 'previous private Waybar did not close')
            require(all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                        for name, digest in evidence['source_sha256'].items()), 'styles changed during preview')
            evidence['status'] = 'passed'
        except BaseException as error:
            evidence.update(status='failed', error=str(error))
            raise
        finally:
            if ipc:
                ipc.close()
            for process in reversed(processes):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
            evidence['cleanup'] = stop_private([], ('XDG_RUNTIME_DIR=' + env['XDG_RUNTIME_DIR']).encode())
            log.close()
            (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
            require(not evidence['cleanup']['remaining_processes'], 'private cleanup left survivors')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
