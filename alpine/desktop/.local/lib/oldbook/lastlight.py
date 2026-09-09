"""How hard the desktop should be breathing as the battery runs out.

Every other power-aware thing on this desktop subtracts. `power_source`'s ladder
sheds blur, then animations, then the edges, so the machine gets quieter exactly
as it gets closer to dying. That leaves nothing saying so. This is the one effect
that runs the other way: it is absent on mains, appears at the warning band and
grows until the battery is gone.

Because it is the warning, it is deliberately absent from `power_source.LADDER`.
An unregistered effect runs at every posture, which is the behaviour a warning
needs -- being shed at `battery-critical` is precisely backwards.

Three channels, one number. `urgency` maps the charge to 0..1 and every channel
is a function of it, so the keys, the screen edges and the backlight always agree
about how bad it is. Nothing here reads the hardware or touches a device; it is
arithmetic, so the daemon's behaviour can be tested against a table of charges
rather than against a dying laptop.
"""
import json
import os
from pathlib import Path

import math

# On by default, unlike every other effect here. The rule that ambient things
# ship off and are opted into exists because eyecandy that arrives unasked is an
# imposition; a warning that ships off is just broken. It is quiet by
# construction instead: above the warning band it draws nothing, runs no frame
# clock and reads one file every twenty seconds.
DEFAULTS = {'enabled': True, 'keys': True, 'edges': True, 'backlight': True}

# The two bands the rest of the desktop already uses, so "low" means one thing
# everywhere, plus a third that only this effect knows about.
WARNING = 25
CRITICAL = 10
TERMINAL = 4

STAGES = ('clear', 'warning', 'critical', 'terminal')

# Breath period in seconds at each end. The keyboard's resting breath is 6.0s;
# starting there means the effect begins as a slight quickening of something
# already present rather than as a new thing switching on.
PERIOD_CALM = 6.0
PERIOD_FRANTIC = 1.15

# The vignette's outer alpha, and how far in it reaches as a fraction of the
# half-diagonal. Both stay modest: this has to be readable *through*.
ALPHA_MAX = 0.62
REACH_MIN = 0.34
REACH_MAX = 0.92

# Backlight wave, as a fraction of the level the daemon found when it started.
# Three percent is visible as a breath on a dim screen and invisible as a flicker.
WAVE_MAX = 0.030
# The wave rides slower than the keys on purpose. Equal periods read as one
# machine twitching; a slight offset reads as two things labouring.
WAVE_PERIOD_SCALE = 1.45

# Seconds to cross the whole 0..1 range. Falling into the warning is quicker
# than climbing out of it: the arrival should be noticed, the recovery should
# just quietly stop having been true.
GLIDE_IN = 2.5
GLIDE_OUT = 9.0


def preferences_path():
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / 'oldbook/lastlight.json'


def preferences(path=None):
    """The three channels, each switchable, and one switch over all of them.

    Split per channel because they are not equally welcome. A vignette is easy
    to read past; a backlight that breathes while you are reading may not be.
    Turning one off must not cost the other two.
    """
    settings = dict(DEFAULTS)
    try:
        record = json.loads((path or preferences_path()).read_text())
    except (OSError, ValueError, AttributeError):
        return settings
    if isinstance(record, dict):
        for key, value in record.items():
            if key in settings and isinstance(value, bool):
                settings[key] = value
    return settings


def _clamp(value, low=0.0, high=1.0):
    return low if value < low else high if value > high else value


def stage(capacity):
    """Which band a charge falls in, or 'clear' above the warning."""
    if capacity is None:
        return 'clear'
    if capacity <= TERMINAL:
        return 'terminal'
    if capacity <= CRITICAL:
        return 'critical'
    if capacity <= WARNING:
        return 'warning'
    return 'clear'


def urgency(capacity, mains=False):
    """0 on mains or above the warning band, rising to 1 at an empty battery.

    The curve is deliberately slow to start. At 25 percent this is barely
    present; the machine should not cry wolf at a quarter tank. It steepens
    through the critical band and is close to full by the terminal one.
    """
    if mains or capacity is None or capacity > WARNING:
        return 0.0
    fallen = (WARNING - capacity) / float(WARNING)
    return _clamp(fallen ** 1.7)


def breath_period(level):
    """Seconds per keyboard breath. Shorter is more frantic."""
    return PERIOD_CALM + (PERIOD_FRANTIC - PERIOD_CALM) * _clamp(level)


def vignette(level):
    """Outer alpha and how far the darkness reaches inward.

    Alpha and reach grow together, so the corners go first and the black closes
    in rather than the whole frame fading uniformly. Alpha is what the QML
    animates; keeping the geometry in one number lets the shader stay trivial.
    """
    level = _clamp(level)
    return {
        'alpha': round(ALPHA_MAX * level, 4),
        'reach': round(REACH_MAX - (REACH_MAX - REACH_MIN) * level, 4),
    }


def wave(level, period=None):
    """Backlight swing as a fraction of the base level, and its period."""
    level = _clamp(level)
    period = breath_period(level) if period is None else period
    return {
        'amplitude': round(WAVE_MAX * level, 5),
        'period': round(period * WAVE_PERIOD_SCALE, 3),
    }


def glide(current, target, elapsed):
    """Move `current` toward `target` at a bounded rate, and never overshoot.

    A charge reading jumps in whole percent, and the posture jumps in bands. Both
    would step the effect if they drove it directly. Gliding is also what makes
    charging read as the inverse of dying rather than as an abrupt cancellation:
    the same code runs, only the direction changes.
    """
    if elapsed <= 0:
        return current
    span = GLIDE_IN if target > current else GLIDE_OUT
    step = elapsed / span
    if abs(target - current) <= step:
        return target
    return current + math.copysign(step, target - current)


def describe(capacity, mains, level):
    """The whole published state for one moment, for the surface and for `status`."""
    return {
        'capacity': capacity,
        'mains': bool(mains),
        'stage': 'clear' if mains else stage(capacity),
        'target': round(urgency(capacity, mains), 4),
        'level': round(_clamp(level), 4),
        'breath_period': round(breath_period(level), 3),
        'vignette': vignette(level),
        'wave': wave(level),
    }
