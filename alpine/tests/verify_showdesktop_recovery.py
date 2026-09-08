#!/usr/bin/env python3
"""Exercise real show-desktop overlays and recovery in an isolated Sway session."""
import argparse
from contextlib import nullcontext
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from verify_decoration_attachment import SwayIPC, walk


REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/desktop/.local/bin/mbp-intel-showdesktop'
BUS_MARKER = 'MBP_INTEL_SHOWDESKTOP_PRIVATE_BUS'
ROOT_MARKER = 'MBP_INTEL_SHOWDESKTOP_PRIVATE_ROOT'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def cleanup_private(runtime):
    marker = ('XDG_RUNTIME_DIR=' + str(runtime)).encode()

    def owned():
        result = []
        for path in Path('/proc').iterdir():
            if path.name.isdecimal():
                try:
                    if marker in (path / 'environ').read_bytes().split(b'\0'):
                        result.append(int(path.name))
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    pass
        return result

    for identifier in owned():
        try:
            os.kill(identifier, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 1
    while owned() and time.monotonic() < deadline:
        time.sleep(.025)
    for identifier in owned():
        try:
            os.kill(identifier, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    sources = [HELPER, REPO / 'alpine/desktop/.local/lib/mbp_intel/showdesktop.py',
               REPO / 'alpine/desktop/.local/bin/mbp-intel-workspaces',
               REPO / 'alpine/desktop/.local/lib/mbp_intel/workspace_model.py']
    snapshots = {str(path.relative_to(REPO)): path.read_bytes() for path in sources}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in snapshots.items()}
    evidence = {'status': 'running', 'checks': [], 'source_sha256': hashes,
                'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'host_changes': 0, 'isolation': 'private Sway, D-Bus, HOME and XDG directories',
                'fixtures': 'two synthetic Foot windows; private carousel dispatch recorder'}
    processes = []
    ipc = None
    with nullcontext(os.environ[ROOT_MARKER]) as directory:
        base = Path(directory)
        env = dict(os.environ)
        for key, name in (('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'), ('XDG_CONFIG_HOME', 'config'),
                          ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')):
            path = base / name
            path.mkdir(mode=0o700, exist_ok=True)
            env[key] = str(path)
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        env.update(WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='2',
                   GTK_USE_PORTAL='0', NO_AT_BRIDGE='1')
        config = output / 'sway.conf'
        config.write_text('xwayland disable\noutput HEADLESS-1 mode 1000x700 position 0 0\n'
                          'output HEADLESS-2 mode 800x600 position 1000 0\n'
                          'output * bg #13091f solid_color\nseat seat0 fallback true\n'
                          'focus_follows_mouse no\n'
                          'for_window [app_id="^showdesktop-fixture-"] floating enable\n'
                          'workspace "1: Recovery Café" output HEADLESS-1\n'
                          'workspace "9: Other output" output HEADLESS-2\n')
        (base / 'foot.ini').write_text('[main]\nfont=monospace:size=10\n')
        local_bin = Path(env['HOME']) / '.local/bin'
        local_bin.mkdir(parents=True)
        for name, data in snapshots.items():
            relative = Path(name).relative_to('alpine/desktop')
            destination = Path(env['HOME']) / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            destination.chmod(0o755 if destination.parent == local_bin else 0o644)
        helper = local_bin / 'mbp-intel-showdesktop'
        trace = base / 'carousel.jsonl'
        carousel = local_bin / 'mbp-intel-carousel'
        carousel.write_text('#!/usr/bin/env python3\nimport json,sys\n'
                            f'with open({str(trace)!r}, "a") as stream:\n'
                            '    stream.write(json.dumps(sys.argv[1:]) + "\\n")\n')
        carousel.chmod(0o755)
        state_dir = Path(env['XDG_RUNTIME_DIR']) / 'mbp-intel/showdesktop'
        log = (output / 'runtime.log').open('w')

        def spawn(command):
            process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
            processes.append(process)
            return process

        def wait_for(predicate, message, seconds=12, interval=.01):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if value := predicate():
                    return value
                time.sleep(interval)
            raise AssertionError(message)

        def request(kind=4, text=''):
            return ipc.requests([(kind, text)])[0]

        def command(text):
            result = request(0, text)
            require(result and all(item.get('success') for item in result), f'private Sway rejected {text}')

        def focused():
            return next(item for item in request(1) if item['focused'])

        def state():
            try:
                return json.loads((state_dir / 'state.json').read_text())
            except FileNotFoundError:
                return {}

        def busy():
            try:
                with (state_dir / 'gesture.lock').open('a') as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        return False
                    except BlockingIOError:
                        return True
            except FileNotFoundError:
                return False

        def action(name):
            child = spawn([str(helper), name])
            require(child.wait(timeout=6) == 0, f'{name} command failed')

        def cleared():
            return not state() and not (state_dir / 'capture.ppm').exists() and not busy()

        def hide():
            command('workspace number "1: Recovery Café"')
            action('show')
            wait_for(lambda: state().get('hidden') and not busy(), 'hide did not finish')
            require(focused()['name'] == 'desktop', 'hide did not enter its private desktop')

        def leave(number, label):
            command(f'workspace number "{number}: {label}"')
            destination = focused()
            wait_for(cleared, 'leaving workspace retained state, capture or animation')
            # Longer than either animation: an old callback must not move focus
            # back after cancellation has appeared to succeed.
            deadline = time.monotonic() + .9
            while time.monotonic() < deadline:
                require(focused()['id'] == destination['id'], 'cancelled animation changed the destination')
                time.sleep(.04)
            return destination

        def carousel_calls():
            return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []

        def record(name):
            evidence['checks'].append(name)
            (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

        def private_helpers():
            marker = ('XDG_RUNTIME_DIR=' + env['XDG_RUNTIME_DIR']).encode()
            result = []
            for path in Path('/proc').iterdir():
                if not path.name.isdecimal():
                    continue
                try:
                    if marker in (path / 'environ').read_bytes().split(b'\0'):
                        args = (path / 'cmdline').read_bytes().split(b'\0')
                        if str(helper).encode() in args and b'daemon' in args:
                            result.append(int(path.name))
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    pass
            return result

        try:
            sway = spawn(['swayfx', '-c', str(config)])

            def ready():
                runtime = Path(env['XDG_RUNTIME_DIR'])
                sockets = list(runtime.glob('sway-ipc.*.sock'))
                displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
                return (sockets[0], displays[0]) if sockets and displays else None

            sway_socket, display = wait_for(ready, 'private Sway did not start')
            env.update(SWAYSOCK=str(sway_socket), WAYLAND_DISPLAY=display.name)
            subprocess.run(['dbus-update-activation-environment', 'WAYLAND_DISPLAY', 'SWAYSOCK'],
                           env=env, check=True, timeout=4, stdout=log, stderr=log)
            ipc = SwayIPC(sway_socket)
            command('workspace number "9: Other output"; workspace number "1: Recovery Café"')
            for number in (1, 2):
                spawn(['/usr/bin/foot', '--config', str(base / 'foot.ini'),
                       '--window-size-pixels=320x240',
                       '--app-id', f'showdesktop-fixture-{number}', '--title', f'Private recovery fixture {number}',
                       'sh', '-c', 'sleep 180'])
                node = wait_for(lambda: next((item for item in walk(request())
                                if item.get('app_id') == f'showdesktop-fixture-{number}'), None), 'Foot did not map')
                wait_for(lambda: any(item.get('id') == node['id'] and 0 < item['rect']['width'] <= 400
                                     and 0 < item['rect']['height'] <= 350 for item in walk(request())),
                         'fixture initial floating size did not settle')
                command(f'[con_id={node["id"]}] move position {80 + number * 170} px {80 + number * 100} px')
                time.sleep(.15)
            original = next(item for item in walk(request()) if item.get('type') == 'workspace' and item.get('num') == 1)
            windows = {item['id']: item['rect'] for item in walk(original) if item.get('app_id')}
            evidence['fixture_windows'] = [{'id': identifier, 'rect': rect} for identifier, rect in windows.items()]

            def usable():
                current = next(item for item in walk(request()) if item.get('id') == original['id'])
                actual = {item['id']: item['rect'] for item in walk(current) if item.get('app_id')}
                evidence.setdefault('geometry_checks', []).append(actual)
                require(actual == windows, 'captured windows changed identity, workspace or geometry')
                for identifier in windows:
                    command(f'[con_id={identifier}] focus')
                    require(any(item.get('id') == identifier and item.get('focused') for item in walk(request())),
                            'captured window cannot receive focus')

            daemon = spawn([str(helper), 'daemon'])
            wait_for(lambda: state_dir.exists() and list(state_dir.glob('control-*.sock')), 'daemon control did not appear')
            hide()
            require(daemon.poll() is None, 'daemon stopped after its internal hide switch')
            record('own-hide-switch-keeps-guard-and-hidden-state')
            action('restore-or-carousel')
            wait_for(cleared, 'return gesture did not restore')
            usable()
            require(carousel_calls() == [], 'return gesture opened carousel while windows were hidden')
            record('return-gesture-restores-same-windows-without-carousel')
            action('restore-or-carousel')
            wait_for(lambda: carousel_calls() == [['show']], 'bare return gesture did not open carousel exactly once')
            record('bare-return-gesture-dispatches-carousel-show')

            hide()
            destination = leave(2, 'Empty destination')
            evidence['empty_destination'] = {key: destination[key] for key in ('id', 'num', 'name')}
            usable()
            record('external-navigation-retains-empty-destination-and-releases-windows')
            action('show')
            wait_for(lambda: state() and not state().get('hidden') and busy(), 'missed pre-swap hide interval', interval=.002)
            leave(3, 'Before swap')
            usable()
            record('navigation-before-hide-swap-cancels-animation')
            action('show')
            wait_for(lambda: state().get('hidden') and busy(), 'missed active hide interval', interval=.002)
            leave(4, 'During hide')
            usable()
            record('navigation-during-hide-cancels-animation')
            hide()
            action('restore')
            wait_for(busy, 'restore animation did not start', interval=.002)
            time.sleep(.15)
            leave(5, 'During restore')
            usable()
            record('navigation-during-restore-cannot-steal-focus-later')

            hide()
            command('workspace number "9: Other output"')
            destination = focused()
            wait_for(cleared, 'other-output navigation did not recover')
            workspaces = request(1)
            require(focused()['id'] == destination['id'], 'other-output recovery stole focus')
            require(any(item['id'] == original['id'] and item['visible'] for item in workspaces),
                    'captured output remained bare after changing output')
            usable()
            record('other-output-navigation-restores-origin-and-retains-destination')

            hide()
            daemon.terminate()
            require(daemon.wait(timeout=6) == 0, 'daemon did not stop cleanly')
            wait_for(cleared, 'daemon stop retained hidden state')
            usable()
            record('daemon-stop-restores-origin-and-clears-capture')
            action('show')
            wait_for(lambda: state().get('hidden') and not busy(), 'cold fallback did not start guarded hide')
            helpers = private_helpers()
            require(len(helpers) == 1, 'cold fallback started duplicate guard daemons')
            record('missing-helper-starts-one-guard-before-hiding')
            os.kill(helpers[0], signal.SIGKILL)
            wait_for(lambda: not private_helpers(), 'killed guard did not exit')
            require(bool(state()), 'abrupt-stop fixture lost its saved state')
            calls = carousel_calls()
            action('restore-or-carousel')
            wait_for(cleared, 'replacement guard did not recover saved state')
            usable()
            require(carousel_calls() == calls, 'recovering a crashed helper unexpectedly opened carousel')
            record('replacement-helper-recovers-hidden-state-without-carousel')
            subprocess.run(['grim', '-o', 'HEADLESS-1', str(output / 'recovered-windows.png')],
                           env=env, check=True, timeout=5)
            evidence['carousel_calls'] = carousel_calls()
            evidence['source_unchanged_at_end'] = {
                name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() == digest
                for name, digest in hashes.items()}
            require(all(evidence['source_unchanged_at_end'][name]
                        for name in ('alpine/desktop/.local/bin/mbp-intel-showdesktop',
                                     'alpine/desktop/.local/lib/mbp_intel/showdesktop.py')),
                    'owned showdesktop sources changed during verification')
            require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == evidence['verifier_sha256'],
                    'verifier changed during verification')
            evidence['status'] = 'passed'
        except BaseException as error:
            evidence.update(status='failed', error=str(error))
            raise
        finally:
            for identifier in private_helpers():
                try:
                    os.kill(identifier, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if ipc:
                ipc.close()
            for process in reversed(processes):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            for identifier in private_helpers():
                try:
                    os.kill(identifier, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            log.close()
            (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get(BUS_MARKER) != '1':
        with tempfile.TemporaryDirectory(prefix='showdesktop-recovery-') as directory:
            base = Path(directory)
            env = dict(os.environ)
            for key, name in (('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'), ('XDG_CONFIG_HOME', 'config'),
                              ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')):
                path = base / name
                path.mkdir(mode=0o700)
                env[key] = str(path)
            for key in ('DBUS_SESSION_BUS_ADDRESS', 'SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
                env.pop(key, None)
            env.update({BUS_MARKER: '1', ROOT_MARKER: directory, 'GTK_A11Y': 'none',
                        'XDG_CURRENT_DESKTOP': 'sway', 'NO_AT_BRIDGE': '1'})
            bus_log = base / 'bus.log'
            try:
                with bus_log.open('w') as stream:
                    result = subprocess.run(['dbus-run-session', '--', sys.executable,
                                             str(Path(__file__).resolve()), *sys.argv[1:]],
                                            env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
            finally:
                cleanup_private(base / 'run')
            if args.output.is_dir():
                (args.output / 'bus.log').write_bytes(bus_log.read_bytes())
            print(args.output)
            sys.exit(result.returncode)
    require('DBUS_SESSION_BUS_ADDRESS' in os.environ, 'private D-Bus missing')
    run(args.output.resolve())


if __name__ == '__main__':
    main()
