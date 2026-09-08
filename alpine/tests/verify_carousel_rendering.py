#!/usr/bin/env python3
"""Measure the real carousel view with synthetic previews in a private SwayFX."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import traceback

from verify_carousel import stop_private
from verify_decoration_attachment import SwayIPC

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path(os.environ.get('OLDBOOK_RENDER_LIBRARY', ROOT / 'alpine/desktop/.local/lib/oldbook'))
BUS_MARKER = 'OLDBOOK_CAROUSEL_RENDER_BUS'


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {'count': 0}
    return {'count': len(ordered), 'median_ms': statistics.median(ordered),
            'p95_ms': ordered[math.ceil(len(ordered) * .95) - 1],
            'maximum_ms': ordered[-1]}


def popup_probe(output, compose_cards, warm):
    sys.path.insert(0, str(LIBRARY))
    import carousel_view
    from carousel_view import Popup
    from window_switching import SwitchState

    palette = {'background': '#21192c', 'background_hard': '#171020', 'surface': '#362641',
               'foreground': '#eee7f7', 'muted': '#baaccb', 'border': '#674d7c', 'accent': '#b99bea'}
    carousel_view.read_palette = lambda: dict(palette)
    keeper, warmup = None, None
    if warm:
        from graphics_warmup import warm_graphics
        connection = SwayIPC(os.environ['SWAYSOCK'])
        try:
            before = connection.requests([(4, ''), (3, ''), (12, '')])
            started = time.monotonic_ns()
            keeper = warm_graphics()
            elapsed = (time.monotonic_ns() - started) / 1_000_000
            after = connection.requests([(4, ''), (3, ''), (12, '')])
            warmup = {'elapsed_ms': elapsed, 'mapped': keeper.window.get_mapped(),
                      'compositor_tree_layers_and_mode_unchanged': before == after,
                      'renderer': keeper.window.get_renderer().__gtype__.name,
                      'synthetic_target_pixels': [keeper.texture.get_width(), keeper.texture.get_height()]}
            if warmup['mapped'] or before != after:
                raise AssertionError('graphics warmup changed visible windows, focus, layers, or input mode')
        finally:
            connection.close()

    candidates = [{'id': index + 1, 'title': f'SYNTHETIC PREVIEW {index + 1}',
                   'application': 'Private rendering fixture', 'workspace': 'Fixture'}
                  for index in range(7)]
    state = SwitchState(candidates)
    started = time.monotonic_ns()
    view = Popup(state, None, lambda *_args: None, lambda: None, 'HEADLESS-1')
    report = {'construction_ms': (time.monotonic_ns() - started) / 1_000_000,
              'renderer': None, 'runs': [], 'snapshots': [], 'paint_phases': [],
              'preview_dimensions': [1536, 960], 'candidate_count': len(candidates),
              'probe_nice': os.getpriority(os.PRIO_PROCESS, 0), 'fixed_fixture_palette': palette}
    report['graphics_warmup'] = warmup
    GLib = view.GLib
    loop = GLib.MainLoop()
    actions = iter(('next', 'next', 'previous', 'previous', 'next', 'next'))
    timings = []
    errors = []

    def guarded(callback):
        def invoke(*args):
            try:
                return callback(*args)
            except BaseException:
                errors.append(traceback.format_exc())
                loop.quit()
                return False
        return invoke

    original_snapshot = view._snapshot

    def snapshot(native_snapshot, width, height):
        before = GLib.get_monotonic_time()
        cpu_before = time.thread_time_ns()
        original_snapshot(native_snapshot, width, height)
        report['snapshots'].append({'elapsed_ms': (GLib.get_monotonic_time() - before) / 1000,
                                    'thread_cpu_ms': (time.thread_time_ns() - cpu_before) / 1_000_000,
                                    'position': view._position, 'reveal': view._reveal})

    view._snapshot = guarded(snapshot)
    original_tick = view._tick

    def advance():
        action = next(actions, None)
        if action is None:
            loop.quit()
            return False
        state.step(action)
        report['runs'].append({'action': action, 'requested_us': GLib.get_monotonic_time(),
                               'frames': []})
        view.update(state)
        return False

    def tick(widget, clock):
        active = original_tick(widget, clock)
        run = report['runs'][-1]
        sample = {'frame_time_us': clock.get_frame_time(),
                  'callback_time_us': GLib.get_monotonic_time(),
                  'position': view._position, 'reveal': view._reveal}
        run['frames'].append(sample)
        timings.append((sample, clock.get_current_timings()))
        if not active:
            run['settled_ms'] = (sample['callback_time_us'] - run['requested_us']) / 1000
            GLib.timeout_add(120, guarded(advance))
        return active

    view._tick = guarded(tick)
    if compose_cards:
        original_card_node = view._card_node
        composed = {}
        report['card_compositions'] = []

        def card_node(*args):
            node = original_card_node(*args)
            key = id(node)
            if key not in composed:
                scale = view.stage.get_scale_factor()
                bounds = node.get_bounds()
                device = view._rectangle(bounds.origin.x * scale, bounds.origin.y * scale,
                                         bounds.size.width * scale, bounds.size.height * scale)
                drawing = view.Gtk.Snapshot.new()
                drawing.scale(scale, scale)
                drawing.append_node(node)
                texture = view.window.get_renderer().render_texture(drawing.to_node(), device)
                drawing = view.Gtk.Snapshot.new()
                drawing.append_scaled_texture(texture, view.Gsk.ScalingFilter.TRILINEAR, bounds)
                composed[key] = (node, drawing.to_node())
                report['card_compositions'].append({
                    'scale': scale, 'logical_bounds': [bounds.size.width, bounds.size.height],
                    'texture_pixels': [texture.get_width(), texture.get_height()]})
            return composed[key][1]

        view._card_node = card_node
    colors = ('593488', '216d80', 'ad6644', '476b41', '9b3f79', '4e62a3', '956a2d')
    for candidate, color in zip(candidates, colors):
        pixel = bytes.fromhex(color)
        row = (pixel * 16 + bytes.fromhex('dedbe7') * 16) * 48
        shifted = row[48:] + row[:48]
        pixels = (row * 16 + shifted * 16) * 30
        # Checker cells are synthetic; every source pixel reaches MemoryTexture.
        view.set_preview(candidate['id'], 1536, 960, pixels)
    view.window.realize()
    gate = Path(os.environ['OLDBOOK_RENDER_PRIORITY_GATE'])
    gate.with_suffix('.ready').touch()
    deadline = time.monotonic() + 12
    while not gate.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError('private rendering priority gate did not open')
        time.sleep(.01)
    report['probe_nice'] = os.getpriority(os.PRIO_PROCESS, 0)
    report['compose_cards'] = compose_cards
    report['runs'].append({'action': 'show', 'requested_us': GLib.get_monotonic_time(),
                           'frames': []})
    view.present()
    renderer = view.window.get_renderer()
    report['renderer'] = renderer.__gtype__.name if renderer is not None else None
    frame_clock = view.stage.get_frame_clock()
    paint_start = {}

    def before_paint(_clock):
        paint_start.update(wall=GLib.get_monotonic_time(), cpu=time.thread_time_ns())

    def after_paint(_clock):
        if paint_start:
            report['paint_phases'].append({
                'elapsed_ms': (GLib.get_monotonic_time() - paint_start['wall']) / 1000,
                'thread_cpu_ms': (time.thread_time_ns() - paint_start['cpu']) / 1_000_000})
            paint_start.clear()

    frame_clock.connect('before-paint', before_paint)
    frame_clock.connect('after-paint', after_paint)

    def expired():
        errors.append('view did not complete seven animation sequences within 15 seconds')
        loop.quit()
        return False

    watchdog = GLib.timeout_add_seconds(15, expired)
    try:
        loop.run()
        for sample, timing in timings:
            if timing is not None:
                sample.update(presentation_time_us=timing.get_presentation_time(),
                              refresh_interval_us=timing.get_refresh_interval(),
                              complete=timing.get_complete())
        frame_intervals, presentation_intervals = [], []
        for run in report['runs']:
            frames = run['frames']
            frame_intervals.extend((right['frame_time_us'] - left['frame_time_us']) / 1000
                                   for left, right in zip(frames, frames[1:]))
            presented = [frame['presentation_time_us'] for frame in frames
                         if frame.get('presentation_time_us', 0) > 0]
            presentation_intervals.extend((right - left) / 1000
                                          for left, right in zip(presented, presented[1:]))
            run['first_tick_ms'] = ((frames[0]['callback_time_us'] - run['requested_us']) / 1000
                                   if frames else None)
        report['frame_clock_intervals'] = distribution(frame_intervals)
        report['presentation_intervals'] = distribution(presentation_intervals)
        navigation = report['runs'][1:]
        report['navigation_frame_clock_intervals'] = distribution([
            (right['frame_time_us'] - left['frame_time_us']) / 1000
            for run in navigation for left, right in zip(run['frames'], run['frames'][1:])])
        report['navigation_presentation_intervals'] = distribution([
            (right['presentation_time_us'] - left['presentation_time_us']) / 1000
            for run in navigation for left, right in zip(run['frames'], run['frames'][1:])
            if left.get('presentation_time_us', 0) > 0 and right.get('presentation_time_us', 0) > 0])
        report['python_snapshot_time'] = distribution([item['elapsed_ms']
                                                       for item in report['snapshots']])
        report['python_snapshot_cpu_time'] = distribution([item['thread_cpu_ms']
                                                           for item in report['snapshots']])
        report['gtk_paint_time'] = distribution([item['elapsed_ms'] for item in report['paint_phases']])
        report['gtk_paint_cpu_time'] = distribution([item['thread_cpu_ms']
                                                    for item in report['paint_phases']])
        report['idle_gaps'] = 'excluded by separating each requested animation, not by duration'
        report['all_sequences_settled'] = (len(report['runs']) == 7
                                           and all('settled_ms' in run for run in report['runs']))
        report['errors'] = errors
        report['status'] = ('passed' if not errors and report['renderer']
                            and report['all_sequences_settled'] and frame_intervals else 'failed')
        # Export the synthetic scene after timing. A layer-only headless output
        # may never produce the additional frame a screencopy client waits for.
        scale = view.stage.get_scale_factor()
        width, height = view.stage.get_width(), view.stage.get_height()
        drawing = view.Gtk.Snapshot.new()
        drawing.scale(scale, scale)
        original_snapshot(drawing, width, height)
        exported = renderer.render_texture(drawing.to_node(),
            view._rectangle(0, 0, width * scale, height * scale))
        if not exported.save_to_png(str(output / 'cards.png')):
            raise RuntimeError('synthetic GPU scene export failed')
    finally:
        source = GLib.MainContext.default().find_source_by_id(watchdog)
        if source is not None:
            source.destroy()
        view.close()
        if keeper is not None:
            keeper.close()
        save(output / 'render.json', report)
    return 0 if report['status'] == 'passed' else 1


def private_compositor(output, scale, compose_cards, warm):
    report = {'status': 'running', 'isolation': 'private HOME/XDG/D-Bus/SwayFX and synthetic pixels',
              'scale': scale, 'source_sha256': {
                  str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (LIBRARY / 'carousel_view.py', LIBRARY / 'window_switching.py',
                               LIBRARY / 'overlay_theme.py', LIBRARY / 'workspace_model.py',
                               LIBRARY / 'showdesktop.py', Path(__file__))},
              'load_before': list(os.getloadavg())}
    if warm:
        source = LIBRARY / 'graphics_warmup.py'
        report['source_sha256'][str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    env = dict(os.environ, WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
               WLR_LIBINPUT_NO_DEVICES='1', GSK_DEBUG='renderer',
               GDK_DEBUG='opengl,vulkan,no-portals', GTK_A11Y='none')
    runtime = Path(env['XDG_RUNTIME_DIR'])
    marker = ('XDG_RUNTIME_DIR=' + str(runtime)).encode()
    config = output / 'sway.conf'
    config.write_text('xwayland disable\n'
                      f'output HEADLESS-1 mode {1440 * scale}x{900 * scale} scale {scale}\n'
                      'output * bg #171421 solid_color\nseat seat0 fallback true\n')
    processes = []
    with (output / 'runtime.log').open('w') as log:
        try:
            sway = subprocess.Popen(['/usr/bin/swayfx', '-c', str(config)], env=env,
                                    stdout=log, stderr=log, start_new_session=True)
            processes.append(sway)
            helper = Path('/usr/local/sbin/oldbook-ui-priority')
            if helper.is_file():
                applied = subprocess.run(['/usr/bin/doas', '-n', str(helper), str(sway.pid)],
                                         env=env, capture_output=True, text=True, timeout=10, check=True)
                report['private_compositor_startup_priority'] = json.loads(applied.stdout)
            deadline = time.monotonic() + 15
            attempts = 0
            while True:
                if sway.poll() is not None:
                    raise RuntimeError('private SwayFX exited before readiness')
                if time.monotonic() >= deadline:
                    raise TimeoutError('private SwayFX did not answer GET_VERSION within 15 seconds')
                sockets = list(runtime.glob('sway-ipc*.sock'))
                displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
                if sockets and displays:
                    attempts += 1
                    connection = None
                    try:
                        connection = SwayIPC(sockets[0])
                        version = connection.requests([(7, '')])[0]
                        if version.get('human_readable'):
                            report['compositor_readiness'] = {'attempts': attempts, 'version': version,
                                                              'barrier': 'GET_VERSION response'}
                            env.update(SWAYSOCK=str(sockets[0]), WAYLAND_DISPLAY=displays[0].name)
                            break
                    except (OSError, ConnectionError):
                        pass
                    finally:
                        if connection is not None:
                            connection.close()
                time.sleep(.025)
            if helper.is_file():
                applied = subprocess.run(['/usr/bin/doas', '-n', str(helper), '--session',
                                          env['SWAYSOCK']], env=env, capture_output=True,
                                         text=True, timeout=10, check=True)
                report['private_compositor_priority'] = json.loads(applied.stdout)
            gate = runtime / 'private-render-priority.go'
            env['OLDBOOK_RENDER_PRIORITY_GATE'] = str(gate)
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--popup',
                                      '--output', str(output), *(['--compose-cards'] if compose_cards else []),
                                      *(['--warm-graphics'] if warm else [])],
                                     env=env, stdout=log, stderr=log,
                                     start_new_session=True)
            processes.append(child)
            # This explicit test-only operation does not change the installed
            # helper's production allowlist. Verify the exact private PID and
            # runtime marker before using its reviewed per-thread primitive.
            boost = '''import json, os, pathlib, runpy, sys
pid, runtime, uid = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
process = pathlib.Path('/proc') / str(pid)
assert pid > 1 and process.stat().st_uid == uid
assert ('XDG_RUNTIME_DIR=' + runtime).encode() in (process / 'environ').read_bytes().split(b'\\0')
helper = runpy.run_path('/usr/local/sbin/oldbook-ui-priority')
threads = []
for task in (process / 'task').iterdir():
    tid = int(task.name)
    helper['boost_thread'](tid, -5)
    threads.append({'tid': tid, 'nice': os.getpriority(os.PRIO_PROCESS, tid),
                    'policy': helper['scheduler_policy'](tid)})
print(json.dumps({'pid': pid, 'threads': threads}))
'''
            applied = subprocess.run(['/usr/bin/doas', '-n', '/usr/bin/python3', '-I', '-c', boost,
                                      str(child.pid), str(runtime), str(os.getuid())],
                                     env=env, capture_output=True, text=True, check=True, timeout=10)
            report['private_probe_startup_priority'] = json.loads(applied.stdout)
            deadline = time.monotonic() + 15
            while not gate.with_suffix('.ready').exists():
                if child.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('private rendering probe did not reach scheduling gate')
                time.sleep(.01)
            applied = subprocess.run(['/usr/bin/doas', '-n', '/usr/bin/python3', '-I', '-c', boost,
                                      str(child.pid), str(runtime), str(os.getuid())],
                                     env=env, capture_output=True, text=True, check=True, timeout=10)
            report['private_probe_priority'] = json.loads(applied.stdout)
            gate.touch()
            code = child.wait(timeout=30)
            if code != 0:
                raise RuntimeError(f'private carousel renderer probe exited {code}')
            report['render'] = json.loads((output / 'render.json').read_text())
            if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest
                   for path, digest in report['source_sha256'].items()):
                raise RuntimeError('carousel view or rendering verifier changed during verification')
            report['status'] = 'passed'
        except BaseException:
            report['status'] = 'failed'
            report['traceback'] = traceback.format_exc()
        finally:
            sway_pid = processes[0].pid if processes and processes[0].poll() is None else None
            if processes[1:]:
                stop_private(processes[1:], marker, exclude=(sway_pid,) if sway_pid else ())
            if sway_pid:
                processes[0].terminate()
                try:
                    processes[0].wait(timeout=3)
                except subprocess.TimeoutExpired:
                    processes[0].kill()
                    processes[0].wait(timeout=3)
            report['load_after'] = list(os.getloadavg())
            save(output / 'evidence.json', report)
    return 0 if report['status'] == 'passed' else 1


def main():
    global LIBRARY
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scale', type=int, choices=(1, 2), default=2)
    parser.add_argument('--compose-cards', action='store_true',
                        help='compare device-scale card textures against retained render nodes')
    parser.add_argument('--source-library', type=Path,
                        help='use a frozen comparison source directory for both variants')
    parser.add_argument('--warm-graphics', action='store_true',
                        help='keep a synthetic unmapped GPU renderer alive before the popup')
    parser.add_argument('--popup', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.source_library:
        LIBRARY = args.source_library.resolve()
    output = args.output.resolve()
    if args.popup:
        if os.environ.get(BUS_MARKER) != '1':
            raise RuntimeError('popup probe requires the private fixture runtime')
        return popup_probe(output, args.compose_cards, args.warm_graphics)
    if os.environ.get(BUS_MARKER) == '1':
        return private_compositor(output, args.scale, args.compose_cards, args.warm_graphics)
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='carousel-render-') as directory:
        env = dict(os.environ)
        env['OLDBOOK_RENDER_LIBRARY'] = str(LIBRARY)
        for key in ('DBUS_SESSION_BUS_ADDRESS', 'SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        for key in ('HOME', 'XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME',
                    'XDG_STATE_HOME', 'XDG_CACHE_HOME'):
            path = Path(directory) / key.lower()
            path.mkdir(mode=0o700)
            env[key] = str(path)
        env.update({BUS_MARKER: '1', 'NO_AT_BRIDGE': '1', 'GTK_USE_PORTAL': '0'})
        try:
            child = subprocess.run(['dbus-run-session', '--', sys.executable,
                                    str(Path(__file__).resolve()), '--output', str(output),
                                    '--scale', str(args.scale),
                                    *(['--compose-cards'] if args.compose_cards else []),
                                    *(['--warm-graphics'] if args.warm_graphics else [])], env=env)
        finally:
            cleanup = stop_private([], ('XDG_RUNTIME_DIR=' + env['XDG_RUNTIME_DIR']).encode())
            evidence = output / 'evidence.json'
            report = json.loads(evidence.read_text()) if evidence.exists() else {'status': 'failed'}
            report['post_bus_cleanup'] = cleanup
            save(evidence, report)
        if cleanup['remaining_processes']:
            raise RuntimeError('private renderer fixture leaked processes')
    print(json.dumps({'status': report['status'], 'output': str(output)}))
    return child.returncode


if __name__ == '__main__':
    raise SystemExit(main())
