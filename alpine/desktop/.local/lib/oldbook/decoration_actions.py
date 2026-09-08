"""Window-specific actions for the workspace strip; never evaluate menu text."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from decoration import focused_child

BIN = Path.home() / '.local/bin'
TERMINALS = ('foot', 'ghostty', 'kitty', 'alacritty', 'wezterm', 'xterm')


def app_name(node):
    return str(node.get('app_id') or node.get('window_properties', {}).get('class') or 'Window')


def clean(value):
    return ' '.join(str(value).split())


def terminal_source(node):
    properties = node.get('window_properties') or {}
    sources = [node.get('app_id'), properties.get('class'), properties.get('instance')]
    pid = node.get('pid')
    if type(pid) is int and pid > 0:
        process = Path('/proc') / str(pid)
        try:
            if process.stat().st_uid == os.getuid():
                sources.append((process / 'exe').resolve(strict=True).name)
        except OSError:
            pass
    return next((name for name in sources if isinstance(name, str)
                 and any(terminal in name.casefold() for terminal in TERMINALS)), None)


def quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def output_contexts(tree):
    result = {}
    for output in tree.get('nodes', []):
        name = output.get('name', '')
        if output.get('type') != 'output' or name.startswith('__'):
            continue
        workspace = focused_child(output)
        if not workspace:
            continue
        context = {'output': name, 'workspace': workspace.get('name', ''),
                   'layout': workspace.get('layout', ''), 'floating': False,
                   'fullscreen': False,
                   'id': None, 'node': {}}
        node = workspace
        while node:
            # Sway's workspace flag is always 1; only focused containers count.
            if node is not workspace and node.get('type') not in ('root', 'output', 'workspace'):
                context['fullscreen'] |= bool(node.get('fullscreen_mode'))
            if node.get('app_id') or node.get('window'):
                context.update(id=node['id'], node=node, title=clean(node.get('name') or app_name(node)),
                               app=app_name(node), sticky=bool(node.get('sticky')))
                break
            child = focused_child(node)
            if child in node.get('floating_nodes', []):
                context['floating'] = True
            if node.get('layout') in ('splith', 'splitv', 'tabbed', 'stacked'):
                context['layout'] = node['layout']
            node = child
        result[name] = context
    return result


def item(label, command=None, **extra):
    return dict(label=label, command=command, **extra)


def window_item(context, label, command):
    identity = context.get('id')
    if type(identity) is not int or identity <= 0:
        return item(label)
    return item(label, ['swaymsg', f'[con_id={identity}] {command}'], wait=True)


def window_items(tree):
    items = []
    def walk(node, workspace=''):
        if node.get('type') == 'workspace':
            workspace = node.get('name', '')
        if node.get('app_id') or node.get('window'):
            label = f'{clean(workspace)}  ·  {clean(node.get("name") or app_name(node))[:75]}'
            items.append(window_item(node, label, 'scratchpad show' if workspace == '__i3_scratch' else 'focus'))
        for child in node.get('nodes', []) + node.get('floating_nodes', []):
            walk(child, workspace)
    walk(tree)
    return items or [item('No open windows')]


def workspace_names(tree):
    names = []
    def walk(node):
        if node.get('type') == 'workspace' and not node.get('name', '').startswith('__'):
            names.append(node['name'])
        for child in node.get('nodes', []) + node.get('floating_nodes', []):
            walk(child)
    walk(tree)
    return list(dict.fromkeys(names))


def launchers(context):
    choices = [('Terminal', 'utilities-terminal-symbolic', ['foot']),
               ('Files', 'system-file-manager-symbolic', ['thunar']),
               ('Browser', 'web-browser-symbolic', ['firefox']),
               ('Applications…', 'view-app-grid-symbolic', [str(BIN / 'oldbook-menu')])]
    return [item(label, command, icon=icon, workspace=context.get('workspace'))
            for label, icon, command in choices if shutil.which(command[0])]


def menu_items(context, tree):
    items = []
    if context.get('id'):
        floating = context['floating']
        items += [window_item(context, 'Tile this window' if floating else 'Float this window',
                              'floating disable' if floating else 'floating enable'),
                  window_item(context, 'Leave fullscreen' if context['fullscreen'] else 'Fullscreen',
                              'fullscreen disable' if context['fullscreen'] else 'fullscreen enable')]
        if floating:
            items += [window_item(context, 'Center on screen', 'move position center'),
                      window_item(context, 'Unpin from other workspaces' if context.get('sticky')
                                  else 'Pin across workspaces',
                                  'sticky disable' if context.get('sticky') else 'sticky enable')]
        else:
            layouts = [('Side by side', 'splith'), ('Above and below', 'splitv'),
                       ('Tabbed', 'tabbed'), ('Stacked', 'stacking')]
            items.append(item('Tiling layout', children=[
                window_item(context, label, 'layout ' + layout) for label, layout in layouts]))
        moves = [window_item(context, clean(name), 'move container to workspace ' + quote(name))
                 for name in workspace_names(tree) if name != context['workspace']]
        moves += [window_item(context, 'Next workspace', 'move container to workspace next'),
                  window_item(context, 'Previous workspace', 'move container to workspace prev')]
        items += [item('Move to workspace', children=moves),
                  window_item(context, 'Put in scratchpad', 'move scratchpad')]
        if shutil.which('wl-copy'):
            items.append(item('Copy window title', ['wl-copy'], input=context.get('title', ''), wait=True))
        items.append(None)
    items += [item('Switch window', children=window_items(tree)),
              item('Switch workspace', children=[
                  item(clean(name), ['swaymsg', 'workspace --no-auto-back-and-forth ' + quote(name)], wait=True)
                  for name in workspace_names(tree)]),
              item('Bring back scratchpad', ['swaymsg', 'scratchpad show'], wait=True),
              item('Open', children=launchers(context)), None,
              item('Strip appearance…', [str(BIN / 'oldbook-decoration-settings')]),
              item('Move strip to right edge' if context.get('edge') == 'bottom' else 'Move strip to bottom',
                   [str(BIN / 'oldbook-decoration'), 'right' if context.get('edge') == 'bottom' else 'bottom'])]
    if context.get('id'):
        items += [None, window_item(context, 'Close this window', 'kill')]
    return items


def read_command(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def application_items(context):
    """Resolve optional actions only when a user opens this window's menu."""
    node = context.get('node', {})
    actions = []
    terminal = terminal_source(node)
    if terminal:
        from app_identity import ApplicationResolver
        # Custom app IDs (for example agent terminals) still use their actual
        # terminal executable for process/tmux discovery.
        source_node = dict(node, app_id=terminal)
        identity = ApplicationResolver().resolve_all([source_node]).get(node.get('id'), {})
        pane = identity.get('tmux_pane', '')
        cwd = None
        directory_kind = 'launch directory'
        if re.fullmatch(r'%[0-9]+', pane):
            details = read_command(['tmux', 'display-message', '-p', '-t', pane,
                                    '#{pane_pid}\n#{pane_current_path}']).split('\n', 1)
            if len(details) == 2 and details[0].isdigit():
                cwd = details[1]
                directory_kind = 'pane directory'
                guard = {'pane': pane, 'pid': details[0]}
                for label, command in (
                    ('Split pane side by side', ['split-window', '-h']),
                    ('Split pane above and below', ['split-window', '-v']),
                    ('Zoom / unzoom pane', ['resize-pane', '-Z']),
                    ('Pane scrollback', ['copy-mode'])):
                    argv = ['tmux', *command, '-t', pane]
                    if command[0] == 'split-window':
                        argv += ['-c', cwd]
                    actions.append(item(label, argv, wait=True, tmux_guard=guard))
        if not cwd and type(node.get('pid')) is int:
            try:
                cwd = str((Path('/proc') / str(node['pid']) / 'cwd').resolve(strict=True))
            except OSError:
                pass
        if cwd and Path(cwd).is_dir():
            if shutil.which('foot'):
                actions.append(item('New terminal in ' + directory_kind, ['foot', '--working-directory=' + cwd],
                                    workspace=context.get('workspace')))
            if shutil.which('thunar'):
                actions.append(item('Open ' + directory_kind + ' in Files', ['thunar', cwd], workspace=context.get('workspace')))
    actions.extend(media_items(node))
    return actions


def media_items(node):
    """Offer MPRIS controls only for a player owned by this window's process."""
    if type(node.get('pid')) is not int or not shutil.which('playerctl'):
        return []
    from gi.repository import Gio, GLib
    actions = []
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        for player in read_command(['playerctl', '--list-all']).splitlines():
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', player):
                continue
            service = 'org.mpris.MediaPlayer2.' + player
            try:
                pid = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                    'org.freedesktop.DBus', 'GetConnectionUnixProcessID', GLib.Variant('(s)', (service,)),
                    GLib.VariantType.new('(u)'), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
                if pid != node['pid']:
                    continue
                properties = bus.call_sync(service, '/org/mpris/MediaPlayer2',
                    'org.freedesktop.DBus.Properties', 'GetAll',
                    GLib.Variant('(s)', ('org.mpris.MediaPlayer2.Player',)),
                    GLib.VariantType.new('(a{sv})'), Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
                if not properties.get('CanControl'):
                    continue
                playing = properties.get('PlaybackStatus') == 'Playing'
                options = [('Previous track', 'previous', properties.get('CanGoPrevious')),
                           ('Pause' if playing else 'Play', 'pause' if playing else 'play',
                            properties.get('CanPause' if playing else 'CanPlay')),
                           ('Next track', 'next', properties.get('CanGoNext'))]
                actions.append(item('Media · ' + player, children=[
                    item(label, ['playerctl', '--player=' + player, verb], wait=True)
                    for label, verb, enabled in options if enabled]))
            except GLib.Error:
                continue
    except GLib.Error:
        pass
    return actions


def execute(action):
    """Run from a worker thread; GUI launches detach, short control commands finish."""
    command = action.get('command')
    if not command:
        return
    try:
        guard = action.get('tmux_guard')
        if guard and read_command(['tmux', 'display-message', '-p', '-t', guard['pane'],
                                   '#{pane_pid}']) != guard['pid']:
            raise RuntimeError('That terminal pane has closed. Open the menu again.')
        workspace = action.get('workspace')
        if workspace:
            subprocess.run(['swaymsg', 'workspace --no-auto-back-and-forth ' + quote(workspace)],
                           check=True, capture_output=True, timeout=2)
        if action.get('wait'):
            result = subprocess.run(command, input=action.get('input'), text=True,
                                    capture_output=True, timeout=5)
            if result.returncode:
                raise RuntimeError('This action is no longer available. Open the menu again.')
        else:
            subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        try:
            subprocess.run(['notify-send', '--app-name=Workspace strip', 'Window action unavailable',
                            str(error)[:200]], capture_output=True, timeout=2)
        except (OSError, subprocess.SubprocessError):
            pass
