"""Session-scoped activation of the existing Scripture bar."""
import hashlib
import json
import os
from pathlib import Path
import socket

SCOPES = ('bible', 'all', 'reflections')


def endpoint():
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    identity = os.environ.get('SWAYSOCK', os.environ.get('WAYLAND_DISPLAY', 'default'))
    key = hashlib.sha256(identity.encode()).hexdigest()[:12]
    return runtime / 'oldbook' / f'scripture-bar-{key}.sock'


def request(scope='bible', query='', translation=None):
    if scope not in SCOPES:
        raise ValueError('Unknown search scope: ' + scope)
    payload = json.dumps({'scope': scope, 'query': query, 'translation': translation}).encode()
    if len(payload) > 4096:
        raise ValueError('Search request is too long')
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as connection:
            connection.settimeout(.2)
            connection.sendto(payload, str(endpoint()))
        return True
    except OSError:
        return False
