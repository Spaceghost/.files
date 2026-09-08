"""The desktop's air supply: read the keyboard's breath, share it with the scene.

The keyboard light publishes `air.json` in the session runtime directory while
it is breathing. It is the single source of the breath: the volume of the lungs
(a quarter full at rest, filled by keystrokes), the phase of the current cycle,
the instantaneous normalised brightness of the breath curve, and the tempo. The
painting and the caption strip follow that curve, so one breath moves the whole
desktop instead of each surface inventing its own rhythm.

The reader is deliberately cheap. `Watcher` stats the file and only parses when
it actually changed, so a 20 Hz publisher costs a stat per poll and a parse per
frame that matters. Everything here is importable without GTK, so the maths and
the staleness rules can be tested without a display.
"""
import json
import math
import os
from pathlib import Path

FILENAME = 'air.json'
# A breath older than this is a worker that stopped without saying so.
FRESH_SECONDS = 0.5
BREATHING_MODES = ('breathing', 'breathe-air', 'last-breath')
# The keyboard's lungs rest a quarter full; fullness measures the sips above it.
BASELINE_VOLUME = 0.25
# How far the painting swells: a hint at rest, still restrained at full lungs.
REST_AMPLITUDE = 0.006
FULL_AMPLITUDE = 0.018
# The caption's accent glow, from its resting wash to a full breath.
CAPTION_LOW = 0.06
CAPTION_HIGH = 0.22
# Quantising the caption keeps the stylesheet reload rate to a few per second.
CAPTION_STEPS = 24
PREFERENCES = 'breath.json'
DEFAULT_PREFERENCES = {'wallpaper': True, 'caption': True}


def runtime_directory():
    runtime = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    return Path(runtime) / 'oldbook'


def air_path():
    return runtime_directory() / FILENAME


def preferences_path():
    config = os.environ.get('XDG_CONFIG_HOME') or (Path.home() / '.config')
    return Path(config) / 'oldbook' / PREFERENCES


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def parse_air(data, now):
    """Validate one published record; None when it is absent, stale or not breathing.

    The file is written by this user's own worker, but a half-written or
    abandoned record must never move the desktop, so every field is checked and
    an old timestamp counts as no breath at all.
    """
    try:
        record = json.loads(data)
    except (TypeError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    mode = record.get('mode')
    if mode not in BREATHING_MODES:
        return None
    try:
        updated = float(record['updated'])
        volume = float(record['volume'])
        phase = float(record['phase'])
        breath = float(record['breath'])
        tempo = float(record['tempo_seconds'])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (updated, volume, phase, breath, tempo)):
        return None
    if now - updated > FRESH_SECONDS or updated - now > FRESH_SECONDS:
        return None
    return {'mode': mode, 'updated': updated, 'volume': clamp(volume),
            'phase': clamp(phase), 'breath': clamp(breath),
            'tempo_seconds': max(0.1, tempo)}


def fullness(air):
    """How far above the resting quarter the lungs are filled, 0 to 1."""
    if not air:
        return 0.0
    return clamp((air['volume'] - BASELINE_VOLUME) / (1.0 - BASELINE_VOLUME))


def wallpaper_scale(air, rest=REST_AMPLITUDE, full=FULL_AMPLITUDE):
    """Scale for the painting: 1.0 at the bottom of every breath, swelling on air."""
    if not air:
        return 1.0
    amplitude = rest + (full - rest) * fullness(air)
    return 1.0 + amplitude * air['breath']


def caption_alpha(air, low=CAPTION_LOW, high=CAPTION_HIGH):
    """Accent wash behind the caption's brand button; the resting value without air.

    Only the keystroke-fed breath moves the caption: the plain six-second breath
    and the last breath before the lock leave the strip alone, so the pulse means
    "you are typing" rather than "a light is on somewhere".
    """
    if not air or air['mode'] != 'breathe-air':
        return low
    return low + (high - low) * clamp(air['breath'])


def quantise(value, steps=CAPTION_STEPS):
    """Round to a step so a stylesheet is rewritten a few times a second, not sixty."""
    if steps <= 0:
        raise ValueError('quantise needs a positive number of steps')
    return round(value * steps) / steps


def read_preferences(path=None):
    """User switches for the breath; anything unreadable keeps both halves on."""
    try:
        record = json.loads(Path(path or preferences_path()).read_text())
    except (OSError, ValueError):
        return dict(DEFAULT_PREFERENCES)
    if not isinstance(record, dict):
        return dict(DEFAULT_PREFERENCES)
    return {key: bool(record.get(key, default))
            for key, default in DEFAULT_PREFERENCES.items()}


def write_preferences(values, path=None):
    """Save the switches atomically; returns the stored mapping."""
    target = Path(path or preferences_path())
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stored = {key: bool(values.get(key, default))
              for key, default in DEFAULT_PREFERENCES.items()}
    temporary = target.with_name(target.name + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(stored, sort_keys=True) + '\n')
    temporary.replace(target)
    return stored


class Watcher:
    """Read a small JSON file only when it changed, from its stat alone."""

    def __init__(self, path, parse=None):
        self.path = Path(path)
        self.parse = parse
        self.signature = None
        self.value = None

    def stat_signature(self):
        try:
            info = self.path.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size, info.st_ino)

    def poll(self, now=None, force=False):
        """Return the parsed payload, re-reading only when the file moved on."""
        signature = self.stat_signature()
        if signature is None:
            self.signature, self.value = None, None
            return None
        if force or signature != self.signature:
            self.signature = signature
            try:
                data = self.path.read_text()
            except OSError:
                self.value = None
                return None
            self.value = self.parse(data, now) if self.parse is not None else data
        return self.value


class AirWatcher(Watcher):
    """A watcher for the breath itself; staleness is re-checked on every poll."""

    def __init__(self, path=None):
        super().__init__(path or air_path(), parse=None)

    def poll(self, now=None, force=False):
        import time as _time
        moment = _time.time() if now is None else now
        data = super().poll(moment, force=force)
        if data is None:
            return None
        # The record can go stale without the file changing, so parse against
        # the current moment rather than trusting the cached result.
        return parse_air(data, moment)


class Smoother:
    """Exponential approach with exact settling and no overshoot.

    `response` is roughly the time to cover most of a move. A long frame gap is
    capped so a stalled compositor resumes without a jump, and a value inside
    the tolerance snaps to the target so animation can stop entirely.
    """

    MAX_ELAPSED = 0.05

    def __init__(self, value=1.0, response=0.08, tolerance=1e-4):
        if response <= 0 or tolerance < 0:
            raise ValueError('response must be positive and tolerance nonnegative')
        self.value = float(value)
        self.response = float(response)
        self.tolerance = float(tolerance)

    def advance(self, target, elapsed):
        """Step toward `target`; returns (value, settled)."""
        target = float(target)
        if elapsed <= 0:
            return self.value, self.value == target
        if abs(self.value - target) <= self.tolerance:
            self.value = target
            return self.value, True
        step = min(float(elapsed), self.MAX_ELAPSED)
        self.value += (target - self.value) * (1.0 - math.exp(-step / self.response))
        if abs(self.value - target) <= self.tolerance:
            self.value = target
            return self.value, True
        return self.value, False
