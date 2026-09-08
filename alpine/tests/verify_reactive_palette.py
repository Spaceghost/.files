#!/usr/bin/env python3
"""Photograph the accent moving between two paintings, off the live session.

Two gallery paintings with opposite temperaments are put through the real
helper in a private state directory, and the two surfaces that carry the accent
are rendered from it: the bar, in a private headless SwayFX session using the
checked-in stylesheet, and the feedback pill, through its own display-free
preview. The bar configuration here is deliberately small, holding only the
three modules the accent touches, so the evidence does not depend on every
desktop helper being installed.
"""
import argparse
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
GALLERY = REPO / 'alpine/assets/gallery/themes/gruvbox-dark'
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-palette'
OSD = REPO / 'alpine/desktop/.local/bin/oldbook-osd'
STYLE = REPO / 'alpine/desktop/.config/waybar/style.css'
# One warm procession and one polar station: the widest disagreement the
# current collection offers.
SUBJECTS = [('warm', 'crusader-procession-b7da64196555'),
            ('cool', 'antarctic-station-b6c15e380baa')]
BAR = {
    'name': 'evidence', 'layer': 'top', 'position': 'top', 'height': 34,
    'output': 'HEADLESS-1', 'spacing': 3, 'margin-top': 6,
    'margin-left': 10, 'margin-right': 10,
    'modules-left': ['sway/workspaces', 'custom/ai'], 'modules-right': ['clock'],
    'sway/workspaces': {'format': '{value}', 'disable-markup': True},
    'custom/ai': {'exec': "printf '%s' '{\"text\":\"\\u2726 Codex\",\"class\":\"\"}'",
                  'return-type': 'json', 'interval': 3600},
    'clock': {'format': '{:%a %H:%M}', 'interval': 60},
}


def brightest(path, x0, y0, x1, y1, keep=40):
    """The mean of the lit pixels in a region, as #rrggbb.

    Averaging a whole text region mixes glyph and background into mud; the
    brightest pixels are the glyph itself, which is what carries the accent.
    """
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    import numpy
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
    channels, stride = pixbuf.get_n_channels(), pixbuf.get_rowstride()
    width, height = pixbuf.get_width(), pixbuf.get_height()
    raw = numpy.frombuffer(pixbuf.get_pixels(), dtype=numpy.uint8)
    raw = raw[:stride * (height - 1) + width * channels]
    rows = numpy.zeros((height, stride), dtype=numpy.uint8)
    rows.reshape(-1)[:raw.size] = raw
    image = rows[:, :width * channels].reshape(height, width, channels)[..., :3]
    region = image[y0:y1, x0:x1].reshape(-1, 3).astype(float)
    lit = region[region.sum(axis=1).argsort()[-keep:]].mean(axis=0)
    return '#%02x%02x%02x' % tuple(int(value) for value in lit)


def painting_for(fragment):
    for path in sorted(GALLERY.glob('*.png')):
        if fragment in path.name:
            return path
    raise SystemExit('missing evidence painting: ' + fragment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new evidence directory')
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    with tempfile.TemporaryDirectory(prefix='oldbook-accent-') as temporary:
        base = Path(temporary)
        for label, fragment in SUBJECTS:
            painting = painting_for(fragment)
            home = base / label
            (home / 'state').mkdir(parents=True)
            (home / 'config/waybar').mkdir(parents=True)
            env = dict(os.environ, XDG_STATE_HOME=str(home / 'state'),
                       XDG_CONFIG_HOME=str(home / 'config'))
            elected = subprocess.run([sys.executable, str(HELPER), 'apply',
                                      '--painting', str(painting)],
                                     capture_output=True, text=True, timeout=120,
                                     env=env, cwd=str(REPO), check=True)
            record = json.loads((home / 'state/oldbook/palette-override.json').read_text())
            # The bar reads the checked-in stylesheet beside the elected accent.
            shutil.copy(STYLE, home / 'config/waybar/style.css')
            (home / 'config/waybar/waybar-state.css').write_text('/* evidence */\n')
            (home / 'config/waybar/config.jsonc').write_text(json.dumps([BAR], indent=2))
            bar_png = output / f'bar-{label}.png'
            render_bar(home, env, painting, bar_png)
            pill_png = output / f'pill-{label}.png'
            subprocess.run([sys.executable, str(OSD), 'preview', '--kind', 'volume',
                            '--value', '62', '--output', str(pill_png)],
                           capture_output=True, text=True, timeout=120, env=env, check=True)
            results.append({'label': label, 'painting': painting.name,
                            'accent': record['accent'], 'accent_name': record.get('accent_name'),
                            'accent_secondary': record['accent_secondary'],
                            'reason': record['reason'], 'scores': record['scores'],
                            'bar': bar_png.name, 'pill': pill_png.name,
                            'rendered_badge': brightest(bar_png, 92, 10, 158, 30),
                            'helper_said': elected.stdout.strip()})
    accents = {item['accent'] for item in results}
    evidence = {
        'status': 'passed' if len(accents) == len(results) else 'failed',
        'subjects': results,
        'isolation': 'private XDG state and config directories; private headless '
                     'SwayFX (pixman) for the bar; display-free preview for the pill',
        'limits': 'The pixman renderer has no blur, and a small bar configuration '
                  'holding only the accent-bearing modules stands in for the full '
                  'control deck. Neither is a photograph of the live panel.',
    }
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['status'] == 'passed' else 1


def render_bar(home, env, painting, destination):
    """Map the small bar in a private compositor and photograph its strip."""
    runtime = home / 'run'
    runtime.mkdir(mode=0o700, exist_ok=True)
    env = dict(env, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
               WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman',
               GTK_USE_PORTAL='0', NO_AT_BRIDGE='1', GTK_A11Y='none', GDK_BACKEND='wayland')
    for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
        env.pop(key, None)
    config = home / 'sway.conf'
    config.write_text(f'xwayland disable\noutput HEADLESS-1 mode 1440x900\n'
                      f'output * bg "{painting}" fill\nseat seat0 fallback true\n'
                      f'workspace "1: Ghost"\n')
    children = []
    with (home / 'runtime.log').open('w') as log:
        def spawn(command):
            process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                       start_new_session=True)
            children.append(process)
            return process

        def wait_for(predicate, ticks=200):
            for _ in range(ticks):
                if any(child.poll() is not None for child in children):
                    raise RuntimeError('private compositor exited early')
                if predicate():
                    return
                time.sleep(.05)
            raise RuntimeError('private compositor timed out')

        try:
            spawn(['swayfx', '--config', str(config)])
            wait_for(lambda: list(runtime.glob('sway-ipc*.sock')))
            env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
            env['WAYLAND_DISPLAY'] = next(path.name for path in runtime.glob('wayland-*')
                                          if path.is_socket())
            spawn(['waybar', '-c', str(home / 'config/waybar/config.jsonc'),
                   '-s', str(home / 'config/waybar/style.css')])
            time.sleep(3)
            subprocess.run(['grim', '-g', '0,0 1440x60', str(destination)],
                           env=env, check=True, timeout=30)
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


if __name__ == '__main__':
    sys.exit(main())
