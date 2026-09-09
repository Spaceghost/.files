"""Palette cycling for the desktop painting: colour that moves, pictures that do not.

The trick is the one the old indexed-colour machines used. A picture is reduced
to a small palette and stored as indices into it; rotating a run of palette
entries makes every pixel painted with those indices change colour together,
which the eye reads as flow. Nothing is redrawn and nothing moves a pixel,
which is exactly why this is welcome here when a drifting or breathing painting
is not.

Only one run rotates. Rotating the whole palette turns a photograph into a
colour wash; rotating the ramp that a waterfall, a sky or a shadow is painted
in leaves the rock and the trees alone and reads as movement in the water.
Finding that run is this module's real work, because the painting is whatever
the gallery is showing rather than something authored for the effect.

Two knobs, deliberately separate. ``depth`` is the retro one: bits per pixel
before quantising, so 8 posterises hard the way an old display did and 24
leaves the picture alone. ``colors`` is how many palette entries exist at all,
which decides how long a ramp can be and therefore how smooth the cycle looks.
"""
import numpy as np


# Bits per channel for the depths a caller may ask for. 8-bit is the 3-3-2 the
# VGA era used, 16-bit the 5-6-5 of the generation after it, 24-bit untouched.
DEPTHS = {8: (3, 3, 2), 16: (5, 6, 5), 24: (8, 8, 8)}
PALETTE_SIZES = (8, 16, 24, 36)
# A ramp shorter than this cycles as a visible flicker between two or three
# shades rather than as flow.
MIN_RAMP = 4
# How much of the picture a run must paint before rotating it is worth doing.
# Below this the effect is real but nobody sees it.
MIN_COVERAGE = 0.02
# Below this chroma an entry is a grey: shadow, rock, overcast sky, the dark
# mass a painting sits on. Greys are what must hold still, so they are never
# part of a ramp however much of the picture they cover.
GREY_CHROMA = 12
# How far apart two entries' colours may point and still be the same material,
# in degrees around the chroma circle. Wide enough to hold a sky from its cold
# zenith to its warm horizon, narrow enough to keep ochre rock out of blue water.
FAMILY_DEGREES = 40
# Interpolated palettes between one ramp position and the next. Palettes are a
# few dozen bytes, so smoothing the sweep this way costs memory that does not
# round to a megabyte and nothing at all per frame.
SUBSTEPS = 6


def posterise(image, depth):
    """Reduce an RGB array to the given bit depth, keeping full white."""
    if depth not in DEPTHS:
        raise ValueError(f'depth must be one of {sorted(DEPTHS)}')
    channels = []
    for index, bits in enumerate(DEPTHS[depth]):
        channel = image[..., index].astype(np.uint16)
        levels = (1 << bits) - 1
        # Round to the nearest level and stretch back over the full range, so
        # the brightest level stays 255 instead of drifting dark.
        quantised = (channel * levels + 127) // 255
        channels.append(((quantised * 255 + levels // 2) // levels).astype(np.uint8))
    return np.stack(channels, axis=-1)


def _split(box, image):
    """Median-cut one box along its longest channel."""
    pixels = image[box]
    spread = pixels.max(axis=0).astype(np.int16) - pixels.min(axis=0)
    channel = int(np.argmax(spread))
    order = np.argsort(pixels[:, channel], kind='stable')
    middle = len(order) // 2
    return box[order[:middle]], box[order[middle:]]


def quantise(image, colors):
    """Return (indices, palette) for an RGB array, by median cut.

    Median cut is used rather than anything cleverer because it keeps the
    picture's own hues -- a k-means palette drifts toward the average and takes
    the ramps with it, which is the one thing this must not do.
    """
    if colors < 2:
        raise ValueError('a palette needs at least two colours')
    flat = image.reshape(-1, 3)
    # One representative sample is enough to choose a palette and keeps the
    # cut cheap on a large painting; every pixel is mapped to it afterwards.
    sample = flat if len(flat) <= 1 << 18 else flat[::len(flat) // (1 << 18)]
    boxes = [np.arange(len(sample))]
    while len(boxes) < colors:
        widest, size = None, -1
        for position, box in enumerate(boxes):
            if len(box) < 2:
                continue
            pixels = sample[box]
            extent = int((pixels.max(axis=0).astype(np.int16) - pixels.min(axis=0)).max())
            if extent > size:
                widest, size = position, extent
        if widest is None or size <= 0:
            break
        boxes[widest:widest + 1] = _split(boxes[widest], sample)
    palette = np.array([sample[box].mean(axis=0) for box in boxes]).round()
    palette = palette.clip(0, 255).astype(np.uint8)
    # Map every pixel to its nearest palette entry, a slab at a time so the
    # distance matrix never grows past a few tens of megabytes.
    indices = np.empty(len(flat), dtype=np.uint8)
    reference = palette.astype(np.int16)
    for start in range(0, len(flat), 1 << 20):
        chunk = flat[start:start + (1 << 20)].astype(np.int16)
        distance = ((chunk[:, None, :] - reference[None, :, :]) ** 2).sum(axis=2)
        indices[start:start + len(chunk)] = distance.argmin(axis=1)
    return indices.reshape(image.shape[:2]), palette


def _luminance(palette):
    return palette.astype(np.float64) @ np.array([.2126, .7152, .0722])


def _chroma(palette):
    """Return each entry's colour direction and how far it is from grey."""
    values = palette.astype(np.float64)
    vectors = values - values.mean(axis=1, keepdims=True)
    magnitude = np.linalg.norm(vectors, axis=1)
    # The angle around the grey axis, which is what "same colour, different
    # brightness" means: a hue that survives being lightened or darkened.
    angle = np.degrees(np.arctan2(vectors[:, 2] - vectors[:, 1],
                                  vectors[:, 0] - vectors[:, 1]))
    return angle, magnitude


def find_ramp(palette, indices=None, *, minimum=MIN_RAMP):
    """Return the palette entries that should cycle, brightest last.

    Walking the palette in brightness order and cutting at big steps is the
    obvious approach and it is wrong for a painting: a warm picture is one long
    smooth run from its shadows to its highlights, so that method rotates the
    whole palette and turns the painting into a colour wash. What reads as flow
    is one *material* moving while everything else holds, so a ramp here is a
    family of entries pointing the same way off the grey axis -- the ochres of
    firelight, the blues of water -- ordered by brightness.

    Greys are excluded whatever they cover. They are the rock, the shadow and
    the dark mass a painting rests on, and they are exactly what has to stay
    still for the moving part to be legible as movement.
    """
    angle, magnitude = _chroma(palette)
    if indices is None:
        coverage = np.ones(len(palette)) / len(palette)
    else:
        counts = np.bincount(indices.ravel(), minlength=len(palette))
        coverage = counts / max(1, indices.size)
    chromatic = [entry for entry in range(len(palette)) if magnitude[entry] >= GREY_CHROMA]

    best = None
    for centre in chromatic:
        # Angles wrap, so measure the shorter way round before comparing.
        offset = np.abs((angle[chromatic] - angle[centre] + 180) % 360 - 180)
        family = [entry for entry, difference in zip(chromatic, offset)
                  if difference <= FAMILY_DEGREES]
        if len(family) < minimum:
            continue
        share = float(coverage[family].sum())
        if share < MIN_COVERAGE:
            continue
        # Size first, because a long ramp is what makes the cycle smooth;
        # coverage breaks ties so the visible family wins over a hidden one.
        rank = (len(family), share)
        if best is None or rank > best[0]:
            best = (rank, family)
    if best is None:
        return []
    return [int(entry) for entry in
            sorted(best[1], key=lambda entry: _luminance(palette)[entry])]


def cycle_loop(ramp):
    """Return the seamless sequence a ramp is cycled along.

    A painted ramp runs from dark to light and stops. Rotating it plainly makes
    the brightest entry take the darkest colour once per turn, which is a seam
    the eye catches immediately -- the old artists avoided it by authoring
    ramps whose ends already met. A natural gradient has no such courtesy, so
    the ramp is walked up and then back down: every step is one small change,
    the sequence closes on itself, and the picture reads as light sweeping
    across rather than as a palette snapping round.
    """
    ramp = list(ramp)
    if len(ramp) < 3:
        return ramp
    return ramp + ramp[-2:0:-1]


def cycled_palettes(palette, ramp, *, reverse=False, substeps=SUBSTEPS):
    """Return one palette per step of the cycle, moving only ``ramp``.

    The first is the picture as quantised, so switching the cycle off mid-turn
    leaves the painting exactly as it was drawn.

    A ramp's neighbouring shades can be fifty levels apart, and stepping
    straight from one to the next is the stutter the old machines were stuck
    with. Palettes are small and cost nothing to hold, so each step is divided
    into ``substeps`` interpolated palettes and the sweep becomes continuous
    without any extra work per frame.
    """
    if not ramp:
        return [palette.copy()]
    loop = cycle_loop(ramp)
    substeps = max(1, int(substeps))
    values = palette.astype(np.float64)
    result = []
    for step in range(len(loop)):
        for fraction in range(substeps):
            shifted = values.copy()
            offset = -step if reverse else step
            direction = -1 if reverse else 1
            amount = fraction / substeps
            for position, entry in enumerate(ramp):
                near = loop[(position + offset) % len(loop)]
                far = loop[(position + offset + direction) % len(loop)]
                shifted[entry] = values[near] * (1 - amount) + values[far] * amount
            result.append(shifted.round().clip(0, 255).astype(np.uint8))
    return result


def pack(palette):
    """Pack an RGB palette into the 0x00RRGGBB words cairo paints from.

    Cycling one packed word per pixel rather than three bytes is the whole
    difference between an effect that costs three milliseconds a frame and one
    that costs twenty-five, which on this laptop is the difference between
    something that can run all day and something that is heard running.
    """
    values = palette.astype(np.uint32)
    return (values[:, 0] << 16) | (values[:, 1] << 8) | values[:, 2]


def moving_pixels(indices, ramp):
    """Return the flat positions whose colour changes during the cycle.

    Only these are rewritten each frame. On a painting where the ramp is the
    water and the rest is rock, that is a fraction of the picture, which is
    what keeps an effect that runs continuously off the fans.
    """
    if not ramp:
        return np.empty(0, dtype=np.int64)
    return np.flatnonzero(np.isin(indices.ravel(), np.array(ramp, dtype=indices.dtype)))


def prepare(image, *, depth=24, colors=16, reverse=False, substeps=SUBSTEPS):
    """Quantise a painting and return everything needed to cycle it.

    Nothing here is a picture except the base. The cycle is a list of small
    packed palettes and a list of the pixels that move, which is what keeps a
    long smooth cycle from costing hundreds of megabytes: rebuilding a frame is
    one gather and one scatter over the moving pixels, not a stored image.
    """
    reduced = posterise(np.ascontiguousarray(image[..., :3]), depth)
    indices, palette = quantise(reduced, colors)
    ramp = find_ramp(palette, indices)
    moving = moving_pixels(indices, ramp)
    return {
        'shape': indices.shape,
        'base': pack(palette)[indices.ravel()],
        'palette': palette,
        'ramp': ramp,
        'moving': moving,
        'moving_indices': indices.ravel()[moving],
        'palettes': [pack(table) for table in
                     cycled_palettes(palette, ramp, reverse=reverse, substeps=substeps)],
        'coverage': float(len(moving)) / max(1, indices.size),
    }


def apply_step(cycle, step, canvas=None):
    """Write one step of the cycle into a packed canvas and return it.

    ``canvas`` is reused between frames; the pixels that never move are written
    once when it is created and are not touched again.
    """
    if canvas is None:
        canvas = cycle['base'].copy()
    palettes = cycle['palettes']
    if palettes and len(cycle['moving']):
        canvas[cycle['moving']] = palettes[step % len(palettes)][cycle['moving_indices']]
    return canvas
