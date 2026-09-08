"""Small socket-only client for already running desktop gesture helpers."""
import hashlib
import json
import os
import socket
import stat


def send_command(service, action, modifier=None):
    """Return false for a missing helper so its normal startup can recover."""
    runtime, sway = os.environ.get('XDG_RUNTIME_DIR'), os.environ.get('SWAYSOCK')
    if not runtime or not sway:
        return False
    if service == 'carousel':
        if action not in ('show', 'next', 'previous', 'commit', 'cancel'):
            return False
        if modifier not in (None, 'super', 'alt'):
            return False
        payload = json.dumps({'action': action, 'modifier': modifier}).encode()
    elif service == 'showdesktop':
        if action not in ('toggle', 'show', 'restore', 'restore-or-carousel') or modifier:
            return False
        payload = action.encode()
    else:
        return False
    token = hashlib.sha256(sway.encode()).hexdigest()[:12]
    address = (os.path.join(runtime, 'mbp-intel', 'carousel-' + token, 'control.sock')
               if service == 'carousel' else
               os.path.join(runtime, 'mbp-intel', 'showdesktop', 'control-' + token + '.sock'))
    try:
        # Never follow a stale symlink or send a gesture to another user's IPC.
        for path in (sway, address):
            info = os.stat(path, follow_symlinks=False)
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                return False
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            client.setblocking(False)
            client.sendto(payload, address)
        return True
    except OSError:
        return False


def fast_command(service, arguments):
    """Recognize only canonical invocations; the full CLI owns help/errors."""
    modifier = None
    if service == 'carousel' and len(arguments) == 3 and arguments[1] == '--modifier':
        action, modifier = arguments[0], arguments[2]
    elif len(arguments) <= 1:
        action = arguments[0] if arguments else ('show' if service == 'carousel' else 'toggle')
    else:
        return False
    return send_command(service, action, modifier)
