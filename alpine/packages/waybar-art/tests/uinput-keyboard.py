#!/usr/bin/env python3
"""Owned test keyboard. No keys are pressed before a command on standard input."""
import fcntl
import os
from pathlib import Path
import struct
import sys
import time

name = sys.argv[1]
if not name.startswith('oldbook-art-test-') or len(name) > 60:
    raise SystemExit('Invalid test device name')
fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
try:
    fcntl.ioctl(fd, 0x40045564, 1)  # UI_SET_EVBIT / EV_KEY
    for key in (30, 125, 126):
        fcntl.ioctl(fd, 0x40045565, key)  # A, Left/Right Meta
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
    print('ready', flush=True)
    for line in sys.stdin:
        command, key_text = line.split()
        key = int(key_text)
        if command not in ('press', 'release') or key not in (125, 126):
            raise ValueError('Only test Meta keys are permitted')
        os.write(fd, struct.pack('llHHi', 0, 0, 1, key, int(command == 'press')))
        os.write(fd, struct.pack('llHHi', 0, 0, 0, 0, 0))
        print('ok', flush=True)
finally:
    # Device destruction also clears every pressed key on interrupted tests.
    fcntl.ioctl(fd, 0x5502)
    os.close(fd)
