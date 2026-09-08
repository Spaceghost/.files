"""The Apple SMC ambient light sensor, and the maths that follows a room.

Shared, side-effect free logic so both the display and, in time, the keyboard
can read the same sensor the same way. The keyboard light currently carries its
own copy of this reasoning; it can import from here once its own worker is next
touched.

The sensor is `/sys/devices/platform/applesmc.*/light` and reads `(left,right)`.
Newer MacBooks put a single ten-bit value in the left slot and leave the right
at zero, so the reading is the larger of the two.

Rooms are read on a logarithmic scale because perceived brightness is: the step
from a candle to a lamp matters far more than the step from a bright office to a
brighter one. Readings are smoothed towards the new sample rather than snapped,
and a hysteresis band keeps a passing cloud or a hand near the sensor from
starting a fade.

The display and the keyboard want opposite things from the same number. A dark
room wants a bright keyboard and a dim screen; a sunlit desk wants the keyboard
off and the screen at full. `display_fraction` implements the screen half.
"""
import glob
import math
import re

SENSOR_GLOB = '/sys/devices/platform/applesmc.*/light'
SENSOR_INTERVAL = 2.0
# Matching the keyboard light's constants so the two agree on what a room is.
DARK = 3
BRIGHT = 240
SMOOTHING = 0.5
HYSTERESIS = 0.15
FADE_SECONDS = 1.2
# Never black the panel out on the strength of a sensor reading.
FLOOR = 0.15
OFFSET_LIMIT = 0.4
READING = re.compile(r'^\s*\(?\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)?\s*$')


def sensor_paths(pattern=SENSOR_GLOB):
    return sorted(glob.glob(pattern))


def parse_reading(text):
    """The ambient reading from one sysfs line, or None if it is not one."""
    match = READING.match(text or '')
    if not match:
        return None
    left = int(match.group(1))
    right = int(match.group(2)) if match.group(2) is not None else 0
    return max(left, right)


def read_sensor(paths):
    """The first readable sensor's value, or None when no sensor answers."""
    for path in paths:
        try:
            with open(path) as handle:
                value = parse_reading(handle.read())
        except (OSError, ValueError):
            continue
        if value is not None:
            return value
    return None


def log_sample(reading):
    """Readings live on a log scale; zero is a legitimate pitch-dark reading."""
    return math.log(max(0, reading) + 1)


def smooth(previous, sample, alpha=SMOOTHING):
    if previous is None:
        return sample
    return previous + alpha * (sample - previous)


def should_retarget(filtered, reference, hysteresis=HYSTERESIS):
    """True when the room has moved far enough to be worth a fade."""
    return reference is None or abs(filtered - reference) > hysteresis


def position(filtered, dark=DARK, bright=BRIGHT):
    """Where a smoothed log reading sits between a dark room and a bright one."""
    low, high = log_sample(dark), log_sample(bright)
    if high <= low:
        return 1.0
    return min(1.0, max(0.0, (filtered - low) / (high - low)))


def display_fraction(filtered, offset=0.0, floor=FLOOR, dark=DARK, bright=BRIGHT):
    """The panel brightness a room deserves, as a fraction of the maximum."""
    fraction = floor + (1.0 - floor) * position(filtered, dark, bright)
    return min(1.0, max(floor, fraction + offset))


def clamp_offset(value, limit=OFFSET_LIMIT):
    return min(limit, max(-limit, value))


def learned_offset(previous, observed_fraction, expected_fraction, limit=OFFSET_LIMIT):
    """The correction implied by a brightness the user set by hand.

    The whole difference is taken, not a fraction of it: the user moved the
    display deliberately, and the next room change should start from what they
    chose rather than drift back towards the curve.
    """
    return clamp_offset((previous or 0.0) + (observed_fraction - expected_fraction), limit)


def eased(progress):
    """The cosine ease the rest of the desktop's motion uses; settles exactly."""
    progress = min(1.0, max(0.0, progress))
    return (1 - math.cos(math.pi * progress)) / 2


def fade_value(start, target, progress):
    return int(round(start + (target - start) * eased(progress)))
