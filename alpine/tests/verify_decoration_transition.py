#!/usr/bin/env python3
"""Verify caption mode changes without entry fades or duplicate surfaces.

Uses passive GTK callbacks and persistent Sway IPC in a private headless session.
Timing reflects the test host and headless compositor, not physical scanout.
"""
import argparse
import atexit
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'alpine/tests'))
from verify_decoration_attachment import SwayIPC, walk


if len(sys.argv) > 1 and sys.argv[1] == 'observe':
    import gi

    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk

    trace = []

    def record(kind, window, **fields):
        trace.append(dict(
            kind=kind, t=time.monotonic(), name=window.get_name(), **fields,
        ))

    original_init = Gtk.Window.__init__

    def initialize(window, *args, **kwargs):
        original_init(window, *args, **kwargs)
        window.connect('map', lambda w: record('map', w, alpha=w.get_opacity()))
        window.connect('unmap', lambda w: record('unmap', w))
        window.connect('destroy', lambda w: record('destroy', w))

    Gtk.Window.__init__ = initialize
    original_tick = Gtk.Widget.add_tick_callback

    def add_tick(widget, callback, *args):
        def tick(window, clock, *data):
            result = callback(window, clock, *data)
            owner = getattr(callback, '__self__', None)
            record(
                'frame', window,
                alpha=owner.alpha,
                retiring=owner.retiring,
                rect=owner.motion_rect.copy() if owner.motion_rect else None,
                target=owner.motion_target.copy() if owner.motion_target else None,
            )
            return result

        return original_tick(widget, tick, *args)

    Gtk.Widget.add_tick_callback = add_tick
    destination = Path(sys.argv[3])
    helper = Path(sys.argv[2])
    atexit.register(lambda: destination.write_text(json.dumps(trace)))
    sys.argv = [str(helper), 'daemon']
    runpy.run_path(str(helper), run_name='__main__')
    raise SystemExit


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--source', type=Path, default=ROOT)
args = parser.parse_args()
origin = args.source.resolve()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
source = output / 'source'
for relative in (
    'alpine/desktop/.local/bin/mbp-intel-decoration',
    'alpine/desktop/.local/bin/mbp-intel-resize',
):
    dest = source / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(origin / relative, dest)
if not (source / 'alpine/desktop/.local/lib/mbp_intel').exists():
    shutil.copytree(
        origin / 'alpine/desktop/.local/lib/mbp_intel',
        source / 'alpine/desktop/.local/lib/mbp_intel',
        ignore=shutil.ignore_patterns('__pycache__'),
    )
helper = source / 'alpine/desktop/.local/bin/mbp-intel-decoration'


def wait(fn):
    end = time.monotonic() + 8
    while time.monotonic() < end:
        result = fn()
        if result:
            return result
        time.sleep(0.03)
    raise RuntimeError('Timed out')


with tempfile.TemporaryDirectory(prefix='decoration-transition-') as temporary:
    base = Path(temporary)
    env = dict(os.environ)
    for key, name in [
        ('HOME', 'home'),
        ('XDG_RUNTIME_DIR', 'run'),
        ('XDG_CONFIG_HOME', 'config'),
        ('XDG_STATE_HOME', 'state'),
        ('XDG_CACHE_HOME', 'cache'),
        ('XDG_DATA_HOME', 'data'),
    ]:
        (base / name).mkdir(mode=0o700)
        env[key] = str(base / name)
    for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
        env.pop(key, None)
    env.update(
        WLR_BACKENDS='headless',
        WLR_RENDERER='pixman',
        WLR_HEADLESS_OUTPUTS='1',
        NO_AT_BRIDGE='1',
        GTK_USE_PORTAL='0',
        GDK_BACKEND='wayland',
        DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(base / 'no-bus'),
    )
    (base / 'config/foot').mkdir()
    (base / 'config/foot/foot.ini').write_text(
        '[main]\n'
        'font=monospace:size=10\n'
        'resize-by-cells=no\n'
        '[colors-dark]\n'
        'background=382449\n'
        'foreground=eadff5\n'
    )
    (base / 'config/mbp-intel').mkdir()
    (base / 'config/mbp-intel/decoration.json').write_text(
        '{"position":"bottom","opacity":0.78,"corner_radius":7}'
    )
    cfg = base / 'sway.conf'
    cfg.write_text(
        'xwayland disable\n'
        'output HEADLESS-1 mode 1440x900@60Hz\n'
        'output * bg #13091f solid_color\n'
        'seat seat0 fallback true\n'
        'focus_follows_mouse no\n'
        'default_border pixel 0\n'
        'default_floating_border pixel 0\n'
    )
    log = (output / 'runtime.log').open('w')
    procs = []

    def spawn(args):
        p = subprocess.Popen(args, env=env, stdout=log, stderr=log)
        procs.append(p)
        return p

    spawn(['swayfx', '-c', str(cfg)])
    connection = None
    try:
        sock = wait(lambda: next((base / 'run').glob('sway-ipc*.sock'), None))
        env['SWAYSOCK'] = str(sock)
        env['WAYLAND_DISPLAY'] = wait(lambda: next(
            (p.name for p in (base / 'run').glob('wayland-*') if p.is_socket()),
            None,
        ))
        connection = SwayIPC(sock)

        def ipc(kind, text=''):
            return connection.requests([(kind, text)])[0]

        def window():
            return next(
                (n for n in walk(ipc(4))
                 if n.get('app_id') == 'transition-fixture'),
                None,
            )

        def snapshot():
            tree, outputs = connection.requests([(4, ''), (3, '')])
            node = next(
                n for n in walk(tree)
                if n.get('app_id') == 'transition-fixture'
            )
            layers = [
                s for o in outputs for s in o.get('layer_shell_surfaces', [])
                if s['namespace'] == 'mbp-intel-decoration'
            ]
            return dict(
                t=time.monotonic(),
                window=node['rect'],
                floating=node.get('type') == 'floating_con',
                captions=[dict(layer=s['layer'], rect=s['extent']) for s in layers],
            )

        spawn([
            'foot', '--app-id=transition-fixture', '--title=Transition fixture',
            '--override=initial-window-size-pixels=600x400', '-e', 'cat',
        ])
        wait(window)
        observer = spawn([
            'python3', str(Path(__file__).resolve()), 'observe',
            str(helper), str(output / 'frames.json'),
        ])
        wait(lambda: snapshot()['captions'])
        time.sleep(0.6)

        def transition(name, args):
            before = snapshot()
            began = time.monotonic()
            proc = None
            if args:
                proc = spawn(args)
            else:
                ipc(0, '[app_id="transition-fixture"] floating enable')
            samples = []
            while time.monotonic() - began < 1.3:
                samples.append(snapshot())
                time.sleep(0.005)
            if proc:
                proc.wait(timeout=3)
            return dict(name=name, began=began, before=before, samples=samples)

        runs = [transition('plain-floating', None)]
        ipc(0, '[app_id="transition-fixture"] floating disable')
        time.sleep(0.6)
        runs.append(transition('centered-resize', [
            'python3', str(source / 'alpine/desktop/.local/bin/mbp-intel-resize'),
            'shrink',
        ]))
        subprocess.run(['grim', str(output / 'settled.png')], env=env, check=True)
        observer.terminate()
        observer.wait(timeout=4)
        frames = json.loads((output / 'frames.json').read_text())
        summaries = []
        for run in runs:
            start = run['began']
            samples = run['samples']
            changed = []
            prev = run['before']['window']
            for sample in samples:
                if sample['window'] != prev:
                    changed.append(dict(
                        ms=round((sample['t'] - start) * 1000, 2),
                        rect=sample['window'],
                    ))
                    prev = sample['window']
            events = [f for f in frames if start <= f['t'] <= start + 1.3]
            first_top = next(
                (s for s in samples
                 if any(c['layer'] == 'top' for c in s['captions'])),
                None,
            )
            overlaps = [s for s in samples if len(s['captions']) > 1]
            alpha_events = [
                f for f in events if f['kind'] == 'frame' and not f['retiring']
            ]

            def attached(sample):
                if len(sample['captions']) != 1:
                    return False
                caption = sample['captions'][0]
                window_rect = sample['window']
                return (
                    caption['layer'] == 'top'
                    and caption['rect']['x'] == window_rect['x']
                    and caption['rect']['y'] == window_rect['y'] + window_rect['height']
                    and caption['rect']['width'] == window_rect['width']
                )

            settled = next(
                (s for i, s in enumerate(samples)
                 if attached(s) and all(attached(later) for later in samples[i:])),
                None,
            )
            summary = dict(
                name=run['name'],
                window_geometry_changes=changed,
                first_top_ms=(
                    round((first_top['t'] - start) * 1000, 2) if first_top else None
                ),
                overlap_samples=len(overlaps),
                overlap_until_ms=(
                    round((overlaps[-1]['t'] - start) * 1000, 2) if overlaps else 0
                ),
                stable_attachment_ms=(
                    round((settled['t'] - start) * 1000, 2) if settled else None
                ),
                maps=[
                    dict(ms=round((f['t'] - start) * 1000, 2), alpha=f['alpha'])
                    for f in events if f['kind'] == 'map'
                ],
                opaque_ms=next(
                    (round((f['t'] - start) * 1000, 2)
                     for f in alpha_events if f['alpha'] == 1),
                    None,
                ),
                motion_targets=[],
            )
            for f in alpha_events:
                if f['target'] and (
                    not summary['motion_targets']
                    or f['target'] != summary['motion_targets'][-1]['target']
                ):
                    summary['motion_targets'].append(dict(
                        ms=round((f['t'] - start) * 1000, 2), target=f['target'],
                    ))
            summaries.append(summary)
        (output / 'samples.json').write_text(json.dumps(runs, indent=2) + '\n')
        (output / 'summary.json').write_text(json.dumps(dict(
            helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
            runs=summaries,
        ), indent=2) + '\n')
        print(json.dumps(summaries, indent=2))
        for summary in summaries:
            assert summary['maps'] and all(
                item['alpha'] == 1 for item in summary['maps']
            ), summary
            assert summary['overlap_samples'] == 0, summary
            assert summary['stable_attachment_ms'] is not None, summary
    finally:
        if connection:
            connection.close()
        for p in reversed(procs):
            if p.poll() is None:
                p.terminate()
        for p in reversed(procs):
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        log.close()
