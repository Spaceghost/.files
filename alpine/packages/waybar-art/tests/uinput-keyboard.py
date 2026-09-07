#!/usr/bin/env python3
"""Owned test keyboard. No keys are pressed before a command on standard input."""
import fcntl
import os
from pathlib import Path
import struct
import sys
import time

name = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else 'keyboard'
if (not name.startswith(('oldbook-art-test-', 'oldbook-art-noise-test-')) or
        len(name) > 60 or mode not in ('keyboard', 'modifier-only')):
    raise SystemExit('Invalid test device name')
fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
try:
    fcntl.ioctl(fd, 0x40045564, 1)  # UI_SET_EVBIT / EV_KEY
    keys = (28, 30, 42, 54, 57, 125, 126) if mode == 'keyboard' else (125,)
    for key in keys:
        fcntl.ioctl(fd, 0x40045565, key)  # Enter, A, Space, Shift and Meta
    setup = struct.pack('80sHHHHI', name.encode(), 3, 0xfeed, 0xc0de, 1, 0)
    os.write(fd, setup + bytes(64 * 4 * 4))
    fcntl.ioctl(fd, 0x5501)  # UI_DEV_CREATE
    for _ in range(100):
        matches = [p.parent for p in Path('/sys/class/input').glob('event*/device/name')
                   if p.read_text().strip() == name]
        if matches:
            break
        time.sleep(.05)
    else:
        raise RuntimeError('No evdev node appeared')
    if mode == 'modifier-only':
        os.write(fd, struct.pack('llHHi', 0, 0, 1, 125, 1))
        os.write(fd, struct.pack('llHHi', 0, 0, 0, 0, 0))
    print('ready', flush=True)
    for line in sys.stdin:
        if mode != 'keyboard':
            raise ValueError('Modifier-only test device accepts no commands')
        command, key_text = line.split()
        key = int(key_text)
        if command not in ('press', 'release') or key not in (42, 54, 125, 126):
            raise ValueError('Only test Shift and Meta keys are permitted')
        os.write(fd, struct.pack('llHHi', 0, 0, 1, key, int(command == 'press')))
        os.write(fd, struct.pack('llHHi', 0, 0, 0, 0, 0))
        print('ok', flush=True)
finally:
    # Device destruction also clears every pressed key on interrupted tests.
    fcntl.ioctl(fd, 0x5502)
    os.close(fd)
