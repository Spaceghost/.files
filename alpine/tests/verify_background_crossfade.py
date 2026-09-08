#!/usr/bin/env python3
"""Prove the background crossfade in a private headless SwayFX session.

SwayFX lists layer surfaces top-first, so index 0 is what is on top.

Three real gallery paintings take part. swaybg shows A; the daemon starts on A
and fades to the shared painting B; a timed fade to C is photographed early,
part-way and settled; a respawned swaybg covers the surface and the daemon is
shown re-creating it above; a Conky-style card that was below the surface is
restored by the card helper; finally the daemon quits and swaybg's painting
shows through as the fallback. Screenshots, stacking orders and pixel
distances against reference renders are saved for review.
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

import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DAEMON = REPO / 'alpine/desktop/.local/bin/oldbook-background'
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import background_fade as fade  # noqa: E402

WIDTH, HEIGHT = 1280, 720
GRID = (64, 36)
CARD = (40, 40, 200, 120)
CARD_COLOUR = (0.72, 0.73, 0.15)

FAKE_CARD = '''#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell
window = Gtk.Window()
GtkLayerShell.init_for_window(window)
GtkLayerShell.set_namespace(window, 'conky')
GtkLayerShell.set_layer(window, GtkLayerShell.Layer.BACKGROUND)
GtkLayerShell.set_exclusive_zone(window, -1)
GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)
for edge in ('TOP', 'LEFT'):
    GtkLayerShell.set_anchor(window, getattr(GtkLayerShell.Edge, edge), True)
    GtkLayerShell.set_margin(window, getattr(GtkLayerShell.Edge, edge), %d)
window.set_size_request(%d, %d)
area = Gtk.DrawingArea()
def draw(_widget, cr):
    cr.set_source_rgb(%r, %r, %r)
    cr.paint()
    return True
area.connect('draw', draw)
window.add(area)
window.show_all()
Gtk.main()
'''

CARD_HELPER = '''#!/usr/bin/env python3
"""Stand-in for oldbook-conky: restart the fake card and log the request."""
import os
import signal
import subprocess
import sys
from pathlib import Path
base = Path(%r)
log = base / 'cards.log'
pid_file = base / 'card.pid'
with log.open('a') as stream:
    stream.write(' '.join(sys.argv[1:]) + '\\n')
try:
    os.kill(int(pid_file.read_text()), signal.SIGTERM)
except (OSError, ValueError):
    pass
process = subprocess.Popen([sys.executable, str(base / 'fake-card.py')], start_new_session=True,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
pid_file.write_text(str(process.pid))
'''


def paintings():
    files = sorted((REPO / 'alpine/assets/gallery/themes/gruvbox-dark').glob('*.png'))
    if len(files) < 3:
        raise RuntimeError('The Gruvbox gallery needs three paintings for this check')
    return files[0], files[len(files) // 2], files[-1]


def samples(pixbuf):
    small = pixbuf.scale_simple(GRID[0], GRID[1], GdkPixbuf.InterpType.BILINEAR)
    data, channels, stride = small.get_pixels(), small.get_n_channels(), small.get_rowstride()
    return [tuple(data[y * stride + x * channels:y * stride + x * channels + 3])
            for y in range(GRID[1]) for x in range(GRID[0])]


def reference(path):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
    width, height, x, y = fade.fill_geometry(pixbuf.get_width(), pixbuf.get_height(), WIDTH, HEIGHT)
    scaled = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
    return samples(scaled.new_subpixbuf(-x, -y, WIDTH, HEIGHT))


def distance(first, second):
    total = sum(abs(a - b) for pa, pb in zip(first, second) for a, b in zip(pa, pb))
    return round(total / (3 * len(first)), 2)


def blend(first, second, value):
    return [tuple(a * (1 - value) + b * value for a, b in zip(pa, pb))
            for pa, pb in zip(first, second)]


def best_blend(shot, first, second):
    candidates = [(distance(shot, blend(first, second, step / 50)), step / 50) for step in range(51)]
    score, value = min(candidates)
    return {'value': value, 'distance': score}


def card_colour(pixbuf):
    x, y, width, height = CARD
    region = pixbuf.new_subpixbuf(x + 20, y + 20, width - 40, height - 40)
    pixels = samples(region)
    return tuple(round(sum(p[i] for p in pixels) / len(pixels)) for i in range(3))


def card_visible(pixbuf):
    expected = tuple(round(c * 255) for c in CARD_COLOUR)
    return all(abs(a - b) <= 24 for a, b in zip(card_colour(pixbuf), expected))


def shrink(source, dest):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(source))
    pixbuf.scale_simple(640, 360, GdkPixbuf.InterpType.BILINEAR).savev(str(dest), 'png', [], [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
    parser.add_argument('--duration', type=int, default=fade.MAX_DURATION_MS,
                        help='Timed fade in milliseconds; long, because a headless capture under load takes seconds')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    first, second, third = paintings()
    references = {'A': reference(first), 'B': reference(second), 'C': reference(third)}
    evidence = {'paintings': {'A': str(first.relative_to(REPO)), 'B': str(second.relative_to(REPO)),
                              'C': str(third.relative_to(REPO))},
                'daemon_sha256': hashlib.sha256(DAEMON.read_bytes()).hexdigest(),
                'timed_fade_ms': args.duration, 'steps': []}
    with tempfile.TemporaryDirectory(prefix='oldbook-background-') as temporary:
        base = Path(temporary)
        home, runtime = base / 'home', base / 'run'
        home.mkdir()
        runtime.mkdir(mode=0o700)
        share = home / '.local/share/oldbook'
        share.mkdir(parents=True)
        (share / 'wallpaper.png').symlink_to(first)
        (share / 'current-wallpaper.png').symlink_to(second)
        cards = base / 'cards'
        cards.mkdir()
        (cards / 'fake-card.py').write_text(FAKE_CARD % (CARD[0], CARD[2], CARD[3], *CARD_COLOUR))
        helper = cards / 'card-helper.py'
        helper.write_text(CARD_HELPER % str(cards))
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_STATE_HOME=str(home / '.local/state'), WLR_BACKENDS='headless',
                   WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman', GDK_BACKEND='wayland',
                   GTK_USE_PORTAL='0', NO_AT_BRIDGE='1', GTK_A11Y='none',
                   OLDBOOK_BACKGROUND_CHECK_SECONDS='2', OLDBOOK_BACKGROUND_CARDS=str(helper))
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

            def wait_for(predicate, seconds=10, what='condition'):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    value = predicate()
                    if value:
                        return value
                    time.sleep(.05)
                raise RuntimeError(f'Timed out waiting for {what}; see runtime.log')

            def ipc(*arguments):
                return json.loads(subprocess.run(['swaymsg', '-r', *arguments], env=env, check=True,
                                                 capture_output=True, text=True, timeout=10).stdout)

            def surfaces():
                for item in ipc('-t', 'get_outputs'):
                    if item['name'] == 'HEADLESS-1':
                        return [s.get('namespace') for s in item.get('layer_shell_surfaces', [])
                                if s.get('layer') == 'background']
                return []

            def command(*arguments, timeout=20):
                result = subprocess.run([sys.executable, str(DAEMON), *arguments], env=env,
                                        capture_output=True, text=True, timeout=timeout)
                try:
                    return result.returncode, json.loads(result.stdout or 'null')
                except ValueError:
                    return result.returncode, result.stderr.strip()

            def status():
                code, reply = command('status', timeout=10)
                return reply if code == 0 and isinstance(reply, dict) else None

            def showing(path):
                shown = (status() or {}).get('outputs', {}).get('HEADLESS-1', {})
                return (shown.get('path') and not shown.get('fading')
                        and Path(shown['path']).resolve() == path.resolve())

            captures = []

            def shot(name, expect=None):
                """Capture quickly; the pixel analysis waits until the timing no longer matters."""
                path = output / f'{name}.png'
                started = time.monotonic()
                subprocess.run(['grim', str(path)], env=env, check=True, timeout=20)
                captures.append({'name': name, 'expect': expect, 'surfaces': surfaces(),
                                 'capture_seconds': round(time.monotonic() - started, 3)})

            def analyse():
                for record in captures:
                    path = output / f"{record['name']}.png"
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
                    data = samples(pixbuf)
                    record['distance'] = {key: distance(data, value) for key, value in references.items()}
                    record['card_visible'] = card_visible(pixbuf)
                    record['card_colour'] = card_colour(pixbuf)
                    if record['expect'] and '>' in record['expect']:
                        start, end = record['expect'].split('>')
                        record['blend'] = best_blend(data, references[start], references[end])
                    shrink(path, output / f"{record['name']}.small.png")
                    path.unlink()
                evidence['steps'].extend(captures)

            key = hashlib.sha256
            try:
                spawn(['swayfx', '--config', str(config)])
                wait_for(lambda: list(runtime.glob('sway-ipc*.sock')), what='the private compositor')
                env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
                env['WAYLAND_DISPLAY'] = next(p.name for p in runtime.glob('wayland-*') if p.is_socket())
                wait_for(lambda: 'wallpaper' in surfaces(), what='swaybg')
                time.sleep(.5)
                shot('00-swaybg-only', expect='A')
                subprocess.run([sys.executable, str(helper), 'start'], env=env, check=True, timeout=20)
                wait_for(lambda: 'conky' in surfaces(), what='the fake card')
                time.sleep(.3)
                shot('01-card-before-daemon', expect='A')
                endpoint = runtime / 'oldbook' / f"background-{key(env['SWAYSOCK'].encode()).hexdigest()[:12]}.sock"
                daemon = spawn([sys.executable, str(DAEMON), 'daemon'])
                wait_for(endpoint.exists, what='the daemon socket')
                started = time.monotonic()
                wait_for(lambda: showing(second), seconds=15,
                         what='the startup fade to the shared painting')
                evidence['startup_fade_seconds'] = round(time.monotonic() - started, 2)
                wait_for(lambda: surfaces()[:1] == ['conky'], seconds=10, what='the restored card')
                time.sleep(.5)
                shot('02-daemon-shows-current', expect='B')
                code, reply = command('set', str(third), '--duration', str(args.duration), '--no-wait')
                evidence['set_reply'] = reply
                if code != 0 or not isinstance(reply, dict) or reply.get('state') != 'accepted':
                    raise RuntimeError(f'set was not accepted: {reply}')
                wait_for(lambda: (status() or {}).get('outputs', {}).get('HEADLESS-1', {}).get('fading'),
                         what='the timed fade to start')
                fade_started = time.monotonic()
                time.sleep(max(0, .3 - (time.monotonic() - fade_started)))
                shot('03-fade-early', expect='B>C')
                time.sleep(max(0, args.duration / 1000 * .35 - (time.monotonic() - fade_started)))
                shot('04-fade-part-way', expect='B>C')
                evidence['part_way_seconds'] = round(time.monotonic() - fade_started, 2)
                wait_for(lambda: not (status() or {'outputs': {'HEADLESS-1': {'fading': True}}})['outputs']['HEADLESS-1']['fading'],
                         seconds=args.duration / 1000 + 10, what='the timed fade to settle')
                time.sleep(.4)
                shot('05-fade-settled', expect='C')
                ipc(f'output * bg "{first}" fill')
                time.sleep(.3)
                evidence['after_respawn_surfaces'] = surfaces()
                shot('06-swaybg-respawned', expect='A>C')
                wait_for(lambda: 'oldbook-background' in surfaces() and surfaces().index('oldbook-background') < min(
                    i for i, name in enumerate(surfaces()) if name == 'wallpaper'),
                         seconds=10, what='the surface to be re-created above swaybg')
                wait_for(lambda: surfaces()[:1] == ['conky'], seconds=10, what='the card to be restored')
                time.sleep(.6)
                shot('07-healed-above-swaybg', expect='C')
                code, reply = command('raise')
                evidence['raise_reply'] = reply
                wait_for(lambda: surfaces()[:1] == ['conky'], seconds=10, what='the card after raise')
                time.sleep(.4)
                shot('08-after-raise', expect='C')
                evidence['status_before_quit'] = status()
                code, reply = command('quit')
                evidence['quit_reply'] = reply
                wait_for(lambda: daemon.poll() is not None, what='the daemon to exit')
                time.sleep(.5)
                shot('09-fallback-after-quit', expect='A')
                evidence['card_helper_log'] = (cards / 'cards.log').read_text().split()
                evidence['daemon_exit'] = daemon.returncode
                analyse()
            finally:
                for process in reversed(children):
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGTERM)
                            process.wait(timeout=5)
                        except (ProcessLookupError, subprocess.TimeoutExpired):
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                try:
                    os.kill(int((cards / 'card.pid').read_text()), signal.SIGKILL)
                except (OSError, ValueError):
                    pass
    checks = {}
    steps = {step['name']: step for step in evidence['steps']}

    def closest(step):
        return min(step['distance'], key=step['distance'].get)

    checks['swaybg_shows_a'] = closest(steps['00-swaybg-only']) == 'A'
    checks['daemon_starts_on_current'] = closest(steps['02-daemon-shows-current']) == 'B'
    checks['card_restored_at_start'] = steps['02-daemon-shows-current']['card_visible']
    early, part = steps['03-fade-early']['blend'], steps['04-fade-part-way']['blend']
    checks['fade_progresses'] = 0 < early['value'] < part['value'] < 1
    checks['part_way_is_a_blend'] = (part['distance'] + 4 < min(steps['04-fade-part-way']['distance']['B'],
                                                                  steps['04-fade-part-way']['distance']['C']))
    checks['fade_settles_on_c'] = closest(steps['05-fade-settled']) == 'C'
    checks['healed_surface_shows_c'] = closest(steps['07-healed-above-swaybg']) == 'C'
    checks['healed_order'] = steps['07-healed-above-swaybg']['surfaces'][:2] == ['conky', 'oldbook-background']
    checks['card_restored_after_heal'] = steps['07-healed-above-swaybg']['card_visible']
    checks['raise_keeps_order'] = steps['08-after-raise']['surfaces'][:2] == ['conky', 'oldbook-background']
    checks['fallback_after_quit'] = closest(steps['09-fallback-after-quit']) == 'A'
    checks['daemon_exited_cleanly'] = evidence.get('daemon_exit') == 0
    evidence['checks'] = checks
    evidence['passed'] = all(checks.values())
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(checks, indent=2))
    print(output / 'evidence.json')
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
