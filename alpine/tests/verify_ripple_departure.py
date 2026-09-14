#!/usr/bin/env python3
"""Observe real caption departure/landing ripples in a private SwayFX session.

Uses a synthetic terminal and private HOME/XDG/Wayland directories. The daemon,
GTK GLArea, shaders and grim captures are real; observer hooks only record their
results, except for the explicitly labelled delayed-capture rejection probe.
No live desktop is captured or configured. Source snapshots stay in /tmp.
"""

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'alpine/tests'))
from verify_decoration_attachment import SwayIPC, theme_radius, walk


def observe(helper, destination, delay_file):
    """Attach passive callbacks before the real daemon builds GTK surfaces."""
    sys.path.insert(0, str(helper.parents[4] / 'alpine/desktop/.local/lib/oldbook'))
    import ripple

    ctypes.CDLL(ctypes.util.find_library('gtk4-layer-shell')
                or 'libgtk4-layer-shell.so.0', mode=ctypes.RTLD_GLOBAL)
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk

    log = destination.open('w', buffering=1)

    def record(kind, **fields):
        log.write(json.dumps(dict(kind=kind, t=time.monotonic(), **fields)) + '\n')

    original_window = Gtk.Window.__init__

    def window_init(window, *args, **kwargs):
        original_window(window, *args, **kwargs)
        for signal in ('map', 'unmap', 'destroy'):
            window.connect(signal, lambda w, name=signal: record(
                name, name=w.get_name()))

    Gtk.Window.__init__ = window_init
    original_tick = Gtk.Widget.add_tick_callback

    def add_tick(widget, callback, *args):
        def tick(window, clock, *data):
            result = callback(window, clock, *data)
            owner = getattr(callback, '__self__', None)
            rect = getattr(owner, 'motion_rect', None)
            if rect is not None:
                record('caption-frame', rect=rect.copy())
            return result

        return original_tick(widget, tick, *args)

    Gtk.Widget.add_tick_callback = add_tick
    original_capture = ripple.capture
    capture_number = 0

    def capture(*args, **kwargs):
        nonlocal capture_number
        capture_number += 1
        delayed = delay_file.exists()
        record('capture-start', geometry=kwargs.get('geometry'), delayed=delayed)
        result = original_capture(*args, **kwargs)
        record('shutter-return', delayed=delayed)
        # Preserve the real synthetic photograph outside the measured path;
        # PNG encoding happens in the parent after the wave has finished.
        photograph = delay_file.parent / f'{destination.stem}-{capture_number}.ppm'
        shutil.copyfile(result, photograph)
        if delayed:
            time.sleep(0.3)
        record('capture-end', delayed=delayed, photograph=str(photograph))
        return result

    ripple.capture = capture
    original_plan = ripple.plan

    def plan(rect, area, edge='bottom', *args, **kwargs):
        result = original_plan(rect, area, edge, *args, **kwargs)
        record('plan', rect=rect, area=area, edge=edge, plan=result)
        return result

    ripple.plan = plan
    original_init = ripple.Ripple.__init__

    def initialize(wave, *args, **kwargs):
        record('ripple-create')
        original_init(wave, *args, **kwargs)
        record('ripple-init', area=wave.area, plan=wave.plan, size=wave.size)

    ripple.Ripple.__init__ = initialize
    original_start = ripple.Ripple.start

    def start(wave, started=None):
        original_start(wave, started=started)
        record('ripple-start', started=wave.started,
               age_ms=1000 * (time.monotonic() - wave.started))

    ripple.Ripple.start = start
    original_prepare = ripple.Ripple.prepare

    def prepare(wave, canvas):
        original_prepare(wave, canvas)
        renderer = version = None
        if wave.library is not None:
            wave.library.glGetString.restype = ctypes.c_char_p
            renderer = wave.library.glGetString(0x1F01)
            version = wave.library.glGetString(0x1F02)
        record('ripple-prepare', program=wave.program,
               error=str(canvas.get_error()) if canvas.get_error() else None,
               renderer=renderer.decode() if renderer else None,
               version=version.decode() if version else None)

    ripple.Ripple.prepare = prepare
    original_draw = ripple.Ripple.draw

    def draw(wave, canvas, context):
        result = original_draw(wave, canvas, context)
        if result:
            record('ripple-draw', result=bool(result),
                   age_ms=1000 * (time.monotonic() - wave.started),
                   gl_error=wave.library.glGetError())
        return result

    ripple.Ripple.draw = draw
    original_finish = ripple.Ripple.finish

    def finish(wave):
        record('ripple-finish')
        return original_finish(wave)

    ripple.Ripple.finish = finish
    sys.argv = [str(helper), 'daemon']
    runpy.run_path(str(helper), run_name='__main__')


def wait(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise RuntimeError('private ripple probe timed out')


def events(path):
    if not path.exists():
        return []
    lines = path.read_text().splitlines(keepends=True)
    return [json.loads(line) for line in lines if line.endswith('\n')]


def preserve_photograph(source, destination):
    """Losslessly encode grim's synthetic PPM without extra imaging packages."""
    sys.path.insert(0, str(ROOT / 'alpine/desktop/.local/lib/oldbook'))
    import ripple
    data = source.read_bytes()
    width, height, offset = ripple.parse_ppm(data)
    pixels = data[offset:]

    def chunk(kind, payload):
        return (struct.pack('!I', len(payload)) + kind + payload
                + struct.pack('!I', zlib.crc32(kind + payload)))

    rows = b''.join(b'\x00' + pixels[row * width * 3:(row + 1) * width * 3]
                    for row in range(height))
    destination.write_bytes(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('!IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def verify(origin, output, restart_power_off=False):
    output.mkdir(parents=True, exist_ok=False)
    report = dict(runs=[], isolated=True, synthetic_screenshots=True)
    helper_relative = Path('alpine/desktop/.local/bin/oldbook-decoration')
    ripple_relative = Path('alpine/desktop/.local/lib/oldbook/ripple.py')
    report['source_sha256'] = {
        str(path): hashlib.sha256((origin / path).read_bytes()).hexdigest()
        for path in (helper_relative, ripple_relative)
    }
    installed = Path.home() / '.local/bin/oldbook-decoration'
    report['installed_helper_resolves_to_source'] = (
        installed.resolve() == (origin / helper_relative).resolve())
    with tempfile.TemporaryDirectory(prefix='ripple-departure-') as temporary:
        base = Path(temporary)
        source = base / 'source'
        helper = source / helper_relative
        helper.parent.mkdir(parents=True)
        shutil.copy2(origin / helper_relative, helper)
        shutil.copytree(origin / 'alpine/desktop/.local/lib/oldbook',
                        source / 'alpine/desktop/.local/lib/oldbook',
                        ignore=shutil.ignore_patterns('__pycache__'))
        themes = source / 'alpine/themes'
        themes.mkdir(parents=True)
        for path in [origin / 'alpine/themes/current',
                     *(origin / 'alpine/themes').glob('*.json')]:
            shutil.copy2(path, themes / path.name)
        env = dict(os.environ)
        for key, directory in (
            ('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'),
            ('XDG_CONFIG_HOME', 'config'), ('XDG_STATE_HOME', 'state'),
            ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data'),
        ):
            (base / directory).mkdir(mode=0o700)
            env[key] = str(base / directory)
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        env.update(
            WLR_BACKENDS='headless', WLR_RENDERER='gles2',
            WLR_RENDERER_ALLOW_SOFTWARE='1', WLR_HEADLESS_OUTPUTS='1',
            LIBGL_ALWAYS_SOFTWARE='1', GSK_RENDERER='gl',
            NO_AT_BRIDGE='1', GTK_USE_PORTAL='0', GDK_BACKEND='wayland',
            DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(base / 'no-bus'),
        )
        (base / 'config/foot').mkdir()
        (base / 'config/foot/foot.ini').write_text(
            '[main]\nfont=monospace:size=10\nresize-by-cells=no\n'
            '[colors-dark]\nbackground=382449\nforeground=eadff5\n')
        (base / 'config/oldbook').mkdir()
        settings = base / 'config/oldbook/decoration.json'
        cfg = base / 'sway.conf'
        cfg.write_text(
            'xwayland disable\noutput HEADLESS-1 mode 1200x800@60Hz\n'
            'output * bg #13091f solid_color\nseat seat0 fallback true\n'
            'focus_follows_mouse no\ndefault_border pixel 0\n'
            f'default_floating_border pixel 0\ncorner_radius {theme_radius()}\n')
        log = (output / 'runtime.log').open('w')
        processes = []

        def spawn(command):
            process = subprocess.Popen(command, env=env, cwd=base,
                                       stdout=log, stderr=log)
            processes.append(process)
            return process

        connection = None
        observer = None
        spawn(['swayfx', '-c', str(cfg)])
        try:
            sock = wait(lambda: next((base / 'run').glob('sway-ipc*.sock'), None))
            env['SWAYSOCK'] = str(sock)
            env['WAYLAND_DISPLAY'] = wait(lambda: next(
                (p.name for p in (base / 'run').glob('wayland-*') if p.is_socket()),
                None))
            connection = SwayIPC(sock)

            def ipc(kind, text=''):
                return connection.requests([(kind, text)])[0]

            def snapshot():
                tree, outputs = connection.requests([(4, ''), (3, '')])
                windows = [n for n in walk(tree)
                           if n.get('app_id') == 'ripple-fixture']
                layers = [s for o in outputs for s in o.get('layer_shell_surfaces', [])]
                return dict(
                    window=windows[0]['rect'] if windows else None,
                    captions=[s['extent'] for s in layers
                              if s['namespace'] == 'oldbook-decoration'],
                    ripples=[s['extent'] for s in layers
                             if s['namespace'] == 'oldbook-ripple'],
                )

            fixture = base / 'fixture.py'
            fixture.write_text(
                'import time\n'
                'print("PRIVATE RIPPLE PROBE — SYNTHETIC CONTENT", flush=True)\n'
                'for row in range(70):\n'
                '    print(("%02d  | . + . | . + . " % row) * 8, flush=True)\n'
                'time.sleep(90)\n')
            spawn(['foot', '--app-id=ripple-fixture', '--title=Private ripple fixture',
                   '--override=initial-window-size-pixels=540x360',
                   '-e', 'python3', str(fixture)])
            wait(lambda: snapshot()['window'])
            delay_file = base / 'delay-capture'

            if restart_power_off:
                # Reproduce a daemon restart on a sleeping display without
                # waking, configuring or photographing the user's display.
                settings.write_text(json.dumps(dict(
                    position='bottom', opacity=0.78, corner_radius=7)))
                ipc(0, '[app_id="ripple-fixture"] floating enable')
                time.sleep(0.5)
                ipc(0, 'output HEADLESS-1 power off')

                def state():
                    result = snapshot()
                    result['outputs'] = [
                        {key: value.get(key) for key in
                         ('name', 'active', 'power', 'dpms', 'rect', 'current_mode')}
                        for value in ipc(3)
                    ]
                    return result

                wait(lambda: not state()['outputs'][0]['power'])
                before = state()
                observer = spawn(['python3', str(Path(__file__).resolve()), 'observe',
                                  str(helper), str(output / 'restart-events.jsonl'),
                                  str(delay_file)])
                wait(lambda: snapshot()['captions'], timeout=40)
                time.sleep(1)
                sleeping = state()
                began = time.monotonic()
                ipc(0, 'output HEADLESS-1 power on')

                def attached():
                    current = state()
                    if not current['outputs'][0]['power']:
                        return False
                    if len(current['captions']) != 1:
                        return False
                    caption = current['captions'][0]
                    window = current['window']
                    if (caption['width'] == window['width']
                            and caption['x'] == window['x']
                            and caption['y'] + theme_radius()
                                == window['y'] + window['height']):
                        return current
                    return False

                awake = wait(attached, timeout=10)
                report['restart_power_off'] = dict(
                    before_daemon=before, sleeping=sleeping, awake=awake,
                    attachment_after_power_on_ms=1000 * (time.monotonic() - began),
                    initial_placeholder_200x200=(
                        sleeping['captions'][0]['width'] == 200
                        and sleeping['captions'][0]['height'] == 200),
                    restored_attachment=True, live_output_touched=False,
                    screenshots_taken=False,
                )
                assert not sleeping['outputs'][0]['power'], sleeping
                assert not sleeping['ripples'] and not awake['ripples'], report
                observer.terminate()
                observer.wait(timeout=4)
                observer = None

            for edge in (() if restart_power_off else ('bottom', 'right')):
                settings.write_text(json.dumps(dict(
                    position=edge, opacity=0.78, corner_radius=7)))
                ipc(0, '[app_id="ripple-fixture"] floating disable')
                trace = output / f'{edge}-events.jsonl'
                observer = spawn(['python3', str(Path(__file__).resolve()), 'observe',
                                  str(helper), str(trace), str(delay_file)])
                wait(lambda: snapshot()['captions'], timeout=40)
                # Pay the daemon's real delayed GL warm-up before measuring.
                time.sleep(7.5)

                def transition(name, floating, delayed=False, cold=False):
                    before = snapshot()
                    if delayed:
                        delay_file.touch()
                    else:
                        delay_file.unlink(missing_ok=True)
                    began = time.monotonic()
                    ipc(0, '[app_id="ripple-fixture"] floating ' + floating)
                    visible = None
                    until = began + 1.6
                    while time.monotonic() < until:
                        current = snapshot()
                        if (current['ripples'] and visible is None
                                and all(r['width'] and r['height']
                                        for r in current['ripples'])):
                            visible = current
                            time.sleep(0.18)
                            subprocess.run(['grim', str(output / f'{edge}-{name}.png')],
                                           env=env, check=True, timeout=4)
                        time.sleep(0.008)
                    after = snapshot()
                    observed = [e for e in events(trace) if e['t'] >= began]
                    starts = [e for e in observed if e['kind'] == 'ripple-start']
                    created = [e for e in observed if e['kind'] == 'ripple-create']
                    draws = [e for e in observed if e['kind'] == 'ripple-draw']
                    plans = [e for e in observed if e['kind'] == 'plan']
                    captures = [e for e in observed if e['kind'] == 'capture-start']
                    captured = [e for e in observed if e['kind'] == 'capture-end']
                    for index, capture in enumerate(captured):
                        preserve_photograph(Path(capture['photograph']),
                                            output / f'{edge}-{name}-shutter-{index}.png')
                    summary = dict(
                        edge=edge, name=name, began=began, delayed=delayed,
                        before=before, visible=visible, after=after,
                        plans=plans, capture_count=len(captures),
                        ripple_count=len(starts), draw_count=len(draws),
                        first_start_age_ms=starts[0]['age_ms'] if starts else None,
                        first_draw_age_ms=draws[0]['age_ms'] if draws else None,
                        admission_age_ms=(1000 * (created[0]['t'] - starts[0]['started'])
                                          if created and starts else None),
                        shutter_duration_ms=(1000 * (
                            next(e['t'] for e in observed if e['kind'] == 'shutter-return')
                            - captures[0]['t']) if captures else None),
                        gl_errors=sorted({e['gl_error'] for e in draws}),
                        graphics=[e for e in observed if e['kind'] == 'ripple-prepare'],
                    )
                    report['runs'].append(summary)
                    (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
                    assert len(before['captions']) == len(after['captions']) == 1, summary
                    assert not after['ripples'], summary
                    assert len(captures) == len(plans) == 1, summary
                    assert plans[0]['edge'] == edge, summary
                    if 'departure' in name:
                        assert plans[0]['rect'] == before['captions'][0], summary
                    if delayed:
                        assert not starts and not draws and visible is None, summary
                    elif not cold:
                        assert len(starts) == 1 and draws and visible, summary
                        assert all(e['gl_error'] == 0 for e in draws), summary
                        assert summary['admission_age_ms'] < 100, summary
                        assert all(e['program'] and e['error'] is None
                                   for e in summary['graphics']), summary

                # The first real crop imports NumPy. Keep that cold outcome
                # visible in the report; subsequent measurements use the same
                # daemon and its naturally warmed production path.
                transition('cold-departure', 'enable', cold=True)
                transition('warmup-landing', 'disable', cold=True)
                transition('departure', 'enable')
                transition('landing', 'disable')
                transition('departure-late-capture', 'enable', delayed=True)
                delay_file.unlink(missing_ok=True)
                observer.terminate()
                observer.wait(timeout=4)
                observer = None
                wait(lambda: not snapshot()['captions'])
            report['passed'] = True
        finally:
            if connection:
                connection.close()
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=4)
            log.close()
            (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], runs=[{
        key: run[key] for key in ('edge', 'name', 'capture_count', 'ripple_count',
                                 'draw_count', 'first_start_age_ms', 'gl_errors')
    } for run in report['runs']]), indent=2))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'observe':
        observe(*(Path(value) for value in sys.argv[2:5]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--output', type=Path, required=True)
        parser.add_argument('--source', type=Path, default=ROOT)
        parser.add_argument('--restart-power-off', action='store_true',
                            help='only probe caption allocation across private output power-on')
        arguments = parser.parse_args()
        verify(arguments.source.resolve(), arguments.output.resolve(),
               restart_power_off=arguments.restart_power_off)
