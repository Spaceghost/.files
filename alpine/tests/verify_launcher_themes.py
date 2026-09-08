"""Render real Fuzzel menus under isolated Sway, without changing the live theme."""
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
COLORS = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/mbp_intel/launcher_theme.py'))['color_arguments']
OUTPUT = REPO / 'alpine/verification/launcher-themes'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='launcher-theme-') as temporary:
        base = Path(temporary)
        runtime = base / 'run'
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless',
                   WLR_RENDERER='pixman', WLR_LIBINPUT_NO_DEVICES='1')
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        config = base / 'sway.conf'
        config.write_text('output HEADLESS-1 mode 1100x700\noutput * bg #181818 solid_color\nseat seat0 fallback true\n')
        with (base / 'sway.log').open('w') as log:
            sway = subprocess.Popen(['sway', '-c', str(config)], env=env, stdout=log, stderr=log)
            try:
                for _ in range(60):
                    displays = [p for p in runtime.glob('wayland-*') if p.is_socket()]
                    if displays:
                        break
                    time.sleep(.1)
                env['WAYLAND_DISPLAY'] = displays[0].name
                for name, palette in (
                    ('gruvbox', dict(background='#282828', foreground='#ebdbb2', accent='#fabd2f')),
                    ('violet', dict(background='#13091f', foreground='#eaddf5', accent='#dca7ff')),
                    ('parchment', dict(background='#fff6df', foreground='#44392d', accent='#b98938')),
                ):
                    command = [str(REPO / 'alpine/desktop/.local/bin/mbp-intel-fuzzel'),
                               '--dmenu', '--prompt', 'Ghost Gallery ❯ ', '--width', '48', '--lines', '6',
                               *COLORS(palette)]
                    menu = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log, text=True)
                    try:
                        menu.stdin.write('Generate a random theme\nGenerate from a phrase or title\nBrowse paintings\nRotate this workspace\nKeep this painting\nEdit artwork guidance\n')
                        menu.stdin.close()
                        time.sleep(.8)
                        if menu.poll() is not None:
                            raise RuntimeError((base / 'sway.log').read_text())
                        subprocess.run(['grim', str(OUTPUT / (name + '.png'))], env=env, check=True)
                    finally:
                        menu.terminate()
                        menu.wait(timeout=5)
                menu = subprocess.Popen([str(REPO / 'alpine/desktop/.local/bin/mbp-intel-menu')],
                                        env=env, stdout=log, stderr=log)
                try:
                    time.sleep(1)
                    if menu.poll() is not None:
                        raise RuntimeError((base / 'sway.log').read_text())
                    subprocess.run(['grim', str(OUTPUT / 'applications.png')], env=env, check=True)
                finally:
                    menu.terminate()
                    menu.wait(timeout=5)
            finally:
                sway.terminate()
                sway.wait(timeout=5)
    print('Rendered dark, light, and generated palettes plus the real application launcher.')


if __name__ == '__main__':
    main()
