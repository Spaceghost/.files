"""Render the landing ripple offline, without striking the live desktop.

The fragment shader in ripple.py is transliterated into numpy line for line
and run over a synthetic screen -- a window full of text-like lines and the
strip itself along the bottom -- for a handful of moments in the wave's life.
The shader it replaced is rendered the same way, with its origin taken the way
it took it and its straight colour composited the way GTK actually composited
it (as premultiplied), so the two can be compared frame by frame.

    python3 render.py            # writes the PNGs next to this file
    python3 render.py OUTDIR

`old-vs-new.png` shows each moment twice, old above new; `new-wave.png` is the
new wave at full resolution across the middle of the band. The table printed
is each frame's mean change in brightness against the untouched screen, which
is what "brightens" means in numbers, and how much of the band the wave touches.

The screen is synthetic and the maths is float on a CPU, so this is evidence
of the wave's shape, timing and balance, not a capture of the GPU's output.
The settings used are ripple.DEFAULTS; pass a JSON object as VALUES to render
a tuned wave, e.g. '{"strength": 20, "spacing": 32}'.
"""
import json
from pathlib import Path
import struct
import sys
import zlib

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'desktop/.local/lib/oldbook'))
import ripple  # noqa: E402

# The lower third of a 1440x900 output (this MacBook's logical size) and the
# strip docked along its bottom edge with the usual five-pixel margin.
AREA = {'x': 0, 'y': 600, 'width': 1440, 'height': 300}
STRIP = {'x': 5, 'y': 862, 'width': 1430, 'height': 33}
CORNER = 7
AGES = (0.03, 0.1, 0.2, 0.3, 0.45, 0.6, 0.8)


def png(path, rgb):
    rgb = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    height, width, _ = rgb.shape
    raw = b''.join(b'\x00' + rgb[row].tobytes() for row in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

    with open(path, 'wb') as stream:
        stream.write(b'\x89PNG\r\n\x1a\n')
        stream.write(chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)))
        stream.write(chunk(b'IDAT', zlib.compress(raw, 6)))
        stream.write(chunk(b'IEND', b''))


def synthetic_screen(area, strip):
    """A dark desktop: a window of text-like lines, column rules, and the
    strip itself at the bottom, in the region's own coordinates, y down."""
    height, width = area['height'], area['width']
    y, x = np.mgrid[0:height, 0:width]
    img = np.zeros((height, width, 3))
    img[..., 0] = 0.10 + 0.08 * x / width
    img[..., 1] = 0.11 + 0.05 * y / height
    img[..., 2] = 0.16 + 0.06 * (1 - y / height)
    top = strip['y'] - area['y']
    window = (x > 80) & (x < width - 80) & (y < top - 14)
    img[window] = [0.13, 0.14, 0.17]
    text = window & ((y % 22) < 3) & (((x // 9) * 7919 + (y // 22) * 104729) % 5 != 0) \
        & (x > 100) & (x < width - 220)
    img[text] = [0.80, 0.82, 0.85]
    rules = window & ((x % 140) < 1)
    img[rules] = [0.30, 0.30, 0.36]
    border = ((x == 80) | (x == width - 81)) & (y < top - 14)
    img[border] = [0.45, 0.45, 0.50]
    inside = (x >= strip['x'] - area['x']) & (x < strip['x'] - area['x'] + strip['width']) \
        & (y >= top) & (y < top + strip['height'])
    img[inside] = [0.55, 0.42, 0.30]
    return np.clip(img, 0, 1)


def bilinear(img, sx, sy):
    height, width = img.shape[:2]
    sx = np.clip(sx, 0, width - 1)
    sy = np.clip(sy, 0, height - 1)
    x0 = np.floor(sx).astype(int)
    y0 = np.floor(sy).astype(int)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    fx = (sx - x0)[..., None]
    fy = (sy - y0)[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy)
            + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def smoothstep(lower, upper, value):
    step = np.clip((value - lower) / (upper - lower), 0.0, 1.0)
    return step * step * (3.0 - 2.0 * step)


def new_frame(screen, area, strip, edge, values, corner, age):
    """ripple.FRAGMENT_SHADER, line for line, over the whole region.
    Returns the composited frame plus the envelope and slope fields."""
    plan = ripple.plan(strip, area, edge, values, corner)
    height, width = screen.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width].astype(float) + 0.5
    # texture_position = (xx/width, 1 - yy/height); point = (u, 1 - v) * scale
    px = xx / width * plan['scale'][0]
    py = yy / height * plan['scale'][1]
    cx, cy = plan['centre']
    hx, hy = plan['half']
    rx, ry = px - cx, py - cy
    ax = rx - np.clip(rx, -hx, hx)
    ay = ry - np.clip(ry, -hy, hy)
    apart = np.hypot(ax, ay)
    water = apart - plan['radius']
    safe = np.maximum(apart, 1e-9)
    nx = np.where(apart > 1e-5, ax / safe, 0.0)
    ny = np.where(apart > 1e-5, ay / safe, 0.0)
    front = age * plan['reach'] * plan['travel']
    tail = front * ripple.TAIL
    position = np.clip((water - tail) / max(front - tail, 1e-5), 0.0, 1.0)
    bump = 6.75 * position * position * (1.0 - position)
    fade = max(1.0 - age, 0.0) ** ripple.DECAY
    edge_fade = 1.0 - smoothstep(plan['travel'] * (1.0 - ripple.MARGIN), plan['travel'], water)
    envelope = np.where((water > tail) & (water < front), bump * fade * edge_fade, 0.0)
    phase = 2 * np.pi * (water - ripple.CREST * front) / plan['spacing']
    slope = envelope * np.cos(phase)
    # bend = (nx, -ny) * slope * strength * texel in texture units; in the
    # region's own pixels (y down) that is simply along the normal.
    shift = slope * plan['strength']
    colour = bilinear(screen, xx + nx * shift - 0.5, yy + ny * shift - 0.5)
    colour = np.clip(colour + (plan['shade'] * slope)[..., None], 0.0, 1.0)
    alpha = np.clip(envelope * 2.0, 0.0, 1.0)[..., None]
    return colour * alpha + screen * (1 - alpha), envelope, slope


def old_frame(screen, area, strip, age):
    """The shader replaced on 2026-09-13, with its origin taken the way it
    took it, and its straight colour composited the way GTK composited it."""
    duration, frequency, speed, amplitude, sharpness = 0.72, 26.0, 1.25, 0.016, 5.5
    height, width = screen.shape[:2]
    # origin(): middle of the landed edge, y measured from the region's top...
    origin = ((strip['x'] + strip['width'] / 2 - area['x']) / width,
              (strip['y'] - area['y']) / height)
    yy, xx = np.mgrid[0:height, 0:width].astype(float) + 0.5
    tu = xx / width
    tv = 1 - yy / height           # ...but compared against a texture v that runs up.
    longest = max(width, height)
    scale = (width / longest, height / longest)
    ox = (tu - origin[0]) * scale[0]
    oy = (tv - origin[1]) * scale[1]
    dist = np.hypot(ox, oy)
    front = age * speed
    ring = (dist - front) * sharpness
    envelope = np.exp(-ring * ring)
    fade = (1 - age) ** 1.5
    reach = 1 / (1 + 1.5 * dist * dist)
    coverage = envelope * fade * reach
    wave = amplitude * coverage * np.sin(dist * frequency - age * speed * frequency)
    safe = np.maximum(dist, 1e-9)
    dx = np.where(dist > 1e-4, ox / safe, 0.0)
    dy = np.where(dist > 1e-4, oy / safe, 0.0)
    su = tu + dx * wave / scale[0]
    sv = tv + dy * wave / scale[1]
    colour = bilinear(screen, su * width - 0.5, (1 - sv) * height - 0.5)
    colour = colour + (wave * 6.0)[..., None]
    alpha = np.clip(coverage * 3.0, 0.0, 1.0)[..., None]
    # Written straight but read as premultiplied: colour + desktop * (1 - alpha).
    return np.clip(colour + screen * (1 - alpha), 0.0, 1.0), coverage, wave


def sheet(frames, gap=6):
    height, width = frames[0].shape[:2]
    out = np.full((len(frames) * (height + gap) - gap, width, 3), 0.5)
    for index, frame in enumerate(frames):
        out[index * (height + gap):index * (height + gap) + height] = frame
    return out


def halve(img):
    height, width = img.shape[0] // 2 * 2, img.shape[1] // 2 * 2
    img = img[:height, :width]
    return (img[0::2, 0::2] + img[1::2, 0::2] + img[0::2, 1::2] + img[1::2, 1::2]) / 4


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    values = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    screen = synthetic_screen(AREA, STRIP)
    print('| age | old: mean brightness change | old: band touched | new: mean brightness change | new: band touched |')
    print('| ---: | ---: | ---: | ---: | ---: |')
    pairs, crops = [], []
    for age in AGES:
        old, coverage, _ = old_frame(screen, AREA, STRIP, age)
        new, envelope, _ = new_frame(screen, AREA, STRIP, 'bottom', values, CORNER, age)
        print('| {:.2f} | {:+.4f} | {:.0f}% | {:+.4f} | {:.0f}% |'.format(
            age, (old - screen).mean(), 100 * (coverage > 0).mean(),
            (new - screen).mean(), 100 * (envelope > 0).mean()))
        pairs += [old, new]
        crops.append(new[:, 200:920])
    png(out / 'old-vs-new.png', halve(sheet(pairs)))
    png(out / 'new-wave.png', sheet(crops))


if __name__ == '__main__':
    main()
