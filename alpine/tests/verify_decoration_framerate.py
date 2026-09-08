#!/usr/bin/env python3
"""Measure production caption frames during private, continuous floating motion.

The observer wraps callbacks the daemon itself installs. It never adds a tick,
requests a repaint, or substitutes a timer for GTK's production frame clock.
GDK presentation timestamps are estimates from Wayland frame callbacks, not
wp_presentation feedback or a physical display probe.

wlroots' headless backend rearms its integer-millisecond refresh timer after
each commit. Rendering/commit time therefore adds to its 16/8ms delay at nominal
60/120Hz; these intervals are not fixed hardware vblank deadlines.
https://gitlab.freedesktop.org/wlroots/wlroots/-/blob/0.20.2/backend/headless/output.c
"""

import argparse
import atexit
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import select
import shutil
import signal
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
import time

from verify_decoration_attachment import build_pointer


REPO = Path(__file__).resolve().parents[2]
HELPER = Path('alpine/desktop/.local/bin/oldbook-decoration')
LIBRARY = Path('alpine/desktop/.local/lib/oldbook')
SOURCES = [HELPER, *(LIBRARY / name for name in (
    'decoration.py', 'decoration_actions.py', 'decoration_placement.py',
    'decoration_motion.py', 'decoration_watch.py', 'overlay_theme.py'))]
BUS_MARKER = 'OLDBOOK_DECORATION_FRAMERATE_PRIVATE_BUS'
HEADER = struct.Struct('=6sII')


def require(value, message):
    if not value:
        raise AssertionError(message)


def observe_helper(helper, destination):
    """Passively observe only callbacks requested by the real daemon."""
    import gi

    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk

    original = Gtk.Widget.add_tick_callback
    frames, paints, draws, timing_objects, resize_calls, updates = [], [], [], [], [], []
    observed = set()
    original_resize = Gtk.Window.resize

    def resize(window, width, height):
        resize_calls.append({'window': window.get_name(),
                             'monotonic_us': time.monotonic_ns() // 1000,
                             'width': width, 'height': height})
        return original_resize(window, width, height)

    def register(widget, callback, *arguments):
        identity = widget.get_name()
        if identity not in observed:
            observed.add(identity)
            clock = widget.get_frame_clock()
            draw_started = None
            owner = getattr(callback, '__self__', None)
            if owner is not None and hasattr(owner, 'update'):
                original_update = owner.update

                def update(*args, **kwargs):
                    started = time.monotonic_ns()
                    result = original_update(*args, **kwargs)
                    updates.append({'window': identity, 'monotonic_us': started // 1000,
                                    'duration_us': (time.monotonic_ns() - started) / 1000})
                    return result

                owner.update = update

            def after_paint(frame_clock):
                paints.append({'window': identity,
                               'counter': frame_clock.get_frame_counter(),
                               'clock_us': frame_clock.get_frame_time(),
                               'monotonic_us': time.monotonic_ns() // 1000})

            def draw(window, _context):
                nonlocal draw_started
                draw_started = time.monotonic_ns()
                draws.append({'window': identity, 'duration_us': None,
                              'counter': window.get_frame_clock().get_frame_counter(),
                              'monotonic_us': draw_started // 1000})
                return False

            def draw_complete(_window, _context):
                if draw_started is not None:
                    draws[-1]['duration_us'] = (time.monotonic_ns() - draw_started) / 1000
                return False

            clock.connect('after-paint', after_paint)
            widget.connect('draw', draw)
            widget.connect_after('draw', draw_complete)

        def observed_callback(window, frame_clock, *data):
            owner = getattr(callback, '__self__', None)
            started = time.monotonic_ns()
            result = callback(window, frame_clock, *data)
            finished = time.monotonic_ns()
            current = frame_clock.get_current_timings()
            if current is not None:
                timing_objects.append((identity, current))
            frames.append({
                'window': identity,
                'counter': frame_clock.get_frame_counter(),
                'clock_us': frame_clock.get_frame_time(),
                'monotonic_us': started // 1000,
                'callback_us': (finished - started) / 1000,
                'rect': dict(owner.motion_rect) if owner and owner.motion_rect else None,
                'target': dict(owner.motion_target) if owner and owner.motion_target else None,
                'continues': bool(result),
            })
            return result

        return original(widget, observed_callback, *arguments)

    def save():
        timings = []
        for identity, value in timing_objects:
            timings.append({
                'window': identity, 'counter': value.get_frame_counter(),
                'clock_us': value.get_frame_time(),
                'complete': value.get_complete(),
                'presentation_us': value.get_presentation_time(),
                'predicted_presentation_us': value.get_predicted_presentation_time(),
                'refresh_interval_us': value.get_refresh_interval(),
            })
        destination.write_text(json.dumps({
            'frames': frames, 'after_paint': paints, 'draws': draws,
            'frame_timings': timings, 'resize_calls': resize_calls, 'updates': updates,
        }, indent=2) + '\n')

    Gtk.Widget.add_tick_callback = register
    Gtk.Window.resize = resize
    atexit.register(save)
    sys.argv = [str(helper), 'daemon']
    runpy.run_path(str(helper), run_name='__main__')


class IPC:
    def __init__(self, path):
        self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connection.settimeout(10)
        self.connection.connect(str(path))

    def read(self, size):
        result = bytearray()
        while len(result) < size:
            part = self.connection.recv(size - len(result))
            if not part:
                raise ConnectionError('private compositor disconnected')
            result.extend(part)
        return result

    def request(self, kind, value=''):
        body = value.encode()
        self.connection.sendall(HEADER.pack(b'i3-ipc', len(body), kind) + body)
        magic, size, returned = HEADER.unpack(self.read(HEADER.size))
        require(magic == b'i3-ipc' and returned == kind, 'invalid private IPC reply')
        result = json.loads(self.read(size))
        if kind == 0:
            require(all(item.get('success') for item in result),
                    f'private command failed: {value}: {result!r}')
        return result

    def close(self):
        self.connection.close()


def pointer_reply(stream, pending, seconds=5):
    """Bound a complete reply, including a peer that stalls mid-line."""
    deadline = time.monotonic() + seconds
    while b'\n' not in pending:
        remaining = deadline - time.monotonic()
        require(remaining > 0 and select.select([stream], [], [], remaining)[0],
                'private pointer reply timed out')
        chunk = os.read(stream.fileno(), 4096)
        require(chunk, 'private pointer disconnected')
        pending.extend(chunk)
    end = pending.index(b'\n')
    line = bytes(pending[:end])
    del pending[:end + 1]
    return line.decode('utf-8').strip()


def walk(node):
    yield node
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from walk(child)


def interval_stats(values, refresh):
    values = sorted(set(values))
    intervals = [(right - left) / 1000 for left, right in zip(values, values[1:])]
    if not intervals:
        return {'count': len(values)}
    ordered = sorted(intervals)
    expected_ms = 1000 / refresh
    buckets = {}
    for interval in intervals:
        label = str(round(interval, 1))
        buckets[label] = buckets.get(label, 0) + 1
    return {
        'count': len(values),
        'rate_hz': round(1000 / statistics.mean(intervals), 3),
        'median_ms': round(statistics.median(intervals), 3),
        'p95_ms': round(ordered[math.ceil(len(ordered) * 0.95) - 1], 3),
        'maximum_ms': round(max(intervals), 3),
        'missed_refresh_slots': sum(max(0, round(value / expected_ms) - 1)
                                    for value in intervals),
        'interval_histogram_ms': buckets,
    }


def duration_stats(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    return {'count': len(values), 'median': round(statistics.median(values), 3),
            'p95': round(values[math.ceil(len(values) * 0.95) - 1], 3),
            'maximum': round(max(values), 3)}


def analyze(raw, start_us, end_us, refresh):
    # Exclude the first half-second of movement from startup/ramp measurement.
    start_us += 500_000
    frames = [frame for frame in raw['frames']
              if start_us <= frame['monotonic_us'] <= end_us]
    require(len(frames) > 30, 'production animation did not run throughout motion')
    require(len({frame['window'] for frame in frames}) == 1,
            'multiple caption windows would inflate the measured frame rate')
    positions = [frame['target']['x'] for frame in frames if frame['target']]
    require(positions and max(positions) - min(positions) >= 100,
            'fixture did not move the production attachment target continuously')
    selected = {(frame['window'], frame['counter']) for frame in frames}
    timings = [value for value in raw['frame_timings']
               if (value['window'], value['counter']) in selected]
    paints = [value for value in raw['after_paint']
              if start_us <= value['monotonic_us'] <= end_us]
    draws = [value for value in raw['draws']
             if start_us <= value['monotonic_us'] <= end_us]
    distinct = []
    previous = None
    for frame in frames:
        rect = {key: round(value) for key, value in (frame['rect'] or {}).items()}
        if rect != previous:
            distinct.append(frame['clock_us'])
            previous = rect
    return {
        'measurement_seconds': (end_us - start_us) / 1_000_000,
        'target_x_span_pixels': max(positions) - min(positions),
        'tick_frame_clock': interval_stats([value['clock_us'] for value in frames], refresh),
        'tick_wall_clock': interval_stats([value['monotonic_us'] for value in frames], refresh),
        'after_paint_frame_clock': interval_stats([value['clock_us'] for value in paints], refresh),
        'draw_wall_clock': interval_stats([value['monotonic_us'] for value in draws], refresh),
        'distinct_rounded_geometry': interval_stats(distinct, refresh),
        'gdk_estimated_presentation': interval_stats([value['presentation_us'] for value in timings
                                                     if value['presentation_us'] > 0], refresh),
        'resize_calls_during_movement': sum(start_us <= value['monotonic_us'] <= end_us
                                          for value in raw['resize_calls']),
        'gdk_refresh_intervals_us': sorted(set(value['refresh_interval_us'] for value in timings)),
        'callback_duration_us': duration_stats([frame['callback_us'] for frame in frames]),
        'draw_signal_duration_us': duration_stats([value['duration_us'] for value in draws
                                                  if value['duration_us'] is not None]),
        'caption_update_duration_us': duration_stats([value['duration_us'] for value in raw['updates']
            if start_us <= value['monotonic_us'] <= end_us]),
    }


def run_case(output, source, rate, seconds, motion):
    output.mkdir()
    evidence = {'status': 'running', 'requested_refresh_hz': rate,
                'isolation': 'private D-Bus, HOME, XDG directories and headless SwayFX',
                'host_changes': 0,
                'observer': 'passive production tick callback, draw and after-paint observation',
                'motion_driver': motion}
    evidence['host_load_before'] = list(os.getloadavg())
    evidence['host_logical_cpus'] = os.cpu_count()
    processes = []
    ipc = None
    with tempfile.TemporaryDirectory(prefix='decoration-framerate-') as directory:
        base = Path(directory)
        env = dict(os.environ)
        for key, child in (('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'),
                           ('XDG_CONFIG_HOME', 'config'), ('XDG_STATE_HOME', 'state'),
                           ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data')):
            path = base / child
            path.mkdir(mode=0o700)
            env[key] = str(path)
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        env.update(WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
                   WLR_RENDERER='pixman', NO_AT_BRIDGE='1', GTK_USE_PORTAL='0')
        config = base / 'config'
        (config / 'oldbook').mkdir()
        (config / 'oldbook/decoration.json').write_text(json.dumps({
            'position': 'bottom', 'opacity': 0.67, 'corner_radius': 7}) + '\n')
        (config / 'foot').mkdir()
        foot_config = config / 'foot/foot.ini'
        foot_config.write_text('[main]\nfont=monospace:size=9.5\n'
                               'resize-by-cells=no\n[colors-dark]\nbackground=33445b\n')
        sway_config = output / 'sway.conf'
        sway_config.write_text(
            'xwayland disable\n'
            f'output HEADLESS-1 mode 1280x720@{rate}Hz\n'
            'output * bg #13091f solid_color\n'
            'seat seat0 fallback true\nfocus_follows_mouse no\nfloating_modifier Mod4\n'
            'default_border pixel 0\ndefault_floating_border pixel 0\n'
            'for_window [app_id="framerate-float"] floating enable, '
            'resize set 440 250, move absolute position 240 170\n')
        with (output / 'runtime.log').open('w') as log:
            def spawn(name, args, interactive=False):
                process = subprocess.Popen(args, env=env,
                                           stdin=subprocess.PIPE if interactive else subprocess.DEVNULL,
                                           stdout=subprocess.PIPE if interactive else log,
                                           stderr=log, start_new_session=True, text=True)
                processes.append((name, process))
                return process

            def wait_for(test, message):
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    for name, process in processes:
                        require(process.poll() is None, f'{name} exited: {process.returncode}')
                    result = test()
                    if result:
                        return result
                    time.sleep(0.05)
                raise AssertionError(message)

            try:
                spawn('swayfx', ['swayfx', '-V', '-c', str(sway_config)])
                runtime = base / 'run'

                def compositor_ready():
                    sockets = list(runtime.glob('sway-ipc*.sock'))
                    displays = [item for item in runtime.glob('wayland-*') if item.is_socket()]
                    return (sockets[0], displays[0].name) if sockets and displays else None

                sway_socket, display = wait_for(compositor_ready, 'private compositor missing')
                env['SWAYSOCK'], env['WAYLAND_DISPLAY'] = str(sway_socket), display
                ipc = IPC(sway_socket)
                output_info = ipc.request(3)[0]
                evidence['output'] = {key: output_info.get(key) for key in (
                    'name', 'rect', 'current_mode', 'refresh', 'make', 'model')}
                refresh = output_info['current_mode']['refresh'] / 1000
                evidence['actual_refresh_hz'] = refresh
                spawn('foot', ['foot', '--config', str(foot_config), '--app-id',
                               'framerate-float', '--title', 'Private frame measurement',
                               'sh', '-c', 'sleep 90'])
                client = wait_for(lambda: next((item for item in walk(ipc.request(4))
                                  if item.get('app_id') == 'framerate-float'), None),
                                  'floating fixture missing')
                raw_path = output / 'frames.json'
                decoration = spawn('decoration', [sys.executable, str(Path(__file__).resolve()),
                    '--observe-helper', str(source / HELPER), '--trace-output', str(raw_path)])
                wait_for(lambda: any(item['namespace'] == 'oldbook-decoration'
                         for item in ipc.request(3)[0].get('layer_shell_surfaces', [])),
                         'production decoration missing')
                time.sleep(0.7)
                pointer = None
                if motion == 'pointer':
                    pointer = spawn('pointer', [str(build_pointer(base))], interactive=True)
                    pending_reply = bytearray()

                    def reply():
                        return pointer_reply(pointer.stdout, pending_reply)

                    require(reply() == 'ready', 'private pointer missing')

                    def event(command):
                        pointer.stdin.write(command + '\n')
                        pointer.stdin.flush()
                        require(reply() == 'ok', 'private pointer input failed')

                    def move(x, y):
                        event(f'move {round(x * 800 / 1280)} {round(y * 600 / 720)}')

                    spawn('modifier', ['wtype', '-M', 'logo', '-s',
                                      str(math.ceil((seconds + 3) * 1000)), '-m', 'logo'])
                    time.sleep(0.15)
                    move(460, 300)
                    event('press 272')
                start = time.monotonic()
                start_us = time.monotonic_ns() // 1000
                command_times = []
                index = 0
                # Pointer movement emits no window::move IPC events while held,
                # exercising the same production path as the user's drag.
                # Optional IPC stress also exercises semantic event bursts.
                cadence = max(240, rate * 2)
                while time.monotonic() - start < seconds:
                    elapsed = time.monotonic() - start
                    x = round(460 + 230 * math.sin(elapsed * 2.1))
                    y = round(300 + 100 * math.sin(elapsed * 1.7))
                    before = time.monotonic_ns()
                    if pointer:
                        move(x, y)
                    else:
                        ipc.request(0, f'[con_id={client["id"]}] move absolute position {x} {y}')
                    command_times.append((time.monotonic_ns() - before) / 1000)
                    index += 1
                    time.sleep(max(0, start + index / cadence - time.monotonic()))
                end_us = time.monotonic_ns() // 1000
                if pointer:
                    event('release 272')
                evidence['movement'] = {'start_monotonic_us': start_us, 'end_monotonic_us': end_us,
                    'commands': len(command_times), 'requested_command_hz': cadence,
                    'driver_roundtrip_median_us': statistics.median(command_times),
                    'driver_roundtrip_maximum_us': max(command_times)}
                time.sleep(0.4)
                decoration.terminate()
                require(decoration.wait(timeout=5) == 0, 'observed daemon did not exit cleanly')
                evidence['metrics'] = analyze(json.loads(raw_path.read_text()), start_us, end_us, refresh)
                log.flush()
                evidence['renderer_log'] = [line for line in (output / 'runtime.log').read_text().splitlines()
                                            if 'GL renderer:' in line or 'GL version:' in line]
                evidence['host_load_after'] = list(os.getloadavg())
                evidence['status'] = 'measured'
            except BaseException as error:
                evidence['status'], evidence['error'] = 'failed', str(error)
                raise
            finally:
                if ipc:
                    ipc.close()
                for _name, process in reversed(processes):
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                for _name, process in reversed(processes):
                    if process.poll() is None:
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            pass
                    # Children can outlive an exited group leader. These are
                    # private sessions created by this verifier, never name matches.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    if process.poll() is None:
                        process.wait(timeout=3)
                (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--source', type=Path, default=REPO,
                        help='source tree to snapshot before running')
    parser.add_argument('--rates', type=int, nargs='+', default=[60, 120])
    parser.add_argument('--seconds', type=float, default=5)
    parser.add_argument('--motion', choices=('pointer', 'ipc'), default='pointer')
    parser.add_argument('--observe-helper', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--trace-output', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.observe_helper:
        require(os.environ.get(BUS_MARKER) == '1', 'observer requires the private verifier bus')
        observe_helper(args.observe_helper, args.trace_output)
        return
    if not args.output:
        parser.error('--output is required')
    require(args.seconds >= 2, 'measurement must last at least two seconds')
    if os.environ.get(BUS_MARKER) != '1':
        env = dict(os.environ)
        env.pop('DBUS_SESSION_BUS_ADDRESS', None)
        env[BUS_MARKER] = '1'
        os.execvpe('dbus-run-session', ['dbus-run-session', '--', sys.executable,
                    str(Path(__file__).resolve()), *sys.argv[1:]], env)
    require('DBUS_SESSION_BUS_ADDRESS' in os.environ, 'private D-Bus is missing')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'source'
    hashes = {}
    for relative in SOURCES:
        origin, destination = args.source.resolve() / relative, source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = origin.read_bytes()
        destination.write_bytes(data)
        hashes[str(relative)] = hashlib.sha256(data).hexdigest()
    shutil.copytree(args.source / 'alpine/themes', source / 'alpine/themes',
                    ignore=shutil.ignore_patterns('profiles', 'assets', '__pycache__'))
    summary = {'source_sha256': hashes,
               'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'limitations': 'Headless SwayFX/SceneFX EGL; frame clock and GDK estimated presentation, '
                              'not physical panel scanout or a guarantee under arbitrary load. '
                              'wlroots headless rearms its integer-millisecond refresh timer after '
                              'commit, adding render/commit time to 16/8 ms at nominal 60/120 Hz.',
               'headless_timing_source': 'https://gitlab.freedesktop.org/wlroots/wlroots/-/blob/'
                                        '0.20.2/backend/headless/output.c',
               'runs': []}
    for rate in args.rates:
        result = run_case(output / f'{rate}hz', source, rate, args.seconds, args.motion)
        summary['runs'].append(result)
        (output / 'evidence.json').write_text(json.dumps(summary, indent=2) + '\n')
        concise = {name: {key: value for key, value in metric.items()
                          if key != 'interval_histogram_ms'} if isinstance(metric, dict) else metric
                   for name, metric in result['metrics'].items()}
        print(json.dumps({'requested_hz': rate, 'actual_hz': result['actual_refresh_hz'],
                          'metrics': concise}, indent=2), flush=True)


if __name__ == '__main__':
    main()
