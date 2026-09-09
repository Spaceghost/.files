"""A fixed band at the caption's edge, so hovering never resizes a window.

The strip re-places itself for whatever holds focus, and `focus_follows_mouse`
means that happens every time the pointer crosses a window border. While the
strip reserved its own space, the reservation came and went with it: focusing a
floating window attached the caption to that window and released the workspace
band, focusing a tiled window took the band back, and every tiled window on the
output was resized by the band's thickness twice per pass of the mouse. A
terminal answers a resize by re-flowing its grid, which is the text jumping
under the pointer.

The two jobs are separated here. One invisible surface holds the reservation and
never changes -- same edge, same thickness, whatever has focus and whatever the
caption says -- and the caption itself reserves nothing and draws inside the
band it is now guaranteed. Nothing the pointer does can change the usable area,
so nothing re-flows.

The caption sits inside the band by anchoring within the usable area and then
stepping back out over it: a zero exclusive zone keeps the perpendicular extent
correct against the other panels, and a negative margin on the anchored edge
puts the strip back where it has always been drawn.

Thickness is measured once per appearance from a reference caption holding every
glyph class the strip can draw, never from the caption currently on screen: a
Nerd Font branch glyph is two pixels taller than plain Latin in the same face,
so a band that followed the live caption would resize windows whenever the
pointer moved from a repository to a plain window.
"""

EDGE_MARGIN = 5
# A measurement below this is a failed measurement, not a thin caption, and a
# band above it would eat the screen over a font the strip cannot really use.
MINIMUM = 24
MAXIMUM = 160
# Ascender, descender, both separators, a Nerd Font branch glyph and a powerline
# divider: whatever the caption ends up saying, it is no taller than this line.
REFERENCE = 'Ag › ·     10/24'
# Ordinary caption text, for the average character width the budget divides by.
SAMPLE = 'abcdefghijklmnopqrstuvwxyz0123456789 ·›/~.-'
# Below this the caption is answering in fragments; ellipsis can take over.
MINIMUM_BUDGET = 16


def band_edge(preferred):
    """The band follows the saved edge, and only ever an edge the strip uses."""
    if preferred not in ('bottom', 'right'):
        raise ValueError('Decoration edge must be bottom or right')
    return preferred


def band_anchors(edge):
    """Anchor the full edge: a layer surface reserves only across a whole side."""
    return ('BOTTOM', 'LEFT', 'RIGHT') if band_edge(edge) == 'bottom' else ('RIGHT', 'TOP', 'BOTTOM')


def band_thickness(measured, margin=EDGE_MARGIN):
    """Reserve the caption's own natural size plus the gap it floats in."""
    try:
        # A failed measurement arrives as anything at all; not a number, not
        # finite, not positive. All of them mean "use the floor".
        value = int(float(measured))
    except (TypeError, ValueError, OverflowError):
        value = 0
    return max(MINIMUM, min(MAXIMUM, value + max(0, int(margin))))


def caption_margin(thickness, margin=EDGE_MARGIN):
    """How far the caption steps back over the band it is not allowed to reserve.

    With no band the caption keeps its ordinary gap; with one it must cross the
    reservation to stay where the user has always seen it, which is a negative
    margin of exactly the part of the band it does not occupy.
    """
    return int(margin) - max(0, int(thickness))


def caption_offset(thickness, matching=True, margin=EDGE_MARGIN):
    """The zone and anchored-edge margin a caption uses, given its band.

    Its own band: reserve nothing, respect the other panels' reservations, and
    step back over this one. A band on the other edge — which only happens while
    fullscreen borrows the bottom from a right-edge strip — is nothing to do
    with this caption, so it takes the whole output rather than being pushed
    sideways out of a reservation it is not sitting in. No band at all leaves
    the ordinary gap and still reserves nothing.
    """
    thickness = max(0, int(thickness))
    if thickness and matching:
        return 0, caption_margin(thickness, margin)
    return (-1 if thickness else 0), int(margin)


def caption_insets(output_rect, usable_rect, edge, thickness, matching, margin=EDGE_MARGIN):
    """Margins putting a caption that declines reservations where one that respected them sat.

    A caption normally keeps a zero exclusive zone, so the compositor seats it
    inside the usable area, and then steps back over its own band with a
    negative margin. GTK4's layer-shell binding cannot carry a negative margin
    at all -- the extent it asks the compositor for collapses to zero and the
    surface is given an arbitrary default -- so the caption declines every
    reservation instead and is measured from the raw output edge.

    Declining them all means the other panels' reservations have to be added
    back by hand, which is what this returns: for each side, whatever is held
    back there plus the ordinary gap. The caption's own band is the one
    exception, subtracted on the edge it sits on, because drawing inside that
    band is the whole reason the caption cannot simply respect them all.

    Rectangles are Sway's: the output's own, and the visible workspace's, which
    is the usable area after every exclusive zone on that output.
    """
    if edge not in ('bottom', 'right'):
        raise ValueError('Decoration edge must be bottom or right')
    margin = max(0, int(margin))
    thickness = max(0, int(thickness))
    held = {}
    for side, value in (
            ('LEFT', usable_rect['x'] - output_rect['x']),
            ('TOP', usable_rect['y'] - output_rect['y']),
            ('RIGHT', (output_rect['x'] + output_rect['width'])
                      - (usable_rect['x'] + usable_rect['width'])),
            ('BOTTOM', (output_rect['y'] + output_rect['height'])
                       - (usable_rect['y'] + usable_rect['height']))):
        held[side] = max(0, int(value))
    own = 'BOTTOM' if edge == 'bottom' else 'RIGHT'
    if matching:
        # Only this caption's band is stepped over; anything else on that side
        # is another panel and is still respected.
        held[own] = max(0, held[own] - thickness)
    return {side: value + margin for side, value in held.items()}


def character_budget(span, character_width, controls=0):
    """How much caption fits along `span`, in characters, after the buttons.

    Approximate on purpose: it decides which whole ideas the line can afford,
    and Pango's ellipsis still catches whatever the estimate got wrong.
    """
    try:
        width = float(character_width)
        room = float(span) - max(0.0, float(controls))
    except (TypeError, ValueError, OverflowError):
        return None
    if not width > 0 or not room == room or room in (float('inf'), float('-inf')):
        return None
    return max(MINIMUM_BUDGET, int(max(0.0, room) / width))


def band_measurement(measures, edge):
    """The thickness for one edge, from a caption drawn along that edge alone.

    A bottom caption's height is no measurement of how wide a vertical strip is,
    and fullscreen borrows the bottom while the band stays on the saved edge. An
    edge no caption is currently drawn along keeps the floor rather than
    borrowing the other edge's number, because borrowing it moves a reservation
    that the whole band exists to hold still.
    """
    found = (measures or {}).get(band_edge(edge))
    return found if isinstance(found, int) and found > 0 else band_thickness(0)


def band_region(output_rect, edge, thickness):
    """The strip of one output the band holds, in the tree's global coordinates.

    Layer surfaces report output-local extents; containers report global ones,
    so the reservation has to be restated in the containers' terms before any
    window can be compared against it.
    """
    edge = band_edge(edge)
    try:
        x, y = int(output_rect['x']), int(output_rect['y'])
        width, height = int(output_rect['width']), int(output_rect['height'])
        thickness = max(0, int(thickness))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if thickness <= 0 or width <= 0 or height <= 0:
        return None
    if edge == 'bottom':
        thickness = min(thickness, height)
        return {'x': x, 'y': y + height - thickness, 'width': width, 'height': thickness}
    thickness = min(thickness, width)
    return {'x': x + width - thickness, 'y': y, 'width': thickness, 'height': height}


def band_clearance(rect, region, edge, bounds=None):
    """Where a floating window has to sit to leave the band alone, or None.

    The exclusive zone is the compositor's whole answer, and it only covers
    tiled layout. Sway clamps no floating move, and `arrange_workspace` re-fixes
    floating coordinates only when the workspace *origin* moves -- a bottom
    reservation moves the workspace's height and never its origin -- so a float
    that was already sitting there when the band appeared is left exactly where
    it was, on top of it, forever.

    The correction is the smallest one that clears the reservation, and it never
    pushes a window off the far side of `bounds`: a window too tall to fit above
    the band goes as far up as it can and stops, which is both the best that can
    be done for it and the reason the correction settles instead of repeating.
    """
    edge = band_edge(edge)
    if not region:
        return None
    try:
        x, y = int(rect['x']), int(rect['y'])
        width, height = int(rect['width']), int(rect['height'])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if width <= 0 or height <= 0:
        return None
    if edge == 'bottom':
        if y + height <= int(region['y']):
            return None
        wanted = int(region['y']) - height
        if bounds:
            wanted = max(wanted, int(bounds.get('y', wanted)))
        return None if wanted == y else (x, wanted)
    if x + width <= int(region['x']):
        return None
    wanted = int(region['x']) - width
    if bounds:
        wanted = max(wanted, int(bounds.get('x', wanted)))
    return None if wanted == x else (wanted, y)


def band_plan(placements, edge, thickness, enabled=True):
    """One reservation per output, from the saved edge rather than the live one.

    Fullscreen forces the caption to the bottom, but a fullscreen window ignores
    exclusive zones anyway: moving the band to follow that override would resize
    every ordinary window on the way in and again on the way out for no gain.
    """
    if not enabled or thickness <= 0:
        return {}
    edge = band_edge(edge)
    return {name: {'edge': edge, 'thickness': int(thickness)} for name in placements}
