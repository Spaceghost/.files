"""Fuzzel workspace/window picker, with session-scoped show/toggle/close control."""
import fcntl
import hashlib
import os
from pathlib import Path
import runpy
import socket
import select
import subprocess


def walk(node):
    yield node
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from walk(child)


def workspaces(tree):
    desktops = {num: {'num': num, 'name': f'{num}:STRATA' if num == 6 else f'Desktop {num}',
                   'windows': []}
             for num in range(1, 11)}
    for node in walk(tree):
        if node.get('type') != 'workspace' or node.get('num', -1) < 0:
            continue
        windows = [view for view in walk(node) if view.get('app_id') or view.get('window')]
        desktops[node['num']] = dict(node, windows=windows)
    return [desktops[num] for num in sorted(desktops)]


def focus_command(target):
    if 'id' in target:
        return f'[con_id={int(target["id"])}] focus'
    return f'workspace number {int(target["num"])}'


def menu_entries(tree):
    entries = []
    desktops = workspaces(tree)
    clean = lambda value: ' '.join(str(value or '').split())[:300]
    for desktop in desktops:
        for view in desktop['windows']:
            app = view.get('app_id') or view.get('window_properties', {}).get('class', '')
            label = 'Window · ' + clean(desktop['name']) + ' · ' + clean(app) + ' · ' + clean(view.get('name'))
            entries.append((label, {'id': view['id']}))
    for desktop in desktops:
        count = len(desktop['windows'])
        label = 'Workspace · ' + clean(desktop['name']) + ' · ' + str(count) + (' window' if count == 1 else ' windows')
        entries.append((label, {'num': desktop['num']}))
    return entries


def selected_target(output, entries):
    try:
        index = int(output.strip())
    except (ValueError, TypeError):
        return None
    return entries[index][1] if 0 <= index < len(entries) else None


def main(action='toggle'):
    ipc = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'bin/oldbook-workspaces'))
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    sway = ipc['find_socket'](runtime)
    directory = ipc['prepare_directory'](runtime).parent
    identity = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
    address = directory / ('expo-' + identity + '.sock')
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        try:
            client.sendto(action.encode(), str(address))
            return
        except (FileNotFoundError, ConnectionRefusedError):
            if action == 'close':
                return
    with (directory / ('expo-' + identity + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        address.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.bind(str(address))
            try:
                show(ipc, sway, control)
            finally:
                address.unlink(missing_ok=True)


def show(ipc, sway, control):
    from overlay_theme import read_palette
    palette = read_palette()
    entries = menu_entries(ipc['request'](sway, 4))
    command = ['fuzzel', '--dmenu', '--index', '--namespace', 'oldbook-expo',
               '--prompt', 'Workspaces & windows ❯ ', '--width', '72',
               '--lines', str(min(14, len(entries)))]
    colors = {'background': 'background', 'text': 'foreground', 'prompt': 'muted',
              'input': 'foreground', 'match': 'accent', 'selection': 'border',
              'selection-text': 'foreground', 'selection-match': 'accent', 'border': 'accent'}
    for option, role in colors.items():
        command += ['--' + option + '-color=' + palette[role][1:] + ('fa' if option == 'background' else 'ff')]
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        child.stdin.write('\n'.join(label for label, _ in entries) + '\n')
        child.stdin.close()
        while child.poll() is None:
            ready, _, _ = select.select([control], [], [], .1)
            if ready and control.recv(32) in (b'close', b'toggle'):
                return
        if child.returncode == 0:
            target = selected_target(child.stdout.read(), entries)
            if target is not None:
                ipc['command'](sway, focus_command(target))
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        child.stdout.close()
