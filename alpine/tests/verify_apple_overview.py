#!/usr/bin/env python3
"""Check Apple overview key dispatch in private Sway, without host input."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import time

from verify_decoration_attachment import SwayIPC, walk
from verify_carousel import stop_private


ROOT = Path(__file__).resolve().parents[2]


def require(value, message):
    if not value:
        raise AssertionError(message)
    return value


def wait_for(callback, message):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if value := callback():
            return value
        time.sleep(.025)
    raise AssertionError(message)


def overview_painted(path):
    """The fixture terminal has no text below its first line; the carousel does."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    image = GdkPixbuf.Pixbuf.new_from_file(str(path))
    data = memoryview(image.get_pixels())
    channels, stride = image.get_n_channels(), image.get_rowstride()
    bright = 0
    for y in range(image.get_height() * 2 // 3, image.get_height()):
        for x in range(image.get_width() // 8, image.get_width() * 7 // 8):
            offset = y * stride + x * channels
            red, green, blue = data[offset:offset + 3]
            bright += min(red, green, blue) > 150
    return bright > 120


def run(output, real=False):
    output.mkdir(parents=True, exist_ok=False)
    fragments = ROOT / 'alpine/desktop/.config/sway/local.d'
    sources = [fragments / name for name in ('apple-overview.conf', 'window-switcher.conf')]
    sources.append(Path(__file__))
    sources.extend(Path(__file__).with_name(name)
                   for name in ('verify_decoration_attachment.py', 'verify_carousel.py'))
    if real:
        library = ROOT / 'alpine/desktop/.local/lib/mbp_intel'
        sources.extend(library / name for name in ('carousel.py', 'carousel_view.py',
                       'window_switching.py', 'showdesktop.py',
                       'overlay_theme.py', 'workspace_model.py'))
        sources.extend(ROOT / 'alpine/desktop/.local/bin' / name
                       for name in ('mbp-intel-carousel', 'mbp-intel-workspaces'))
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sources}
    evidence = {'status': 'running', 'checks': [], 'source_sha256': hashes,
                'host_changes': 0, 'physical_keyboard_events_read': 0,
                'scope': 'Native Sway dispatch to private stubs; real Foot receives raw F3/F4. '
                         'Does not test actual carousel/menu GTK teardown ordering.'}
    if real:
        evidence['scope'] = ('Real warm carousel and private Fuzzel dmenu with one synthetic entry; '
                             'native layer mapping, keyboard handoff and mode recovery.')
    processes = []
    ipc = events = None
    with tempfile.TemporaryDirectory(prefix='apple-overview-') as directory:
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
                   GTK_A11Y='none', GTK_USE_PORTAL='0', XDG_CURRENT_DESKTOP='sway',
                   DBUS_SESSION_BUS_ADDRESS=f'unix:path={base / "bus"}')
        calls, keys = base / 'calls', base / 'keys'
        calls.touch()
        keys.touch()
        binaries = Path(env['HOME']) / '.local/bin'
        binaries.mkdir(parents=True)
        for name in ('mbp-intel-carousel', 'mbp-intel-menu'):
            helper = binaries / name
            if real and name == 'mbp-intel-carousel':
                helper.symlink_to(ROOT / 'alpine/desktop/.local/bin/mbp-intel-carousel')
                continue
            helper.write_text('#!/usr/bin/python3\nimport os, sys\n'
                              f'fd = os.open({str(calls)!r}, os.O_WRONLY | os.O_APPEND)\n'
                              f'os.write(fd, ({name!r} + " " + " ".join(sys.argv[1:]) + "\\n").encode())\n'
                              'os.close(fd)\n')
            helper.chmod(0o755)
            if real:
                with helper.open('a') as stream:
                    stream.write('import subprocess\n'
                                 'result = subprocess.run(["fuzzel", "--config=/dev/null", "--dmenu", '
                                 '"--namespace=apple-launcher-fixture", "--prompt=Private launcher: ", '
                                 '"--lines=3", "--width=36"], '
                                 'input="Synthetic application\\n", text=True)\n'
                                 f'open({str(base / "launcher-exit")!r}, "w").write(str(result.returncode))\n')
        receiver = base / 'receiver.py'
        receiver.write_text('import os, termios, tty\n'
                            'tty.setraw(0)\nprint("Application key receiver", flush=True)\n'
                            f'fd = os.open({str(keys)!r}, os.O_WRONLY | os.O_APPEND)\n'
                            f'open({str(base / "receiver-ready")!r}, "w").close()\n'
                            'while True:\n    os.write(fd, os.read(0, 128))\n')
        config = output / 'sway.conf'
        config.write_text('xwayland disable\noutput HEADLESS-1 mode 900x600\n'
                          'output * bg #160d22 solid_color\nseat seat0 fallback true\n'
                          'input * xkb_layout us\ninput * repeat_delay 200\ninput * repeat_rate 30\n'
                          'focus_follows_mouse no\n' +
                          ''.join(path.read_text() for path in sources[:2]))
        foot_config = base / 'foot.ini'
        foot_config.write_text('[main]\nfont=monospace:size=12\n')
        log = (output / 'runtime.log').open('w')

        def spawn(argv):
            process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
            processes.append(process)
            return process

        def request(kind=4, command=''):
            return ipc.requests([(kind, command)])[0]

        def command(value):
            require(all(item.get('success') for item in request(0, value)),
                    f'Sway rejected {value}')

        def mode():
            return request(12)['name']

        def recorded():
            return calls.read_text().splitlines()

        def press(key, expected, held=False):
            start = len(recorded())
            args = ['-P', key, '-s', '650', '-p', key] if held else ['-k', key]
            subprocess.run(['wtype', *args], env=env, check=True, timeout=4)
            wait_for(lambda: len(recorded()) >= start + len(expected), f'{key} did not dispatch')
            time.sleep(.1)
            observed = recorded()[start:]
            require(sorted(observed) == sorted(expected), f'{key}: unexpected dispatch {observed}')
            return observed

        def check(name):
            evidence['checks'].append({'name': name, 'passed': True})

        def real_flows():
            runtime = Path(env['XDG_RUNTIME_DIR'])
            token = hashlib.sha256(env['SWAYSOCK'].encode()).hexdigest()[:12]
            state_path = runtime / 'mbp-intel' / ('carousel-' + token) / 'state.json'

            def state():
                try:
                    return json.loads(state_path.read_text())
                except (OSError, ValueError):
                    return {}

            def layers(namespace):
                return [surface for item in request(3)
                        for surface in item.get('layer_shell_surfaces', [])
                        if surface.get('namespace') == namespace]

            def key(name):
                subprocess.run(['wtype', '-k', name], env=env, check=True, timeout=4)

            def opened():
                current = state()
                return (current.get('open')
                        and mode() == 'window-switcher' and layers('mbp-intel-carousel'))

            def closed():
                return not state().get('open') and not layers('mbp-intel-carousel') and mode() == 'default'

            spawn([str(binaries / 'mbp-intel-carousel'), 'daemon'])
            initial = wait_for(lambda: state() if state().get('ready') else None,
                               'real carousel daemon did not become ready')
            evidence['carousel_pid'] = initial['pid']
            check('real-carousel-daemon-is-warm-before-keypress')
            key('XF86LaunchA')
            wait_for(opened, 'Mission Control did not map the actual overview')
            require(mode() == 'window-switcher', 'real overview did not enter its mode')
            def painted():
                path = output / 'real-overview.png'
                subprocess.run(['grim', '-o', 'HEADLESS-1', str(path)],
                               env=env, check=True, timeout=5)
                return overview_painted(path)

            wait_for(painted, 'actual overview caption did not paint')
            check('mission-control-maps-real-overview-layer')
            key('XF86LaunchA')
            wait_for(closed, 'second Mission Control did not close actual overview')
            check('second-mission-control-unmaps-overview-and-restores-default-mode')
            key('XF86LaunchA')
            wait_for(opened, 'Mission Control did not reopen the actual overview')
            # Keep one virtual keyboard through the launcher handoff. Destroying
            # it between F4 and Escape can close Fuzzel on keyboard focus loss.
            keyboard = spawn(['wtype', '-k', 'XF86LaunchB', '-s', '1800',
                              '-k', 'Escape', '-s', '500'])
            evidence['real_flow_keyboard'] = 'one persistent wtype device through F4/Escape handoff'
            wait_for(lambda: closed() and layers('apple-launcher-fixture'),
                     'Launchpad did not hand off from carousel to real Fuzzel')
            # Layer mapping precedes Fuzzel's first matching/content paint.
            time.sleep(.35)
            require(layers('apple-launcher-fixture') and not (base / 'launcher-exit').exists(),
                    'Fuzzel lost focus before Escape')
            subprocess.run(['grim', '-o', 'HEADLESS-1', str(output / 'real-launcher.png')],
                           env=env, check=True, timeout=5)
            check('launchpad-unmaps-overview-and-maps-fuzzel-in-default-mode')
            wait_for(lambda: not layers('apple-launcher-fixture') and (base / 'launcher-exit').exists()
                     and (base / 'launcher-exit').read_text(),
                     'Fuzzel did not receive Escape')
            evidence['fuzzel_exit_code'] = int((base / 'launcher-exit').read_text())
            # Fuzzel 1.14 changed dmenu cancellation from exit 1 to exit 2.
            require(evidence['fuzzel_exit_code'] == 2,
                    f'Fuzzel did not cancel with Escape: exit {evidence["fuzzel_exit_code"]}')
            require(closed() and any(item.get('app_id') == 'apple-key-fixture' and item.get('focused')
                    for item in walk(request())), 'Escape did not return to the fixture window')
            require(state()['pid'] == initial['pid'], 'key actions unexpectedly replaced the warm daemon')
            require(keyboard.wait(timeout=3) == 0, 'private key sequence failed')
            check('fuzzel-receives-escape-and-restores-window-focus')

        try:
            spawn(['dbus-daemon', '--session', '--nofork', f'--address={env["DBUS_SESSION_BUS_ADDRESS"]}'])
            wait_for(lambda: (base / 'bus').is_socket(), 'private D-Bus did not start')
            subprocess.run(['/usr/bin/swayfx', '--validate', '--config', str(config)], env=env,
                           stdout=log, stderr=log, check=True, timeout=8)
            check('production-fragments-parse-together')
            spawn(['/usr/bin/swayfx', '--config', str(config)])

            def ready():
                sockets = list(Path(env['XDG_RUNTIME_DIR']).glob('sway-ipc.*.sock'))
                displays = [path for path in Path(env['XDG_RUNTIME_DIR']).glob('wayland-*')
                            if path.is_socket()]
                return (sockets[0], displays[0]) if sockets and displays else None

            sway_socket, display = wait_for(ready, 'private Sway did not start')
            env.update(SWAYSOCK=str(sway_socket), WAYLAND_DISPLAY=display.name)
            subprocess.run(['dbus-update-activation-environment', 'SWAYSOCK', 'WAYLAND_DISPLAY'],
                           env=env, stdout=log, stderr=log, check=True, timeout=4)
            ipc = SwayIPC(sway_socket)
            if real:
                events = SwayIPC(sway_socket)
                require(events.requests([(2, '["binding","mode"]')])[0].get('success'),
                        'private binding trace subscription failed')
            spawn(['/usr/bin/foot', '--config', str(foot_config), '--app-id', 'apple-key-fixture',
                   '--title', 'Private Apple key fixture', sys.executable, str(receiver)])
            wait_for(lambda: any(item.get('app_id') == 'apple-key-fixture' for item in walk(request()))
                     and (base / 'receiver-ready').exists(), 'private key receiver did not map')
            if real:
                real_flows()
            else:
                press('XF86LaunchA', ['mbp-intel-carousel show'], held=True)
                check('held-mission-control-opens-once')
                press('XF86LaunchB', ['mbp-intel-menu '])
                check('launchpad-opens-application-menu')
                command('mode "window-switcher"')
                press('XF86LaunchA', [], held=True)
                require(mode() == 'default', 'Mission Control did not leave switcher mode')
                check('held-mission-control-closes-once-and-restores-default-mode')
                command('mode "window-switcher"')
                press('XF86LaunchB', ['mbp-intel-menu '])
                require(mode() == 'default', 'Launchpad did not leave switcher mode')
                check('launchpad-cancels-overview-opens-menu-and-restores-default-mode')
                command('mode "window-switcher"')
                press('Escape', [])
                require(mode() == 'default', 'existing Escape binding was lost')
                check('later-mode-block-preserves-existing-escape-and-new-apple-keys')
            application_keys = {}
            for key in ('F3', 'F4'):
                before, actions = keys.stat().st_size, recorded()
                subprocess.run(['wtype', '-k', key], env=env, check=True, timeout=4)
                wait_for(lambda: keys.stat().st_size > before, f'{key} did not reach application')
                application_keys[key] = keys.read_bytes()[before:].hex()
                require(recorded() == actions, f'{key} unexpectedly invoked a desktop action')
                check(f'raw-{key}-reaches-application-without-desktop-action')
            evidence['application_key_bytes_hex'] = application_keys
            evidence['dispatch_trace'] = recorded()
            subprocess.run(['grim', '-o', 'HEADLESS-1', str(output / 'private-key-fixture.png')],
                           env=env, check=True, timeout=5)
            require(all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                        for name, digest in hashes.items()), 'verified sources changed during run')
            evidence['status'] = 'passed'
        except BaseException as error:
            evidence.update(status='failed', error=str(error))
            raise
        finally:
            if events:
                try:
                    evidence['final_mode'] = mode()
                    evidence['final_carousel_state'] = [json.loads(path.read_text()) for path in
                            Path(env['XDG_RUNTIME_DIR']).glob('mbp-intel/carousel-*/state.json')]
                    evidence['final_launcher_exit'] = ((base / 'launcher-exit').read_text()
                            if (base / 'launcher-exit').exists() else None)
                    evidence['dispatch_trace'] = recorded()
                    events.connection.setblocking(False)
                    data = bytearray()
                    while len(data) < 1024 * 1024:
                        try:
                            chunk = events.connection.recv(65536)
                        except BlockingIOError:
                            break
                        if not chunk:
                            break
                        data.extend(chunk)
                    trace = []
                    while len(data) >= 14:
                        length, kind = struct.unpack('<II', data[6:14])
                        if len(data) < length + 14:
                            break
                        trace.append({'kind': kind, 'event': json.loads(data[14:14 + length])})
                        del data[:14 + length]
                    evidence['binding_trace'] = trace
                except (OSError, ValueError, RuntimeError, AssertionError) as error:
                    evidence['trace_error'] = str(error)
                finally:
                    events.close()
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
            if evidence['cleanup']['remaining_processes']:
                evidence.update(status='failed', error='private process cleanup left survivors')
            log.close()
            (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
            require(not evidence['cleanup']['remaining_processes'], 'private process cleanup left survivors')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--real', action='store_true', help='exercise actual carousel and Fuzzel layers')
    arguments = parser.parse_args()
    run(arguments.output.resolve(), arguments.real)
