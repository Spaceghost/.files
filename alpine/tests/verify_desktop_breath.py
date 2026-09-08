#!/usr/bin/env python3
"""Watch the painting breathe and drift in a private headless SwayFX session.

Two parts, chosen with `--part`. **breath** publishes a synthetic air record
into a private runtime directory, exactly as the keyboard worker would, and
checks that the background daemon swells the painting while the record stays
fresh, holds still when the preference is off, and settles back to precisely
the untouched picture once the breathing stops. **screensaver** starts the idle
gallery over two real paintings, watches the drift move and the picture change,
then stops it and checks the daemon glides back to the painting it interrupted.

The session is private: its own compositor, runtime directory, HOME and XDG
directories. Nothing here touches the live desktop. The pixman renderer draws no
blur, so these frames prove geometry and timing, not the compositor's glass.
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
import threading
import time

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / 'alpine/desktop/.local/lib/oldbook'
DAEMON = REPO / 'alpine/desktop/.local/bin/oldbook-background'
GALLERY = REPO / 'alpine/assets/gallery/themes/gruvbox-dark'
WIDTH, HEIGHT = 1440, 900
sys.path.insert(0, str(LIB))
import air  # noqa: E402
import background_fade as fade  # noqa: E402


def paintings(count=3):
    found = sorted(path for path in GALLERY.glob('*.png'))
    if len(found) < count:
        raise RuntimeError('the Gruvbox collection has too few paintings for this check')
    return found[:count]


class Breather(threading.Thread):
    """Keep one air record fresh, the way the keyboard worker keeps publishing."""

    def __init__(self, path, mode='breathe-air', volume=1.0, breath=1.0, interval=0.05):
        super().__init__(daemon=True)
        self.path, self.interval = Path(path), interval
        self.record = {'mode': mode, 'volume': volume, 'phase': 0.0, 'breath': breath,
                       'tempo_seconds': 4.0}
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            payload = dict(self.record, updated=time.time())
            temporary = self.path.with_name(self.path.name + '.tmp')
            temporary.write_text(json.dumps(payload))
            temporary.replace(self.path)
            self.stop.wait(self.interval)

    def close(self):
        self.stop.set()
        self.join(timeout=2)


def strip_signature(path, rows=110):
    """Average colour of the bottom band, where the caption sits."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
    pixels, stride, channels = pixbuf.get_pixels(), pixbuf.get_rowstride(), pixbuf.get_n_channels()
    height, width = pixbuf.get_height(), pixbuf.get_width()
    totals, count = [0, 0, 0], 0
    for y in range(max(0, height - rows), height):
        row = y * stride
        for x in range(0, width, 3):
            offset = row + x * channels
            for index in range(3):
                totals[index] += pixels[offset + index]
            count += 1
    return [total / max(1, count) for total in totals]


def caption_part(output, env, spawn, wait_for, air_file, evidence, check):
    """Does the caption's accent follow the keystroke breath, and only that one?"""
    def ipc(*arguments):
        return json.loads(subprocess.run(['swaymsg', '-r', *arguments], env=env, check=True,
                                         capture_output=True, text=True, timeout=10).stdout)

    def walk(node):
        yield node
        for child in node.get('nodes', []) + node.get('floating_nodes', []):
            yield from walk(child)

    def publish(mode, breath):
        record = {'mode': mode, 'volume': 1.0, 'phase': 0.0, 'breath': breath,
                  'tempo_seconds': 4.0, 'updated': time.time()}
        temporary = air_file.with_name(air_file.name + '.tmp')
        temporary.write_text(json.dumps(record))
        temporary.replace(air_file)

    def shot(name):
        path = output / f'{name}.png'
        subprocess.run(['grim', str(path)], env=env, check=True, timeout=25)
        return path

    spawn(['foot', '--app-id=breath-preview', '--title=FIELD NOTES', 'sh', '-c', 'sleep 600'])
    wait_for(lambda: any(node.get('app_id') == 'breath-preview'
                         for node in walk(ipc('-t', 'get_tree'))), what='a window to caption')
    caption = spawn([str(REPO / 'alpine/desktop/.local/bin/oldbook-decoration'), 'daemon'])
    time.sleep(2.5)
    if caption.poll() is not None:
        raise RuntimeError('the caption daemon exited; see runtime.log')

    keeper = threading.Event()

    def hold(mode, breath, seconds=2.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not keeper.is_set():
            publish(mode, breath)
            time.sleep(0.05)

    hold('breathe-air', 0.0)
    empty = strip_signature(shot('01-caption-empty-lungs'))
    hold('breathe-air', 1.0)
    full = strip_signature(shot('02-caption-full-breath'))
    hold('breathing', 1.0)
    plain = strip_signature(shot('03-caption-plain-breathing'))
    publish('off', 0.0)
    time.sleep(1.5)
    settled = strip_signature(shot('04-caption-settled'))
    evidence['caption_strip_rgb'] = {'empty': empty, 'full': full, 'plain': plain,
                                     'settled': settled}
    moved = sum(abs(a - b) for a, b in zip(empty, full))
    check('the caption brightens with the breath', moved > 0.05, round(moved, 4))
    check('the plain six-second breath leaves the caption alone',
          sum(abs(a - b) for a, b in zip(empty, plain)) < moved / 2,
          [round(value, 3) for value in plain])
    check('the caption settles back when the breathing stops',
          sum(abs(a - b) for a, b in zip(empty, settled)) < moved / 2,
          [round(value, 3) for value in settled])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
    parser.add_argument('--part', choices=('breath', 'screensaver', 'caption'), required=True)
    parser.add_argument('--hold', type=int, default=4000, help='screensaver hold in milliseconds')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    first, second, third = paintings()
    evidence = {'part': args.part, 'checks': [], 'frames': [],
                'daemon_sha256': hashlib.sha256(DAEMON.read_bytes()).hexdigest(),
                'air_sha256': hashlib.sha256((LIB / 'air.py').read_bytes()).hexdigest(),
                'renderer': 'pixman (headless); no compositor blur in these frames',
                'paintings': [str(path.relative_to(REPO)) for path in (first, second, third)]}
    failures = []

    def check(name, condition, detail=None):
        evidence['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            failures.append(name)
        return bool(condition)

    with tempfile.TemporaryDirectory(prefix='oldbook-breath-') as temporary:
        base = Path(temporary)
        home, runtime = base / 'home', base / 'run'
        home.mkdir()
        runtime.mkdir(mode=0o700)
        share = home / '.local/share/oldbook'
        share.mkdir(parents=True)
        (share / 'wallpaper.png').symlink_to(first)
        (share / 'current-wallpaper.png').symlink_to(first)
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_STATE_HOME=str(home / '.local/state'), WLR_BACKENDS='headless',
                   WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman', GDK_BACKEND='wayland',
                   GTK_USE_PORTAL='0', NO_AT_BRIDGE='1', GTK_A11Y='none',
                   OLDBOOK_BACKGROUND_CHECK_SECONDS='30')
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        config = output / 'sway.conf'
        config.write_text(f'xwayland disable\noutput HEADLESS-1 mode {WIDTH}x{HEIGHT}\n'
                          f'output * bg "{first}" fill\nseat seat0 fallback true\n')
        children = []
        with (output / 'runtime.log').open('w') as log:
            def spawn(command):
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                           stdin=subprocess.DEVNULL, start_new_session=True)
                children.append(process)
                return process

            def wait_for(predicate, seconds=15, what='condition'):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    value = predicate()
                    if value:
                        return value
                    time.sleep(.05)
                raise RuntimeError(f'Timed out waiting for {what}; see runtime.log')

            def command(*arguments, timeout=25):
                result = subprocess.run([sys.executable, str(DAEMON), *arguments], env=env,
                                        capture_output=True, text=True, timeout=timeout)
                try:
                    return result.returncode, json.loads(result.stdout or 'null')
                except ValueError:
                    return result.returncode, result.stderr.strip()

            def status():
                code, reply = command('status', timeout=15)
                return reply if code == 0 and isinstance(reply, dict) else {}

            def output_state():
                return status().get('outputs', {}).get('HEADLESS-1', {})

            def transform():
                return output_state().get('transform') or [1.0, 0.0, 0.0]

            def shot(name):
                path = output / f'{name}.png'
                subprocess.run(['grim', str(path)], env=env, check=True, timeout=25)
                evidence['frames'].append({'name': name, 'transform': transform()})
                return path

            def settle(predicate, seconds=6, what='the daemon'):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    if predicate():
                        return True
                    time.sleep(.05)
                return False

            try:
                spawn(['swayfx', '--config', str(config)])
                wait_for(lambda: list(runtime.glob('sway-ipc*.sock')), what='the compositor')
                env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
                env['WAYLAND_DISPLAY'] = next(path.name for path in runtime.glob('wayland-*')
                                              if path.is_socket())
                air_file = runtime / 'oldbook' / air.FILENAME
                air_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if args.part != 'caption':
                    spawn([sys.executable, str(DAEMON), 'daemon'])
                    wait_for(lambda: output_state().get('size'), what='the background surface')
                    wait_for(lambda: not output_state().get('fading'), what='the first painting')

                if args.part == 'caption':
                    caption_part(output, env, spawn, wait_for, air_file, evidence, check)
                elif args.part == 'breath':
                    shot('01-at-rest')
                    check('the painting starts untouched', transform() == [1.0, 0.0, 0.0],
                          transform())

                    breather = Breather(air_file, volume=1.0, breath=1.0)
                    breather.start()
                    swelled = settle(lambda: transform()[0] > 1.0 + air.FULL_AMPLITUDE * 0.9,
                                     what='the swell')
                    shot('02-full-lungs')
                    check('full lungs swell the painting', swelled, transform())
                    check('the swell keeps to its ceiling',
                          transform()[0] <= 1.0 + air.FULL_AMPLITUDE + 1e-6, transform())
                    breather.close()

                    breather = Breather(air_file, volume=air.BASELINE_VOLUME, breath=1.0)
                    breather.start()
                    rested = settle(lambda: 1.0 + air.REST_AMPLITUDE * 0.9 < transform()[0]
                                    <= 1.0 + air.REST_AMPLITUDE + 1e-6, what='the resting swell')
                    shot('03-resting-lungs')
                    check('resting lungs swell it only a little', rested, transform())
                    breather.close()

                    air_file.write_text(json.dumps(
                        {'mode': 'off', 'volume': 0.0, 'phase': 0.0, 'breath': 0.0,
                         'tempo_seconds': 0.0, 'updated': time.time()}))
                    stopped = settle(lambda: transform() == [1.0, 0.0, 0.0], what='the rest')
                    shot('04-settled')
                    check('the breath settles back to the untouched painting', stopped,
                          transform())

                    air.write_preferences({'wallpaper': False, 'caption': False},
                                          Path(env['XDG_CONFIG_HOME']) / 'oldbook/breath.json')
                    time.sleep(1.0)
                    breather = Breather(air_file, volume=1.0, breath=1.0)
                    breather.start()
                    time.sleep(2.0)
                    shot('05-preference-off')
                    check('the preference holds the painting still',
                          transform() == [1.0, 0.0, 0.0], transform())
                    breather.close()
                else:
                    started_on = output_state().get('path')
                    shot('01-before')
                    code, reply = command('screensaver', 'start', str(second), str(third),
                                          '--hold', str(args.hold), '--fade', '600')
                    check('the daemon accepts the idle gallery',
                          code == 0 and isinstance(reply, dict) and reply.get('screensaver'),
                          reply)
                    drifting = settle(lambda: transform()[0] > 1.001, seconds=5,
                                      what='the drift')
                    shot('02-drifting')
                    check('the painting drifts', drifting, transform())
                    panned = settle(lambda: abs(transform()[1]) > 0.5, seconds=8,
                                    what='the pan')
                    check('the drift pans as it zooms', panned, transform())
                    moved_on = settle(lambda: output_state().get('path') not in (None, started_on),
                                      seconds=args.hold / 1000 + 12, what='the next painting')
                    shot('03-next-painting')
                    check('it crossfades to the next painting', moved_on,
                          output_state().get('path'))
                    check('the shared painting link is untouched',
                          Path(share / 'current-wallpaper.png').resolve() == first.resolve(),
                          str(Path(share / 'current-wallpaper.png').resolve()))
                    code, reply = command('screensaver', 'stop')
                    check('the daemon accepts the stop',
                          code == 0 and isinstance(reply, dict) and not reply.get('screensaver'),
                          reply)
                    returned = settle(lambda: transform() == [1.0, 0.0, 0.0], seconds=6,
                                      what='the glide back')
                    restored = settle(lambda: output_state().get('path')
                                      and Path(output_state()['path']).resolve() == Path(started_on).resolve()
                                      and not output_state().get('fading'),
                                      seconds=10, what='the original painting')
                    shot('04-restored')
                    check('the drift glides back to rest', returned, transform())
                    check('the painting it interrupted comes back', restored,
                          output_state().get('path'))
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
    evidence['status'] = 'passed' if not failures else 'failed'
    evidence['failures'] = failures
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'status': evidence['status'], 'failures': failures,
                      'checks': len(evidence['checks'])}, indent=2))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
