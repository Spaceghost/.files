#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prove actual CLI hold/release/chord behavior on a private Xvfb/Openbox server."""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def child(output):
    from Xlib import X, XK, Xatom
    from Xlib.display import Display
    from Xlib.ext import xtest
    from hold_to_help.hold import KEY_CAPSLOCK, KEY_LEFTMETA
    from hold_to_help.service import SessionLease
    from hold_to_help.x11 import physical_trigger_codes

    connection = Display()
    root = connection.screen().root
    control = root.create_window(30, 810, 600, 80, 0, connection.screen().root_depth,
                                 X.InputOutput, X.CopyFromParent,
                                 background_pixel=connection.screen().white_pixel)
    control.set_wm_name('Hold to Help synthetic application')
    control.set_wm_class('hth-test', 'firefox')
    control.change_property(connection.intern_atom('_NET_WM_PID'), Xatom.CARDINAL, 32, [os.getpid()])
    control.map()
    connection.sync()
    time.sleep(.3)
    root.change_property(connection.intern_atom('_NET_ACTIVE_WINDOW'), Xatom.WINDOW, 32, [control.id])
    connection.set_input_focus(control, X.RevertToParent, X.CurrentTime)
    connection.sync()
    focus = connection.get_input_focus().focus.id
    assert focus == control.id
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    config_home = runtime / 'config'
    config_home.mkdir()
    os.environ['XDG_CONFIG_HOME'] = str(config_home)
    config_dir = config_home / 'hold-to-help'
    config_dir.mkdir()
    profiles = {'profiles': {'firefox': {'name': 'Synthetic Firefox', 'aliases': ['firefox'],
                'coverage': 'Partial synthetic verification profile',
                'rows': [{'key': f'Ctrl+{index}', 'description': f'Action {index}'} for index in range(60)]}}}
    (config_dir / 'profiles.json').write_text(json.dumps(profiles))
    lease = SessionLease(runtime, display=os.environ['DISPLAY'])
    keycodes = physical_trigger_codes(os.environ['DISPLAY'])
    physical = {portable: raw for raw, portable in keycodes.items()}
    chord = connection.keysym_to_keycode(XK.string_to_keysym('a'))
    # Remap only this private server: physical CAPS must still trigger while
    # its current keysym is Escape. No xmodmap or live keyboard changes.
    connection.change_keyboard_mapping(physical[KEY_CAPSLOCK], [(XK.string_to_keysym('Escape'),)])
    connection.sync()
    time.sleep(.1)
    evidence = {'private_display': True, 'host_input_unchanged': True, 'triggers': {}}

    def read_status():
        try:
            return json.loads(lease.status_path.read_text())
        except (OSError, ValueError):
            return {}

    def wait_for(predicate, process, description, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f'daemon exited while {description}: {read_status()}')
            value = read_status()
            if predicate(value):
                return value
            time.sleep(.015)
        raise AssertionError(f'timed out {description}: {read_status()}')

    def key(raw, down):
        xtest.fake_input(connection, X.KeyPress if down else X.KeyRelease, raw)
        connection.sync()

    for trigger, raw in [('super', physical[KEY_LEFTMETA]), ('capslock', physical[KEY_CAPSLOCK])]:
        config = config_dir / 'config.toml'
        config.write_text(f"trigger='{trigger}'\nhold_seconds=0.2\nbackend='x11'\n")
        command = [sys.executable, '-m', 'hold_to_help']
        dumped = subprocess.run([*command, 'dump'], capture_output=True, text=True, timeout=5)
        assert dumped.returncode == 0, dumped.stderr
        snapshot = json.loads(dumped.stdout)
        assert snapshot['app'] == 'Synthetic Firefox', snapshot
        assert snapshot['_output_rect']['width'] == 1280
        label = 'Caps Lock' if trigger == 'capslock' else 'Super'
        assert snapshot['sections'][-1]['rows'][0]['key'] == f'{label} (hold)'
        (output / f'{trigger}-snapshot.json').write_text(dumped.stdout)
        process = None
        try:
            with (output / f'{trigger}-daemon.log').open('w') as log:
                process = subprocess.Popen([*command, 'daemon'], stdin=subprocess.DEVNULL,
                                            stdout=log, stderr=subprocess.STDOUT)
            ready = wait_for(lambda status: status.get('device_count') == 1
                             and status.get('graphical_active') and not status.get('locked'),
                             process, 'waiting for ready input')
            duplicate = subprocess.run([*command, 'daemon'], capture_output=True, text=True, timeout=3)
            assert duplicate.returncode == 0, duplicate.stderr
            assert read_status()['pid'] == process.pid
            key(raw, True)
            time.sleep(.07)
            assert not read_status().get('visible'), read_status()
            key(raw, False)
            time.sleep(.3)
            assert not read_status().get('visible'), read_status()
            key(raw, True)
            visible = wait_for(lambda status: status.get('visible') and not status.get('source_pending'),
                               process, 'showing on held trigger')
            assert connection.get_input_focus().focus.id == focus
            time.sleep(.65)
            assert read_status()['visible'], 'autorepeat canceled a held trigger'
            # A press and release in one flush is shorter than a polling frame.
            xtest.fake_input(connection, X.KeyPress, chord)
            xtest.fake_input(connection, X.KeyRelease, chord)
            connection.sync()
            wait_for(lambda status: not status.get('visible'), process, 'canceling same-flush chord', 1)
            time.sleep(.35)
            assert not read_status().get('visible')
            key(raw, False)
            time.sleep(.05)
            key(raw, True)
            wait_for(lambda status: status.get('visible'), process, 'fresh trigger after chord')
            # Pointer wheel events must not act as keyboard chord cancellation.
            xtest.fake_input(connection, X.ButtonPress, 5)
            xtest.fake_input(connection, X.ButtonRelease, 5)
            connection.sync()
            time.sleep(.1)
            assert read_status()['visible']
            assert connection.get_input_focus().focus.id == focus
            connection.force_screen_saver(X.ScreenSaverActive)
            connection.sync()
            wait_for(lambda status: not status.get('visible'), process, 'suppressing on screensaver', 1)
            connection.force_screen_saver(X.ScreenSaverReset)
            connection.sync()
            time.sleep(.1)
            assert not read_status()['visible'], 'unlock must require a fresh trigger'
            key(raw, False)
            time.sleep(.05)
            key(raw, True)
            wait_for(lambda status: status.get('visible'), process, 'fresh trigger after screensaver')
            released_at = time.monotonic()
            key(raw, False)
            wait_for(lambda status: not status.get('visible'), process, 'hiding on release', 1)
            release_latency = time.monotonic() - released_at
            assert release_latency < .2, release_latency
            evidence['triggers'][trigger] = {
                'config_selected_trigger': ready['trigger'], 'tap_stays_hidden': True,
                'held_shows_context': True, 'same_flush_chord_cancels_until_release': True,
                'fresh_hold_after_chord': True, 'pointer_wheel_keeps_visible': True,
                'release_hides_seconds': release_latency, 'focus_preserved': True,
                'duplicate_daemon_excluded': True, 'xdg_profiles_and_ewmh_context': True,
                'autorepeat_keeps_visible': True, 'screensaver_cancels_until_fresh_hold': True,
                'physical_caps_remapped_escape': trigger == 'capslock'}
        finally:
            key(raw, False)
            key(chord, False)
            stop(process)
    control.destroy()
    connection.close()
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    if args.child:
        child(output)
        return
    with tempfile.TemporaryDirectory(prefix='hth-daemon-x11-') as directory:
        runtime = Path(directory)
        runtime.chmod(0o700)
        reader, writer = os.pipe()
        xvfb = wm = None
        try:
            with (output / 'xvfb.log').open('w') as log:
                xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(writer), '-screen', '0',
                                         '1280x960x24', '-nolisten', 'tcp'], pass_fds=(writer,),
                                        stdout=log, stderr=subprocess.STDOUT)
            os.close(writer)
            writer = None
            if not select.select([reader], [], [], 10)[0]:
                raise RuntimeError('private Xvfb did not become ready')
            number = os.read(reader, 100).decode().strip()
            if not number.isdigit():
                raise RuntimeError('invalid private Xvfb display')
            env = dict(os.environ, DISPLAY=':' + number, XDG_RUNTIME_DIR=str(runtime),
                       PYTHONPATH=str(PROJECT), QT_QPA_PLATFORM='xcb', PYTHONDONTWRITEBYTECODE='1')
            for key in ('WAYLAND_DISPLAY', 'SWAYSOCK', 'XDG_SESSION_ID', 'XDG_VTNR',
                        'DBUS_SESSION_BUS_ADDRESS', 'QT_QPA_PLATFORMTHEME'):
                env.pop(key, None)
            config = runtime / 'openbox.xml'
            config.write_text('<openbox_config xmlns="http://openbox.org/3.4/rc"/>\n')
            with (output / 'openbox.log').open('w') as log:
                wm = subprocess.Popen(['openbox', '--config', str(config)], env=env,
                                      stdout=log, stderr=subprocess.STDOUT)
            time.sleep(.3)
            result = subprocess.run([sys.executable, __file__, '--child', '--output', str(output)],
                                    env=env, capture_output=True, text=True, timeout=45)
            (output / 'client.log').write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f'daemon proof failed; inspect {output / "client.log"}')
            xvfb.send_signal(signal.SIGSTOP)
            try:
                started = time.monotonic()
                stalled = subprocess.run([sys.executable, '-m', 'hold_to_help', 'dump', '--backend', 'x11'],
                                         env=env, capture_output=True, text=True, timeout=4)
                elapsed = time.monotonic() - started
                assert stalled.returncode == 1 and elapsed < 2.5, (stalled.returncode, elapsed)
                assert 'timed out' in stalled.stderr, stalled.stderr
            finally:
                xvfb.send_signal(signal.SIGCONT)
            evidence_path = output / 'evidence.json'
            evidence = json.loads(evidence_path.read_text())
            evidence['stalled_display_setup_fails_within_seconds'] = elapsed
            evidence_path.write_text(json.dumps(evidence, indent=2) + '\n')
            print(json.dumps(evidence))
        finally:
            os.close(reader)
            if writer is not None:
                os.close(writer)
            stop(wm)
            stop(xvfb)


if __name__ == '__main__':
    main()
