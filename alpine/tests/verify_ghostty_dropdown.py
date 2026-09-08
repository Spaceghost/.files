#!/usr/bin/env python3
"""Verify console and Foot monitor behavior in a private Sway session.

Run directly; requires sway, dbus-daemon, ghostty, foot, btop, wtype, and grim.
Retains JSON and a screenshot in alpine/verification/ghostty-dropdown.
"""
import argparse
import json
import os
import pathlib
import runpy
import shutil
import subprocess
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=pathlib.Path,
                    default=ROOT / 'alpine/verification/ghostty-dropdown')
OUT = parser.parse_args().output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)
LOGS = OUT / 'logs'
LOGS.mkdir(exist_ok=True)
HELPER = ROOT / 'alpine/desktop/.local/bin/mbp-intel-dropdown'
api = runpy.run_path(str(HELPER))


def monitor_child(parent):
    """Find btop descended from this private Foot process."""
    processes = {}
    for entry in pathlib.Path('/proc').glob('[0-9]*/stat'):
        try:
            data = entry.read_text()
            fields = data.rsplit(') ', 1)[1].split()
            processes[int(entry.parent.name)] = (
                int(fields[1]), data.split('(', 1)[1].rsplit(')', 1)[0])
        except (OSError, ProcessLookupError):
            continue
    for pid, (_, name) in processes.items():
        if name != 'btop':
            continue
        ancestor = pid
        seen = set()
        while ancestor in processes and ancestor not in seen:
            if ancestor == parent:
                return pid
            seen.add(ancestor)
            ancestor = processes[ancestor][0]
    return None


def wait(fn):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(0.1)
    raise RuntimeError('Timed out')


with tempfile.TemporaryDirectory(prefix='ghostty-dropdown-') as tmp:
    base = pathlib.Path(tmp)
    home = base / 'home'
    home.mkdir()
    runtime = base / 'run'
    runtime.mkdir(mode=0o700)
    (base / 'cache').mkdir(mode=0o700)
    config = home / '.config/ghostty/config'
    config.parent.mkdir(parents=True)
    config.write_text((ROOT / 'alpine/desktop/.config/ghostty/config').read_text()
                      + '\ncommand = /bin/sh\nshell-integration = none\n'
                      + 'working-directory = ' + str(home) + '\n')
    for application in ('foot', 'btop'):
        shutil.copytree(ROOT / 'alpine/desktop/.config' / application,
                        home / '.config' / application)
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
               XDG_DATA_HOME=str(home / '.local/share'),
               XDG_STATE_HOME=str(home / '.local/state'), XDG_CACHE_HOME=str(base / 'cache'),
               XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless', WLR_RENDERER='gles2',
               WLR_LIBINPUT_NO_DEVICES='1', WLR_RENDERER_ALLOW_SOFTWARE='1',
               GDK_BACKEND='wayland', GDK_DEBUG='no-portals', GTK_A11Y='test',
               GTK_USE_PORTAL='0', NO_AT_BRIDGE='1',
               WLR_RENDER_DRM_DEVICE='/dev/dri/renderD129')
    for k in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
        env.pop(k, None)
    wrapper = base / 'bin'
    wrapper.mkdir()
    (wrapper / 'ghostty').write_text('#!/bin/sh\nexec /usr/bin/ghostty "$@" 2>' + str(LOGS / 'ghostty.log') + '\n')
    (wrapper / 'ghostty').chmod(0o755)
    env['PATH'] = str(wrapper) + ':' + env['PATH']
    swayconfig = base / 'sway.conf'
    swayconfig.write_text('output HEADLESS-1 mode 1440x900\n'
                          'output * bg #655179 solid_color\nseat seat0 fallback true\n'
                          'focus_follows_mouse no\ngaps top 39\nset $mod Mod4\ninclude '
                          + str(ROOT / 'alpine/desktop/.config/sway/local.d/dropdown.conf') + '\n')
    log = (LOGS / 'headless.log').open('w')
    busconfig = base / 'bus.conf'
    busconfig.write_text('<busconfig><type>session</type><listen>unix:path='
                         + str(runtime / 'bus') + '</listen><auth>EXTERNAL</auth>'
                         '<policy context="default"><allow send_destination="*"/>'
                         '<allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
    bus = subprocess.Popen(['dbus-daemon', '--nofork', '--config-file=' + str(busconfig)],
                           env=env, stdout=log, stderr=log)
    wait(lambda: (runtime / 'bus').is_socket())
    env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(runtime / 'bus')
    sway = subprocess.Popen(['sway', '-c', str(swayconfig)], env=env, stdout=log, stderr=log)

    def command(*args):
        r = subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)
        if r.returncode:
            print(r.stdout, r.stderr, flush=True)
        r.check_returncode()
        return r

    def ipc(kind, cmd=None):
        args = ['swaymsg', '-r', '-t', kind]
        if cmd:
            args.append(cmd)
        return json.loads(command(*args).stdout)

    def find(profile='terminal'):
        return api['terminal'](ipc('get_tree'), app_id=api['PROFILES'][profile][0])

    def toggle(profile='terminal'):
        start = time.monotonic()
        command(str(HELPER), profile)
        return round(time.monotonic() - start, 3)

    try:
        sock = wait(lambda: next(runtime.glob('sway-ipc*.sock'), None))
        display = wait(lambda: next((p for p in runtime.glob('wayland-*') if p.is_socket()), None))
        env.update(SWAYSOCK=str(sock), WAYLAND_DISPLAY=display.name)
        cold = toggle()
        node, workspace = wait(find)
        assert node['app_id'] == 'com.mbp-intel.dropdown' and node['visible']
        first_id, first_pid = (node['id'], node['pid'])
        rect = node['rect']
        assert rect == dict(x=43, y=39, width=1354, height=468), rect
        assert node['window_rect']['y'] == 0, node['window_rect']
        hidden_time = toggle()
        hidden, where = find()
        assert where == '__i3_scratch' and (not hidden['visible'])
        show_time = toggle()
        shown, where = find()
        assert shown['id'] == first_id and shown['pid'] == first_pid and shown['focused']
        wait(lambda: 'started subcommand' in (LOGS / 'ghostty.log').read_text())
        time.sleep(1)
        command('wtype', '-d', '20', '-s', '100', 'touch keyboard-ok', '-s', '200', '-k', 'Return', '-s', '300')
        wait(lambda: (home / 'keyboard-ok').exists())
        command('wtype', '-s', '100', '-M', 'ctrl', '-M', 'shift', '-k', 'n', '-m', 'shift', '-m', 'ctrl', '-s', '200')

        def dropdown_count(node):
            return int(node.get('app_id') == api['APP_ID']) + sum(
                dropdown_count(child)
                for child in node.get('nodes', []) + node.get('floating_nodes', []))

        time.sleep(0.5)
        assert dropdown_count(ipc('get_tree')) == 1
        command('grim', str(OUT / 'headless.png'))

        # A dropdown shown on another workspace must arrive on the first toggle.
        # Retain the real Foot and btop processes through moves and hiding.
        home_workspace = next(item['name'] for item in ipc('get_workspaces')
                              if item.get('focused'))
        toggle('monitor')
        monitor, where = find('monitor')
        assert monitor['visible'] and where == home_workspace
        monitor_id, monitor_pid = monitor['id'], monitor['pid']
        assert pathlib.Path(f'/proc/{monitor_pid}/exe').resolve().name == 'foot'
        btop_pid = wait(lambda: monitor_child(monitor_pid))
        workspace_moves = []
        for number in (2, 10):
            ipc('command', f'workspace number {number}')
            toggle('monitor')
            moved, where = find('monitor')
            assert moved['visible'] and moved['focused'] and where == str(number), (
                'one monitor toggle must recall it to the focused workspace', where)
            assert (moved['id'], moved['pid']) == (monitor_id, monitor_pid)
            assert monitor_child(monitor_pid) == btop_pid
            workspace_moves.append({'workspace': where, 'container': moved['id'],
                                    'foot_pid': moved['pid'], 'btop_pid': btop_pid})
            toggle('monitor')
            hidden_monitor, where = find('monitor')
            assert where == '__i3_scratch' and not hidden_monitor['visible']
            toggle('monitor')
            reshown_monitor, where = find('monitor')
            assert reshown_monitor['visible'] and where == str(number)
            assert (reshown_monitor['id'], reshown_monitor['pid']) == (monitor_id, monitor_pid)
            assert monitor_child(monitor_pid) == btop_pid
        command('grim', str(OUT / 'monitor-workspace-ten.png'))
        toggle('monitor')
        # Console recall is independent; the hidden monitor stays alive.
        toggle()
        recalled_console, where = find()
        assert recalled_console['visible'] and where == '10'
        assert (recalled_console['id'], recalled_console['pid']) == (first_id, first_pid)
        assert find('monitor')[1] == '__i3_scratch'
        ipc('command', 'workspace ' + json.dumps(home_workspace))
        toggle()
        recalled_console, where = find()
        assert recalled_console['visible'] and where == home_workspace
        assert (recalled_console['id'], recalled_console['pid']) == (first_id, first_pid)
        assert monitor_child(monitor_pid) == btop_pid

        ipc('command', f'[con_id={first_id}] move scratchpad')
        ipc('command', 'output HEADLESS-1 pos 1440 100')
        toggle()
        offset, _ = find()
        assert offset['rect'] == dict(x=1483, y=139, width=1354, height=468), offset['rect']
        command('wtype', '-d', '20', '-s', '100', 'exit', '-s', '200', '-k', 'Return', '-s', '200')
        wait(lambda: not find())
        reopened_time = toggle()
        reopened, _ = find()
        assert reopened['id'] != first_id
        report = {
            'isolation': 'private HOME, XDG directories, non-activating session bus, headless Sway',
            'app_id': node['app_id'], 'first_container': first_id,
            'reopened_container': reopened['id'], 'geometry': rect,
            'offset_geometry': offset['rect'],
            'checks': {'native_wayland': node['shell'] == 'xdg_shell',
                       'hide_show_preserves_shell': True, 'focused_when_shown': True,
                       'undecorated': True, 'exit_then_reopen': True, 'offset_output': True,
                       'keyboard_input': True, 'new_window_shortcut_unbound': True},
            'workspace_checks': {'monitor_first_toggle_recalls_other_workspace': True,
                                 'monitor_local_toggle_hides': True,
                                 'monitor_retains_foot_and_btop': True,
                                 'console_recall_independent': True},
            'monitor_workspace_moves': workspace_moves,
            'seconds': {'cold_start': cold, 'hide': hidden_time,
                        'show': show_time, 'reopen': reopened_time},
            'screenshot': 'headless.png',
            'monitor_screenshot': 'monitor-workspace-ten.png'}
        (OUT / 'headless.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    except Exception:
        command('grim', str(LOGS / 'failure.png'))
        print('Diagnostic screenshot and logs:', LOGS, flush=True)
        raise
    finally:
        subprocess.run(['swaymsg', 'exit'], env=env, capture_output=True, timeout=5)
        sway.wait(timeout=10)
        bus.terminate()
        bus.wait(timeout=5)
        log.close()
