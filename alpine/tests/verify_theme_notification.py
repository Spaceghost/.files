#!/usr/bin/env python3
"""Render the real completion notification in a private SwayFX/D-Bus session."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get('OLDBOOK_NOTIFICATION_PRIVATE_BUS'):
        # No service directories: private checks must not auto-start desktop
        # portals, mount a document filesystem, or inherit a live service.
        with tempfile.TemporaryDirectory(prefix='oldbook-notification-bus-') as bus:
            config = Path(bus) / 'session.conf'
            config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                              '<auth>EXTERNAL</auth><policy context="default">'
                              '<allow send_destination="*"/><allow receive_sender="*"/>'
                              '<allow own="*"/></policy></busconfig>')
            return subprocess.call(['dbus-run-session', '--config-file=' + str(config), '--',
                                    sys.executable, __file__, *sys.argv[1:]],
                                   env=dict(os.environ, OLDBOOK_NOTIFICATION_PRIVATE_BUS='1'))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='oldbook-theme-notification-') as temporary:
        base = Path(temporary)
        home, runtime = base / 'home', base / 'run'
        home.mkdir()
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_STATE_HOME=str(home / '.local/state'), WLR_BACKENDS='headless',
                   WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman', GTK_USE_PORTAL='0',
                   NO_AT_BRIDGE='1', GTK_A11Y='none', GDK_BACKEND='wayland')
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        config = output / 'sway.conf'
        config.write_text('xwayland disable\noutput HEADLESS-1 mode 1280x720\n'
                          'output * bg #261631 solid_color\nseat seat0 fallback true\n')
        children = []
        with (output / 'runtime.log').open('w') as log:
            def spawn(command):
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                           start_new_session=True)
                children.append(process)
                return process

            def wait_for(predicate):
                for _ in range(160):
                    if any(child.poll() is not None for child in children):
                        raise RuntimeError('Private notification process exited')
                    if predicate():
                        return
                    time.sleep(.05)
                raise RuntimeError('Private notification fixture timed out')

            try:
                spawn(['swayfx', '--config', str(config)])
                wait_for(lambda: list(runtime.glob('sway-ipc*.sock')))
                env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
                env['WAYLAND_DISPLAY'] = next(path.name for path in runtime.glob('wayland-*') if path.is_socket())
                subprocess.run(['dbus-update-activation-environment', 'HOME', 'XDG_CONFIG_HOME',
                                'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR',
                                'WAYLAND_DISPLAY', 'SWAYSOCK'], env=env, check=True, timeout=5)
                daemon = spawn(['swaync', '--config', str(REPO / 'alpine/desktop/.config/swaync/config.json'),
                       '--style', str(REPO / 'alpine/desktop/.config/swaync/style.css')])
                wait_for(lambda: 'true' in subprocess.run(['gdbus', 'call', '--session', '--dest',
                    'org.freedesktop.DBus', '--object-path', '/org/freedesktop/DBus', '--method',
                    'org.freedesktop.DBus.NameHasOwner', 'org.freedesktop.Notifications'], env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5).stdout)
                owner = subprocess.check_output(['gdbus', 'call', '--session', '--dest',
                    'org.freedesktop.DBus', '--object-path', '/org/freedesktop/DBus', '--method',
                    'org.freedesktop.DBus.GetConnectionUnixProcessID', 'org.freedesktop.Notifications'],
                    env=env, text=True, timeout=5)
                if str(daemon.pid) not in owner:
                    raise RuntimeError('Notification server is not the owned private process')
                wait_for(lambda: 'Loading widget: widget-notifications' in (output / 'runtime.log').read_text())
                time.sleep(.5)
                source = REPO / 'alpine/wallpapers/generate.py'
                spec = importlib.util.spec_from_file_location('theme_notification_generator', source)
                generator = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(generator)
                painting = REPO / 'alpine/assets/gallery/delaware.png'
                entry = {'theme_name': 'Moonlight & <Brass>', 'title': 'Crossing & <Dawn>',
                         'file': str(painting.relative_to(REPO))}
                # Invoke the real wrapper with only the private session environment.
                previous = dict(os.environ)
                try:
                    os.environ.clear()
                    os.environ.update(env)
                    generator.notify_theme_complete(entry, {'status': 'complete', 'activated': True})
                finally:
                    os.environ.clear()
                    os.environ.update(previous)
                wait_for(lambda: subprocess.run(['swaync-client', '-sw', '-c'], env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout.strip() == '1')
                import gi
                gi.require_version('GdkPixbuf', '2.0')
                from gi.repository import GdkPixbuf

                def rendered():
                    subprocess.run(['grim', str(output / 'notification.png')], env=env, check=True, timeout=10)
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(output / 'notification.png'))
                    pixels = pixbuf.get_pixels()
                    # This compositor has only a solid background and our popup.
                    return len(set(pixels[index:index + 3] for index in
                                   range(0, len(pixels), pixbuf.get_n_channels()))) > 32

                wait_for(rendered)
                evidence = {'status': 'passed', 'notification_count': 1, 'entry': entry,
                            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                            'image_sha256': hashlib.sha256(painting.read_bytes()).hexdigest(),
                            'isolation': 'private headless SwayFX, D-Bus, HOME and XDG directories',
                            'fixture': 'Existing artwork with synthetic theme and painting labels',
                            'generation_requests': 0, 'live_session_notifications': 0,
                            'owned_notification_server_pid': daemon.pid,
                            'rendered_pixels_verified': True}
                (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
                print(json.dumps(evidence, indent=2))
            finally:
                for child in reversed(children):
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGTERM)
                for child in children:
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
