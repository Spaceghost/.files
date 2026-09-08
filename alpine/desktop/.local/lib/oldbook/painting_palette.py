"""Choose the theme accent that suits the painting on screen.

The desktop's accent is never sampled from the artwork: a colour lifted out of a
painting rarely sits well beside charcoal chrome, and a theme is a designed set
of colours rather than a swatch pile. Instead the painting is reduced to a
weighted hue signature and that signature elects one of the *theme's own* accent
candidates. A warm firelit scene lands on amber or burnt orange, a nocturne on
blue-grey or aqua, and a picture with no chromatic opinion keeps the theme's
declared accent.

The maths runs in OKLab, whose hue angles are perceptually even, so a
histogram bin near orange covers about as much apparent colour as one near
blue. Weighting is deliberately simple and explainable: each pixel counts by its
chroma times its lightness, which discounts both the charcoal background and the
near-black shadows that fill a chiaroscuro painting.

Each histogram bin then goes to whichever candidate sits nearest it on the hue
circle, and the candidate holding the largest share wins. That partition is
deliberate: scoring every candidate with a soft kernel quietly favours whichever
one has the most neighbours, which on a six-colour wheel means amber wins even
pictures it has no business winning. A share is also a plain number to read in
the record, being the fraction of the painting's colour nearest that accent.
"""
import json
import math
import re

HEX = re.compile(r'#[0-9a-fA-F]{6}')
# Red stays out: the desktop reserves it for urgency, never for decoration.
ACCENT_KEYS = ('yellow', 'orange', 'aqua', 'green', 'blue', 'purple')
BINS = 72
# Below this mean chroma the picture is grey enough to have no opinion at all.
NEUTRAL_CHROMA = 0.012
# A pixel this dark says more about the shadow than about the palette.
LIGHTNESS_FLOOR = 0.12
# A winner must own a third of the painting's colour. Below that the picture is
# arguing with itself and the theme's declared accent is the better answer.
MIN_SHARE = 0.34
# A companion colour needs real presence before it earns the secondary slot.
SECONDARY_SHARE = 0.06


def _srgb_to_linear(channel):
    import numpy
    return numpy.where(channel <= 0.04045, channel / 12.92,
                       ((channel + 0.055) / 1.055) ** 2.4)


def oklab(rgb):
    """sRGB rows in 0..1 to OKLab rows; Ottosson's matrices, vectorised."""
    import numpy
    linear = _srgb_to_linear(numpy.asarray(rgb, dtype=numpy.float64))
    red, green, blue = linear[..., 0], linear[..., 1], linear[..., 2]
    long_ = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    long_, medium, short = numpy.cbrt(long_), numpy.cbrt(medium), numpy.cbrt(short)
    lightness = 0.2104542553 * long_ + 0.7936177850 * medium - 0.0040720468 * short
    green_red = 1.9779984951 * long_ - 2.4285922050 * medium + 0.4505937099 * short
    blue_yellow = 0.0259040371 * long_ + 0.7827717662 * medium - 0.8086757660 * short
    return numpy.stack([lightness, green_red, blue_yellow], axis=-1)


def chroma_hue(lab):
    """Chroma and hue angle (radians, 0..2pi) for OKLab rows."""
    import numpy
    chroma = numpy.hypot(lab[..., 1], lab[..., 2])
    hue = numpy.arctan2(lab[..., 2], lab[..., 1]) % (2 * math.pi)
    return chroma, hue


def colour_rows(value):
    """A #rrggbb string as one sRGB row in 0..1."""
    text = value.strip()
    return [int(text[index:index + 2], 16) / 255.0 for index in (1, 3, 5)]


def load_pixels(path, edge=96):
    """Down-sample a painting to at most `edge` on its long side, as sRGB rows."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf
    import numpy
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), edge, edge, True)
    channels = pixbuf.get_n_channels()
    width, height, stride = pixbuf.get_width(), pixbuf.get_height(), pixbuf.get_rowstride()
    raw = numpy.frombuffer(pixbuf.get_pixels(), dtype=numpy.uint8)
    # The last row may be short: a pixbuf only guarantees width*channels there.
    usable = stride * (height - 1) + width * channels
    rows = numpy.zeros((height, stride), dtype=numpy.uint8)
    flat = rows.reshape(-1)
    flat[:usable] = raw[:usable]
    pixels = rows[:, :width * channels].reshape(height, width, channels)
    return pixels[..., :3].reshape(-1, 3).astype(numpy.float64) / 255.0


def signature(rows):
    """Weighted hue histogram plus the summary statistics behind the choice."""
    import numpy
    lab = oklab(rows)
    chroma, hue = chroma_hue(lab)
    lightness = lab[..., 0]
    visible = lightness > LIGHTNESS_FLOOR
    # Colour counts by how coloured and how lit it is: the charcoal ground and
    # the shadows fall away without a hard mask that would ignore a dim ember.
    weight = numpy.where(visible, chroma * lightness, 0.0)
    total = float(weight.sum())
    histogram = numpy.zeros(BINS)
    if total > 0:
        index = numpy.minimum((hue / (2 * math.pi) * BINS).astype(int), BINS - 1)
        histogram = numpy.bincount(index, weights=weight, minlength=BINS)[:BINS]
        histogram = histogram / total
    lit = int(visible.sum())
    mean_chroma = float(chroma[visible].mean()) if lit else 0.0
    return {'histogram': [float(value) for value in histogram],
            'mean_chroma': mean_chroma,
            'mean_lightness': float(lightness.mean()),
            'lit_fraction': lit / max(1, lightness.size),
            'weight': total / max(1, lightness.size)}


def candidates(theme):
    """The theme's own accent choices, in descriptor order."""
    palette = theme.get('palette') if isinstance(theme.get('palette'), dict) else {}
    names = theme.get('accent_candidates')
    if not isinstance(names, (list, tuple)) or not names:
        names = ACCENT_KEYS
    chosen = []
    for name in names:
        value = palette.get(name) if isinstance(name, str) else None
        if isinstance(value, str) and HEX.fullmatch(value.strip()):
            chosen.append((name, value.strip().lower()))
    return chosen


def default_accent(theme):
    palette = theme.get('palette') if isinstance(theme.get('palette'), dict) else {}
    for key in ('accent', 'yellow', 'orange', 'foreground'):
        value = palette.get(key)
        if isinstance(value, str) and HEX.fullmatch(value.strip()):
            return value.strip().lower()
    return None


def separation(first, second):
    """Shortest angle between two hues, in radians."""
    gap = abs(first - second) % (2 * math.pi)
    return min(gap, 2 * math.pi - gap)


def shares(histogram, hues):
    """Fraction of the painting's colour nearest each candidate hue."""
    result = {name: 0.0 for name in hues}
    for index, weight in enumerate(histogram):
        if not weight:
            continue
        centre = (index + 0.5) / BINS * 2 * math.pi
        nearest = min(hues, key=lambda name: (separation(hues[name], centre), name))
        result[nearest] += weight
    return result


def choose(sig, theme):
    """Elect an accent and a secondary from the theme's candidates.

    Returns the two colours and the scoring detail, so the record explains
    itself later without re-running the analysis.
    """
    fallback = default_accent(theme)
    options = candidates(theme)
    if not options:
        return {'accent': fallback, 'accent_secondary': fallback,
                'reason': 'theme declares no accent candidates', 'scores': {}}
    hues = {}
    for name, value in options:
        lab = oklab([colour_rows(value)])[0]
        _, hue = chroma_hue(lab)
        hues[name] = float(hue)
    scores = {name: shares(sig['histogram'], hues)[name] for name, _ in options}
    rounded = {name: round(value, 6) for name, value in scores.items()}
    colours = dict(options)
    ranked = sorted(scores, key=lambda name: (-scores[name], name))
    accent = ranked[0]
    if sig['mean_chroma'] < NEUTRAL_CHROMA:
        return {'accent': fallback, 'accent_secondary': fallback,
                'reason': 'painting is close to grey', 'scores': rounded}
    if scores[accent] < MIN_SHARE:
        return {'accent': fallback, 'accent_secondary': fallback,
                'reason': 'no colour holds a third of the painting', 'scores': rounded}
    secondary = accent
    for name in ranked[1:]:
        if scores[name] >= SECONDARY_SHARE:
            secondary = name
            break
    else:
        if fallback and fallback != colours[accent]:
            return {'accent': colours[accent], 'accent_secondary': fallback,
                    'accent_name': accent, 'accent_secondary_name': 'theme accent',
                    'reason': 'one colour dominates the painting', 'scores': rounded}
    return {'accent': colours[accent], 'accent_secondary': colours[secondary],
            'accent_name': accent, 'accent_secondary_name': secondary,
            'reason': 'largest share of the painting\'s colour', 'scores': rounded}


def analyse(path, theme, edge=96):
    """Full record for one painting under one theme descriptor."""
    sig = signature(load_pixels(path, edge))
    result = choose(sig, theme)
    result['mean_chroma'] = round(sig['mean_chroma'], 6)
    result['mean_lightness'] = round(sig['mean_lightness'], 6)
    return result


def dumps(record):
    return json.dumps(record, indent=2, sort_keys=True) + '\n'
