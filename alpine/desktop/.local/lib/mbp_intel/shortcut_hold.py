"""Detect a lone Super hold from Linux input devices without grabbing input."""
import errno
import fcntl
import os
import struct


EV_SYN = 0
EV_KEY = 1
SYN_REPORT = 0
SYN_DROPPED = 3
KEY_LEFTMETA = 125
KEY_RIGHTMETA = 126
KEY_MAX = 0x2ff
EV_MAX = 0x1f

SUPER_KEYS = frozenset((KEY_LEFTMETA, KEY_RIGHTMETA))
INPUT_EVENT = struct.Struct('@llHHi')

_IOC_READ = 2
_IOC_DIRSHIFT = 30
_IOC_SIZESHIFT = 16
_IOC_TYPESHIFT = 8


def _ioc_read(number, size):
    return ((_IOC_READ << _IOC_DIRSHIFT) | (size << _IOC_SIZESHIFT)
            | (ord('E') << _IOC_TYPESHIFT) | number)


def _eviocgbit(event_type, size):
    return _ioc_read(0x20 + event_type, size)


def _eviocgkey(size):
    return _ioc_read(0x18, size)


def _has_bit(bits, code):
    offset = code // 8
    return offset < len(bits) and bool(bits[offset] & (1 << (code % 8)))


def _set_bits(bits):
    return {code for code in range(len(bits) * 8) if _has_bit(bits, code)}


class HoldState:
    """Track a single eligible Super hold across all attached keyboards."""

    threshold = 0.5

    def __init__(self):
        self._pressed = {}
        self._started_at = None
        self._cancelled = False

    def _all_pressed(self):
        return {(device, code) for device, codes in self._pressed.items()
                for code in codes}

    def _super_down(self):
        return {(device, code) for device, code in self._all_pressed()
                if code in SUPER_KEYS}

    def update(self, device, code, value, now):
        """Consume one EV_KEY value (release 0, press 1, repeat 2)."""
        if value == 2 or value not in (0, 1):
            return

        keys = self._pressed.setdefault(device, set())
        if value == 0:
            keys.discard(code)
            if not keys:
                self._pressed.pop(device, None)
            if code in SUPER_KEYS:
                self._started_at = None
                if self._super_down():
                    self._cancelled = True
                else:
                    self._cancelled = False
            return

        if code in keys:
            return
        keys.add(code)

        if code not in SUPER_KEYS:
            if self._super_down():
                self.cancel()
            return

        pressed = self._all_pressed()
        super_down = {(item_device, item_code)
                      for item_device, item_code in pressed
                      if item_code in SUPER_KEYS}
        other_down = pressed - super_down
        if self._cancelled or other_down or len(super_down) != 1:
            self._started_at = None
            self._cancelled = True
        else:
            self._started_at = now

    def visible(self, now):
        """Return true once an eligible lone Super has lasted 500 ms."""
        return (not self._cancelled and self._started_at is not None
                and len(self._super_down()) == 1
                and not (self._all_pressed() - self._super_down())
                and now - self._started_at >= self.threshold)

    def cancel(self):
        """Invalidate the current hold until every Super key is released."""
        self._started_at = None
        self._cancelled = bool(self._super_down())

    def remove_device(self, device):
        """Forget a disconnected device and invalidate any active hold."""
        self._pressed.pop(device, None)
        self.cancel()

    def _resync_device(self, device, pressed):
        """Replace device state without allowing held keys to start a timer."""
        if pressed:
            self._pressed[device] = set(pressed)
        else:
            self._pressed.pop(device, None)
        self.cancel()


class _SystemBackend:
    """Small syscall boundary used by EvdevMonitor and deterministic tests."""

    @staticmethod
    def list_devices(directory):
        with os.scandir(directory) as entries:
            return sorted(entry.path for entry in entries
                          if entry.name.startswith('event'))

    @staticmethod
    def open(path):
        flags = os.O_RDONLY | os.O_NONBLOCK
        flags |= getattr(os, 'O_CLOEXEC', 0)
        return os.open(path, flags)

    @staticmethod
    def close(fd):
        os.close(fd)

    @staticmethod
    def read(fd, size):
        return os.read(fd, size)

    @staticmethod
    def ioctl(fd, request, target):
        return fcntl.ioctl(fd, request, target, True)


class _Device:
    def __init__(self, fd):
        self.fd = fd
        self.buffer = bytearray()
        self.dropped = False


class EvdevMonitor:
    """Poll keyboard event nodes with bounded, nonblocking read work."""

    def __init__(self, state=None, input_dir='/dev/input', scan_interval=1.0,
                 max_events_per_poll=256, backend=None):
        if max_events_per_poll < 1:
            raise ValueError('max_events_per_poll must be positive')
        self.state = state if state is not None else HoldState()
        self._input_dir = input_dir
        self._scan_interval = max(0.0, scan_interval)
        self._max_events_per_poll = max_events_per_poll
        self._backend = backend if backend is not None else _SystemBackend()
        self._devices = {}
        self._next_scan = float('-inf')
        self._poll_cursor = 0
        self._closed = False

    @property
    def device_count(self):
        return len(self._devices)

    def _bitmap(self, fd, request, size):
        result = bytearray(size)
        self._backend.ioctl(fd, request, result)
        return result

    def _keyboard_capabilities(self, fd):
        event_size = (EV_MAX + 8) // 8
        events = self._bitmap(fd, _eviocgbit(0, event_size), event_size)
        if not _has_bit(events, EV_KEY):
            return None

        key_size = (KEY_MAX + 8) // 8
        keys = self._bitmap(fd, _eviocgbit(EV_KEY, key_size), key_size)
        # Full keyboards expose letter/space keys. Numeric pads expose the
        # keypad block. Pointer buttons begin at 0x100 and match neither.
        full_keyboard = _has_bit(keys, 30) and _has_bit(keys, 57)
        numeric_pad = any(_has_bit(keys, code) for code in range(71, 84))
        return keys if full_keyboard or numeric_pad else None

    def _current_keys(self, fd):
        size = (KEY_MAX + 8) // 8
        return _set_bits(self._bitmap(fd, _eviocgkey(size), size))

    def _add(self, path):
        fd = None
        try:
            fd = self._backend.open(path)
            if self._keyboard_capabilities(fd) is None:
                self._backend.close(fd)
                return
            pressed = self._current_keys(fd)
        except OSError:
            if fd is not None:
                try:
                    self._backend.close(fd)
                except OSError:
                    pass
            return
        self._devices[path] = _Device(fd)
        # Opening or hotplugging never inherits an apparently eligible hold.
        self.state._resync_device(path, pressed)

    def _remove(self, path):
        device = self._devices.pop(path, None)
        if device is None:
            return
        try:
            self._backend.close(device.fd)
        except OSError:
            pass
        self.state.remove_device(path)

    def _rescan(self):
        try:
            paths = set(self._backend.list_devices(self._input_dir))
        except OSError:
            return
        for path in set(self._devices) - paths:
            self._remove(path)
        for path in sorted(paths - set(self._devices)):
            self._add(path)

    def _resync(self, path, device):
        try:
            pressed = self._current_keys(device.fd)
        except OSError:
            self._remove(path)
            return False
        self.state._resync_device(path, pressed)
        return True

    def _event(self, path, device, event_type, code, value, now):
        if device.dropped:
            if event_type == EV_SYN and code == SYN_REPORT:
                device.dropped = False
                return self._resync(path, device)
            return True
        if event_type == EV_SYN and code == SYN_DROPPED:
            device.dropped = True
            self.state.cancel()
        elif event_type == EV_KEY:
            self.state.update(path, code, value, now)
        return True

    def _read_device(self, path, device, now, budget):
        consumed = 0
        calls = 0
        while consumed < budget and calls < budget:
            wanted = (budget - consumed) * INPUT_EVENT.size
            try:
                calls += 1
                chunk = self._backend.read(device.fd, wanted)
            except BlockingIOError:
                break
            except OSError as error:
                if error.errno == errno.EINTR:
                    continue
                self._remove(path)
                break
            if not chunk:
                self._remove(path)
                break
            device.buffer.extend(chunk)
            while (len(device.buffer) >= INPUT_EVENT.size
                   and consumed < budget):
                raw = bytes(device.buffer[:INPUT_EVENT.size])
                del device.buffer[:INPUT_EVENT.size]
                _seconds, _micros, event_type, code, value = INPUT_EVENT.unpack(raw)
                consumed += 1
                if not self._event(path, device, event_type, code, value, now):
                    device.buffer.clear()
                    return consumed
        return consumed

    def poll(self, now):
        """Process bounded pending input and return current overlay visibility."""
        if self._closed:
            return False
        if now >= self._next_scan:
            self._rescan()
            self._next_scan = now + self._scan_interval

        remaining = self._max_events_per_poll
        paths = list(self._devices)
        start = self._poll_cursor % len(paths) if paths else 0
        paths = paths[start:] + paths[:start]
        for path in paths:
            if remaining <= 0:
                break
            device = self._devices.get(path)
            if device is None:
                continue
            remaining -= self._read_device(path, device, now, remaining)
        if paths:
            self._poll_cursor = start + 1
        if remaining <= 0:
            # An unread key on another device could be a release or chord.
            # Hide conservatively until later polls catch up.
            self.state.cancel()
        return self.state.visible(now)

    def close(self):
        """Close all open input descriptors; safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        for path in list(self._devices):
            self._remove(path)
        self.state.cancel()
