"""Native Wayland clicks advance quiet cards while applications retain input."""
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / 'alpine/desktop/.local/bin'
LIB = REPO / 'alpine/desktop/.local/lib/mbp_intel'
OUTPUT = REPO / 'alpine/verification/conky-clicks'
sys.path.insert(0, str(LIB))
import conky_layout
from verify_decoration_attachment import build_pointer


def cover():
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk
    window = Gtk.Window(title='Conky click cover')
    window.set_default_size(400, 200)
    box = Gtk.EventBox()
    box.add(Gtk.Label(label='Application input stays above the desktop cards'))
    box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    box.connect('button-press-event', lambda *_: Path(sys.argv[2]).write_text('clicked'))
    window.add(box)
    window.show_all()
    Gtk.main()


def wait_for(test, message, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = test()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError(message)


def stop_private_clients(environment, compositor_pid, timeout=10):
    """Stop every private client generation before its compositor disappears.

    Click refreshes start detached Conky replacements, so neither the original
    Popen children nor the latest pids.json cover every client. Pin each target
    with a pidfd, then verify its UID and this run's unique HOME/runtime pair.
    Private click workers are included so they cannot restart a card later.
    """
    expected = {os.fsencode(f'{name}={environment[name]}')
                for name in ('HOME', 'XDG_RUNTIME_DIR')}
    deadline = time.monotonic() + timeout
    stopped = forced = 0
    while True:
        descriptors = []
        for process in Path('/proc').iterdir():
            if not process.name.isdecimal() or int(process.name) == compositor_pid:
                continue
            descriptor = None
            try:
                descriptor = os.pidfd_open(int(process.name))
                if (process.stat().st_uid == os.getuid()
                        and expected.issubset(set((process / 'environ').read_bytes().split(b'\0')))):
                    descriptors.append(descriptor)
                    descriptor = None
            except (OSError, ValueError):
                pass
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        if not descriptors:
            return {'private_clients_stopped': stopped, 'forced_clients': forced}

        def signal_clients(targets, kind):
            for descriptor in targets:
                try:
                    signal.pidfd_send_signal(descriptor, kind)
                except ProcessLookupError:
                    pass

        def wait_clients(targets, duration):
            pending = set(targets)
            end = min(deadline, time.monotonic() + duration)
            while pending:
                ready, _, _ = select.select(list(pending), [], [], max(0, end - time.monotonic()))
                pending.difference_update(ready)
                if time.monotonic() >= end:
                    break
            return pending

        try:
            stopped += len(descriptors)
            signal_clients(descriptors, signal.SIGTERM)
            pending = wait_clients(descriptors, 2)
            forced += len(pending)
            signal_clients(pending, signal.SIGKILL)
            pending = wait_clients(pending, 2)
            if pending:
                raise RuntimeError('Private desktop clients survived SIGKILL')
        finally:
            for descriptor in descriptors:
                os.close(descriptor)
        # A refresh already running when cleanup began can create one last
        # replacement. Rescan after all pinned workers have exited.
        if time.monotonic() >= deadline:
            raise RuntimeError('Private desktop cleanup did not settle before its deadline')


def verify():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='conky-clicks-') as temporary:
        root = Path(temporary)
        runtime = root / 'run'
        runtime.mkdir(mode=0o700)
        home = root / 'home'
        home.mkdir()
        target = home / '.local/bin/mbp-intel-conky-click'
        target.parent.mkdir(parents=True)
        target.symlink_to(BIN / 'mbp-intel-conky-click')
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_DATA_HOME=str(home / '.local/share'),
                   WLR_BACKENDS='headless', WLR_RENDERER='pixman', WLR_LIBINPUT_NO_DEVICES='1')
        for name in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(name, None)
        config = root / 'sway.conf'
        config.write_text('output HEADLESS-1 mode 1000x700\n'
                          'output * bg #282828 solid_color\nseat seat0 fallback true\n')
        pointer_binary = build_pointer(root)
        children = []
        state = home / '.local/state/mbp-intel/conky'
        with (OUTPUT / 'native.log').open('w') as log:
            def spawn(arguments, pointer=False):
                process = subprocess.Popen(arguments, env=env,
                    stdin=subprocess.PIPE if pointer else subprocess.DEVNULL,
                    stdout=subprocess.PIPE if pointer else log, stderr=log, text=True)
                children.append(process)
                return process

            def command(*arguments):
                return subprocess.run(arguments, env=env, check=True, capture_output=True,
                                      text=True, timeout=20).stdout

            compositor = spawn(['sway', '-c', str(config)])
            try:
                wait_for(lambda: list(runtime.glob('sway-ipc*.sock')), 'Sway did not start')
                display = wait_for(lambda: [p for p in runtime.glob('wayland-*') if p.is_socket()],
                                   'Wayland display did not start')[0]
                env.update(SWAYSOCK=str(next(runtime.glob('sway-ipc*.sock'))), WAYLAND_DISPLAY=display.name)
                command(str(BIN / 'mbp-intel-scripture'), 'select', 'John 3:16')
                state.mkdir(parents=True)
                panels = [
                    ('scripture', 30, 30, '${execpi 60 ' + str(BIN / 'mbp-intel-scripture') + ' panel}'),
                    ('witness', 520, 30, '${execpi 300 ' + str(BIN / 'mbp-intel-scripture') + ' witness}'),
                    ('ghost', 30, 340, '${execi 240 ' + str(BIN / 'mbp-intel-journal') + ' show}'),
                ]
                pids = {}
                for identifier, x, y, text in panels:
                    panel = {'id': identifier, 'text': '${color1}' + identifier.upper() + '\n' + text}
                    placement = {'x': x, 'y': y, 'width': 430, 'height': 250,
                                 'background': [40, 40, 40]}
                    colours = conky_layout.panel_colours(placement, conky_layout.resolve_palette({}))
                    rendered = conky_layout.render_config(panel, placement, colours,
                        {'font': 'monospace:size=11', 'update_interval': 60,
                         'click_hook': str(LIB / 'conky_click.lua')})
                    path = state / f'{identifier}.conf'
                    path.write_text(rendered)
                    pids[identifier] = spawn(['conky', '-c', str(path)]).pid
                (state / 'pids.json').write_text(json.dumps(pids))
                time.sleep(2)
                command('grim', str(OUTPUT / 'before.png'))
                pointer = spawn([str(pointer_binary)], pointer=True)
                assert pointer.stdout.readline().strip() == 'ready'

                def event(line):
                    pointer.stdin.write(line + '\n')
                    pointer.stdin.flush()
                    assert pointer.stdout.readline().strip() == 'ok'

                def click(x, y, button=272):
                    event(f'move {round(x * 800 / 1000)} {round(y * 600 / 700)}')
                    time.sleep(.15)
                    event(f'press {button}')
                    event(f'release {button}')

                def current_pids():
                    return json.loads((state / 'pids.json').read_text())

                def click_complete():
                    with (state / 'click.lock').open('a+') as lock:
                        try:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            return False
                        return True

                durations = {}
                for identifier, x, y, _ in panels:
                    def pixels():
                        return subprocess.check_output(['grim', '-g', f'{x},{y} 430x250', '-'], env=env)

                    before = current_pids()
                    before_pixels = pixels()
                    if identifier == 'ghost':
                        with sqlite3.connect(home / '.local/share/mbp-intel/journal/entries.sqlite3') as db:
                            previous_entry = db.execute('SELECT entry_id FROM rotation').fetchone()[0]
                    started = time.monotonic()
                    click(x + 60, y + 50)
                    after = wait_for(lambda: (now if (now := current_pids())[identifier]
                                              != before[identifier] else None),
                                     f'{identifier} did not react to its native click')
                    assert all(after[key] == before[key] for key in before if key != identifier)
                    wait_for(click_complete, f'{identifier} click did not finish replacing its card')
                    wait_for(lambda: pixels() != before_pixels, f'{identifier} did not draw its new text')
                    if identifier == 'ghost':
                        with sqlite3.connect(home / '.local/share/mbp-intel/journal/entries.sqlite3') as db:
                            assert db.execute('SELECT entry_id FROM rotation').fetchone()[0] != previous_entry
                    durations[identifier] = round(time.monotonic() - started, 2)
                    time.sleep(.5)
                selected = json.loads((home / '.local/state/mbp-intel/scripture/selection.json').read_text())
                assert selected['reference'] == 'John 3:17'
                command('grim', str(OUTPUT / 'after.png'))
                assert (OUTPUT / 'before.png').read_bytes() != (OUTPUT / 'after.png').read_bytes()

                # A native right-click on the Scripture card returns to the passage shown before it.
                identifier, x, y, _ = panels[0]

                def scripture_pixels():
                    return subprocess.check_output(['grim', '-g', f'{x},{y} 430x250', '-'], env=env)

                before = current_pids()
                before_pixels = scripture_pixels()
                started = time.monotonic()
                click(x + 60, y + 50, button=273)
                after = wait_for(lambda: (now if (now := current_pids())[identifier]
                                          != before[identifier] else None),
                                 'scripture did not react to its native right-click')
                assert all(after[key] == before[key] for key in before if key != identifier)
                wait_for(click_complete, 'scripture right-click did not finish replacing its card')
                wait_for(lambda: scripture_pixels() != before_pixels,
                         'scripture did not draw the returned passage')
                durations['scripture-right-click'] = round(time.monotonic() - started, 2)
                returned = json.loads((home / '.local/state/mbp-intel/scripture/selection.json').read_text())
                assert returned['reference'] == 'John 3:16', returned['reference']
                command('grim', str(OUTPUT / 'returned.png'))

                marker = root / 'application-click'
                app = spawn([sys.executable, __file__, 'cover', str(marker)])
                wait_for(lambda: 'Conky click cover' in command('swaymsg', '-r', '-t', 'get_tree'),
                         'Application did not appear')
                for floating in (False, True):
                    if floating:
                        command('swaymsg', '[title="Conky click cover"] floating enable, '
                                'resize set width 430 height 250, move position 30 30')
                    marker.unlink(missing_ok=True)
                    before = current_pids()
                    click(90, 80)
                    wait_for(marker.exists, 'Application did not receive the click')
                    time.sleep(.3)
                    assert current_pids() == before, 'Application click advanced a desktop card'
                command('grim', str(OUTPUT / 'floating-cover.png'))
                report = {'native_wayland_clicks': durations, 'only_clicked_card_restarted': True,
                          'each_clicked_card_redrawn': True,
                          'selected_reference': selected['reference'],
                          'right_click_returned_reference': returned['reference'],
                          'tiled_and_floating_application_input': True,
                          'periodic_seconds': {'display': 60, 'scripture': 60, 'witness': 300, 'journal': 240}}
                (OUTPUT / 'native.json').write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps(report))
            finally:
                if state.is_dir():
                    (state / 'disabled').touch()
                try:
                    cleanup = stop_private_clients(env, compositor.pid)
                    (OUTPUT / 'cleanup.json').write_text(json.dumps(cleanup, indent=2) + '\n')
                finally:
                    # Reap direct children only after detached replacements
                    # have exited; keep private Sway alive through that wait.
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
    cover() if len(sys.argv) > 1 and sys.argv[1] == 'cover' else verify()
