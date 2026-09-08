#!/usr/bin/env python3
"""Drive the real carousel keys in private Sway with synthetic colored windows."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import traceback

from verify_decoration_attachment import SwayIPC, walk


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'alpine/desktop/.local/bin/oldbook-carousel'
BUS_MARKER = 'OLDBOOK_CAROUSEL_VERIFY_BUS'
HEADER = struct.Struct('=6sII')


def require(value, message):
    if not value:
        raise AssertionError(message)
    return value


def wait_for(callback, message, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = callback()
        if value:
            return value
        time.sleep(.025)
    raise AssertionError(message)


class FocusTrace:
    def __init__(self, path):
        self.ipc = SwayIPC(path)
        reply = self.ipc.requests([(2, '["window","workspace"]')])[0]
        require(reply.get('success'), 'private focus subscription rejected')
        self.ipc.connection.setblocking(False)
        self.buffer = bytearray()

    def drain(self):
        while True:
            try:
                data = self.ipc.connection.recv(65536)
            except BlockingIOError:
                break
            if not data:
                break
            self.buffer.extend(data)
        events = []
        while len(self.buffer) >= HEADER.size:
            magic, size, kind = HEADER.unpack(self.buffer[:HEADER.size])
            require(magic == b'i3-ipc' and size < 32 * 1024 * 1024,
                    'invalid private focus event')
            if len(self.buffer) < HEADER.size + size:
                break
            event = json.loads(self.buffer[HEADER.size:HEADER.size + size])
            del self.buffer[:HEADER.size + size]
            if event.get('change') == 'focus':
                item = event.get('container') or event.get('current') or {}
                events.append({'kind': kind, 'id': item.get('id'),
                               'app_id': item.get('app_id'), 'type': item.get('type')})
        return events

    def close(self):
        self.ipc.close()


def color_pixels(path, color, tolerance=8):
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
    pixels = memoryview(pixbuf.get_pixels())
    target = bytes.fromhex(color)
    channels, stride = pixbuf.get_n_channels(), pixbuf.get_rowstride()
    count = 0
    for y in range(pixbuf.get_height()):
        for x in range(pixbuf.get_width()):
            index = y * stride + x * channels
            if all(abs(pixels[index + channel] - target[channel]) <= tolerance
                   for channel in range(3)):
                count += 1
    return count


def stop_private(processes, marker, exclude=()):
    """Pin private process identities before TERM/KILL; never signal host clients."""
    pinned = []
    groups = {process.pid for process in processes}
    parents = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdecimal():
            try:
                fields = (entry / 'stat').read_text().rsplit(') ', 1)[1].split()
                parents[int(entry.name)] = int(fields[1])
            except (OSError, IndexError, ValueError):
                pass
    owned = set(groups)
    while True:
        descendants = {pid for pid, parent in parents.items() if parent in owned}
        if descendants.issubset(owned):
            break
        owned.update(descendants)
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal() or int(entry.name) in (*exclude, os.getpid()):
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            fields = (entry / 'stat').read_text().rsplit(') ', 1)[1].split()
            if groups and int(fields[2]) not in groups and int(entry.name) not in owned:
                continue
            descriptor = os.pidfd_open(int(entry.name))
            try:
                if marker not in (entry / 'environ').read_bytes().split(b'\0'):
                    os.close(descriptor)
                    continue
            except OSError:
                os.close(descriptor)
                continue
            pinned.append(descriptor)
            signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            continue
    deadline = time.monotonic() + 1.5
    while pinned and time.monotonic() < deadline:
        if all(select.select([fd], [], [], 0)[0] for fd in pinned):
            break
        time.sleep(.025)
    for descriptor in pinned:
        try:
            if not select.select([descriptor], [], [], 0)[0]:
                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 2
    while pinned and time.monotonic() < deadline:
        if all(select.select([fd], [], [], 0)[0] for fd in pinned):
            break
        time.sleep(.025)
    survivors = sum(not select.select([fd], [], [], 0)[0] for fd in pinned)
    for descriptor in pinned:
        os.close(descriptor)
    for process in processes:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    return {'matched_processes': len(pinned), 'remaining_processes': survivors}


def run(arguments):
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = Path(os.environ['OLDBOOK_CAROUSEL_VERIFY_BASE'])
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    env = dict(os.environ, WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
               WLR_LIBINPUT_NO_DEVICES='1', NO_AT_BRIDGE='1', GTK_USE_PORTAL='0')
    bindings = arguments.bindings
    if bindings is None:
        bindings = ROOT / 'alpine/desktop/.config/sway/local.d/window-switcher.conf'
    require(bindings.is_file(), f'binding source is not ready: {bindings}')
    sources = [bindings]
    if not arguments.baseline:
        require(HELPER.is_file(), 'carousel executable is not ready')
        sources.extend([HELPER, HELPER.with_name('oldbook-workspaces')])
        library = ROOT / 'alpine/desktop/.local/lib/oldbook'
        sources.extend([library / 'window_switching.py', library / 'overlay_theme.py',
                        library / 'showdesktop.py', library / 'workspace_model.py'])
        sources.extend(library.glob('*carousel*.py'))
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    report = {'status': 'running', 'baseline': arguments.baseline, 'host_changes': 0,
              'source_sha256': hashes, 'checks': [], 'states': {},
              'isolation': 'private HOME/XDG, D-Bus, Sway, Foot and virtual keyboard',
              'keyboard': 'one wtype device owns each full modifier/key/release sequence'}
    report['verifier_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    processes = []
    connection = trace = None
    log = (output / 'runtime.log').open('w')
    marker = ('XDG_RUNTIME_DIR=' + str(runtime)).encode()
    local = Path(env['HOME']) / '.local/bin'
    local.mkdir(parents=True)
    if not arguments.baseline:
        (local / 'oldbook-carousel').symlink_to(HELPER)
    config = output / 'sway.conf'
    captured_bindings = output / 'bindings.conf'
    captured_bindings.write_bytes(bindings.read_bytes())
    config.write_text('xwayland disable\noutput HEADLESS-1 mode 1440x900\n'
                      'output * bg #13151b solid_color\nseat seat0 fallback true\n'
                      'focus_follows_mouse no\ndefault_border pixel 0\n'
                      'default_floating_border pixel 0\nset $mod Mod4\n'
                      'input type:keyboard repeat_delay 600\n'
                      'mode "fixture-other" {\n bindsym Escape mode "default"\n}\n'
                      'include ' + str(captured_bindings) + '\n')
    foot = base / 'foot.ini'
    foot.write_text('[main]\nfont=monospace:size=12\npad=12x12\n'
                    'resize-by-cells=no\n[colors-dark]\nforeground=ffffff\nalpha=1.0\n')

    def save():
        (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')

    def check(name, state=None):
        report['checks'].append(name)
        if state is not None:
            report['states'][name] = state
        save()

    def spawn(name, argv):
        process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True)
        processes.append(process)
        return process

    def command(*argv):
        return subprocess.run(argv, env=env, stdin=subprocess.DEVNULL,
                              stdout=log, stderr=log, check=True, timeout=12)

    def ipc(kind=4, text=''):
        result = connection.requests([(kind, text)])[0]
        if kind == 0:
            require(result and all(item.get('success') for item in result),
                    f'private command failed: {text}: {result!r}')
        return result

    def views():
        return [node for node in walk(ipc()) if node.get('app_id') or node.get('window')]

    def focused():
        return next((node['id'] for node in views() if node.get('focused')), None)

    def workspace_number():
        return next(item['num'] for item in ipc(1) if item.get('focused'))

    def focus(identifier):
        ipc(0, f'[con_id={identifier}] focus')
        wait_for(lambda: focused() == identifier, 'could not establish fixture focus')
        time.sleep(.1)

    def client(number, app_id, color, title):
        ipc(0, f'workspace number {number}')
        spawn(app_id, ['foot', '--config', str(foot), '--app-id', app_id,
                      '--title', title, '--override=colors-dark.background=' + color,
                      'sh', '-c', 'printf "Private carousel fixture\\n"; exec sleep 180'])
        return wait_for(lambda: next((node for node in views()
                                     if node.get('app_id') == app_id), None),
                        f'{app_id} did not map')

    def layers():
        return [surface for item in ipc(3) for surface in item.get('layer_shell_surfaces', [])
                if surface.get('namespace') == 'oldbook-carousel']

    state_path = None

    def state():
        try:
            return json.loads(state_path.read_text())
        except (FileNotFoundError, ValueError):
            return {}

    def opened(selected=None):
        current = state()
        return current if current.get('open') and (selected is None
                        or current.get('selected_id') == selected) else None

    def settled(identifier, label):
        wait_for(lambda: not state().get('open') and not layers()
                 and focused() == identifier, label)
        require(ipc(12).get('name') == 'default', label + ': Sway mode not restored')

    def start_keys(family, middle, reverse=False):
        modifier, key = ('logo', 'Super_L') if family == 'super' else ('alt', 'Alt_L')
        argv = ['wtype', '-M', modifier, '-P', key]
        if reverse:
            argv += ['-M', 'shift']
        argv += ['-k', 'Tab']
        if reverse:
            argv += ['-m', 'shift']
        argv += middle + ['-m', modifier, '-p', key]
        return spawn('keys-' + family, argv)

    try:
        # The host's /usr/local/bin/sway wrapper chooses stock Sway when the
        # private HOME has no desktop launcher. Exercise production SwayFX.
        compositor = Path('/usr/bin/swayfx')
        report['compositor'] = {'path': str(compositor),
                               'sha256': hashlib.sha256(compositor.read_bytes()).hexdigest()}
        sway = spawn('sway', [str(compositor), '-c', str(config)])

        def ready():
            sockets = list(runtime.glob('sway-ipc*.sock'))
            displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
            return (sockets[0], displays[0].name) if sockets and displays else None

        sway_socket, display = wait_for(ready, 'private Sway did not start')
        env.update(SWAYSOCK=str(sway_socket), WAYLAND_DISPLAY=display)
        command('dbus-update-activation-environment', 'SWAYSOCK', 'WAYLAND_DISPLAY')
        connection = SwayIPC(sway_socket)
        trace = FocusTrace(sway_socket)
        spawn('seat-keyboard', ['wtype', '-s', '120000'])
        time.sleep(.2)
        a = client(1, 'carousel-blue', '214eaa', 'Blue terminal A')
        b = client(1, 'firefox', '247742', 'Green browser B')
        c = client(2, 'carousel-orange', 'dd712b', 'Orange terminal C')
        d = client(10, 'oldbook-strata', '1bd6cc', 'Cyan Strata D')
        ids = [item['id'] for item in (a, b, c, d)]
        report['fixture_ids'] = ids
        report['fixture_workspaces'] = [1, 1, 2, 10]
        if arguments.baseline:
            focus(a['id'])
            focus(c['id'])
            keys = start_keys('super', ['-s', '1200', '-k', 'Tab', '-s', '1200'])
            wait_for(lambda: workspace_number() == 1, 'baseline first Tab did not switch workspace')
            first = focused()
            wait_for(lambda: workspace_number() == 2, 'baseline repeated Tab did not bounce back')
            keys.wait(timeout=4)
            require(first == a['id'] and focused() == c['id'] and not layers(),
                    'baseline did not reproduce two-workspace bounce')
            report['status'] = 'expected-failure-reproduced'
            check('super-tab-bounces-workspaces-instead-of-cycling-windows',
                  {'origin': c['id'], 'first': first, 'second': focused(),
                   'omitted_window_ids': [b['id'], d['id']]})
            return

        session = hashlib.sha256(str(sway_socket).encode()).hexdigest()[:12]
        state_path = runtime / 'oldbook' / ('carousel-' + session) / 'state.json'
        daemon = spawn('carousel-daemon', [str(HELPER), 'daemon'])
        wait_for(lambda: state_path.is_file() or daemon.poll() is not None,
                 'carousel daemon did not initialize')
        require(daemon.poll() is None, 'carousel daemon exited at startup')
        original_pid = state()['pid']
        duplicate = spawn('duplicate-carousel-daemon', [str(HELPER), 'daemon'])
        require(duplicate.wait(timeout=4) == 0 and state()['pid'] == original_pid,
                'second daemon did not preserve singleton')
        check('duplicate-daemon-preserves-single-owner', {'pid': original_pid})
        for item in (a, c, b):
            focus(item['id'])
        expected = [b['id'], c['id'], a['id'], d['id']]

        command(str(HELPER), 'show')
        current = wait_for(lambda: opened(b['id']), 'persistent carousel did not select current window')
        require(current['candidate_ids'] == expected, 'global MRU regressed to workspace grouping')
        wait_for(lambda: len(layers()) == 1 and ipc(12).get('name') == 'window-switcher',
                 'carousel did not map exactly one layer and own its input mode')
        check('global-mru-interleaves-workspaces-and-includes-ordinary-windows', current)
        # Opening/capturing hidden candidates must not visit their workspaces.
        trace.drain()
        wait_for(lambda: set(ids).issubset(state().get('preview_ids', [])),
                 'real previews were not captured for every fixture', seconds=12)
        command(str(HELPER), 'previous')
        wait_for(lambda: opened(d['id']), 'hidden Strata preview could not be highlighted')
        time.sleep(.6)
        require(workspace_number() == 1, 'capturing hidden previews changed workspace')
        events = trace.drain()
        require(not any(event['type'] in ('con', 'floating_con')
                        and event['id'] != b['id'] for event in events),
                'hidden preview capture focused another fixture')
        shot = output / 'carousel-hidden-previews.png'
        command('grim', '-o', 'HEADLESS-1', str(shot))
        cyan = color_pixels(shot, '1bd6cc', tolerance=14)
        require(cyan > 400, f'hidden Strata preview has no cyan fixture pixels: {cyan}')
        check('hidden-workspace-preview-renders-without-focus-change',
              {'preview_ids': state().get('preview_ids'), 'cyan_pixels': cyan,
               'workspace_focus': workspace_number(), 'focus_events': events})
        command(str(HELPER), 'next')
        wait_for(lambda: opened(b['id']), 'preview selection did not return to origin')
        command('wtype', '-M', 'logo', '-P', 'Super_L', '-s', '100', '-m', 'logo', '-p', 'Super_L')
        time.sleep(.15)
        require(opened(b['id']), 'modifier release accepted persistent gesture')
        command('wtype', '-k', 'Escape')
        settled(b['id'], 'persistent Escape changed focus or stranded popup')
        check('persistent-show-ignores-modifier-release-and-escape-cancels')

        keys = start_keys('super', ['-s', '1500', '-k', 'Tab', '-s', '1200',
                                   '-M', 'shift', '-k', 'Tab', '-m', 'shift', '-s', '1500'])
        initial = wait_for(lambda: opened(c['id']), 'Super+Tab did not select actual previous window')
        frozen = initial['candidate_ids']
        require(workspace_number() == 1, 'held Super+Tab changed workspace before release')
        wait_for(lambda: opened(a['id']), 'second held Tab did not advance')
        wait_for(lambda: opened(c['id']), 'held Shift+Tab did not reverse')
        require(state()['candidate_ids'] == frozen and len(layers()) == 1,
                'cycling reordered candidates or duplicated popup')
        keys.wait(timeout=5)
        settled(c['id'], 'Super release failed to commit')
        times = state().get('frame_times', [])
        intervals = [(right - left) / 1000 for left, right in zip(times, times[1:])]
        animation_intervals = [value for value in intervals if 0 < value < 100]
        require(state().get('frames', 0) > 0 and animation_intervals,
                'renderer produced no frame-clock animation evidence')
        check('super-tab-repeat-reverse-frozen-order-and-release-commit',
              {'frames': state()['frames'], 'frame_times_us': times,
               'active_frame_interval_median_ms': statistics.median(animation_intervals),
               'idle_gaps_excluded': len(intervals) - len(animation_intervals)})

        keys = start_keys('alt', ['-s', '1300'])
        wait_for(lambda: opened(b['id']), 'Alt+Tab omitted ordinary Firefox or disagreed with Super')
        keys.wait(timeout=3)
        settled(b['id'], 'Alt release failed to commit')
        check('alt-tab-shares-all-window-order-and-final-release')
        keys = start_keys('alt', ['-s', '1200'], reverse=True)
        reverse = wait_for(lambda: opened(), 'Alt+Shift+Tab did not open')
        require(reverse['selected_id'] == reverse['candidate_ids'][-1],
                'Alt+Shift+Tab did not select reverse end')
        target = reverse['selected_id']
        keys.wait(timeout=3)
        settled(target, 'reverse Alt release failed')
        check('alt-shift-tab-uses-reverse-binding')

        focus(b['id'])
        keys = start_keys('super', ['-s', '1300', '-k', 'Escape', '-s', '200'])
        wait_for(lambda: opened(), 'cancel gesture did not map')
        keys.wait(timeout=3)
        settled(b['id'], 'held Escape changed focus')
        check('held-escape-cancels-and-restores-default-mode')

        focus(c['id'])
        focus(b['id'])
        for family, target in (('super', c['id']), ('alt', b['id'])):
            keys = start_keys(family, [])
            keys.wait(timeout=3)
            settled(target, 'quick tap did not commit last used window')
        check('quick-super-and-alt-taps-toggle-last-two-windows')

        command(str(HELPER), 'show')
        current = wait_for(lambda: opened(b['id']), 'persistent window picker missing')
        before_new = current['candidate_ids']
        ipc(0, 'no_focus [app_id="^carousel-new$"]')
        extra = client(1, 'carousel-new', '8646b4', 'Purple late window E')
        time.sleep(.25)
        require(state()['candidate_ids'] == before_new, 'new window changed frozen gesture list')
        command('wtype', '-k', 'Tab')
        selected = wait_for(lambda: opened(c['id']), 'persistent Tab did not advance')
        ipc(0, f'[con_id={selected["selected_id"]}] kill')
        wait_for(lambda: c['id'] not in state().get('candidate_ids', [])
                 and state().get('selected_id') != c['id'], 'closed selected window was not removed')
        target = state()['selected_id']
        command('wtype', '-k', 'Return')
        settled(target, 'Enter accepted a closed identity or left picker open')
        check('persistent-frozen-list-removes-closed-selection-and-enter-commits',
              {'removed': c['id'], 'committed': target, 'deferred_new': extra['id']})
        command(str(HELPER), 'show')
        wait_for(lambda: opened() and extra['id'] in state()['candidate_ids'],
                 'new gesture did not discover late window')
        command(str(HELPER), 'cancel')
        settled(target, 'explicit cancel failed')
        check('next-gesture-discovers-new-window')

        for _ in range(3):
            command(str(HELPER), 'show')
            command(str(HELPER), 'cancel')
        command(str(HELPER), 'show')
        current = wait_for(lambda: opened(), 'rapid reopen stranded the carousel')
        wait_for(lambda: set(current['candidate_ids']).issubset(state().get('preview_ids', [])),
                 'rapid reopen did not finish current previews', seconds=12)
        require(set(state()['preview_ids']).issubset(state()['candidate_ids']) and len(layers()) == 1,
                'old preview generation escaped into new popup')
        check('rapid-close-reopen-keeps-one-current-preview-generation')
        ipc(0, 'mode "fixture-other"')
        wait_for(lambda: not state().get('open') and not layers(), 'mode takeover kept popup open')
        require(ipc(12).get('name') == 'fixture-other', 'dismissal overrode new Sway mode')
        command('wtype', '-k', 'Escape')
        wait_for(lambda: ipc(12).get('name') == 'default', 'fixture mode Escape failed')
        ipc(0, 'mode "window-switcher"')
        command('wtype', '-k', 'Escape')
        settled(target, 'orphaned window-switcher mode did not recover on Escape')
        check('mode-takeover-and-orphaned-mode-escape-recovery')
        # Sway's exec binding restores the mode synchronously, but its small
        # cancel client is asynchronous. Let that last client finish first.
        time.sleep(.25)
        # Check whether live activation can load just the bindings and mode;
        # these commands deliberately follow every user-behavior assertion.
        include_command = 'include ' + json.dumps(str(bindings.resolve()))
        include_reply = connection.requests([(0, include_command)])[0]
        activation = {'include_command': include_command, 'include_reply': include_reply}
        if not include_reply or not all(item.get('success') for item in include_reply):
            inline = 'mode "probe-mode" { bindsym Escape mode "default" }'
            modes_before = ipc(8)
            inline_reply = connection.requests([(0, inline)])[0]
            modes_after = ipc(8)
            activation.update(inline_command=inline, inline_reply=inline_reply,
                              modes_before=modes_before, modes_after=modes_after,
                              probe_mode_created='probe-mode' in modes_after)
        activation['mode_after_probe'] = ipc(12)
        ipc(0, 'mode "default"')
        report['targeted_activation_probe'] = activation
        require(all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
                    for path, digest in hashes.items()), 'implementation changed during native verification')
        check('production-source-hashes-stable')
        try:
            ipc(0, 'exit')
        except ConnectionError:
            pass
        require(sway.wait(timeout=5) == 0, 'private compositor did not exit')
        daemon_exit = daemon.wait(timeout=8)
        log.flush()
        gdk_disconnect = 'Error flushing display: Broken pipe' in (output / 'runtime.log').read_text()
        require(daemon_exit == 0 or (daemon_exit == 1 and gdk_disconnect),
                f'carousel exited unexpectedly during compositor shutdown: {daemon_exit}')
        check('compositor-exit-stops-carousel-daemon',
              {'exit_status': daemon_exit, 'gdk_display_disconnect': gdk_disconnect})
        report['screenshot_sha256'] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in output.glob('*.png')}
        report['status'] = 'passed'
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        report['traceback'] = traceback.format_exc()
        if state_path is not None:
            report['last_state'] = state()
        if connection is not None:
            try:
                report['last_outputs'] = ipc(3)
                command('grim', '-o', 'HEADLESS-1', str(output / 'failure.png'))
            except (OSError, RuntimeError, subprocess.SubprocessError):
                pass
        raise
    finally:
        if trace is not None:
            trace.close()
        if connection is not None:
            connection.close()
        # Stop fixture clients before tearing down their private compositor.
        sway_pid = sway.pid if 'sway' in locals() and sway.poll() is None else None
        stop_private(processes[1:], marker, exclude=(sway_pid,) if sway_pid else ())
        if sway_pid:
            sway.terminate()
            try:
                sway.wait(timeout=3)
            except subprocess.TimeoutExpired:
                sway.kill()
                sway.wait(timeout=3)
        log.close()
        report['cleanup'] = 'private process identities stopped before compositor teardown'
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bindings', type=Path)
    parser.add_argument('--baseline', action='store_true')
    arguments = parser.parse_args()
    if os.environ.get(BUS_MARKER) != '1':
        with tempfile.TemporaryDirectory(prefix='carousel-native-') as directory:
            env = dict(os.environ)
            for key in ('DBUS_SESSION_BUS_ADDRESS', 'SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
                env.pop(key, None)
            for key, name in (('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'),
                              ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                              ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')):
                path = Path(directory) / name
                path.mkdir(mode=0o700)
                env[key] = str(path)
            env.update({BUS_MARKER: '1', 'OLDBOOK_CAROUSEL_VERIFY_BASE': directory,
                        'NO_AT_BRIDGE': '1', 'GTK_USE_PORTAL': '0'})
            try:
                child = subprocess.run(['dbus-run-session', '--', sys.executable,
                                        str(Path(__file__).resolve()), *sys.argv[1:]], env=env)
            finally:
                # The bus wrapper is gone now: also collect activated portal
                # services or reparented fixture children from this runtime.
                cleanup = stop_private([], ('XDG_RUNTIME_DIR=' + env['XDG_RUNTIME_DIR']).encode())
                evidence = arguments.output.resolve() / 'evidence.json'
                if evidence.exists():
                    data = json.loads(evidence.read_text())
                    data['post_bus_cleanup'] = cleanup
                    evidence.write_text(json.dumps(data, indent=2) + '\n')
                require(cleanup['remaining_processes'] == 0, 'private fixture process leaked')
        return child.returncode
    run(arguments)
    print(json.dumps({'output': str(arguments.output), 'status': 'completed'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
