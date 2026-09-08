"""Check adaptive search and stationary Conky cards in private SwayFX."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib


REPO = Path(__file__).resolve().parents[2]
BIN = REPO / 'alpine/desktop/.local/bin'
OUTPUT = REPO / 'alpine/verification/desktop-space'
SURFACE = r'''
import sys
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell
window = Gtk.Window()
GtkLayerShell.init_for_window(window)
top = sys.argv[1] == 'top'
GtkLayerShell.set_namespace(window, 'top' if top else 'mbp-intel-decoration')
GtkLayerShell.set_layer(window, GtkLayerShell.Layer.TOP if top else GtkLayerShell.Layer.OVERLAY)
GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)
GtkLayerShell.set_exclusive_zone(window, 40 if top else -1)
GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP if top else GtkLayerShell.Edge.BOTTOM, True)
GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.LEFT, True)
GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.RIGHT, True)
GtkLayerShell.set_margin(window, GtkLayerShell.Edge.BOTTOM, 0 if top else 5)
window.set_size_request(-1, 40 if top else 28)
window.add(Gtk.Label(label='PRIVATE GEOMETRY CHECK' if top else 'Workspace caption'))
provider = Gtk.CssProvider()
provider.load_from_data(b'window { background: #3c3836; color: #fabd2f; }')
Gtk.StyleContext.add_provider_for_screen(window.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
window.show_all()
Gtk.main()
'''
BAR_OBSERVER = r'''
import json
from pathlib import Path
import runpy
import sys
api = runpy.run_path(sys.argv[1])
bar_class = api['SearchBar']
refresh = bar_class.refresh_geometry
status = Path(sys.argv[2])
previous = None
def observed_refresh(self):
    global previous
    result = refresh(self)
    shell = api['GtkLayerShell']
    values = {'bottom': shell.get_margin(self.window, shell.Edge.BOTTOM),
              'left': shell.get_margin(self.window, shell.Edge.LEFT),
              'screen': self.geometry}
    if values != previous:
        status.write_text(json.dumps(values))
        previous = values
    return result
bar_class.refresh_geometry = observed_refresh
sys.exit(api['main']())
'''


def write_wallpaper(path):
    """A flat fixture isolates placement from wallpaper detail scoring."""
    def chunk(kind, data):
        return (struct.pack('!I', len(data)) + kind + data
                + struct.pack('!I', zlib.crc32(kind + data)))
    pixels = (b'\x00' + bytes((29, 32, 33)) * 1440) * 900
    path.write_bytes(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('!2I5B', 1440, 900, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


def wait_for(condition, description, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(.1)
    raise AssertionError('Timed out waiting for ' + description)


def terminate(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main():
    for executable in ('swayfx', 'swaymsg', 'conky', 'foot', 'grim'):
        if not shutil.which(executable):
            raise RuntimeError('Missing native verification tool: ' + executable)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'scenarios': [], 'isolated_home_runtime_compositor': True}
    with tempfile.TemporaryDirectory(prefix='desktop-space-') as temporary:
        root = Path(temporary)
        runtime, home = root / 'run', root / 'home'
        runtime.mkdir(mode=0o700)
        home.mkdir()
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_STATE_HOME=str(home / '.local/state'), GDK_BACKEND='wayland',
                   WLR_BACKENDS='headless', WLR_RENDERER='gles2', WLR_LIBINPUT_NO_DEVICES='1',
                   WLR_RENDERER_ALLOW_SOFTWARE='1', WLR_RENDER_DRM_DEVICE='/dev/dri/renderD129')
        for name in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(name, None)
        conky = home / '.local/bin/conky'
        conky.parent.mkdir(parents=True)
        conky.write_text('#!/bin/sh\nexec /usr/bin/conky -D "$@" 2>>"$MBP_INTEL_GEOMETRY_CONKY_LOG"\n')
        conky.chmod(0o755)
        env['PATH'] = str(conky.parent) + os.pathsep + env['PATH']
        env['MBP_INTEL_GEOMETRY_CONKY_LOG'] = str(OUTPUT / 'conky.log')
        (OUTPUT / 'conky.log').write_text('')
        panel_config = home / '.config/conky/panels.json'
        panel_config.parent.mkdir(parents=True)
        panel_config.write_text(json.dumps({'font': 'monospace:size=11', 'update_interval': 60,
            'gap': 1, 'panels': [
                {'id': 'masthead', 'width': 280, 'height': 100, 'prefer': 'top',
                 'priority': 100, 'text': '${color1}TOP CARD ${time %H:%M}\n${color}Origin follows the top bar'},
                {'id': 'ghost', 'width': 220, 'height': 120, 'prefer': 'bottom-right',
                 'priority': 90, 'text': '${color1}BOTTOM CARD ${time %H:%M}\n${color}Room at the free edge'}]}))
        wallpaper = home / '.local/share/mbp-intel/current-wallpaper.png'
        wallpaper.parent.mkdir(parents=True)
        write_wallpaper(wallpaper)
        config = root / 'sway.conf'
        config.write_text('output HEADLESS-1 mode 1440x900\n'
                          'output * bg #1d2021 solid_color\nseat seat0 fallback true\n'
                          'gaps inner 0\ngaps outer 0\ndefault_border pixel 2\n')
        state = home / '.local/state/mbp-intel/conky'
        processes = []
        with (OUTPUT / 'native.log').open('w') as log:
            def start(command):
                process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=log)
                processes.append(process)
                return process

            def command(*arguments):
                return subprocess.run(arguments, env=env, capture_output=True,
                                      text=True, check=True, timeout=15)

            def ipc(*arguments):
                return json.loads(command('swaymsg', '-r', *arguments).stdout)

            def output():
                return next(item for item in ipc('-t', 'get_outputs') if item['name'] == 'HEADLESS-1')

            def saved_layout():
                try:
                    return json.loads((state / 'layout.json').read_text())
                except (FileNotFoundError, ValueError):
                    return None

            def snapshot(name, bottom, fullscreen=False):
                def ready():
                    layout = saved_layout()
                    if not layout or layout['screen']['bottom'] < 60:
                        return None
                    try:
                        bar_status = json.loads((root / 'bar-status.json').read_text())
                    except (FileNotFoundError, ValueError):
                        return None
                    if bar_status['bottom'] != bottom:
                        return None
                    native = output()
                    surfaces = native.get('layer_shell_surfaces', [])
                    bars = [item['extent'] for item in surfaces
                            if item['namespace'] == 'mbp-intel-scripture']
                    cards = [item['extent'] for item in surfaces if item['namespace'] == 'conky']
                    if fullscreen:
                        if bars or cards:
                            return None
                        bar = None
                    else:
                        if len(bars) != 1 or len(cards) != len(layout['placements']):
                            return None
                        bar = bars[0]
                        if native['rect']['height'] - bar['y'] - bar['height'] != bottom:
                            return None
                        for plan in layout['placements']:
                            if not any(card['x'] == plan['x'] and card['y'] == plan['y'] for card in cards):
                                return None
                    return {'scenario': name, 'screen': layout['screen'], 'pairing': layout['pairing'],
                            'bar_bottom': bottom, 'pids': json.loads((state / 'pids.json').read_text()),
                            'bar_properties': bar_status,
                            'placements': layout['placements'], 'conky_extents': cards,
                            'bar_extent': bar, 'surfaces': surfaces}
                try:
                    result = wait_for(ready, name + ' synchronized native layer extents')
                except AssertionError:
                    (OUTPUT / (name + '-failure.json')).write_text(json.dumps(
                        {'output': output(), 'layout': saved_layout()}, indent=2) + '\n')
                    raise
                report['scenarios'].append(result)
                command('grim', str(OUTPUT / (name + '.png')))
                print(name, 'bottom', bottom, 'bar', result['bar_extent'], flush=True)
                return result

            start(['swayfx', '-c', str(config)])
            try:
                def sockets():
                    displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
                    ipc_sockets = list(runtime.glob('sway-ipc*.sock'))
                    return (displays[0], ipc_sockets[0]) if displays and ipc_sockets else None
                display, socket = wait_for(sockets, 'private Sway sockets')
                env.update(WAYLAND_DISPLAY=display.name, SWAYSOCK=str(socket))
                start([sys.executable, '-c', SURFACE, 'top'])
                def top_ready():
                    try:
                        return any(item['namespace'] == 'top'
                                   for item in output().get('layer_shell_surfaces', []))
                    except subprocess.CalledProcessError:
                        return False
                try:
                    wait_for(top_ready, 'top bar')
                except AssertionError:
                    (OUTPUT / 'top-failure.json').write_text(json.dumps(output(), indent=2))
                    raise
                bar_process = start([sys.executable, '-c', BAR_OBSERVER,
                                     str(BIN / 'mbp-intel-scripture-bar'), str(root / 'bar-status.json')])
                command(str(BIN / 'mbp-intel-conky'), 'start')
                first = snapshot('01-free', 16)
                assert first['screen']['origin_y'] == 40, first['screen']

                terminal = start(['foot', '--app-id=desktop-space-client',
                                  '--title=Geometry fixture', 'sh', '-c', 'sleep 300'])
                tiled = snapshot('02-tiled', 60)
                assert tiled['pairing'] == first['pairing']
                ipc('[app_id="desktop-space-client"] floating enable, resize set 640 420, move position 400 220')
                floating = snapshot('03-floating', 16)
                assert floating['pairing'] == first['pairing']
                ipc('[app_id="desktop-space-client"] fullscreen enable')
                snapshot('04-fullscreen', 60, fullscreen=True)
                ipc('[app_id="desktop-space-client"] fullscreen disable')
                snapshot('05-restored-floating', 16)
                terminate(terminal)
                snapshot('06-clear', 16)

                caption = start([sys.executable, '-c', SURFACE, 'caption'])
                snapshot('07-workspace-caption', 60)
                terminate(caption)
                restored = snapshot('08-caption-cleared', 16)
                assert restored['pairing'] == first['pairing']
                assert all(item['pids'] == first['pids'] and item['placements'] == first['placements']
                           for item in report['scenarios'])
                report['window_changes_keep_conky_processes_and_placements'] = True

                def cpu_ticks():
                    fields = Path(f'/proc/{bar_process.pid}/stat').read_text().split(') ', 1)[1].split()
                    return int(fields[11]) + int(fields[12])
                started = time.monotonic()
                before_ticks = cpu_ticks()
                time.sleep(5)
                duration = time.monotonic() - started
                cpu_seconds = (cpu_ticks() - before_ticks) / os.sysconf('SC_CLK_TCK')
                report['idle_bar'] = {'measured_seconds': round(duration, 3),
                                      'cpu_seconds': cpu_seconds,
                                      'percent_of_one_core': round(100 * cpu_seconds / duration, 3)}

                # An explicit user opt-out must survive future edge changes.
                command(str(BIN / 'mbp-intel-conky'), 'toggle')
                before = (state / 'layout.json').read_bytes()
                caption = start([sys.executable, '-c', SURFACE, 'caption'])
                wait_for(lambda: any(item['namespace'] == 'mbp-intel-decoration'
                                     for item in output().get('layer_shell_surfaces', [])), 'disabled caption')
                time.sleep(2.2)
                assert (state / 'disabled').is_file()
                assert (state / 'layout.json').read_bytes() == before
                assert not any(item['namespace'] == 'conky'
                               for item in output().get('layer_shell_surfaces', []))
                report['disabled_panels_stay_disabled'] = True
                report['native_origins_match_planner_with_top_exclusive_zone'] = True
                report['conky_extent_note'] = ('SwayFX reports desired layer size 1x1; screenshots '
                                               'show rendered cards at the recorded origins.')
                report['status'] = 'passed'
            finally:
                if state.exists():
                    subprocess.run([str(BIN / 'mbp-intel-conky'), 'stop'], env=env,
                                   stdout=log, stderr=log, timeout=10)
                for process in reversed(processes):
                    terminate(process)
                (OUTPUT / 'native.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'scenarios': len(report['scenarios'])}))


if __name__ == '__main__':
    main()
