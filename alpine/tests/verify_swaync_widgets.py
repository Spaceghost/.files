#!/usr/bin/env python3
"""Render the SwayNC control center with its widgets in a private SwayFX/D-Bus session.

A fake MPRIS player on the private bus supplies album art so the media card is
exercised without touching the live Pithos session; the volume widget reads the
live PipeWire Pulse socket read-only when it exists.
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
CONFIG = REPO / 'alpine/desktop/.config/swaync/config.json'
STYLE = REPO / 'alpine/desktop/.config/swaync/style.css'
PAINTING = REPO / 'alpine/assets/gallery/themes/gruvbox-dark/2026-09-07-gruvbox-dark-yosemite-f932fef36c22.png'
ALBUM_ART = REPO / 'alpine/assets/spaceghost.png'
EXPECTED_WIDGETS = ('title', 'dnd', 'mpris', 'volume',
                    'backlight', 'buttons-grid', 'widget-notifications')

FAKE_PLAYER = r'''
import sys
from gi.repository import Gio, GLib

ART = sys.argv[1]
XML = """<node>
 <interface name="org.mpris.MediaPlayer2">
  <method name="Raise"/><method name="Quit"/>
  <property name="CanQuit" type="b" access="read"/>
  <property name="CanRaise" type="b" access="read"/>
  <property name="HasTrackList" type="b" access="read"/>
  <property name="Identity" type="s" access="read"/>
  <property name="DesktopEntry" type="s" access="read"/>
  <property name="SupportedUriSchemes" type="as" access="read"/>
  <property name="SupportedMimeTypes" type="as" access="read"/>
 </interface>
 <interface name="org.mpris.MediaPlayer2.Player">
  <method name="Next"/><method name="Previous"/><method name="Pause"/>
  <method name="PlayPause"/><method name="Stop"/><method name="Play"/>
  <method name="Seek"><arg name="Offset" type="x" direction="in"/></method>
  <method name="SetPosition"><arg name="TrackId" type="o" direction="in"/><arg name="Position" type="x" direction="in"/></method>
  <method name="OpenUri"><arg name="Uri" type="s" direction="in"/></method>
  <property name="PlaybackStatus" type="s" access="read"/>
  <property name="LoopStatus" type="s" access="readwrite"/>
  <property name="Rate" type="d" access="readwrite"/>
  <property name="Shuffle" type="b" access="readwrite"/>
  <property name="Metadata" type="a{sv}" access="read"/>
  <property name="Volume" type="d" access="readwrite"/>
  <property name="Position" type="x" access="read"/>
  <property name="MinimumRate" type="d" access="read"/>
  <property name="MaximumRate" type="d" access="read"/>
  <property name="CanGoNext" type="b" access="read"/>
  <property name="CanGoPrevious" type="b" access="read"/>
  <property name="CanPlay" type="b" access="read"/>
  <property name="CanPause" type="b" access="read"/>
  <property name="CanSeek" type="b" access="read"/>
  <property name="CanControl" type="b" access="read"/>
 </interface>
</node>"""
V = GLib.Variant
PROPS = {
    'org.mpris.MediaPlayer2': {
        'CanQuit': V('b', False), 'CanRaise': V('b', False), 'HasTrackList': V('b', False),
        'Identity': V('s', 'Ghost Planet Radio'), 'DesktopEntry': V('s', 'io.github.Pithos'),
        'SupportedUriSchemes': V('as', []), 'SupportedMimeTypes': V('as', [])},
    'org.mpris.MediaPlayer2.Player': {
        'PlaybackStatus': V('s', 'Playing'), 'LoopStatus': V('s', 'None'), 'Rate': V('d', 1.0),
        'Shuffle': V('b', False),
        'Metadata': V('a{sv}', {
            'mpris:trackid': V('o', '/org/mpris/MediaPlayer2/Track/1'),
            'mpris:length': V('x', 214000000), 'mpris:artUrl': V('s', 'file://' + ART),
            'xesam:title': V('s', 'Coast to Coast (Ghost Planet Mix)'),
            'xesam:artist': V('as', ['Space Ghost & The Zorak Quartet']),
            'xesam:album': V('s', 'Late Night Transmissions')}),
        'Volume': V('d', 0.8), 'Position': V('x', 42000000), 'MinimumRate': V('d', 1.0),
        'MaximumRate': V('d', 1.0), 'CanGoNext': V('b', True), 'CanGoPrevious': V('b', True),
        'CanPlay': V('b', True), 'CanPause': V('b', True), 'CanSeek': V('b', False),
        'CanControl': V('b', True)},
}


def on_method(connection, sender, path, interface, method, parameters, invocation):
    invocation.return_value(None)


def on_get(connection, sender, path, interface, prop):
    return PROPS[interface][prop]


def on_set(connection, sender, path, interface, prop, value):
    PROPS[interface][prop] = value
    return True


def on_bus(connection, name):
    info = Gio.DBusNodeInfo.new_for_xml(XML)
    for interface in info.interfaces:
        connection.register_object('/org/mpris/MediaPlayer2', interface, on_method, on_get, on_set)
    print('fake player ready', flush=True)


Gio.bus_own_name(Gio.BusType.SESSION, 'org.mpris.MediaPlayer2.ghostradio',
                 Gio.BusNameOwnerFlags.NONE, on_bus, None, None)
GLib.MainLoop().run()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--style', type=Path, default=STYLE)
    args = parser.parse_args()
    if not os.environ.get('OLDBOOK_NOTIFICATION_PRIVATE_BUS'):
        with tempfile.TemporaryDirectory(prefix='oldbook-swaync-bus-') as bus:
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
    config_path, style_path = args.config.resolve(), args.style.resolve()
    with tempfile.TemporaryDirectory(prefix='oldbook-swaync-widgets-') as temporary:
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
        pulse = Path('/run/user') / str(os.getuid()) / 'pulse/native'
        if pulse.exists():
            env['PULSE_SERVER'] = 'unix:' + str(pulse)
        sway_config = output / 'sway.conf'
        sway_config.write_text(f'xwayland disable\noutput HEADLESS-1 mode 1440x900\n'
                               f'output * bg "{PAINTING}" fill\nseat seat0 fallback true\n')
        player_script = base / 'fake_player.py'
        player_script.write_text(FAKE_PLAYER)
        children = []
        with (output / 'runtime.log').open('w') as log:
            def spawn(command):
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                           start_new_session=True)
                children.append(process)
                return process

            def wait_for(predicate, ticks=200):
                for _ in range(ticks):
                    if any(child.poll() is not None for child in children):
                        raise RuntimeError('Private fixture process exited')
                    if predicate():
                        return
                    time.sleep(.05)
                raise RuntimeError('Private fixture timed out')

            def log_text():
                return (output / 'runtime.log').read_text()

            def client(*flags):
                return subprocess.run(['swaync-client', '-sw', *flags], env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, timeout=10).stdout.strip()

            try:
                spawn(['swayfx', '--config', str(sway_config)])
                wait_for(lambda: list(runtime.glob('sway-ipc*.sock')))
                env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
                env['WAYLAND_DISPLAY'] = next(path.name for path in runtime.glob('wayland-*')
                                              if path.is_socket())
                subprocess.run(['dbus-update-activation-environment', 'HOME', 'XDG_CONFIG_HOME',
                                'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR',
                                'WAYLAND_DISPLAY', 'SWAYSOCK'], env=env, check=True, timeout=5)
                spawn([sys.executable, str(player_script), str(ALBUM_ART)])
                wait_for(lambda: 'fake player ready' in log_text())
                daemon = spawn(['swaync', '--config', str(config_path), '--style', str(style_path)])
                wait_for(lambda: 'Loading widget: widget-notifications' in log_text())
                time.sleep(1)
                for summary, body, extra in (
                        ('Ghost Gallery', 'A new painting is ready: Yosemite, with commentary.',
                         ['-i', str(ALBUM_ART)]),
                        ('Codex', 'Approval requested in the Lab workspace.', ['-u', 'normal'])):
                    subprocess.run(['notify-send', *extra, summary, body], env=env, check=True, timeout=10)
                wait_for(lambda: client('-c') == '2')
                client('-op')
                time.sleep(2)
                subprocess.run(['grim', str(output / 'control-center.png')], env=env, check=True, timeout=15)
                client('-cp')
                time.sleep(.5)
                subprocess.run(['grim', str(output / 'closed.png')], env=env, check=True, timeout=15)
                text = log_text()
                loaded = [name for name in EXPECTED_WIDGETS if f'Loading widget: {name}' in text]
                problems = [line for line in text.splitlines()
                            if any(word in line.lower() for word in ('invalid', 'error', 'critical', 'warning'))]
                evidence = {
                    'status': 'passed' if len(loaded) == len(EXPECTED_WIDGETS) else 'failed',
                    'widgets_loaded': loaded,
                    'widgets_expected': list(EXPECTED_WIDGETS),
                    'log_problems': problems,
                    'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest(),
                    'style_sha256': hashlib.sha256(style_path.read_bytes()).hexdigest(),
                    'isolation': 'private headless SwayFX (pixman), private D-Bus session, private HOME and XDG directories',
                    'fake_player': 'org.mpris.MediaPlayer2.ghostradio with local album art',
                    'live_session_notifications': 0,
                    'owned_notification_server_pid': daemon.pid,
                    'notification_count': 2,
                }
                (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
                print(json.dumps(evidence, indent=2))
                return 0 if evidence['status'] == 'passed' else 1
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


if __name__ == '__main__':
    sys.exit(main())
