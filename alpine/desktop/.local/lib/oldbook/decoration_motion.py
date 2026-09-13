"""Frame-rate independent springs for decoration geometry and opacity."""

import math


_RECT_KEYS = ('x', 'y', 'width', 'height')
_MAX_ELAPSED = 0.050


def advance(value, velocity, target, elapsed, response=0.10, tolerance=0.05,
            damping=1.0):
    """Advance one spring, critically damped unless asked to settle.

    ``response`` is approximately the time in seconds to cover 90% of a move
    from rest. Preserve the returned velocity between frames. The exact spring
    solution keeps normal animation independent of refresh rate; a long frame
    gap is capped so resuming after a stall does not cause a visual jump.

    ``damping`` of 1 is the critically damped spring everything that follows a
    window uses: it never passes its target, because a caption chasing a
    dragged window must not wobble around it. Below 1 the spring is
    underdamped and does overshoot, which is wanted in exactly one place -- a
    strip released from a window, arriving in the band with enough of a settle
    to read as a landing rather than a stop. The overshoot is a fixed fraction
    of the distance travelled, so a long flight rebounds further than a short
    one, which is what a thrown object does.
    """
    if response <= 0 or tolerance < 0:
        raise ValueError('response must be positive and tolerance nonnegative')
    if not 0 < damping <= 1:
        raise ValueError('damping must be above zero and at most one')
    offset = value - target
    if offset == 0:
        return target, 0.0
    if elapsed <= 0:
        return value, velocity
    elapsed = min(elapsed, _MAX_ELAPSED)
    rate = 4.0 / response
    if damping < 1:
        # Underdamped: the exact solution of the same spring with a lighter
        # brake. Momentum is deliberately kept through a retarget here, since
        # carrying it is the whole point of a settle.
        ring = rate * math.sqrt(1 - damping * damping)
        decay = math.exp(-damping * rate * elapsed)
        rise = (velocity + damping * rate * offset) / ring
        turn, swing = math.cos(ring * elapsed), math.sin(ring * elapsed)
        position = target + decay * (offset * turn + rise * swing)
        speed = decay * ((rise * ring - damping * rate * offset) * turn
                         - (offset * ring + damping * rate * rise) * swing)
        if (abs(position - target) <= tolerance
                and abs(speed) <= tolerance / response):
            return target, 0.0
        return position, speed
    # A reversed target should not let old momentum pull the decoration away.
    if velocity * offset > 0:
        velocity = 0.0
    change = velocity + rate * offset
    decay = math.exp(-rate * elapsed)
    position = target + (offset + change * elapsed) * decay
    speed = (velocity - rate * change * elapsed) * decay
    if (position - target) * offset <= 0:
        return target, 0.0
    if (abs(position - target) <= tolerance
            and abs(speed) <= tolerance / response):
        return target, 0.0
    return position, speed


def advance_rect(current, velocity, target, elapsed, response=0.10,
                 tolerance=0.05, damping=1.0):
    """Return ``(rect, velocity, settled)`` for x/y/width/height mappings.

    An empty velocity mapping starts at rest. Values stay fractional until the
    caller rounds them for native positioning, and settled coordinates equal
    their targets exactly.
    """
    rect = {}
    speeds = {}
    for key in _RECT_KEYS:
        rect[key], speeds[key] = advance(
            current[key], velocity.get(key, 0.0), target[key], elapsed,
            response=response, tolerance=tolerance, damping=damping)
    return rect, speeds, all(rect[key] == target[key] for key in _RECT_KEYS)


def approach_signs(departure, target, tolerance=1.0):
    """Which way each coordinate of a flight has to go, as -1, 0 or 1.

    Taken once, when the flight begins; contact() reads it to tell a strip
    that has passed its target from one still on its way. A coordinate that
    starts within ``tolerance`` of home has nowhere to go and is 0.
    """
    signs = {}
    for key in _RECT_KEYS:
        offset = departure[key] - target[key]
        signs[key] = 0 if abs(offset) <= tolerance else (1 if offset > 0 else -1)
    return signs


def contact(rect, target, signs, tolerance=1.0):
    """Whether a flight has reached its target for the first time.

    The moment of impact is when the strip first gets home, not when the
    rebound after it has died away: a settling spring passes its target and
    comes back, and advance() only reports it settled once it is inside the
    tolerance *and* nearly still, a fifth of a second or more after the strip
    was seen to arrive. So a coordinate counts as arrived once it is within
    ``tolerance`` of its target or already past it, judged against the sign it
    set out with, and the strip has made contact when every coordinate that
    had anywhere to go has arrived. All four ride the same spring from rest,
    so they arrive together; the test is per coordinate only so a flight
    retargeted on the way cannot report contact early on a stale sign.
    """
    for key, sign in signs.items():
        if sign == 0:
            continue
        offset = rect[key] - target[key]
        if abs(offset) > tolerance and offset * sign > 0:
            return False
    return True
