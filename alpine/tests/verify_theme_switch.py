#!/usr/bin/env python3
"""Exercise real theme deployment and Waybar reload in a disposable desktop."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import select
import signal
import subprocess
import sys
import tempfile
import time

import cairo

REPO = Path(__file__).resolve().parents[2]
THEMES = ('gruvbox-dark', 'vespersteel-archive-968881e8a08a')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_fixture(destination, themes):
    for relative in ('alpine/desktop/.config', 'alpine/themes/profiles/gruvbox-dark'):
        shutil.copytree(REPO / relative, destination / relative)
    files = ['alpine/bin/deploy-home', 'alpine/desktop/.local/bin/mbp-intel-theme',
             'alpine/wallpapers/theme_catalog.py', 'alpine/wallpapers/desktop_theme.py']
    files.extend('alpine/themes/' + identity + '.json' for identity in themes)
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    return {relative: digest(REPO / relative) for relative in files}


def fixture_bar(path):
    """Keep the deployed bar design while removing all commands and telemetry."""
    original = json.loads(path.read_text())[0]
    keep = ('name', 'layer', 'position', 'height', 'spacing', 'margin-top',
            'margin-bottom', 'margin-left', 'margin-right', 'exclusive', 'fixed-center')
    bar = {key: original[key] for key in keep if key in original}
    bar.update({'output': 'HEADLESS-1', 'reload_style_on_change': False,
                'modules-left': ['custom/ghost', 'sway/workspaces'],
                'modules-center': [], 'modules-right': ['clock'],
                'custom/ghost': {'format': '󰊠'},
                'sway/workspaces': {'format': '{value}', 'disable-markup': True},
                # Thick fixture glyphs have fully covered pixels even with a
                # small serif theme font, so color evidence survives antialiasing.
                'clock': {'format': '<span size="large" weight="bold">PRIVATE THEME PREVIEW</span>',
                          'tooltip': False}})
    path.write_text(json.dumps(bar, indent=2) + '\n')
    return bar


def screenshot_evidence(path, foreground):
    surface = cairo.ImageSurface.create_from_png(str(path))
    surface.flush()
    pixels = bytes(surface.get_data())[:surface.get_stride() * 72]
    red, green, blue = (int(foreground[index:index + 2], 16) for index in (1, 3, 5))
    expected = bytes((blue, green, red)) if sys.byteorder == 'little' else bytes((red, green, blue))
    count = sum(pixels[index:index + 3] == expected
                for index in range(0 if sys.byteorder == 'little' else 1, len(pixels), 4))
    if count < 10:
        raise RuntimeError('The native bar did not render the selected foreground color')
    return {'sha256': digest(path), 'bar_pixels_sha256': hashlib.sha256(pixels).hexdigest(),
            'foreground': foreground, 'foreground_pixel_count': count,
            'dimensions': [surface.get_width(), surface.get_height()]}


def verify(output, themes=THEMES):
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='mbp-intel-theme-switch-') as temporary:
        base = Path(temporary)
        home, runtime, checkout = base / 'home', base / 'run', base / 'repo'
        home.mkdir()
        runtime.mkdir(mode=0o700)
        sources = copy_fixture(checkout, themes)
        foreign = home / '.local/state/mbp-intel/backups/scripture-fixture/manifest.json'
        foreign.parent.mkdir(parents=True)
        foreign.write_text(json.dumps({'created_utc': '2000-01-01T00:00:00Z',
                                       'databases': [{'name': 'synthetic.sqlite3', 'bytes': 0}],
                                       'note': 'Synthetic unrelated backup; never a deployment journal.'}))
        foreign_hash = digest(foreign)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_DATA_HOME=str(home / '.local/share'), XDG_STATE_HOME=str(home / '.local/state'),
                   XDG_CACHE_HOME=str(home / '.cache'), XDG_RUNTIME_DIR=str(runtime),
                   WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman',
                   WLR_LIBINPUT_NO_DEVICES='1', GTK_USE_PORTAL='0', NO_AT_BRIDGE='1',
                   PYTHONDONTWRITEBYTECODE='1')
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS',
                    'DBUS_SESSION_BUS_PID', 'DBUS_STARTER_ADDRESS', 'DBUS_STARTER_BUS_TYPE'):
            env.pop(key, None)
        config = output / 'sway.conf'
        config.write_text(f'''xwayland disable
output HEADLESS-1 mode 1280x800
output * bg #0c1016 solid_color
seat seat0 fallback true
include "{home / '.config/sway/theme.conf'}"
include "{home / '.config/swayfx/effects.conf'}"
for_window [app_id="theme-switch-preview"] floating enable
for_window [app_id="theme-switch-preview"] resize set 870 470
for_window [app_id="theme-switch-preview"] move position center
''')
        processes = []
        captures = []
        log_path = output / 'runtime.log'
        with log_path.open('w') as log:
            def spawn(command):
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                           start_new_session=True)
                processes.append(process)
                return process

            def stop(process):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                processes.remove(process)

            def wait_for(predicate):
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    if any(process.poll() is not None for process in processes):
                        raise RuntimeError('Private preview process exited; inspect runtime.log')
                    value = predicate()
                    if value:
                        return value
                    time.sleep(.05)
                raise RuntimeError('Private preview timed out; inspect runtime.log')

            try:
                for index, identity in enumerate(themes):
                    command = [sys.executable, str(checkout / 'alpine/desktop/.local/bin/mbp-intel-theme'),
                               'use', identity, '--no-reload']
                    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=30)
                    (output / (identity + '-deployment.log')).write_text(result.stdout + result.stderr)
                    if result.returncode:
                        raise RuntimeError('Private theme deployment failed: ' + result.stderr)
                    if (checkout / 'alpine/themes/current').read_text().strip() != identity:
                        raise RuntimeError('Private theme selection was not recorded')
                    profile = checkout / 'alpine/themes/profiles' / identity
                    for relative in ('.config/waybar/style.css', '.config/foot/foot.ini',
                                     '.config/sway/theme.conf', '.config/gtk-3.0/gtk.css'):
                        if (home / relative).resolve() != profile / relative:
                            raise RuntimeError('HOME did not point at the selected theme: ' + relative)
                    design = fixture_bar(home / '.config/waybar/config.jsonc')
                    configured = log_path.read_text().count('Bar configured')
                    if index == 0:
                        subprocess.run(['swayfx', '--validate', '--config', str(config)],
                                       env=env, stdout=log, stderr=log, check=True, timeout=15)
                        sway = spawn(['swayfx', '--config', str(config)])
                        wait_for(lambda: list(runtime.glob('sway-ipc*.sock')))
                        env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
                        env['WAYLAND_DISPLAY'] = wait_for(lambda: next(
                            (path.name for path in runtime.glob('wayland-*') if path.is_socket()), None))
                        # Start the bus only after its activation environment is
                        # entirely private, including HOME and Wayland socket.
                        bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                                               env=env, stdout=subprocess.PIPE, stderr=log,
                                               text=True, start_new_session=True)
                        processes.append(bus)
                        if not select.select([bus.stdout], [], [], 5)[0]:
                            raise RuntimeError('Private D-Bus did not start')
                        env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().strip()
                        bus.stdout.close()
                        if not env['DBUS_SESSION_BUS_ADDRESS'].startswith('unix:'):
                            raise RuntimeError('Private D-Bus returned no usable address')
                        bar = spawn(['waybar', '--config', str(home / '.config/waybar/config.jsonc'),
                                     '--style', str(home / '.config/waybar/style.css')])
                    else:
                        reply = subprocess.run(['swaymsg', '-r', 'reload'], env=env,
                                               capture_output=True, text=True, check=True, timeout=10)
                        if not all(item.get('success') for item in json.loads(reply.stdout)):
                            raise RuntimeError('Private compositor did not reload the selected theme')
                        os.kill(bar.pid, signal.SIGUSR2)
                    wait_for(lambda: log_path.read_text().count('Bar configured') > configured)
                    descriptor = json.loads((checkout / 'alpine/themes' / (identity + '.json')).read_text())
                    sample = output / (identity + '-sample.txt')
                    sample.write_text('\n  ' + descriptor['name'] + '\n\n  ' + '\n  '.join(
                        f'{key}: {value}' for key, value in descriptor['design'].items())
                        + '\n\n  Theme applied by mbp-intel-theme into a private HOME.\n'
                        + '  This Waybar process remains running across both themes.\n')
                    terminal = spawn(['foot', '--config', str(home / '.config/foot/foot.ini'),
                                      '--app-id=theme-switch-preview', '--title=Theme application preview',
                                      'sh', '-c', 'cat "$1"; exec sleep 60', 'preview', str(sample)])
                    wait_for(lambda: 'theme-switch-preview' in subprocess.check_output(
                        ['swaymsg', '-r', '-t', 'get_tree'], env=env, text=True, timeout=5))
                    # Let the compositor finish its short appearance animation.
                    time.sleep(.5)
                    screenshot = output / (identity + '.png')
                    subprocess.run(['grim', str(screenshot)], env=env, check=True, timeout=15)
                    captures.append({'theme': identity, 'waybar_pid': bar.pid, 'sway_pid': sway.pid,
                                     'bar_reload_count': log_path.read_text().count('Bar configured'),
                                     'bar_design': design,
                                     'style_sha256': digest(home / '.config/waybar/style.css'),
                                     'foot_config_sha256': digest(home / '.config/foot/foot.ini'),
                                     'screenshot': screenshot_evidence(screenshot, descriptor['palette']['foreground'])})
                    stop(terminal)
                if captures[0]['screenshot']['bar_pixels_sha256'] == captures[1]['screenshot']['bar_pixels_sha256']:
                    raise RuntimeError('The native bar pixels did not change across themes')
                if digest(foreign) != foreign_hash:
                    raise RuntimeError('An unrelated backup manifest changed during deployment')
                summary = {'source_sha256': sources, 'themes': captures,
                           'same_waybar_process': captures[0]['waybar_pid'] == captures[1]['waybar_pid'],
                           'foreign_backup_unchanged': True, 'foreign_backup_sha256': foreign_hash,
                           'private_home_and_compositor': True,
                           'refresh_session_called': False}
                (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
            finally:
                for process in list(reversed(processes)):
                    stop(process)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--themes', nargs=2, default=THEMES,
                        help='Two theme IDs to deploy, in order')
    arguments = parser.parse_args()
    verify(arguments.output.resolve(), arguments.themes)
    print('Verified two real deployments and native style reload in the same private Waybar process.')
