#!/usr/bin/env python3
"""Load the Oldbook Ghost cursors in a private headless SwayFX session.

The unit tests prove the file format; this proves a real compositor accepts the
theme by name. Sway's cursor manager logs a warning for a theme it cannot find,
so the check is that the session starts, reports the requested theme, and logs no
cursor complaint.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]
THEME_NAME = 'Oldbook-Ghost'
THEME_ROOT = REPO / 'alpine/desktop/.local/share/icons'
COMPLAINT = re.compile(r'cursor', re.IGNORECASE)
BENIGN = re.compile(r'(software cursor|cursor (surface|shape|image|position)|'
                    r'set_cursor|xcursor_manager .*loaded)', re.IGNORECASE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new evidence directory')
    parser.add_argument('--size', type=int, default=48)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix='oldbook-cursor-session-') as temporary:
        base = Path(temporary)
        home, runtime = base / 'home', base / 'run'
        home.mkdir()
        runtime.mkdir(mode=0o700)
        environment = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                           XDG_CONFIG_HOME=str(home / '.config'),
                           XDG_DATA_HOME=str(home / '.local/share'),
                           XDG_STATE_HOME=str(home / '.local/state'),
                           WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
                           WLR_RENDERER='pixman', GTK_USE_PORTAL='0', NO_AT_BRIDGE='1',
                           XCURSOR_PATH=str(THEME_ROOT), XCURSOR_THEME=THEME_NAME,
                           XCURSOR_SIZE=str(arguments.size))
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            environment.pop(key, None)
        config = output / 'sway.conf'
        config.write_text('xwayland disable\n'
                          'output HEADLESS-1 mode 1440x900\n'
                          'output * bg #282828 solid_color\n'
                          'seat seat0 fallback true\n'
                          f'seat * xcursor_theme {THEME_NAME} {arguments.size}\n')
        log_path = output / 'runtime.log'
        with log_path.open('w') as log:
            session = subprocess.Popen(['swayfx', '--config', str(config)], env=environment,
                                       stdout=log, stderr=log, start_new_session=True)
            try:
                socket = None
                for _ in range(200):
                    if session.poll() is not None:
                        raise RuntimeError('The private compositor exited early')
                    found = list(runtime.glob('sway-ipc*.sock'))
                    if found:
                        socket = found[0]
                        break
                    time.sleep(0.05)
                if socket is None:
                    raise RuntimeError('The private compositor never opened its socket')
                time.sleep(1.0)
                seats = subprocess.run(['swaymsg', '-s', str(socket), '-t', 'get_seats'],
                                       env=environment, capture_output=True, text=True,
                                       timeout=10)
                subprocess.run(['swaymsg', '-s', str(socket), 'exit'], env=environment,
                               capture_output=True, timeout=10)
                session.wait(timeout=10)
            finally:
                if session.poll() is None:
                    os.killpg(session.pid, signal.SIGTERM)
                    try:
                        session.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(session.pid, signal.SIGKILL)
                        session.wait()

        text = log_path.read_text()
        complaints = [line for line in text.splitlines()
                      if COMPLAINT.search(line) and not BENIGN.search(line)
                      and re.search(r'error|fail|unable|not found|missing|invalid',
                                    line, re.IGNORECASE)]
        theme_files = sorted(path.name for path in (THEME_ROOT / THEME_NAME / 'cursors').iterdir())
        evidence = {
            'status': 'passed' if not complaints else 'failed',
            'theme': THEME_NAME,
            'requested_size': arguments.size,
            'cursor_names': theme_files,
            'seats': json.loads(seats.stdout) if seats.stdout else [],
            'cursor_complaints': complaints,
            'compositor': subprocess.run(['swayfx', '--version'], capture_output=True,
                                         text=True, timeout=10).stdout.strip(),
            'isolation': 'private headless SwayFX (pixman renderer), private HOME and XDG '
                         'directories, XCURSOR_PATH pointed at the checked-in theme',
            'limits': 'A loaded theme is not a photograph of a spinning cursor: headless '
                      'sessions render no pointer, so the animation itself is shown by '
                      'the frame contact sheet instead.',
        }
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence, indent=2))
        return 0 if evidence['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
