"""Collect read-only contextual shortcuts from Sway, tmux, and profiles.

The optional local profile file defaults to
``~/.config/oldbook/shortcuts.json``. Its schema is::

    {
      "profiles": {
        "profile-id": {
          "name": "Display name",
          "aliases": ["wayland.app.id", "X11Class"],
          "coverage": "Partial local profile",
          "rows": [
            {"key": "Ctrl+S", "description": "Save"}
          ]
        }
      }
    }

Names, aliases, keys, and descriptions must be single-line strings. Coverage
must begin with ``Partial``; local profiles cannot claim universal coverage.
At most 64 profiles and 100 rows per profile are accepted, and the file is
limited to 256 KiB. The collector reads configuration and process names only.
It never reads process arguments, terminal contents, or scrollback, and it
never executes a command found in Sway or tmux configuration.
"""
from collections import OrderedDict
import glob
import json
import os
from pathlib import Path
import re
import shlex
import socket
import stat
import struct
import subprocess

from .shortcut_profiles import PROFILES, SYSTEM_ROWS, TERMINAL_ROWS


_CONTROL = re.compile(r'[\x00-\x1f\x7f]+')
_VARIABLE = re.compile(r'\$[A-Za-z_][A-Za-z0-9_]*')
_PANE_ID = re.compile(r'%[0-9]+')
_SESSION_ID = re.compile(r'\$[0-9]+')
_WINDOW_ID = re.compile(r'@[0-9]+')
_SHELLS = {'ash', 'bash', 'dash', 'fish', 'sh', 'zsh'}
_TERMINALS = {'foot', 'footclient'}


def _clean(value, limit):
    if not isinstance(value, str):
        return ''
    return ' '.join(_CONTROL.sub(' ', value).split())[:limit].strip()


def _source_key(value):
    return _clean(value, 128).casefold().rsplit('/', 1)[-1]


def _profile_index(profiles):
    result = {}
    for profile_id, profile in profiles.items():
        for alias in (profile_id, *profile['aliases']):
            result[_source_key(alias)] = profile
    return result


def _profile_section(profile):
    return {
        'title': f"{profile['name']} shortcuts",
        'coverage': profile.get('coverage', 'Partial documented baseline'),
        'rows': [
            {'key': key, 'description': description}
            for key, description in profile['rows']
        ],
    }


class ShortcutProvider:
    """Return one bounded, privacy-preserving shortcut snapshot."""

    GET_TREE = 4
    GET_CONFIG = 9
    GET_BINDING_STATE = 12
    GET_VERSION = 7
    TMUX_CLIENT_FORMAT = '#{client_pid}\t#{session_id}\t#{window_id}'
    TMUX_PANE_FORMAT = (
        '#{session_id}\t#{window_id}\t#{pane_id}\t#{pane_active}\t'
        '#{q:pane_current_command}\t#{pane_in_mode}\t#{q:pane_mode}'
    )
    _IPC_MAGIC = b'i3-ipc'
    _MAX_IPC = 2 * 1024 * 1024
    _MAX_COMMAND = 512 * 1024
    _TIMEOUT = 0.75

    def __init__(self, socket_path, profiles_path=None):
        self.socket_path = os.fspath(socket_path)
        self._profiles_explicit = profiles_path is not None
        if profiles_path is None:
            profiles_path = Path.home() / '.config/oldbook/shortcuts.json'
        self.profiles_path = Path(profiles_path).expanduser()

    def snapshot(self):
        custom_profiles, profile_error = self._load_custom_profiles()
        profiles = dict(PROFILES)
        profiles.update(custom_profiles)
        index = _profile_index(profiles)

        tree = None
        try:
            reply = self._sway_request(self.GET_TREE)
            if isinstance(reply, dict):
                tree = reply
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
            tree = None
        window, output = self._focused_view(tree)

        source = self._window_source(window)
        identity_source = source
        terminal_source = source if _source_key(source) in _TERMINALS else None
        tmux_context = None
        if terminal_source and window:
            identity_source, tmux_context = self._terminal_identity(window, source)

        profile = index.get(_source_key(identity_source))
        if profile:
            app = profile['name']
            sections = [_profile_section(profile)]
        else:
            app = _clean(identity_source, 80) or 'Application'
            sections = [{
                'title': f'{app} shortcuts',
                'coverage': 'Unavailable: no shortcut profile',
                'rows': [],
            }]

        sections.append(self._sway_section())
        if terminal_source and _source_key(identity_source) not in _TERMINALS:
            terminal_profile = index.get(_source_key(terminal_source))
            terminal_name = terminal_profile['name'] if terminal_profile else 'Terminal'
            sections.append({
                'title': f'{terminal_name} terminal',
                'coverage': 'Partial documented baseline',
                'rows': [
                    {'key': key, 'description': description}
                    for key, description in TERMINAL_ROWS
                ],
            })
        if tmux_context:
            sections.append(self._tmux_section(tmux_context))
        sections.append({
            'title': 'System controls',
            'coverage': 'Partial configured controls',
            'rows': [
                {'key': key, 'description': description}
                for key, description in SYSTEM_ROWS
            ],
        })
        if profile_error:
            sections.append({
                'title': 'Local shortcut profiles',
                'coverage': f'Unavailable: {profile_error}',
                'rows': [],
            })
        return {'app': app, 'output': output, 'sections': sections}

    def _sway_request(self, message_type):
        request = self._IPC_MAGIC + struct.pack('<II', 0, message_type)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self._TIMEOUT)
            connection.connect(self.socket_path)
            connection.sendall(request)
            header = self._recv_exact(connection, 14)
            if header[:6] != self._IPC_MAGIC:
                raise ValueError('invalid Sway IPC magic')
            length, response_type = struct.unpack('<II', header[6:])
            if length > self._MAX_IPC or response_type != message_type:
                raise ValueError('invalid Sway IPC response')
            payload = self._recv_exact(connection, length)
        return json.loads(payload.decode('utf-8'))

    @staticmethod
    def _recv_exact(connection, length):
        chunks = []
        remaining = length
        while remaining:
            chunk = connection.recv(min(remaining, 65536))
            if not chunk:
                raise OSError('short Sway IPC response')
            chunks.append(chunk)
            remaining -= len(chunk)
        return b''.join(chunks)

    def _run_command(self, argv):
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return ''
        if completed.returncode != 0:
            return ''
        return completed.stdout[:self._MAX_COMMAND]

    @staticmethod
    def _focused_view(tree):
        best = None

        def visit(node, output, depth):
            nonlocal best
            if not isinstance(node, dict):
                return
            if node.get('type') == 'output' and node.get('name') not in {
                    '__i3', '__sway'}:
                output = _clean(node.get('name'), 80) or None
            properties = node.get('window_properties')
            is_view = bool(
                node.get('app_id')
                or (isinstance(properties, dict)
                    and (properties.get('class') or properties.get('instance')))
            )
            if node.get('focused') is True and is_view:
                candidate = (depth, node, output)
                if best is None or depth > best[0]:
                    best = candidate
            for collection in ('nodes', 'floating_nodes'):
                children = node.get(collection)
                if isinstance(children, list):
                    for child in children:
                        visit(child, output, depth + 1)

        if isinstance(tree, dict):
            visit(tree, None, 0)
        return (best[1], best[2]) if best else (None, None)

    @staticmethod
    def _window_source(window):
        if not isinstance(window, dict):
            return ''
        properties = window.get('window_properties')
        properties = properties if isinstance(properties, dict) else {}
        for source in (window.get('app_id'), properties.get('class'),
                       properties.get('instance')):
            source = _clean(source, 128)
            if source:
                return source
        return ''

    def _sway_section(self):
        try:
            config_reply = self._sway_request(self.GET_CONFIG)
            state_reply = self._sway_request(self.GET_BINDING_STATE)
            version_reply = self._sway_request(self.GET_VERSION)
            config = config_reply.get('config') if isinstance(config_reply, dict) else None
            mode = state_reply.get('name') if isinstance(state_reply, dict) else None
            main_name = (version_reply.get('loaded_config_file_name')
                         if isinstance(version_reply, dict) else None)
            if (not isinstance(config, str) or not isinstance(mode, str)
                    or not isinstance(main_name, str) or not main_name
                    or len(main_name) > 4096 or _CONTROL.search(main_name)):
                raise ValueError('malformed Sway reply')
            mode = _clean(mode, 80) or 'default'
            config, included = self._expand_sway_includes(config, Path(main_name))
            rows = self._parse_sway_bindings(config, mode)
            coverage = 'Loaded main config · active mode'
            if included:
                coverage = ('Loaded main config + current included files · '
                            'active mode; reload after edits')
            return {
                'title': f'Sway — {mode}',
                'coverage': coverage,
                'rows': rows,
            }
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
            return {
                'title': 'Sway shortcuts',
                'coverage': 'Unavailable: compositor query failed',
                'rows': [],
            }

    @classmethod
    def _expand_sway_includes(cls, config, main_path):
        """Inline current include files without shell evaluation.

        GET_CONFIG is the loaded main text on current Sway releases, while
        include files can only be read from disk. The caller labels that mixed
        provenance and tells users to reload after editing an include.
        """
        variables = {'$HOME': str(Path.home())}
        limits = {'files': 0, 'bytes': len(config.encode('utf-8', 'replace'))}
        included = False
        seen = set()

        def expand(text, source_path, depth):
            nonlocal included
            output = []
            for raw_line in cls._logical_lines(text):
                try:
                    raw_tokens = shlex.split(raw_line, comments=False, posix=True)
                except ValueError:
                    output.append(raw_line)
                    continue
                if (len(raw_tokens) >= 3 and raw_tokens[0] == 'set'
                        and raw_tokens[1].startswith('$')):
                    variables[raw_tokens[1]] = cls._expand_variables(
                        ' '.join(raw_tokens[2:]), variables)
                    output.append(raw_line)
                    continue
                expanded_line = cls._expand_variables(raw_line, variables)
                try:
                    tokens = shlex.split(expanded_line, comments=False, posix=True)
                except ValueError:
                    output.append(raw_line)
                    continue
                if not tokens or tokens[0] != 'include' or depth >= 16:
                    output.append(raw_line)
                    continue
                for pattern in tokens[1:]:
                    pattern = cls._expand_variables(pattern, variables)
                    pattern = os.path.expanduser(pattern)
                    candidate = Path(pattern)
                    if not candidate.is_absolute():
                        candidate = source_path.parent / candidate
                    for matched_name in sorted(glob.glob(os.fspath(candidate))):
                        if limits['files'] >= 128:
                            break
                        try:
                            matched = Path(matched_name).resolve(strict=True)
                            info = matched.stat()
                            if (matched in seen or not stat.S_ISREG(info.st_mode)
                                    or info.st_size > 256 * 1024
                                    or limits['bytes'] + info.st_size > 2 * 1024 * 1024):
                                continue
                            with matched.open('rb') as stream:
                                raw_contents = stream.read(256 * 1024 + 1)
                            if (len(raw_contents) > 256 * 1024
                                    or limits['bytes'] + len(raw_contents) > 2 * 1024 * 1024):
                                continue
                            contents = raw_contents.decode('utf-8')
                        except (OSError, UnicodeError):
                            continue
                        limits['files'] += 1
                        limits['bytes'] += len(raw_contents)
                        seen.add(matched)
                        included = True
                        output.extend(expand(contents, matched, depth + 1))
            return output

        try:
            main_path = main_path.expanduser().resolve(strict=False)
        except OSError:
            main_path = main_path.expanduser()
        seen.add(main_path)
        lines = expand(config, main_path, 0)
        return '\n'.join(lines), included

    @classmethod
    def _parse_sway_bindings(cls, config, active_mode):
        variables = {}
        mode_stack = ['default']
        group_stack = []
        effective = OrderedDict()
        for raw_line in cls._logical_lines(config):
            try:
                raw_tokens = shlex.split(raw_line, comments=False, posix=True)
            except ValueError:
                continue
            if (len(raw_tokens) >= 3 and raw_tokens[0] == 'set'
                    and raw_tokens[1].startswith('$')):
                variables[raw_tokens[1]] = cls._expand_variables(
                    ' '.join(raw_tokens[2:]), variables)
                continue
            line = cls._expand_variables(raw_line, variables).strip()
            if not line:
                continue
            if line == '}':
                if group_stack:
                    group_stack.pop()
                elif len(mode_stack) > 1:
                    mode_stack.pop()
                continue
            try:
                tokens = shlex.split(line, comments=False, posix=True)
            except ValueError:
                continue
            if not tokens:
                continue
            if tokens[0] == 'mode' and tokens[-1] == '{' and len(tokens) >= 3:
                mode_stack.append(' '.join(tokens[1:-1]))
                continue
            if tokens[-1] == '{' and tokens[0] in {
                    'bindsym', 'bindcode', 'unbindsym', 'unbindcode'}:
                group_stack.append(tokens[:-1])
                continue
            if group_stack and tokens[0] not in {
                    'bindsym', 'bindcode', 'unbindsym', 'unbindcode'}:
                tokens = [*group_stack[-1], *tokens]
            if tokens[0] not in {'bindsym', 'bindcode', 'unbindsym', 'unbindcode'}:
                continue
            mode = mode_stack[-1]
            parsed = cls._parse_binding(tokens, mode)
            if parsed is None:
                continue
            identity, row, unbind = parsed
            if unbind:
                effective.pop(identity, None)
            else:
                effective[identity] = row
        return [row for identity, row in effective.items() if identity[0] == active_mode]

    @classmethod
    def _logical_lines(cls, config):
        pending = ''
        for physical in config.splitlines():
            line = cls._strip_comment(physical).strip()
            if not line:
                continue
            if line.endswith('\\'):
                pending += line[:-1].rstrip() + ' '
                continue
            line = pending + line
            pending = ''
            yield line
        if pending:
            yield pending.rstrip()

    @staticmethod
    def _strip_comment(line):
        quote = None
        escaped = False
        for index, character in enumerate(line):
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif quote:
                if character == quote:
                    quote = None
            elif character in "'\"":
                quote = character
            elif character == '#':
                return line[:index]
        return line

    @staticmethod
    def _expand_variables(line, variables):
        for _ in range(10):
            expanded = _VARIABLE.sub(lambda match: variables.get(match.group(), match.group()), line)
            if expanded == line:
                break
            line = expanded
        return line

    @classmethod
    def _parse_binding(cls, tokens, mode):
        command_type = tokens[0]
        unbind = command_type.startswith('unbind')
        bind_type = command_type[2:] if unbind else command_type
        flags = {
            'release': False,
            'locked': False,
            'inhibited': False,
            'whole-window': False,
            'border': False,
            'exclude-titlebar': False,
            'to-code': False,
            'input-device': '',
        }
        index = 1
        while index < len(tokens) and tokens[index].startswith('--'):
            option = tokens[index][2:]
            if option.startswith('input-device='):
                flags['input-device'] = option.split('=', 1)[1]
            elif option == 'input-device' and index + 1 < len(tokens):
                index += 1
                flags['input-device'] = tokens[index]
            elif option in flags:
                flags[option] = True
            index += 1
        if index >= len(tokens):
            return None
        key = tokens[index]
        command = ' '.join(tokens[index + 1:])
        identity = (
            mode, bind_type, cls._binding_key_identity(key, bind_type),
            flags['release'], flags['locked'], flags['inhibited'],
            flags['whole-window'], flags['border'], flags['exclude-titlebar'],
            flags['to-code'], flags['input-device'],
        )
        display_key = cls._sway_key(key, bind_type)
        if flags['release']:
            display_key += ' (release)'
        description = cls._sway_description(command)
        if mode == 'window-switcher' and command == 'mode default':
            description = 'Leave the overview and return to your window'
        row = {'key': display_key, 'description': description}
        return identity, row, unbind

    @staticmethod
    def _binding_key_identity(key, bind_type):
        if bind_type == 'bindcode':
            return key
        modifier_aliases = {
            'shift': 'Shift', 'control': 'Ctrl', 'ctrl': 'Ctrl',
            'mod1': 'Alt', 'alt': 'Alt', 'mod4': 'Super', 'super': 'Super',
            'mod2': 'Mod2', 'mod3': 'Mod3', 'mod5': 'Mod5',
        }
        order = {'Ctrl': 0, 'Alt': 1, 'Shift': 2, 'Super': 3,
                 'Mod2': 4, 'Mod3': 5, 'Mod5': 6}
        modifiers = []
        keys = []
        for part in key.split('+'):
            modifier = modifier_aliases.get(part.casefold())
            if modifier:
                modifiers.append(modifier)
            else:
                keys.append(part)
        modifiers.sort(key=lambda item: order[item])
        return tuple(modifiers), tuple(keys)

    @staticmethod
    def _sway_key(key, bind_type):
        if bind_type == 'bindcode':
            return f'code {_clean(key, 40)}'
        names = {
            'mod4': 'Super', 'mod1': 'Alt', 'control': 'Ctrl', 'ctrl': 'Ctrl',
            'shift': 'Shift', 'return': 'Enter', 'prior': 'PageUp',
            'next': 'PageDown', 'space': 'Space',
            'xf86launcha': 'Mission Control (F3)',
            'xf86launchb': 'Launchpad (F4)',
        }
        parts = key.split('+')
        normalized = []
        for part in parts:
            replacement = names.get(part.casefold())
            if replacement:
                normalized.append(replacement)
            elif len(part) == 1 and part.isalpha():
                normalized.append(part.upper())
            else:
                normalized.append(_clean(part, 40))
        return '+'.join(normalized)

    @staticmethod
    def _sway_description(command):
        command = _clean(command, 180)
        if re.fullmatch(r'exec (?:[^ ]*/)?oldbook-carousel cancel, mode ["\']?default["\']?', command):
            return 'Leave the overview and return to your window'
        if re.fullmatch(r'exec (?:[^ ]*/)?oldbook-carousel cancel, mode ["\']?default["\']?, exec (?:[^ ]*/)?oldbook-menu', command):
            return 'Leave the overview and open the application launcher'
        if re.fullmatch(r'mode ["\']?default["\']?, exec (?:[^ ]*/)?oldbook-menu', command):
            return 'Leave the overview and open the application launcher'
        if command == 'kill':
            return 'Close focused window'
        if command == 'reload':
            return 'Reload Sway configuration'
        if command == 'splith':
            return 'Split horizontally'
        if command == 'splitv':
            return 'Split vertically'
        if command == 'fullscreen toggle' or command == 'fullscreen':
            return 'Toggle fullscreen'
        if command == 'floating toggle':
            return 'Toggle floating'
        if command == 'focus mode_toggle':
            return 'Switch tiling / floating focus'
        if command == 'workspace back_and_forth':
            return 'Return to previous workspace'
        match = re.fullmatch(r'workspace number (?:"([0-9]+)(?:: [^"]+)?"|([0-9]+))', command)
        if match:
            return f'Switch to workspace {match.group(1) or match.group(2)}'
        match = re.fullmatch(r'move container to workspace number (?:"([0-9]+)(?:: [^"]+)?"|([0-9]+))', command)
        if match:
            return f'Move window to workspace {match.group(1) or match.group(2)}'
        match = re.fullmatch(r'focus (left|right|up|down|parent|child)', command)
        if match:
            return f"Focus {match.group(1)}"
        match = re.fullmatch(r'move (left|right|up|down)', command)
        if match:
            return f"Move window {match.group(1)}"
        match = re.match(r'resize (shrink|grow) (width|height) ([0-9]+) px(?: .*)?$', command)
        if match:
            verb = 'Shrink' if match.group(1) == 'shrink' else 'Grow'
            return f'{verb} {match.group(2)} by {match.group(3)} px'
        match = re.fullmatch(r'mode (.+)', command)
        if match:
            target = match.group(1).strip('"\'')
            return 'Return to default mode' if target == 'default' else f'Enter {target} mode'
        if command.startswith('exec '):
            try:
                arguments = shlex.split(command[5:])
            except ValueError:
                arguments = []
            if arguments:
                executable = arguments[0].rsplit('/', 1)[-1]
                action = tuple(arguments[1:])
                known_exec = {
                    ('foot',): 'Open terminal',
                    ('oldbook-dropdown',): 'Toggle drop-down console',
                    ('oldbook-dropdown', 'monitor'): 'Toggle system monitor',
                    ('oldbook-center',): 'Center and raise focused window',
                    ('oldbook-resize', 'near-full'): 'Give this window room: float, nearly fill, and center',
                    ('oldbook-carousel', 'next', '--modifier', 'super'): 'Next recent window — hold Super to browse, release to land',
                    ('oldbook-carousel', 'previous', '--modifier', 'super'): 'Previous window — Shift reverses; Escape brings you back',
                    ('oldbook-carousel', 'next', '--modifier', 'alt'): 'Next recent window — hold Alt to browse, release to land',
                    ('oldbook-carousel', 'previous', '--modifier', 'alt'): 'Previous window — Shift reverses; Escape brings you back',
                    ('oldbook-carousel', 'show'): 'Browse every workspace: choose a window, then Enter to land',
                    ('oldbook-showdesktop', 'restore-or-carousel'): 'Bring hidden windows home, or browse every window',
                    ('oldbook-control',): 'Open system controls',
                    ('oldbook-lock',): 'Lock session',
                    ('oldbook-menu',): 'Open application launcher',
                    ('oldbook-wallpaper', 'pick'): 'Choose wallpaper',
                    ('oldbook-wallpaper', 'next'): 'Next wallpaper',
                    ('oldbook-wallpaper', 'prev'): 'Previous wallpaper',
                    ('oldbook-wallpaper', 'pause'): 'Pause or resume wallpaper rotation',
                    ('oldbook-workspaces', 'ai-next'): 'Focus next AI workspace',
                    ('oldbook-workspaces', 'ai-menu'): 'Choose AI workspace',
                    ('swaync-client', '-t'): 'Toggle notification center',
                    ('oldbook-screenshot', 'full'): 'Capture full screen',
                    ('oldbook-screenshot', 'area'): 'Capture selected area',
                    ('oldbook-screenshot', 'window'): 'Capture focused window',
                    ('oldbook-audio', 'up'): 'Increase volume',
                    ('oldbook-audio', 'down'): 'Decrease volume',
                    ('oldbook-audio', 'mute'): 'Toggle audio mute',
                    ('oldbook-audio', 'mic-mute'): 'Toggle microphone mute',
                    ('oldbook-brightness', 'up'): 'Increase brightness',
                    ('oldbook-brightness', 'down'): 'Decrease brightness',
                    ('oldbook-keyboard-backlight', 'up'): 'Brighten the keys — adjusts the peak while breathing',
                    ('oldbook-keyboard-backlight', 'down'): 'Dim the keys — all the way down turns breathing off',
                    ('oldbook-keyboard-backlight', 'toggle'): 'Toggle keyboard backlight',
                    ('oldbook-keyboard-backlight', 'breathe'): 'Let the whole keyboard breathe — press again for steady light',
                    ('oldbook-keyboard-backlight', 'steady'): 'Hold that glow — stop breathing at your chosen brightness',
                    ('oldbook-keyboard-backlight', 'typing'): 'Pulse the keyboard with each keypress',
                    ('oldbook-keyboard-backlight', 'typing-dark'): 'Start bright, darken as you keep typing',
                    ('oldbook-keyboard-backlight', 'typing-wpm'): 'Pulse only during sustained fast typing',
                    ('oldbook-keyboard-backlight', 'typing-dark-wpm'): 'Darken only during sustained fast typing',
                    ('oldbook-keyboard-backlight', 'ambient'): 'Follow the room light — bright keys in the dark, off in daylight',
                    ('oldbook-keyboard-backlight', 'breathe-air'): 'Breathe on air — every keystroke deepens and quickens the breath',
                    ('oldbook-keyboard-backlight', 'last-breath'): 'One last keyboard breath, then dark until you return',
                    ('oldbook-idle', 'dim'): 'Ease the display down before the lock',
                    ('oldbook-idle', 'undim'): 'Bring the display and keyboard light back',
                }
                label = known_exec.get((executable, *action))
                if label:
                    return label
                if executable == 'swaynag':
                    return 'Open logout confirmation'
        return command or 'No command'

    def _process_snapshot(self):
        processes = {}
        proc_root = Path('/proc')
        try:
            entries = list(proc_root.iterdir())
        except OSError:
            return processes
        uid = os.getuid()
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != uid:
                    continue
                raw_stat = (entry / 'stat').read_text(errors='replace')
                comm = (entry / 'comm').read_text(errors='replace')
            except OSError:
                continue
            close = raw_stat.rfind(')')
            fields = raw_stat[close + 1:].split() if close >= 0 else []
            if len(fields) < 6:
                continue
            try:
                pid = int(entry.name)
                processes[pid] = {
                    'pid': pid,
                    'ppid': int(fields[1]),
                    'pgrp': int(fields[2]),
                    'tty': int(fields[4]),
                    'tpgid': int(fields[5]),
                    'comm': _clean(comm, 64),
                }
            except ValueError:
                continue
        return processes

    @staticmethod
    def _descendants(root_pid, processes):
        children = {}
        for process in processes.values():
            children.setdefault(process.get('ppid'), []).append(process.get('pid'))
        result = {root_pid: 0}
        pending = [root_pid]
        while pending:
            parent = pending.pop()
            for child in children.get(parent, ()):
                if not isinstance(child, int) or child in result:
                    continue
                result[child] = result[parent] + 1
                pending.append(child)
        return result

    def _terminal_identity(self, window, terminal_source):
        pid = window.get('pid')
        if not isinstance(pid, int) or isinstance(pid, bool):
            return terminal_source, None
        processes = self._process_snapshot()
        descendants = self._descendants(pid, processes)
        clients = self._tmux_clients(self._run_command([
            'tmux', 'list-clients', '-F', self.TMUX_CLIENT_FORMAT,
        ]))
        panes = self._tmux_panes(self._run_command([
            'tmux', 'list-panes', '-a', '-F', self.TMUX_PANE_FORMAT,
        ]))
        displayed = [
            (descendants[client_pid], client_pid, target)
            for client_pid, target in clients.items()
            if client_pid in descendants
            and processes.get(client_pid, {}).get('tty')
            and processes.get(client_pid, {}).get('tpgid', -1) > 0
            and processes.get(client_pid, {}).get('pgrp')
                == processes.get(client_pid, {}).get('tpgid')
        ]
        if displayed:
            _, _, (session, window_id) = max(displayed)
            active = [
                pane for pane in panes
                if pane['session'] == session
                and pane['window'] == window_id
                and pane['active']
            ]
            if active:
                pane = max(active, key=lambda item: item['pane_id'])
                return pane['command'] or terminal_source, pane

        foreground = []
        for child_pid, depth in descendants.items():
            if child_pid == pid:
                continue
            process = processes.get(child_pid, {})
            if (process.get('tty') and process.get('tpgid', -1) > 0
                    and process.get('pgrp') == process.get('tpgid')):
                foreground.append((depth, child_pid, process.get('comm', '')))
        if foreground:
            _, _, command = max(foreground)
            return command or terminal_source, None
        return terminal_source, None

    @staticmethod
    def _tmux_clients(output):
        clients = {}
        for line in output.splitlines():
            fields = line.split('\t')
            if len(fields) != 3:
                continue
            try:
                pid = int(fields[0])
            except ValueError:
                continue
            if _SESSION_ID.fullmatch(fields[1]) and _WINDOW_ID.fullmatch(fields[2]):
                clients[pid] = (fields[1], fields[2])
        return clients

    @staticmethod
    def _tmux_unquote(value):
        result = []
        escaped = False
        for character in value:
            if escaped:
                result.append(' ' if character in 'nrt' else character)
                escaped = False
            elif character == '\\':
                escaped = True
            else:
                result.append(character)
        if escaped:
            result.append('\\')
        return _clean(''.join(result), 128)

    @classmethod
    def _tmux_panes(cls, output):
        panes = []
        for line in output.splitlines():
            fields = line.split('\t', 6)
            if len(fields) != 7:
                continue
            session, window, pane_id, active, command, in_mode, pane_mode = fields
            if not (_SESSION_ID.fullmatch(session) and _WINDOW_ID.fullmatch(window)
                    and _PANE_ID.fullmatch(pane_id)):
                continue
            try:
                active_value = bool(int(active))
                in_mode_value = bool(int(in_mode))
            except ValueError:
                continue
            panes.append({
                'session': session,
                'window': window,
                'pane_id': pane_id,
                'active': active_value,
                'command': cls._tmux_unquote(command),
                'in_mode': in_mode_value,
                'pane_mode': cls._tmux_unquote(pane_mode),
            })
        return panes

    def _tmux_section(self, pane):
        prefix = _clean(self._run_command([
            'tmux', 'show-options', '-v', '-t', pane['session'], 'prefix',
        ]), 32) or 'C-b'
        prefix_label = self._tmux_key(prefix)
        rows = self._tmux_rows(
            self._run_command(['tmux', 'list-keys', '-T', 'prefix']),
            prefix_label,
            copy_mode=False,
        )
        if pane.get('in_mode') and 'copy-mode' in pane.get('pane_mode', ''):
            mode_keys = _clean(self._run_command([
                'tmux', 'show-options', '-wv', '-t', pane['window'], 'mode-keys',
            ]), 16)
            if mode_keys in {'vi', 'emacs'}:
                table = 'copy-mode-vi' if mode_keys == 'vi' else 'copy-mode'
                rows.extend(self._tmux_rows(
                    self._run_command(['tmux', 'list-keys', '-T', table]),
                    prefix_label,
                    copy_mode=True,
                ))
        return {
            'title': f'tmux ({prefix_label})',
            'coverage': 'Live effective bindings',
            'rows': rows[:100],
        }

    @classmethod
    def _tmux_rows(cls, output, prefix, copy_mode):
        rows = []
        for line in output.splitlines()[:200]:
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if not tokens or tokens[0] not in {'bind-key', 'bind'}:
                continue
            index = 1
            while index < len(tokens):
                option = tokens[index]
                if option in {'-T', '-N'} and index < len(tokens):
                    index += 2
                elif option.startswith(('-T=', '-N=')) or option in {'-n', '-r'}:
                    index += 1
                elif option == '--':
                    index += 1
                    break
                else:
                    break
            if index >= len(tokens):
                continue
            key = cls._tmux_key(tokens[index])
            command = ' '.join(tokens[index + 1:])
            display = f'{key} (copy mode)' if copy_mode else f'{prefix}, {key}'
            rows.append({'key': display, 'description': cls._tmux_description(command)})
        return rows

    @staticmethod
    def _tmux_key(key):
        replacements = {'Space': 'Space', 'Enter': 'Enter', 'Escape': 'Escape'}
        if key in replacements:
            return replacements[key]
        if key.startswith('C-') and len(key) > 2:
            suffix = key[2:]
            if len(suffix) == 1 and suffix.isupper():
                return 'Ctrl+Shift+' + suffix
            return 'Ctrl+' + (suffix.upper() if len(suffix) == 1 else suffix)
        if key.startswith('M-') and len(key) > 2:
            suffix = key[2:]
            if len(suffix) == 1 and suffix.isupper():
                return 'Alt+Shift+' + suffix
            return 'Alt+' + (suffix.upper() if len(suffix) == 1 else suffix)
        if len(key) == 1 and key.isupper():
            return 'Shift+' + key
        return _clean(key, 40)

    @staticmethod
    def _tmux_description(command):
        command = _clean(command, 180)
        if command.startswith('new-window'):
            return 'New window'
        if command.startswith('split-window -h'):
            return 'Split pane horizontally'
        if command.startswith('split-window'):
            return 'Split pane vertically'
        if command.startswith('kill-pane'):
            return 'Close pane'
        if command.startswith('next-window'):
            return 'Next window'
        if command.startswith('previous-window'):
            return 'Previous window'
        if command.startswith('copy-mode'):
            return 'Enter copy mode'
        if command.startswith('paste-buffer'):
            return 'Paste tmux buffer'
        if command.startswith('detach-client'):
            return 'Detach client'
        if command.startswith('send-keys -X cancel'):
            return 'Exit copy mode'
        if 'send-keys -X copy-selection' in command:
            return 'Copy selection and exit copy mode'
        if 'send-keys -X begin-selection' in command:
            return 'Begin selection'
        return command or 'No command'

    def _load_custom_profiles(self):
        try:
            info = self.profiles_path.stat()
        except FileNotFoundError:
            return ({}, 'profile file not found') if self._profiles_explicit else ({}, None)
        except OSError:
            return {}, 'profile file unreadable'
        if not stat.S_ISREG(info.st_mode) or info.st_size > 256 * 1024:
            return {}, 'invalid profile file'
        try:
            with self.profiles_path.open(encoding='utf-8') as stream:
                document = json.load(stream)
        except json.JSONDecodeError:
            return {}, 'invalid JSON'
        except (OSError, UnicodeError):
            return {}, 'profile file unreadable'
        try:
            return self._validate_profiles(document), None
        except ValueError:
            return {}, 'invalid schema'

    @staticmethod
    def _validate_profiles(document):
        if not isinstance(document, dict) or set(document) != {'profiles'}:
            raise ValueError('invalid root')
        raw_profiles = document['profiles']
        if not isinstance(raw_profiles, dict) or len(raw_profiles) > 64:
            raise ValueError('invalid profiles')
        profiles = {}
        for profile_id, raw in raw_profiles.items():
            if (not isinstance(profile_id, str) or not _clean(profile_id, 64)
                    or _clean(profile_id, 64) != profile_id):
                raise ValueError('invalid profile id')
            if not isinstance(raw, dict) or set(raw) != {
                    'name', 'aliases', 'coverage', 'rows'}:
                raise ValueError('invalid profile')
            name = _clean(raw['name'], 80)
            coverage = _clean(raw['coverage'], 80)
            aliases = raw['aliases']
            rows = raw['rows']
            if (not name or name != raw['name'] or coverage != raw['coverage']
                    or not coverage.startswith('Partial')
                    or not isinstance(aliases, list) or len(aliases) > 32
                    or not isinstance(rows, list) or len(rows) > 100):
                raise ValueError('invalid fields')
            clean_aliases = []
            for alias in aliases:
                cleaned = _clean(alias, 128)
                if not cleaned or cleaned != alias:
                    raise ValueError('invalid alias')
                clean_aliases.append(cleaned)
            clean_rows = []
            for row in rows:
                if not isinstance(row, dict) or set(row) != {'key', 'description'}:
                    raise ValueError('invalid row')
                key = _clean(row['key'], 80)
                description = _clean(row['description'], 180)
                if not key or not description or key != row['key'] or description != row['description']:
                    raise ValueError('invalid row text')
                clean_rows.append((key, description))
            profiles[profile_id] = {
                'name': name,
                'aliases': tuple(clean_aliases),
                'coverage': coverage,
                'rows': tuple(clean_rows),
            }
        return profiles
