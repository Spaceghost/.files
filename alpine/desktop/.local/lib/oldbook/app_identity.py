"""Resolve privacy-preserving display identities for Sway application windows."""
from pathlib import Path
import os
import re
import subprocess


_CONTROL = re.compile(r'[\x00-\x1f\x7f]+')
_PANE_ID = re.compile(r'%[0-9]+')
_TTY_PATH = re.compile(r'/dev/(?:pts/[0-9]+|tty[0-9]+)')
_CODEX_STATE = re.compile(r'[A-Za-z][A-Za-z -]{0,31}')

_APP_NAMES = {
    'btop': 'btop',
    'chromium': 'Chromium',
    'code': 'Visual Studio Code',
    'codium': 'VSCodium',
    'firefox': 'Firefox',
    'foot': 'Foot',
    'google-chrome': 'Google Chrome',
    'htop': 'htop',
    'kitty': 'Kitty',
    'mpv': 'mpv',
    'nvim': 'Neovim',
    'opensnitch_ui': 'OpenSnitch',
    'pithos': 'Pithos',
    'thunar': 'Thunar',
    'vim': 'Vim',
    'wezterm': 'WezTerm',
}
_SHELLS = {'ash', 'bash', 'dash', 'fish', 'sh', 'zsh'}


def _tty_path(device):
    """Map Linux's /proc stat tty_nr to a validated terminal device path."""
    if type(device) is not int or device <= 0:
        return None
    try:
        major = os.major(device)
        minor = os.minor(device)
    except (OverflowError, ValueError):
        return None
    if 136 <= major <= 143:
        return f'/dev/pts/{(major - 136) * 256 + minor}'
    if major == 4 and 0 < minor < 64:
        return f'/dev/tty{minor}'
    return None


def _clean(value, limit=32):
    """Return a short, single-line label without exposing a window title."""
    if not isinstance(value, str):
        return ''
    value = ' '.join(_CONTROL.sub(' ', value).split())
    return value[:limit].strip()


def _tmux_unquote(value):
    """Decode tmux's ``q:`` backslash quoting without invoking a shell."""
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
    return _clean(''.join(result), 256)


def _tmux_title(value):
    if any(escape in value for escape in ('\\n', '\\r', '\\t')):
        return ''
    return _tmux_unquote(value)


def _app_key(value):
    value = _clean(value, 128).casefold()
    return value.rsplit('/', 1)[-1]


def _known_app(value):
    key = _app_key(value)
    if not key:
        return None
    if 'chatgpt' in key or key in {'com.openai.chat', 'openai'}:
        return {'name': 'ChatGPT', 'kind': 'chatgpt', 'state': None}
    if key == 'codex' or key.startswith('codex-'):
        return {'name': 'Codex', 'kind': 'codex', 'state': None}
    for token, name in _APP_NAMES.items():
        if key == token or key.endswith('.' + token):
            return {'name': name, 'kind': 'app', 'state': None}
    if 'firefox' in key:
        return {'name': 'Firefox', 'kind': 'app', 'state': None}
    if 'chromium' in key:
        return {'name': 'Chromium', 'kind': 'app', 'state': None}
    return None


def _is_terminal(value):
    key = _app_key(value)
    return any(token in key for token in ('foot', 'kitty', 'alacritty', 'wezterm', 'xterm'))


def _is_browser(value):
    key = _app_key(value)
    return any(token in key for token in ('firefox', 'chromium', 'chrome', 'brave', 'vivaldi'))


def _codex_state(title):
    """Read only the configured Codex run-state field from its native title."""
    parts = [_clean(part, 64) for part in title.split('|')]
    for index, part in enumerate(parts):
        if part.casefold() != 'codex' or index + 2 >= len(parts):
            continue
        state = parts[index + 2]
        if _CODEX_STATE.fullmatch(state):
            return state
    return None


class ApplicationResolver:
    """Resolve all windows from one bounded process and tmux snapshot."""

    CLIENT_FORMAT = '#{client_pid}\t#{session_id}\t#{window_id}'
    PANE_FORMAT = (
        '#{session_id}\t#{window_id}\t#{window_zoomed_flag}\t#{pane_id}\t'
        '#{pane_pid}\t#{pane_tty}\t#{q:pane_current_command}\t#{pane_width}\t'
        '#{pane_height}\t#{pane_active}\t#{q:pane_title}'
    )

    def __init__(self, proc_root='/proc', command_runner=None, uid=None):
        self.proc_root = Path(proc_root)
        self.command_runner = command_runner or self._run_command
        self.uid = os.getuid() if uid is None else uid

    @staticmethod
    def _run_command(argv):
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=1,
            )
        except (OSError, subprocess.SubprocessError):
            return ''
        return completed.stdout if completed.returncode == 0 else ''

    def resolve_all(self, windows: list[dict]) -> dict[int, dict]:
        processes = self._process_snapshot()
        terminal_windows = [window for window in windows if self._terminal_source(window)]
        clients = {}
        panes = []
        if terminal_windows:
            clients = self._tmux_clients(self.command_runner([
                'tmux', 'list-clients', '-F', self.CLIENT_FORMAT,
            ]))
            panes = self._tmux_panes(self.command_runner([
                'tmux', 'list-panes', '-a', '-F', self.PANE_FORMAT,
            ]))

        resolved = {}
        for window in windows:
            con_id = window.get('id')
            if not isinstance(con_id, int) or isinstance(con_id, bool):
                continue
            resolved[con_id] = self._resolve_window(window, processes, clients, panes)
        return resolved

    def _process_snapshot(self):
        processes = {}
        try:
            entries = list(self.proc_root.iterdir())
        except OSError:
            return processes
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != self.uid:
                    continue
                stat = (entry / 'stat').read_text(errors='replace')
                comm = (entry / 'comm').read_text(errors='replace')
            except OSError:
                continue
            close = stat.rfind(')')
            if close < 0:
                continue
            fields = stat[close + 1:].split()
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
                processes[pid]['tty_path'] = _tty_path(processes[pid]['tty'])
            except ValueError:
                continue
        return processes

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
            if re.fullmatch(r'\$[0-9]+', fields[1]) and re.fullmatch(r'@[0-9]+', fields[2]):
                clients[pid] = (fields[1], fields[2])
        return clients

    @staticmethod
    def _tmux_panes(output):
        panes = []
        for line in output.splitlines():
            fields = line.split('\t', 10)
            if len(fields) != 11:
                continue
            session, window, zoomed, pane_id, pane_pid, tty, command, width, height, active, title = fields
            try:
                pane = {
                    'session': session,
                    'window': window,
                    'zoomed': int(zoomed),
                    'pane_id': pane_id,
                    'pane_pid': int(pane_pid),
                    'tty': tty,
                    'command': _tmux_unquote(command),
                    'width': int(width),
                    'height': int(height),
                    'active': int(active),
                    'title': _tmux_title(title),
                }
            except ValueError:
                continue
            if not re.fullmatch(r'\$[0-9]+', session) or not re.fullmatch(r'@[0-9]+', window):
                continue
            if not _PANE_ID.fullmatch(pane_id):
                continue
            panes.append(pane)
        return panes

    @staticmethod
    def _window_sources(window):
        properties = window.get('window_properties')
        properties = properties if isinstance(properties, dict) else {}
        return [window.get('app_id'), properties.get('class'), properties.get('instance')]

    def _terminal_source(self, window):
        return next((source for source in self._window_sources(window) if _is_terminal(source)), None)

    @staticmethod
    def _title(window):
        properties = window.get('window_properties')
        properties = properties if isinstance(properties, dict) else {}
        return _clean(window.get('name') or properties.get('title'), 256)

    def _resolve_window(self, window, processes, clients, panes):
        sources = self._window_sources(window)
        title = self._title(window)
        browser = next((source for source in sources if _is_browser(source)), None)
        if browser and re.search(r'(?<![A-Za-z0-9])(?:chatgpt|chat\.openai\.com)(?![A-Za-z0-9])', title, re.I):
            return {'name': 'ChatGPT', 'kind': 'chatgpt', 'state': None}

        terminal = self._terminal_source(window)
        if terminal:
            return self._terminal_identity(window, terminal, title, processes, clients, panes)

        for source in sources:
            identity = _known_app(source)
            if identity:
                if identity['kind'] == 'codex':
                    identity['state'] = _codex_state(title)
                    tty = self._foreground_tty(window.get('pid'), processes)
                    if tty:
                        identity['tty'] = tty
                return identity
        fallback = next((_clean(source) for source in sources if _clean(source)), 'Application')
        return {'name': fallback, 'kind': 'app', 'state': None}

    def _terminal_identity(self, window, terminal, title, processes, clients, panes):
        base = _known_app(terminal) or {'name': 'Terminal', 'kind': 'app', 'state': None}
        pid = window.get('pid')
        if not isinstance(pid, int) or isinstance(pid, bool) or pid not in processes:
            return base

        descendants = self._descendants(pid, processes)
        displayed = [
            (descendants[client_pid], client_pid, target)
            for client_pid, target in clients.items()
            if client_pid in descendants and self._foreground(processes.get(client_pid))
        ]
        if displayed:
            _, _, (session, current_window) = max(displayed)
            visible = [
                pane for pane in panes
                if pane['session'] == session and pane['window'] == current_window
            ]
            if visible:
                zoomed = any(pane['zoomed'] for pane in visible)
                choices = [pane for pane in visible if pane['active']] if zoomed else visible
                if not choices:
                    choices = visible
                pane = max(
                    choices,
                    key=lambda item: (item['width'] * item['height'], item['active'], item['pane_id']),
                )
                identity = self._command_identity(pane['command'], base, pane['title'])
                if _PANE_ID.fullmatch(pane['pane_id']):
                    identity['tmux_pane'] = pane['pane_id']
                if _TTY_PATH.fullmatch(pane['tty']):
                    identity['tty'] = pane['tty']
                return identity

        candidates = [
            (depth, process)
            for candidate_pid, depth in descendants.items()
            if candidate_pid != pid
            for process in [processes.get(candidate_pid)]
            if self._foreground(process)
        ]
        if not candidates:
            return base
        _, foreground = max(
            candidates,
            key=lambda item: (item[0], _app_key(item[1]['comm']) not in _SHELLS, item[1]['pid']),
        )
        identity = self._command_identity(foreground['comm'], base, title)
        if identity['kind'] == 'codex' and foreground.get('tty_path'):
            identity['tty'] = foreground['tty_path']
        return identity

    def _foreground_tty(self, pid, processes):
        if not isinstance(pid, int) or isinstance(pid, bool) or pid not in processes:
            return None
        candidates = [
            (depth, process)
            for candidate_pid, depth in self._descendants(pid, processes).items()
            for process in [processes.get(candidate_pid)]
            if self._foreground(process) and process.get('tty_path')
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[0], item[1]['pid']))[1]['tty_path']

    @staticmethod
    def _foreground(process):
        return bool(
            process
            and process['tty'] != 0
            and process['tpgid'] > 0
            and process['pgrp'] == process['tpgid']
        )

    @staticmethod
    def _descendants(root_pid, processes):
        children = {}
        for process in processes.values():
            children.setdefault(process['ppid'], []).append(process['pid'])
        depths = {root_pid: 0}
        pending = [root_pid]
        while pending:
            parent = pending.pop()
            for child in children.get(parent, []):
                if child in depths:
                    continue
                depths[child] = depths[parent] + 1
                pending.append(child)
        return depths

    @staticmethod
    def _command_identity(command, base, title):
        key = _app_key(command)
        if key in _SHELLS:
            return dict(base)
        identity = _known_app(command)
        if identity:
            if identity['kind'] == 'codex':
                identity['state'] = _codex_state(title)
            return identity
        name = _clean(command) or base['name']
        return {'name': name, 'kind': 'app', 'state': None}
