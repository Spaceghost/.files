"""Frame-rate independent springs for decoration geometry and opacity."""

import math


_RECT_KEYS = ('x', 'y', 'width', 'height')
_MAX_ELAPSED = 0.050


def advance(value, velocity, target, elapsed, response=0.10, tolerance=0.05):
    """Advance one critically damped spring without passing its target.

    ``response`` is approximately the time in seconds to cover 90% of a move
    from rest. Preserve the returned velocity between frames. The exact spring
    solution keeps normal animation independent of refresh rate; a long frame
    gap is capped so resuming after a stall does not cause a visual jump.
    """
    if response <= 0 or tolerance < 0:
        raise ValueError('response must be positive and tolerance nonnegative')
    offset = value - target
    if offset == 0:
        return target, 0.0
    if elapsed <= 0:
        return value, velocity
    elapsed = min(elapsed, _MAX_ELAPSED)
    # A reversed target should not let old momentum pull the decoration away.
    if velocity * offset > 0:
        velocity = 0.0
    rate = 4.0 / response
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
                 tolerance=0.05):
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
            response=response, tolerance=tolerance)
    return rect, speeds, all(rect[key] == target[key] for key in _RECT_KEYS)
