#!/usr/bin/env python3
"""Exercise the themed Scripture header in a private native Wayland session."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / 'alpine/desktop/.local/bin'
LIB = REPO / 'alpine/desktop/.local/lib/mbp_intel'
sys.path.insert(0, str(LIB))
import conky_layout
from verify_conky_clicks import stop_private_clients, wait_for
from verify_decoration_attachment import build_pointer


def accent_pixels(path, colour):
    """Count solid accent pixels, independent of font-edge antialiasing."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    picture = GdkPixbuf.Pixbuf.new_from_file(str(path))
    data = picture.get_pixels()
    stride, channels = picture.get_rowstride(), picture.get_n_channels()
    target = conky_layout.parse_colour(colour)
    return sum(all(abs(data[y * stride + x * channels + channel] - target[channel]) <= 4
                   for channel in range(3))
               for y in range(picture.get_height()) for x in range(picture.get_width()))


def verify(output, scales=(1, 2)):
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    with tempfile.TemporaryDirectory(prefix='scripture-header-') as temporary:
        root = Path(temporary)
        runtime, home = root / 'run', root / 'home'
        runtime.mkdir(mode=0o700)
        home.mkdir()
        target = home / '.local/bin/mbp-intel-conky-click'
        target.parent.mkdir(parents=True)
        target.symlink_to(BIN / 'mbp-intel-conky-click')
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_DATA_HOME=str(home / '.local/share'),
                   WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
                   WLR_RENDERER='pixman', WLR_LIBINPUT_NO_DEVICES='1',
                   NO_AT_BRIDGE='1', GTK_USE_PORTAL='0')
        for name in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(name, None)
        config = root / 'sway.conf'
        config.write_text('output HEADLESS-1 mode 1600x1200\n'
                          'output * bg #202024 solid_color\nseat seat0 fallback true\n')
        pointer_binary = build_pointer(root)
        state = home / '.local/state/mbp-intel/conky'
        children = []
        with (output / 'native.log').open('w') as log:
            def spawn(arguments, pointer=False):
                process = subprocess.Popen(arguments, env=env,
                    stdin=subprocess.PIPE if pointer else subprocess.DEVNULL,
                    stdout=subprocess.PIPE if pointer else log, stderr=log, text=True)
                children.append(process)
                return process

            def command(*arguments):
                return subprocess.run(arguments, env=env, check=True, capture_output=True,
                                      text=True, timeout=90).stdout

            def reader_open():
                return 'Scripture history' in command('swaymsg', '-r', '-t', 'get_tree')

            def selection():
                return (home / '.local/state/mbp-intel/scripture/selection.json').read_bytes()

            def pids():
                return json.loads((state / 'pids.json').read_text())

            compositor = spawn(['sway', '-c', str(config)])
            try:
                wait_for(lambda: list(runtime.glob('sway-ipc*.sock')), 'Sway did not start')
                display = wait_for(lambda: [p for p in runtime.glob('wayland-*') if p.is_socket()],
                                   'Wayland display did not start')[0]
                env.update(SWAYSOCK=str(next(runtime.glob('sway-ipc*.sock'))),
                           WAYLAND_DISPLAY=display.name)
                pointer = spawn([str(pointer_binary)], pointer=True)
                assert pointer.stdout.readline().strip() == 'ready'

                def event(line):
                    pointer.stdin.write(line + '\n')
                    pointer.stdin.flush()
                    assert pointer.stdout.readline().strip() == 'ok'

                def click(x, y, scale):
                    event(f'move {round(x * 800 * scale / 1600)} '
                          f'{round(y * 600 * scale / 1200)}')
                    time.sleep(.15)
                    event('press 272')
                    event('release 272')

                for scale in scales:
                    accent = {1: '#d9a4eb', 2: '#edc66e'}[scale]
                    folder = output / f'scale-{scale}'
                    folder.mkdir()
                    command('swaymsg', 'output HEADLESS-1 scale ' + str(scale))
                    command(str(BIN / 'mbp-intel-scripture'), 'select', 'John 3:16')
                    state.mkdir(parents=True, exist_ok=True)
                    placement = {'x': 30, 'y': 30, 'width': 430, 'height': 250,
                                 'background': [32, 32, 36]}
                    colours = conky_layout.panel_colours(placement,
                        conky_layout.resolve_palette({'palette': {'accent': accent}}))
                    panel = {'id': 'scripture', 'text':
                        '${color1}󰂺 SCRIPTURE${color2} ${hr 1}\n'
                        '${execpi 3600 ' + str(BIN / 'mbp-intel-scripture') + ' panel}'}
                    rendered = conky_layout.render_config(panel, placement, colours,
                        {'font': 'JetBrainsMono Nerd Font:size=9', 'update_interval': 60,
                         'click_hook': str(LIB / 'conky_click.lua')})
                    path = state / 'scripture.conf'
                    path.write_text(rendered)
                    (folder / 'scripture.conf').write_text(rendered)
                    assert 'History' in rendered
                    match = re.search(r"lua_startup_hook\s*=\s*'mbp_intel_history (\d+) (\d+) (\d+)'",
                                      rendered)
                    assert match, 'Generated header has no click rectangle'
                    box = dict(zip(('x', 'width', 'height'), map(int, match.groups())), y=0)
                    process = spawn(['conky', '-c', str(path)])
                    (state / 'pids.json').write_text(json.dumps({'scripture': process.pid}))
                    header = f"{30 + box['x']},{30 + box['y']} {box['width']}x{box['height']}"
                    def drawn():
                        assert process.poll() is None, 'Conky exited before header verification'
                        command('grim', '-g', header, str(folder / 'history-link.png'))
                        return accent_pixels(folder / 'history-link.png', colours['accent'])
                    try:
                        pixels = wait_for(lambda: (count if (count := drawn()) > 5 else None),
                            'History did not draw in the active accent in its hit rectangle', timeout=60)
                    finally:
                        command('grim', str(folder / 'desktop.png'))
                    saved, before_pids = selection(), pids()
                    click(30 + box['x'] + box['width'] / 2,
                          30 + box['y'] + box['height'] / 2, scale)
                    wait_for(reader_open, 'Native History click did not open the reader', timeout=30)
                    assert selection() == saved, 'History click changed the selected passage'
                    assert pids() == before_pids, 'History click restarted the reading card'
                    def reader_drawn():
                        command('grim', str(folder / 'reader.png'))
                        return ((folder / 'reader.png').read_bytes()
                                != (folder / 'desktop.png').read_bytes())
                    wait_for(reader_drawn, 'History reader did not draw its first frame', timeout=30)
                    command('swaymsg', '[title="Scripture history"] kill')
                    wait_for(lambda: not reader_open(), 'History reader did not close')
                    click(90, 80, scale)
                    wait_for(lambda: pids() != before_pids, 'Passage click did not advance the card',
                             timeout=60)
                    assert json.loads(selection())['reference'] == 'John 3:17'
                    assert not reader_open(), 'Passage body click opened History'
                    reports.append({'scale': scale, 'accent': colours['accent'],
                                    'accent_pixels_in_history_hit_rectangle': pixels,
                                    'native_history_click': True,
                                    'history_preserves_selection_and_card_pid': True,
                                    'body_click_advances_to': 'John 3:17'})
                    (output / 'native.json').write_text(json.dumps(reports, indent=2) + '\n')
                    # Stop this generation before the next scale creates its card.
                    pid = pids()['scripture']
                    os.kill(pid, 15)
                    wait_for(lambda: not Path(f'/proc/{pid}').exists()
                             or Path(f'/proc/{pid}/stat').read_text().split()[2] == 'Z',
                             'Conky did not stop between scale checks')
                    (state / 'pids.json').unlink()
                (output / 'native.json').write_text(json.dumps(reports, indent=2) + '\n')
                print(json.dumps(reports))
            finally:
                if state.is_dir():
                    (state / 'disabled').touch()
                try:
                    cleanup = stop_private_clients(env, compositor.pid)
                    (output / 'cleanup.json').write_text(json.dumps(cleanup, indent=2) + '\n')
                finally:
                    for process in reversed(children):
                        if process.poll() is None:
                            process.terminate()
                    for process in reversed(children):
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=REPO / 'alpine/verification/scripture-header')
    parser.add_argument('--scales', type=int, nargs='+', choices=(1, 2), default=(1, 2))
    arguments = parser.parse_args()
    verify(arguments.output, arguments.scales)
