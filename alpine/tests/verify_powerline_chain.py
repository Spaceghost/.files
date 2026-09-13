#!/usr/bin/env python3
"""Render each theme's bar status chain in a private headless SwayFX session."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

from verify_apple_overview import require, wait_for
from verify_carousel import stop_private
from verify_decoration_attachment import SwayIPC

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / 'alpine/themes/profiles'
THEMES = ('gruvbox-dark', 'catppuccin-mocha', 'monochrome-test')
# Every helper-driven module is a still label under its own id, so no helper runs.
STILLS = {'custom/link': ' ↓26K', 'custom/radio': '', 'custom/firewall': '',
          'custom/notifications': '', 'custom/still-sound': ' 27%'}
# What oldbook-palette writes for gruvbox's declared accent.
ACCENT = ('@define-color oldbook_accent #fabd2f;\n@define-color oldbook_accent_secondary #fe8019;\n'
          '#clock { background: alpha(@oldbook_accent, .18); }\n')


def chain_bar(path):
    document = json.loads(re.sub(r'^\s*//.*$', '', path.read_text(), flags=re.M))
    production = document[0] if isinstance(document, list) else document
    bar = {key: production[key] for key in ('name', 'layer', 'position', 'height', 'margin-top',
                                            'margin-left', 'margin-right', 'exclusive')
           if key in production}
    bar.update({'modules-left': [], 'modules-center': [], 'modules-right': ['group/status'],
                'group/status': production['group/status'],
                'group/telemetry': dict(production['group/telemetry'], modules=['cpu']),
                'group/transmission': dict(production['group/transmission'], modules=['custom/link']),
                'group/sound': dict(production['group/sound'], modules=['custom/still-sound']),
                'group/power': dict(production['group/power'], modules=['battery']),
                'cpu': {'format': ' 13%', 'interval': 3600},
                'battery': {'format': ' 84%', 'interval': 3600},
                'clock': {'format': 'Sun 13:20', 'interval': 3600}, 'tray': {}})
    for index in range(7):
        bar[f'custom/sep{index}'] = {'format': production[f'custom/sep{index}']['format'],
                                     'tooltip': False}
    bar.update({name: {'format': text, 'tooltip': False} for name, text in STILLS.items()})
    return bar


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    evidence = {'status': 'running', 'checks': [],
                'scope': 'Private headless SwayFX and real Waybar for each theme; still labels stand '
                         'in for helper-driven modules; the live session is never touched.',
                'source_sha256': {}, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    processes, ipc = [], None
    with tempfile.TemporaryDirectory(prefix='powerline-chain-') as directory:
        base = Path(directory)
        env = dict(os.environ)
        for key, name in (('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'), ('XDG_CONFIG_HOME', 'config'),
                          ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')):
            path = base / name
            path.mkdir(mode=0o700)
            env[key] = str(path)
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        env.update(WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', NO_AT_BRIDGE='1', GTK_A11Y='none',
                   XDG_CURRENT_DESKTOP='sway', DBUS_SESSION_BUS_ADDRESS=f'unix:path={base / "bus"}')
        sway_config = base / 'sway.conf'
        sway_config.write_text('xwayland disable\noutput HEADLESS-1 mode 2880x160 scale 2\n'
                               'output * bg #2a2622 solid_color\nseat seat0 fallback true\n')
        log = (base / 'runtime.log').open('w')

        def spawn(argv):
            process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True)
            processes.append(process)
            return process

        def surfaces(namespace):
            return [surface for item in ipc.requests([(3, '')])[0]
                    for surface in item.get('layer_shell_surfaces', [])
                    if surface.get('namespace') == namespace]

        try:
            spawn(['dbus-daemon', '--session', '--nofork', f'--address={env["DBUS_SESSION_BUS_ADDRESS"]}'])
            wait_for(lambda: (base / 'bus').is_socket(), 'private D-Bus did not start')
            spawn(['/usr/bin/swayfx', '--config', str(sway_config)])

            def ready():
                runtime = Path(env['XDG_RUNTIME_DIR'])
                sockets = list(runtime.glob('sway-ipc.*.sock'))
                displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
                return (sockets[0], displays[0]) if sockets and displays else None

            sway, display = wait_for(ready, 'private Sway did not start')
            env.update(SWAYSOCK=str(sway), WAYLAND_DISPLAY=display.name)
            ipc = SwayIPC(sway)
            for theme in THEMES:
                profile = PROFILES / theme / '.config/waybar'
                for source in (profile / 'style.css', profile / 'config.jsonc'):
                    evidence['source_sha256'][str(source.relative_to(ROOT))] = hashlib.sha256(
                        source.read_bytes()).hexdigest()
                styles = base / theme
                styles.mkdir()
                (styles / 'style.css').write_text((profile / 'style.css').read_text()
                                                  + '\n#custom-still-sound { padding: 0 8px; margin: 4px 0; }\n')
                (styles / 'waybar-accent.css').write_text(ACCENT)
                (styles / 'waybar-state.css').write_text('/* Private render: no fullscreen window. */\n')
                bar = chain_bar(profile / 'config.jsonc')
                (styles / 'waybar.json').write_text(json.dumps(bar, indent=2) + '\n')
                namespace = bar.get('name', 'waybar')
                process = spawn(['waybar', '--config', str(styles / 'waybar.json'),
                                 '--style', str(styles / 'style.css')])
                wait_for(lambda: surfaces(namespace), f'{theme}: private Waybar did not map')
                time.sleep(1.5)
                require(process.poll() is None, f'{theme}: Waybar exited, so GTK refused its stylesheet')
                image = output / f'{theme}.png'
                subprocess.run(['grim', '-g', '880,0 560x52', str(image)], env=env, check=True,
                               stdout=log, stderr=log, timeout=6)
                evidence['checks'].append({'name': f'{theme}-chain-renders', 'passed': True,
                                           'image': image.name})
                process.terminate()
                process.wait(timeout=4)
                wait_for(lambda: not surfaces(namespace), f'{theme}: private Waybar did not close')
            evidence['status'] = 'passed'
        except BaseException as error:
            evidence.update(status='failed', error=str(error))
            raise
        finally:
            if ipc:
                ipc.close()
            for process in reversed(processes):
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        break
                    try:
                        process.wait(timeout=2)
                        break
                    except subprocess.TimeoutExpired:
                        continue
            evidence['cleanup'] = stop_private([], ('XDG_RUNTIME_DIR=' + env['XDG_RUNTIME_DIR']).encode())
            log.close()
            (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
            require(not evidence['cleanup']['remaining_processes'], 'private cleanup left survivors')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
