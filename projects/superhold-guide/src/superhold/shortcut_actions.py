"""Bounded native keyboard actions for a captured Sway application.

Actions contain key events or literal text, never executable command strings.
The UI must unmap and wait for physical modifiers to be released before send().
Wayland cannot atomically combine a Sway focus check with virtual keyboard input;
we check the original target again immediately before each bounded dispatch.
"""
import ctypes
import ctypes.util
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess


_MODIFIERS = {
    'ctrl': 'ctrl', 'control': 'ctrl', 'alt': 'alt', 'mod1': 'alt',
    'shift': 'shift', 'super': 'logo', 'mod4': 'logo', 'logo': 'logo',
    'win': 'logo', 'altgr': 'altgr', 'mod5': 'altgr',
}
_KEY_NAMES = {
    'enter': 'Return', 'return': 'Return', 'esc': 'Escape', 'escape': 'Escape',
    'space': 'space', 'tab': 'Tab', 'backspace': 'BackSpace', 'delete': 'Delete',
    'insert': 'Insert', 'pageup': 'Page_Up', 'prior': 'Page_Up',
    'pagedown': 'Page_Down', 'next': 'Page_Down', 'home': 'Home', 'end': 'End',
    'left': 'Left', 'right': 'Right', 'up': 'Up', 'down': 'Down', 'print': 'Print',
}
_PUNCTUATION = {
    '+': 'plus', '-': 'minus', '/': 'slash', '?': 'question', ':': 'colon',
    ';': 'semicolon', ',': 'comma', '.': 'period', '[': 'bracketleft',
    ']': 'bracketright', '{': 'braceleft', '}': 'braceright',
    '=': 'equal', '\\': 'backslash', '|': 'bar', "'": 'apostrophe',
    '"': 'quotedbl', '`': 'grave', '~': 'asciitilde', '!': 'exclam',
    '@': 'at', '#': 'numbersign', '$': 'dollar', '%': 'percent', '^': 'asciicircum',
    '&': 'ampersand', '*': 'asterisk', '(': 'parenleft', ')': 'parenright',
    '_': 'underscore', '<': 'less', '>': 'greater',
}


@lru_cache(maxsize=1)
def _xkb():
    try:
        library = ctypes.CDLL(ctypes.util.find_library('xkbcommon') or 'libxkbcommon.so.0')
        library.xkb_keysym_from_name.argtypes = [ctypes.c_char_p, ctypes.c_int]
        library.xkb_keysym_from_name.restype = ctypes.c_uint32
        library.xkb_keysym_get_name.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        library.xkb_keysym_get_name.restype = ctypes.c_int
        return library
    except (OSError, AttributeError):
        return None


def _valid_key(key):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,80}', key):
        return False
    library = _xkb()
    if library is not None:
        return bool(library.xkb_keysym_from_name(key.encode('ascii'), 0))
    return (len(key) == 1 or key in _KEY_NAMES.values()
            or key in _PUNCTUATION.values() or bool(re.fullmatch(r'F[1-9][0-9]?', key)))


def sway_keysym(key):
    """Resolve a symbol using Sway's case-insensitive keysym-name semantics.

    Sway 1.12's identify_key uses XKB_KEYSYM_CASE_INSENSITIVE:
    https://github.com/swaywm/sway/blob/1.12/sway/commands/bind.c
    Numeric forms remain exact: 0x58 resolves to uppercase X, named X to x.
    """
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,80}', key):
        return None
    library = _xkb()
    if library is None:
        if len(key) == 1 and key.isascii():
            return key.lower()
        normalized = _KEY_NAMES.get(key.casefold(), key)
        return normalized if _valid_key(normalized) else None
    symbol = library.xkb_keysym_from_name(key.encode('ascii'), 1)
    if not symbol:
        return None
    name = ctypes.create_string_buffer(128)
    length = library.xkb_keysym_get_name(symbol, name, len(name))
    return name.value.decode('ascii') if 0 < length < len(name) else None


def _chord(value, source=False):
    modifiers = []
    remaining = value
    while '+' in remaining:
        first, suffix = remaining.split('+', 1)
        modifier = _MODIFIERS.get(first.casefold())
        if not modifier:
            break
        if modifier not in modifiers:
            modifiers.append(modifier)
        remaining = suffix
    key = _KEY_NAMES.get(remaining.casefold(), _PUNCTUATION.get(remaining, remaining))
    if not source and len(key) == 1 and key.isascii() and key.isalpha():
        if not modifiers and key.isupper():
            modifiers.append('shift')
        # wtype supplies a one-level keymap: Shift alone does not turn a
        # lower-case symbol into its uppercase counterpart. Supply both the
        # shifted symbol and modifier, as a physical keyboard would.
        key = key.upper() if 'shift' in modifiers else key.lower()
    if source:
        key = sway_keysym(key)
    if not _valid_key(key):
        raise ValueError('unrecognized keyboard shortcut')
    return {'modifiers': modifiers, 'key': key}


def prepare_actions(key):
    """Translate a profile label into individually selectable alternatives."""
    if (not isinstance(key, str) or not 0 < len(key) <= 256
            or any(ord(character) < 32 or ord(character) == 127 for character in key)):
        return []
    key = re.sub(r' \(copy mode\)$', '', key)
    actions = []
    try:
        for alternative in key.split(' / '):
            sequence = []
            for piece in alternative.split(', '):
                piece = piece.strip()
                if len(piece) > 1 and piece.startswith(('/', ':')):
                    sequence.append({'text': piece})
                else:
                    sequence.append(_chord(piece))
            action = {'label': alternative, 'sequence': sequence}
            wtype_argv(action)
            actions.append(action)
    except ValueError:
        return []
    return actions


def sway_actions(key, release=False):
    """Match Sway's configured keysyms, including its case-insensitive names.

    A complete press/release naturally activates either ordinary or --release
    bindings. The release argument documents that source distinction.
    """
    try:
        action = {'label': key, 'sequence': [_chord(key, source=True)]}
        wtype_argv(action)
        return [action]
    except (TypeError, ValueError):
        return []


def wtype_argv(action, key_delay_ms=12):
    """Validate an action and build one argument vector with balanced releases."""
    if (not isinstance(key_delay_ms, int) or isinstance(key_delay_ms, bool)
            or not 0 <= key_delay_ms <= 250):
        raise ValueError('key delay must be between 0 and 250 ms')
    if not isinstance(action, dict) or set(action) != {'label', 'sequence'}:
        raise ValueError('invalid shortcut action')
    label, sequence = action['label'], action['sequence']
    if (not isinstance(label, str) or not 0 < len(label) <= 256
            or not isinstance(sequence, list) or not 0 < len(sequence) <= 64):
        raise ValueError('invalid shortcut sequence')
    arguments = ['wtype']
    key_count = 0
    for step in sequence:
        if not isinstance(step, dict):
            raise ValueError('invalid shortcut step')
        if set(step) == {'text'}:
            text = step['text']
            if (not isinstance(text, str) or not 0 < len(text) <= 256
                    or any(ord(c) < 32 or ord(c) == 127 for c in text)):
                raise ValueError('invalid shortcut text')
            keys = [f'0x{ord(c):x}' if ord(c) < 256 else f'U{ord(c):04X}' for c in text]
            modifiers = []
        elif set(step) == {'key', 'modifiers'}:
            key, modifiers = step['key'], step['modifiers']
            if (not _valid_key(key) or not isinstance(modifiers, list)
                    or len(modifiers) > 5 or any(m not in _MODIFIERS.values() for m in modifiers)
                    or len(set(modifiers)) != len(modifiers)):
                raise ValueError('invalid shortcut chord')
            # wtype resolves names case-insensitively. Numeric keysyms preserve
            # an explicitly uppercase Sway symbol instead of folding it to lower.
            keys = [f'0x{ord(key):x}' if len(key) == 1 and key.isupper() else key]
        else:
            raise ValueError('invalid shortcut step')
        key_count += len(keys)
        if key_count > 256 or key_count * key_delay_ms > 3000:
            raise ValueError('shortcut sequence is too long for the configured key delay')
        for modifier in modifiers:
            arguments.extend(('-M', modifier))
        for key in keys:
            arguments.extend(('-P', key))
            if key_delay_ms:
                arguments.extend(('-s', str(key_delay_ms)))
            arguments.extend(('-p', key))
        for modifier in reversed(modifiers):
            arguments.extend(('-m', modifier))
    return arguments


def process_start(pid):
    try:
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            return None
        process = Path('/proc') / str(pid)
        if process.stat().st_uid != os.getuid():
            return None
        fields = process.joinpath('stat').read_text().rsplit(')', 1)[1].split()
        return fields[19] if fields[0] not in {'Z', 'X'} else None
    except (OSError, IndexError):
        return None


def socket_identity(path):
    try:
        info = Path(path).stat(follow_symlinks=False)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            return None
        return [info.st_dev, info.st_ino, info.st_ctime_ns]
    except OSError:
        return None


def capture_target(window, socket_path):
    if not isinstance(window, dict):
        return None
    con_id, pid = window.get('id'), window.get('pid')
    if (not isinstance(con_id, int) or isinstance(con_id, bool) or con_id <= 0
            or not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0):
        return None
    properties = window.get('window_properties') or {}
    return {'con_id': con_id, 'pid': pid, 'app_id': window.get('app_id') or '',
            'window_class': properties.get('class') or '',
            'process_start': process_start(pid), 'socket_identity': socket_identity(socket_path)}


class NativeShortcutSender:
    """Restore and verify the captured app before bounded virtual-keyboard input."""

    def __init__(self, socket_path, *, wayland_display=None, guard=None,
                 key_delay_ms=12, request=None, runner=None):
        self.socket_path = os.fspath(socket_path)
        self.wayland_display = wayland_display or os.environ.get('WAYLAND_DISPLAY', '')
        self.runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
        self.wayland_socket = self.runtime / self.wayland_display
        self._wayland_identity = socket_identity(self.wayland_socket)
        self.guard = guard or self._default_guard
        self.key_delay_ms = key_delay_ms
        self.request = request or self._request
        self.runner = runner or subprocess.run

    def _default_guard(self):
        # Reuse the desktop guard's synchronous probes here; send runs off the UI
        # thread and must not rely solely on its periodically refreshed cache.
        from .shortcut_overlay import _default_graphical_probe, screen_locked
        return (not screen_locked(self.runtime, self.wayland_socket)
                and _default_graphical_probe(self.runtime, self.wayland_socket))

    def _request(self, message_type, payload=''):
        payload = payload.encode('utf-8')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(.75)
            connection.connect(self.socket_path)
            connection.sendall(b'i3-ipc' + struct.pack('<II', len(payload), message_type) + payload)
            def receive(length):
                result = bytearray()
                while len(result) < length:
                    chunk = connection.recv(min(65536, length - len(result)))
                    if not chunk:
                        raise OSError('Sway connection closed')
                    result.extend(chunk)
                return bytes(result)
            header = receive(14)
            size, reply_type = struct.unpack('<II', header[6:])
            if header[:6] != b'i3-ipc' or reply_type != message_type or size > 2 * 1024 * 1024:
                raise ValueError('Invalid Sway reply')
            return json.loads(receive(size).decode('utf-8'))

    def _verify(self, target, require_focus):
        if (not isinstance(target, dict) or not target.get('process_start')
                or not target.get('socket_identity')
                or socket_identity(self.socket_path) != target['socket_identity']
                or process_start(target.get('pid')) != target['process_start']
                or not self._wayland_identity
                or socket_identity(self.wayland_socket) != self._wayland_identity
                or not self.guard()):
            raise ValueError('Original application or graphical session is no longer available')
        tree = self.request(4)
        pending, target_view, focused = [tree], None, None
        count = 0
        while pending:
            node = pending.pop()
            count += 1
            if not isinstance(node, dict) or count > 10000:
                raise ValueError('Invalid Sway window tree')
            if node.get('id') == target.get('con_id'):
                target_view = node
            if node.get('focused') and (node.get('app_id') or node.get('window_properties')):
                focused = node
            pending.extend(node.get('nodes', []))
            pending.extend(node.get('floating_nodes', []))
        if (not target_view or target_view.get('pid') != target.get('pid')
                or (target_view.get('app_id') or '') != target.get('app_id')
                or (target_view.get('window_properties') or {}).get('class', '') != target.get('window_class')):
            raise ValueError('Original application window has closed or changed')
        if ((focused and focused.get('id') != target.get('con_id'))
                or (require_focus and (not focused or focused.get('id') != target.get('con_id')))):
            raise ValueError('Application focus changed; open the guide again')

    def send(self, target, action):
        try:
            wtype_argv(action, self.key_delay_ms)
            self._verify(target, require_focus=False)
            con_id = target['con_id']
            if not isinstance(con_id, int) or isinstance(con_id, bool) or con_id <= 0:
                raise ValueError('Invalid target window')
            replies = self.request(0, f'[con_id={con_id}] focus')
            if (not isinstance(replies, list) or not replies
                    or any(not isinstance(reply, dict) or reply.get('success') is not True for reply in replies)):
                raise ValueError('Original application could not be focused')
            self._verify(target, require_focus=True)
            environment = dict(os.environ, WAYLAND_DISPLAY=self.wayland_display)
            for index, step in enumerate(action['sequence']):
                if index:
                    self._verify(target, require_focus=True)
                if not self.guard():
                    raise ValueError('Graphical session became unavailable')
                arguments = wtype_argv(
                    {'label': action['label'], 'sequence': [step]}, self.key_delay_ms)
                result = self.runner(arguments, env=environment, check=False,
                                     capture_output=True, text=True, timeout=5)
                if result.returncode:
                    raise ValueError('Native keyboard backend could not send this shortcut')
            return {'ok': True, 'error': ''}
        except FileNotFoundError:
            return {'ok': False, 'error': 'Install wtype to activate native shortcuts'}
        except subprocess.TimeoutExpired:
            return {'ok': False, 'error': 'Native shortcut dispatch timed out'}
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
            return {'ok': False, 'error': str(error) or 'Native shortcut dispatch failed'}
