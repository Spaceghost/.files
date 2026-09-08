"""Crossfade wallpaper protocol, fill geometry and easing, importable without GTK.

`oldbook-background` owns one opaque background-layer surface per output and
fades between paintings. This module holds everything the daemon shares with
its callers and tests: the session-scoped socket, the datagram protocol, the
fill-scaling and easing maths, and the stacking check that tells the daemon
when a respawned swaybg surface has covered it.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import struct
import time
import uuid

NAMESPACE = 'oldbook-background'
WALLPAPER_NAMESPACE = 'wallpaper'
CARD_NAMESPACES = ('conky',)
DEFAULT_DURATION_MS = 800
ROTATION_DURATION_MS = 1600
STARTUP_DURATION_MS = 1000
MAX_DURATION_MS = 20000
MAX_MESSAGE = 8192
ACTIONS = ('set', 'status', 'raise', 'quit')
FEATHER = 0.14
IPC_HEADER = struct.Struct('=6sII')
IPC_SUBSCRIBE = 2
IPC_GET_OUTPUTS = 3
IPC_EVENT_OUTPUT = 0x80000003
IPC_EVENT_SHUTDOWN = 0x80000006


def session_key():
    identity = os.environ.get('SWAYSOCK') or os.environ.get('WAYLAND_DISPLAY') or 'default'
    return hashlib.sha256(identity.encode()).hexdigest()[:12]


def runtime_directory():
    runtime = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    return Path(runtime) / 'oldbook'


def endpoint():
    return runtime_directory() / f'background-{session_key()}.sock'


def lock_path():
    return runtime_directory() / f'background-{session_key()}.lock'


def fill_geometry(image_width, image_height, target_width, target_height):
    """Size and offset that cover the target while keeping the image's aspect.

    The scaled size never falls short of the target, so no hairline of the
    surface below shows through; the overflow is centred and cropped.
    """
    if min(image_width, image_height, target_width, target_height) <= 0:
        raise ValueError('fill geometry needs positive sizes')
    scale = max(target_width / image_width, target_height / image_height)
    width = max(target_width, math.ceil(image_width * scale))
    height = max(target_height, math.ceil(image_height * scale))
    return width, height, (target_width - width) // 2, (target_height - height) // 2


def ease_out(t):
    """Cubic ease-out: fast start, exact arrival at 1.0, no overshoot."""
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3


def progress(elapsed_us, duration_us):
    """Eased progress for a fade; exactly 1.0 once the duration has elapsed."""
    if duration_us <= 0 or elapsed_us >= duration_us:
        return 1.0
    if elapsed_us <= 0:
        return 0.0
    return ease_out(elapsed_us / duration_us)


def reveal_radius(origin, width, height):
    """Distance from a reveal origin to the farthest corner of the surface."""
    x, y = origin
    return max(math.hypot(x - cx, y - cy) for cx in (0, width) for cy in (0, height))


def reveal_rings(value, radius, feather=FEATHER):
    """Inner (opaque) and outer (transparent) radii of a radial reveal.

    The outer ring passes the far corner before the fade ends, so the last
    frames finish the soft edge instead of leaving a faint arc behind.
    """
    band = max(1.0, radius * feather)
    outer = value * (radius + band)
    return max(0.0, outer - band), outer


def parse_origin(text):
    try:
        x, y = (float(part) for part in text.split(','))
    except (AttributeError, ValueError):
        raise ValueError('origin must be X,Y in logical output pixels') from None
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError('origin must be finite')
    return x, y


def encode_request(action, path=None, duration_ms=None, origin=None, token=None):
    message = parse_request(json.dumps({
        'action': action, 'path': path, 'duration_ms': duration_ms,
        'origin': list(origin) if origin is not None else None,
        'id': token or uuid.uuid4().hex}).encode())
    return json.dumps(message).encode()


def parse_request(data):
    """Validate one datagram; the socket is private but the payload is still data."""
    if len(data) > MAX_MESSAGE:
        raise ValueError('request too long')
    try:
        message = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise ValueError('request is not JSON') from None
    if not isinstance(message, dict) or message.get('action') not in ACTIONS:
        raise ValueError('unknown action')
    token = message.get('id')
    if not isinstance(token, str) or not token or len(token) > 64:
        raise ValueError('request needs a short id')
    result = {'action': message['action'], 'id': token, 'path': None,
              'duration_ms': None, 'origin': None}
    if message['action'] == 'set':
        path = message.get('path')
        if not isinstance(path, str) or not path.startswith('/') or '\0' in path:
            raise ValueError('set needs an absolute path')
        result['path'] = path
        duration = message.get('duration_ms')
        if duration is not None:
            if isinstance(duration, bool) or not isinstance(duration, (int, float)):
                raise ValueError('duration must be a number of milliseconds')
            result['duration_ms'] = int(min(MAX_DURATION_MS, max(0, duration)))
        origin = message.get('origin')
        if origin is not None:
            if (not isinstance(origin, (list, tuple)) or len(origin) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) for v in origin)):
                raise ValueError('origin must be [x, y]')
            result['origin'] = (float(origin[0]), float(origin[1]))
    return result


def surface_order(output):
    """Classify background-layer stacking for one `get_outputs` entry.

    SwayFX lists `layer_shell_surfaces` from the top of each layer downwards:
    the newest surface comes first (verified against a screenshot of two
    overlapping surfaces in a private session). `buried` means a swaybg
    surface was created after ours and covers it; `cards_below` means Conky
    cards were created before ours and are hidden underneath it. While a
    surface is being re-created both copies exist; the newest one counts.
    """
    names = [surface.get('namespace') or '' for surface in output.get('layer_shell_surfaces', [])
             if surface.get('layer') == 'background']
    if NAMESPACE not in names:
        return {'present': False, 'buried': False, 'cards_below': False}
    ours = names.index(NAMESPACE)
    return {'present': True,
            'buried': WALLPAPER_NAMESPACE in names[:ours],
            'cards_below': any(name in CARD_NAMESPACES for name in names[ours + 1:])}


def sway_background_images(sway_socket, proc=Path('/proc')):
    """Images swaybg shows for this compositor, by output name (`*` for all).

    Sway spawns `swaybg -o NAME -i PATH -m MODE ...` as its own child, and the
    IPC socket name carries the compositor's pid, so the daemon can start on
    exactly what is on screen and fade from there instead of flashing.
    """
    try:
        pid = int(Path(sway_socket).name.split('.')[2])
    except (AttributeError, IndexError, TypeError, ValueError):
        return {}
    images = {}
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[1]) != pid or entry.stat().st_uid != os.getuid():
                continue
            argv = (entry / 'cmdline').read_bytes().split(b'\0')
        except (OSError, IndexError, ValueError):
            continue
        if not argv or Path(argv[0].decode(errors='replace')).name != 'swaybg':
            continue
        output = '*'
        for flag, value in zip(argv, argv[1:]):
            if flag == b'-o':
                output = value.decode(errors='replace')
            elif flag == b'-i':
                images[output] = value.decode(errors='replace')
    return images


def ipc_frame(kind, payload=''):
    body = payload.encode('utf-8')
    return IPC_HEADER.pack(b'i3-ipc', len(body), kind) + body


def ipc_unpack(header):
    magic, length, kind = IPC_HEADER.unpack(header)
    if magic != b'i3-ipc' or length > 32 * 1024 * 1024:
        raise ValueError('invalid Sway IPC frame')
    return length, kind


def request(message, ack_timeout=2.0, settle_timeout=None):
    """Send one request and collect replies.

    Returns None when no daemon answers (missing socket, no listener, or no
    acknowledgement within `ack_timeout`). Otherwise returns the last reply,
    whose `state` is `accepted` when the final reply did not arrive within
    `settle_timeout`, `settled` when the fade finished, or `error`.
    """
    token = json.loads(message)['id']
    directory = runtime_directory()
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        return None
    reply_path = directory / f'background-reply-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock'
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        connection.bind(str(reply_path))
        try:
            connection.sendto(message, str(endpoint()))
        except OSError:
            return None
        last = None
        deadline = time.monotonic() + ack_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return last
            connection.settimeout(remaining)
            try:
                data = connection.recv(MAX_MESSAGE)
            except socket.timeout:
                return last
            except OSError:
                return last
            try:
                reply = json.loads(data.decode('utf-8'))
            except (UnicodeDecodeError, ValueError):
                continue
            if not isinstance(reply, dict) or reply.get('id') != token:
                continue
            last = reply
            if reply.get('state') == 'accepted':
                if settle_timeout is None:
                    return reply
                deadline = time.monotonic() + settle_timeout
                continue
            return reply
    finally:
        connection.close()
        try:
            reply_path.unlink()
        except OSError:
            pass


def crossfade(path, duration_ms=None, origin=None, ack_timeout=2.0, settle_timeout=None):
    """Ask the daemon to fade to `path`; see `request` for the result shape."""
    if settle_timeout is None:
        settle_timeout = (duration_ms or DEFAULT_DURATION_MS) / 1000 + 6.0
    return request(encode_request('set', path=path, duration_ms=duration_ms, origin=origin),
                   ack_timeout=ack_timeout, settle_timeout=settle_timeout)
