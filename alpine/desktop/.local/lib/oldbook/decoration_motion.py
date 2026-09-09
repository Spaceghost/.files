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
