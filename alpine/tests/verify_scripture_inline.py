#!/usr/bin/env python3
"""Prove inline input, focus and selection in an isolated native Wayland session."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / 'alpine/desktop/.local/bin'
from verify_decoration_attachment import build_pointer, pointer_reply
from verify_conky_clicks import stop_private_clients

BAR_OBSERVER = r'''
import json, runpy, sys
from pathlib import Path
api = runpy.run_path(sys.argv[1])
status = Path(sys.argv[2])
Base = api['SearchBar']
class ObservedBar(Base):
    def __init__(self):
        self.input_events = []
        super().__init__()
        api['GLib'].timeout_add(20, self.observe)
    def key_pressed(self, entry, event):
        self.input_events.append({'key': event.keyval, 'state': int(event.state)})
        return super().key_pressed(entry, event)
    def select_result(self, *arguments):
        self.input_events.append({'activate': True})
        return super().select_result(*arguments)
    def observe(self):
        shell = api['GtkLayerShell']
        selected = self.result_list.get_selected_row()
        document = {'editing': self.editing, 'focus_received': self.acquired_focus,
            'active': self.window.is_active(), 'entry_focus': self.entry.has_focus(),
            'text': self.entry.get_text(), 'scope': getattr(self, 'scope', None),
            'results': self.results, 'selected': selected.get_index() if selected else None,
            'layer': int(shell.get_layer(self.window)),
            'keyboard': int(shell.get_keyboard_mode(self.window)),
            'gtk_windows': len(api['Gtk'].Window.list_toplevels()),
            'window_identity': hash(self.window), 'pid': __import__('os').getpid(),
            'input_events': self.input_events[-30:],
            'label': self.label.get_text(),
            'status': self.status.get_text(),
            'width': self.window.get_allocated_width(), 'height': self.window.get_allocated_height()}
        temporary = status.with_suffix('.tmp')
        temporary.write_text(json.dumps(document)); temporary.replace(status)
        return True
api['main'].__globals__['SearchBar'] = ObservedBar
sys.argv = [sys.argv[1]]
raise SystemExit(api['main']())
'''
APP = r'''
import json, sys
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
window = Gtk.Window(title='Inline input fixture')
window.set_default_size(500, 180)
entry = Gtk.Entry()
entry.set_placeholder_text('Focus returns here')
window.add(entry); window.show_all(); entry.grab_focus()
status = Path(sys.argv[1])
def observe():
    temporary = status.with_suffix('.tmp')
    temporary.write_text(json.dumps({'text': entry.get_text(), 'focus': entry.has_focus()}))
    temporary.replace(status)
    return True
GLib.timeout_add(20, observe)
Gtk.main()
'''


def wait_for(callback, label, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = callback()
            if result:
                return result
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(.025)
    raise AssertionError('Timed out waiting for ' + label)


def verify(output, scales):
    output.mkdir(parents=True, exist_ok=False)
    report = {'scenarios': [], 'isolation': 'private HOME, XDG data, runtime, compositor',
              'sources': {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in [BIN / 'oldbook-scripture-bar', BIN / 'oldbook-scripture',
                    REPO / 'alpine/desktop/.local/lib/oldbook/scripture_search.py',
                    REPO / 'alpine/desktop/.local/lib/oldbook/scripture_bar_ipc.py',
                    Path(__file__).resolve()]}}
    with tempfile.TemporaryDirectory(prefix='scripture-inline-') as temporary:
        root = Path(temporary)
        runtime, home = root / 'run', root / 'home'
        runtime.mkdir(mode=0o700); home.mkdir()
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
            XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
            WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman',
            WLR_LIBINPUT_NO_DEVICES='1', GDK_BACKEND='wayland', NO_AT_BRIDGE='1', GTK_USE_PORTAL='0')
        for name in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(name, None)
        config = root / 'sway.conf'
        config.write_text('output HEADLESS-1 mode 1440x900\noutput * bg #202024 solid_color\n'
            'seat seat0 fallback true\nfocus_follows_mouse no\n'
            'for_window [title="Inline input fixture"] floating enable, move position 100 100\n'
            f'bindsym Mod4+slash exec {BIN}/oldbook-scripture find\n'
            f'bindsym Mod4+question exec {BIN}/oldbook-scripture find --all\n')
        pointer_binary = build_pointer(root)
        children = []
        with (output / 'native.log').open('w') as log:
            def spawn(arguments, pointer=False):
                process = subprocess.Popen(arguments, env=env, start_new_session=True,
                    stdin=subprocess.PIPE if pointer else subprocess.DEVNULL,
                    stdout=subprocess.PIPE if pointer else log, stderr=log, text=True)
                children.append(process)
                return process
            def command(*arguments):
                # A new wtype process creates a new keyboard/keymap. Let that
                # protocol setup reach GTK before sending its first key.
                if arguments[0] == 'wtype':
                    arguments = ('wtype', '-s', '100', *arguments[1:])
                return subprocess.run(arguments, env=env, check=True, capture_output=True,
                                      text=True, timeout=30).stdout
            def read(path):
                return json.loads(path.read_text())
            def bar():
                return read(root / 'bar.json')
            def app():
                return read(root / 'app.json')
            def outputs():
                return json.loads(command('swaymsg', '-r', '-t', 'get_outputs'))
            def surfaces():
                return [surface for item in outputs() for surface in item.get('layer_shell_surfaces', [])
                        if surface.get('namespace') == 'oldbook-scripture']
            def normal_windows():
                def walk(node):
                    yield node
                    for child in node.get('nodes', []) + node.get('floating_nodes', []):
                        yield from walk(child)
                tree = json.loads(command('swaymsg', '-r', '-t', 'get_tree'))
                return [node['name'] for node in walk(tree) if node.get('app_id') or node.get('window')]
            compositor = spawn(['swayfx', '-c', str(config)])
            try:
                socket_path = wait_for(lambda: next(runtime.glob('sway-ipc*.sock'), None), 'private Sway')
                display = wait_for(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None),
                                   'private Wayland')
                env.update(SWAYSOCK=str(socket_path), WAYLAND_DISPLAY=display.name)
                spawn(['wtype', '-s', '120000'])
                command(str(BIN / 'oldbook-scripture'), 'select', 'John 3:16')
                state = home / '.local/state/oldbook/conky'
                state.mkdir(parents=True)
                for identifier in ('scripture', 'witness'):
                    text = ('${execpi 3600 ' + str(BIN / 'oldbook-scripture') + ' panel --width 52}'
                            if identifier == 'scripture' else 'Unchanged witness fixture')
                    config_file = state / (identifier + '.conf')
                    config_file.write_text("conky.config={out_to_wayland=true,out_to_x=false,own_window=true,"
                        "own_window_type='desktop',alignment='top_right',gap_x=30,gap_y=" +
                        ('80' if identifier == 'scripture' else '400') +
                        ",minimum_width=440,maximum_width=440,minimum_height=180,update_interval=60,"
                        "font='monospace:size=12',use_xft=true,text_buffer_size=8192}\nconky.text=[[" + text + ']]\n')
                    process = spawn(['conky', '-c', str(config_file)])
                    pids = read(state / 'pids.json') if (state / 'pids.json').exists() else {}
                    pids[identifier] = process.pid
                    (state / 'pids.json').write_text(json.dumps(pids))
                spawn([sys.executable, '-c', APP, str(root / 'app.json')])
                daemon = spawn([sys.executable, '-c', BAR_OBSERVER, str(BIN / 'oldbook-scripture-bar'),
                                str(root / 'bar.json')])
                initial = wait_for(lambda: bar(), 'bar startup')
                wait_for(lambda: app()['focus'], 'prior application focus')
                assert not initial['editing'] and initial['layer'] == 1 and initial['keyboard'] == 0
                pointer = spawn([str(pointer_binary)], pointer=True)
                pointer_reply(pointer, 'ready')
                def event(line):
                    pointer.stdin.write(line + '\n'); pointer.stdin.flush(); pointer_reply(pointer, 'ok')
                def click(x, y, width=1440, height=900, button=272):
                    event(f'move {round(x * 800 / width)} {round(y * 600 / height)}')
                    event(f'press {button}'); event(f'release {button}')
                def focused(scope='bible'):
                    sample = bar()
                    return sample if (sample['editing'] and sample['entry_focus'] and
                                      sample['focus_received'] and sample['keyboard'] == 1 and
                                      sample['scope'] == scope) else None
                def idle():
                    sample = bar()
                    return sample if (not sample['editing'] and sample['keyboard'] == 0 and
                                      sample['layer'] == 1) else None
                for scale in scales:
                    folder = output / f'scale-{scale}'; folder.mkdir()
                    command('swaymsg', f'output HEADLESS-1 mode {1440 * scale}x{900 * scale} scale {scale}')
                    command('wtype', '-M', 'logo', '-k', 'slash', '-m', 'logo')
                    activated = wait_for(focused, 'shortcut keyboard focus')
                    command('wtype', 'John 3:17')
                    typed = wait_for(lambda: bar() if (bar()['text'] == 'John 3:17' and
                        bar()['results'] and bar()['results'][0]['reference'] == 'John 3:17') else None,
                        'inline typed Bible result')
                    assert typed['window_identity'] == initial['window_identity']
                    assert typed['gtk_windows'] == 1 and len(surfaces()) == 1
                    assert normal_windows() == ['Inline input fixture'], normal_windows()
                    command('grim', str(folder / 'inline-results.png'))
                    previous = read(state / 'pids.json')
                    started = time.monotonic()
                    command('wtype', '-k', 'Return')
                    wait_for(idle, 'Enter keyboard release')
                    saved_path = home / '.local/state/oldbook/scripture/selection.json'
                    saved = wait_for(lambda: read(saved_path) if read(saved_path)['reference'] == 'John 3:17' else None,
                                     'durable selected passage')
                    replaced = wait_for(lambda: read(state / 'pids.json')
                        if read(state / 'pids.json')['scripture'] != previous['scripture'] else None,
                        'Scripture-only immediate refresh', timeout=30)
                    assert replaced['witness'] == previous['witness']
                    history = json.loads(command(str(BIN / 'oldbook-scripture'), 'history-list', '--json', '--limit', '1'))
                    assert history['document']['reference'] == 'John 3:17'
                    elapsed = round((time.monotonic() - started) * 1000, 2)
                    wait_for(lambda: app()['focus'], 'prior app after Enter')
                    command('wtype', 'after-enter')
                    wait_for(lambda: app()['text'].endswith('after-enter'), 'app receives text after Enter')
                    # Requests target the same daemon even when made together.
                    activators = [subprocess.Popen([str(BIN / 'oldbook-scripture'), 'find'], env=env,
                        stdout=log, stderr=log) for _ in range(3)]
                    for process in activators:
                        process.wait(timeout=10); assert process.returncode == 0
                    wait_for(focused, 'concurrent singleton activation')
                    assert bar()['pid'] == daemon.pid and len(surfaces()) == 1
                    command('wtype', 'not-saved', '-k', 'Escape')
                    wait_for(idle, 'Escape keyboard release')
                    wait_for(lambda: app()['focus'], 'prior app after Escape')
                    assert read(saved_path)['reference'] == 'John 3:17'
                    # Pointer activation acquires the same entry, then an outside
                    # click must leave it and permit ordinary application typing.
                    surface = wait_for(lambda: surfaces()[0] if surfaces() else None, 'idle surface')
                    extent = surface['extent']
                    click(extent['x'] + extent['width'] / 2, extent['y'] + extent['height'] / 2)
                    wait_for(focused, 'pointer focus')
                    command('wtype', 'love')
                    wait_for(lambda: bar()['text'] == 'love' and bar()['results'], 'pointer activation typing')
                    click(250, 180)
                    wait_for(idle, 'outside-click keyboard release')
                    command('wtype', 'after-click')
                    wait_for(lambda: app()['text'].endswith('after-click'), 'outside app typing')
                    command('wtype', '-M', 'logo', '-k', 'question', '-m', 'logo')
                    wait_for(lambda: focused('all'), 'all-collection shortcut')
                    command('wtype', 'Genesis 1:1')
                    wait_for(lambda: len(bar()['results']) >= 2 and
                        bar()['results'][0]['reference'].startswith('Torah '), 'Torah before Bible results')
                    command('wtype', '-k', 'Escape'); wait_for(idle, 'all-scope Escape')
                    extent = surfaces()[0]['extent']
                    click(extent['x'] + 100, extent['y'] + extent['height'] / 2, button=273)
                    wait_for(lambda: focused('reflections'), 'right-click reflections')
                    wait_for(lambda: bar()['results'] and
                        all(item['action'] == 'select-reflection' for item in bar()['results']), 'study choices')
                    command('wtype', '-k', 'Escape'); wait_for(idle, 'reflections Escape')
                    assert normal_windows() == ['Inline input fixture']
                    command('grim', str(folder / 'selection-and-idle.png'))
                    report['scenarios'].append({'scale': scale, 'same_window': True,
                        'shortcut_pointer_typing_with_bounded_keyboard_grab': True,
                        'enter_escape_outside_click_release': True, 'concurrent_singleton': True,
                        'selection': saved['reference'], 'history_saved': True,
                        'only_scripture_replaced': True, 'selection_refresh_ms': elapsed,
                        'all_scope_order_and_reflection_scope': True, 'extra_managed_windows': 0})
                    # Ensure the second scale actually changes the selected passage.
                    command(str(BIN / 'oldbook-scripture'), 'select', 'John 3:16')
                report['passed'] = True
            except Exception as error:
                report['passed'] = False; report['error'] = repr(error)
                try:
                    report['last_bar'] = bar()
                except Exception:
                    pass
                raise
            finally:
                report['cleanup'] = stop_private_clients(env, compositor.pid)
                for process in reversed(children):
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
                survivors = []
                for proc in Path('/proc').iterdir():
                    if proc.name.isdigit():
                        try:
                            if (b'XDG_RUNTIME_DIR=' + os.fsencode(runtime) + b'\0') in (proc / 'environ').read_bytes():
                                survivors.append(int(proc.name))
                        except (OSError, PermissionError):
                            pass
                report['private_survivors'] = survivors
                (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
                if survivors:
                    raise AssertionError('Private clients survived cleanup: ' + str(survivors))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scales', nargs='+', type=int, default=[1, 2])
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.output, arguments.scales), indent=2))
