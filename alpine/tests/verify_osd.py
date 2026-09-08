#!/usr/bin/env python3
"""Exercise the real oldbook-osd daemon in a private headless SwayFX session.

Records the pill while shown and mid-fade, proves it reserves no workspace
space and unmaps when hidden, captures the screenshot flash, and opens Satty
with the repository profile to confirm its app_id, floating rule and config.
Nothing here touches the live outputs; the evidence directory must be new.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
DESKTOP = REPO / 'alpine/desktop'
ART = REPO / 'alpine/assets/gallery/themes/gruvbox-dark/2026-09-07-gruvbox-dark-yosemite-f932fef36c22.png'
PILL = (300, 66)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def swaymsg(env, *arguments):
    result = subprocess.run(['swaymsg', '-s', env['SWAYSOCK'], *arguments], env=env,
                            capture_output=True, text=True, timeout=10, check=True)
    return json.loads(result.stdout) if '-t' in arguments else result.stdout


def surfaces(env, namespace):
    return [surface for output in swaymsg(env, '-t', 'get_outputs')
            for surface in output.get('layer_shell_surfaces', [])
            if surface.get('namespace') == namespace]


def workspace_rect(env):
    return next(space['rect'] for space in swaymsg(env, '-t', 'get_workspaces') if space['focused'])


def grab(env, path):
    subprocess.run(['grim', '-o', 'HEADLESS-1', str(path)], env=env, check=True, timeout=10)
    return path


def load(path):
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    return GdkPixbuf.Pixbuf.new_from_file(str(path))


def crop(source, box, destination):
    pixbuf = load(source)
    x, y, width, height = box
    x, y = max(0, x), max(0, y)
    width = min(width, pixbuf.get_width() - x)
    height = min(height, pixbuf.get_height() - y)
    pixbuf.new_subpixbuf(x, y, width, height).savev(str(destination), 'png', [], [])
    return destination


def shrink(source, destination, width=720):
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    pixbuf = load(source)
    height = round(pixbuf.get_height() * width / pixbuf.get_width())
    pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR).savev(
        str(destination), 'png', [], [])
    return destination


def mean_luma(path, box=None):
    pixbuf = load(path)
    if box:
        x, y, width, height = box
        pixbuf = pixbuf.new_subpixbuf(x, y, width, height)
    data, stride, channels = pixbuf.get_pixels(), pixbuf.get_rowstride(), pixbuf.get_n_channels()
    total = count = 0
    for row in range(0, pixbuf.get_height(), 4):
        base = row * stride
        for column in range(0, pixbuf.get_width(), 4):
            offset = base + column * channels
            red, green, blue = data[offset], data[offset + 1], data[offset + 2]
            total += 0.299 * red + 0.587 * green + 0.114 * blue
            count += 1
    return total / max(1, count)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new evidence directory')
    parser.add_argument('--renderer', default='pixman', choices=['pixman', 'gles2'])
    parser.add_argument('--render-device', default='/dev/dri/renderD128')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'renderer': args.renderer, 'artwork': ART.name, 'artwork_sha256': sha256(ART),
              'daemon_sha256': sha256(DESKTOP / '.local/bin/oldbook-osd'),
              'library_sha256': sha256(DESKTOP / '.local/lib/oldbook/osd.py'),
              'versions': {}}
    for command in (['swayfx', '--version'], ['satty', '--version'], ['grim', '-h']):
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=10)
            report['versions'][command[0]] = (done.stdout or done.stderr).strip().splitlines()[0]
        except (OSError, IndexError):
            report['versions'][command[0]] = 'unavailable'
    with tempfile.TemporaryDirectory(prefix='oldbook-osd-verify-') as temporary:
        base = Path(temporary)
        home, runtime = base / 'home', base / 'run'
        home.mkdir()
        runtime.mkdir(mode=0o700)
        (home / '.config/satty').mkdir(parents=True)
        shutil.copy(DESKTOP / '.config/satty/config.toml', home / '.config/satty/config.toml')
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_STATE_HOME=str(home / '.local/state'), XDG_CACHE_HOME=str(home / '.cache'),
                   WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER=args.renderer,
                   WLR_RENDERER_ALLOW_SOFTWARE='1', WLR_RENDER_DRM_DEVICE=args.render_device,
                   GTK_USE_PORTAL='0', NO_AT_BRIDGE='1', GTK_A11Y='none', GDK_BACKEND='wayland',
                   GSK_RENDERER='cairo')
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        config = output / 'sway.conf'
        config.write_text(f'''xwayland disable
output HEADLESS-1 mode 1440x900
output * bg "{ART}" fill
seat seat0 fallback true
focus_follows_mouse no
include "{DESKTOP / '.config/swayfx/effects.conf'}"
include "{DESKTOP / '.config/sway/local.d/screenshot.conf'}"
''')
        children = []
        with (output / 'runtime.log').open('w') as log:
            def spawn(command, **extra):
                process = subprocess.Popen(command, env=dict(env, **extra), stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                children.append(process)
                return process

            def wait_for(predicate, what, seconds=8):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    if predicate():
                        return
                    if children[0].poll() is not None:
                        raise RuntimeError('The private compositor exited while waiting for ' + what)
                    time.sleep(.05)
                raise RuntimeError('Timed out waiting for ' + what)

            try:
                spawn(['swayfx', '--config', str(config)])
                wait_for(lambda: list(runtime.glob('sway-ipc*.sock')), 'the compositor socket')
                env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
                wait_for(lambda: [path for path in runtime.glob('wayland-*') if path.is_socket()],
                         'the Wayland socket')
                env['WAYLAND_DISPLAY'] = next(path.name for path in runtime.glob('wayland-*')
                                              if path.is_socket())
                wait_for(lambda: swaymsg(env, '-t', 'get_outputs'), 'the headless output')
                report['sway_version'] = swaymsg(env, '-t', 'get_version').get('human_readable')
                helper = DESKTOP / '.local/bin/oldbook-osd'
                daemon = spawn([sys.executable, str(helper), 'daemon'])
                socket_path = runtime / 'oldbook/osd.sock'
                wait_for(socket_path.exists, 'the OSD socket')
                # A short settle so the toolkit has connected before the first show.
                time.sleep(.3)
                rect_before = workspace_rect(env)
                idle = grab(env, base / 'idle.png')
                report['idle_surfaces'] = surfaces(env, 'oldbook-osd')

                def show(kind, value, muted=False):
                    command = [sys.executable, str(helper), 'show', '--kind', kind,
                               '--value', str(value)] + (['--muted'] if muted else [])
                    subprocess.run(command, env=env, check=True, timeout=10)

                show('volume', 42)
                shown_at = time.monotonic()
                wait_for(lambda: surfaces(env, 'oldbook-osd'), 'the pill surface', 3)
                time.sleep(.2)
                shown = grab(env, base / 'shown.png')
                pill = surfaces(env, 'oldbook-osd')
                report['pill_surface'] = pill
                extent = pill[0]['extent']
                box = (extent['x'], extent['y'], extent['width'], extent['height'])
                report['pill_box'] = box
                report['workspace_rect_before'] = rect_before
                report['workspace_rect_shown'] = workspace_rect(env)
                crop(shown, box, output / 'pill-shown.png')
                # Fade window: the hold ends 1.1 s after the show.
                while time.monotonic() - shown_at < 1.22:
                    time.sleep(.01)
                fading = grab(env, base / 'fading.png')
                crop(fading, box, output / 'pill-fading.png')
                while time.monotonic() - shown_at < 2.0:
                    time.sleep(.05)
                wait_for(lambda: not surfaces(env, 'oldbook-osd'), 'the pill to unmap', 3)
                hidden = grab(env, base / 'hidden.png')
                report['hidden_surfaces'] = surfaces(env, 'oldbook-osd')
                report['luma'] = {'idle_box': mean_luma(idle, box), 'shown_box': mean_luma(shown, box),
                                  'fading_box': mean_luma(fading, box),
                                  'hidden_box': mean_luma(hidden, box)}
                # Second reading during a fade snaps back and re-uses the surface.
                show('brightness', 65)
                time.sleep(.6)
                show('mic-mute', 100, muted=True)
                time.sleep(.2)
                crop(grab(env, base / 'second.png'), box, output / 'pill-second-reading.png')
                report['second_surfaces'] = surfaces(env, 'oldbook-osd')
                time.sleep(1.8)
                wait_for(lambda: not surfaces(env, 'oldbook-osd'), 'the pill to unmap again', 3)

                subprocess.run([sys.executable, str(helper), 'flash'], env=env, check=True, timeout=10)
                wait_for(lambda: surfaces(env, 'oldbook-flash'), 'the flash surface', 2)
                flash = grab(env, base / 'flash.png')
                report['flash_surface'] = surfaces(env, 'oldbook-flash')
                time.sleep(.5)
                after = grab(env, base / 'after-flash.png')
                report['flash_surfaces_after'] = surfaces(env, 'oldbook-flash')
                report['luma']['flash_full'] = mean_luma(flash)
                report['luma']['after_flash_full'] = mean_luma(after)
                report['luma']['idle_full'] = mean_luma(idle)
                shrink(flash, output / 'flash.png')

                # The now-transmitting card: slide in, hold, slide out, then go.
                def announce(*arguments):
                    subprocess.run([sys.executable, str(helper), 'card', *arguments],
                                   env=env, check=True, timeout=10)

                announce('--title', 'Coast to Coast', '--artist', 'Space Ghost & The Zorak Quartet',
                         '--album', 'Late Night Transmissions', '--art', str(ART))
                wait_for(lambda: surfaces(env, 'oldbook-card'), 'the track card surface', 3)
                time.sleep(.45)
                card_shot = grab(env, base / 'card.png')
                card_surface = surfaces(env, 'oldbook-card')
                report['card_surface'] = card_surface
                extent = card_surface[0]['extent']
                card_box = (extent['x'], extent['y'], extent['width'], extent['height'])
                report['card_box'] = card_box
                report['workspace_rect_card'] = workspace_rect(env)
                crop(card_shot, card_box, output / 'card-shown.png')
                report['luma']['card_idle_box'] = mean_luma(idle, card_box)
                report['luma']['card_shown_box'] = mean_luma(card_shot, card_box)
                wait_for(lambda: not surfaces(env, 'oldbook-card'), 'the card to unmap', 8)
                gone = grab(env, base / 'card-gone.png')
                report['card_surfaces_after'] = surfaces(env, 'oldbook-card')
                report['luma']['card_gone_box'] = mean_luma(gone, card_box)

                # A locked desktop keeps the card away; the daemon reads the
                # lock helper's own readiness record and checks it is live.
                lock_record = runtime / 'oldbook-screen-lock'
                lock_record.mkdir(mode=0o700, exist_ok=True)
                (lock_record / 'ready.json').write_text(json.dumps(
                    {'process': {'pid': os.getpid()}, 'locker': 'verifier'}))
                announce('--title', 'Not While Locked', '--artist', 'Zorak')
                time.sleep(1.2)
                report['card_surfaces_while_locked'] = surfaces(env, 'oldbook-card')
                shutil.rmtree(lock_record)

                capture = home / 'capture.png'
                shutil.copy(idle, capture)
                satty_log = output / 'satty.log'
                with satty_log.open('w') as satty_out:
                    satty = subprocess.Popen(['satty', '--filename', str(capture),
                                              '--output-filename', str(home / 'annotated.png')],
                                             env=env, stdout=satty_out, stderr=subprocess.STDOUT,
                                             start_new_session=True)
                children.append(satty)

                def satty_view():
                    tree = swaymsg(env, '-t', 'get_tree')
                    stack = [tree]
                    while stack:
                        node = stack.pop()
                        if node.get('app_id') and 'satty' in node['app_id'].lower():
                            return node
                        stack.extend(node.get('nodes', []) + node.get('floating_nodes', []))
                    return None

                wait_for(satty_view, 'the Satty window', 15)
                time.sleep(1.0)
                view = satty_view()
                report['satty'] = {'app_id': view.get('app_id'), 'type': view.get('type'),
                                   'floating': view.get('type') == 'floating_con',
                                   'rect': view.get('rect')}
                shrink(grab(env, base / 'satty.png'), output / 'satty.png')
                os.killpg(satty.pid, signal.SIGTERM)
                satty.wait(timeout=5)
                report['satty']['log'] = satty_log.read_text().strip().splitlines()[-5:]
                report['daemon_alive_at_end'] = daemon.poll() is None
            finally:
                for child in reversed(children):
                    if child.poll() is None:
                        try:
                            os.killpg(child.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                for child in children:
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
    luma = report['luma']
    checks = {
        'pill_on_overlay_layer': bool(report['pill_surface']) and report['pill_surface'][0]['layer'] == 'overlay',
        'pill_size_matches': tuple(report['pill_box'][2:]) == PILL,
        'workspace_unchanged_while_shown': report['workspace_rect_before'] == report['workspace_rect_shown'],
        'pill_unmapped_after_fade': report['hidden_surfaces'] == [],
        'pill_visible_then_fading': luma['shown_box'] != luma['idle_box'] and
                                    abs(luma['fading_box'] - luma['idle_box']) < abs(luma['shown_box'] - luma['idle_box']),
        'pill_gone_after_hide': abs(luma['hidden_box'] - luma['idle_box']) < 2.0,
        'flash_brightened_output': luma['flash_full'] > luma['idle_full'] + 40,
        'flash_gone_after': abs(luma['after_flash_full'] - luma['idle_full']) < 2.0
                            and report['flash_surfaces_after'] == [],
        'card_on_overlay_layer': bool(report['card_surface']) and
                                 report['card_surface'][0]['layer'] == 'overlay',
        'card_visible_while_held': abs(luma['card_shown_box'] - luma['card_idle_box']) > 2.0,
        'workspace_unchanged_while_card_shown': report['workspace_rect_before'] == report['workspace_rect_card'],
        'card_unmapped_after_hold': report['card_surfaces_after'] == [] and
                                    abs(luma['card_gone_box'] - luma['card_idle_box']) < 2.0,
        'card_suppressed_while_locked': report['card_surfaces_while_locked'] == [],
        'satty_floats': report['satty']['floating'],
        'satty_config_accepted': not any('error' in line.lower() for line in report['satty']['log']),
        'daemon_survived': report['daemon_alive_at_end'],
    }
    report['checks'] = checks
    report['passed'] = all(checks.values())
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(checks, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
