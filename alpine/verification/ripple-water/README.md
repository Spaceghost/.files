# Landing ripple, rendered offline — 2026-09-13

Jack: "I really like the new ripple.py, but it sort of brightens a bit before
rippling and it doesn't ripple out from the bar in a watery way." The fix is
`ripple:` check-in 6ee76c6022. These renders are how it was verified without
ever striking the live desktop: `render.py` transliterates the fragment shader
in `ripple.py` into numpy, line for line, and runs it over a synthetic screen
(a window of text-like lines with the strip docked along the bottom, at this
MacBook's 1440x900 logical size) for seven moments of the wave's life. The
shader it replaced is rendered the same way, with its origin taken the way it
took it and its straight colour composited the way GTK actually composited it.

Regenerate with `python3 render.py`; pass a JSON object as a second argument
to render a tuned wave, for example `python3 render.py . '{"strength": 20}'`.

## What the pictures show

`old-vs-new.png` is each moment twice, the old shader above the new one.
`new-wave.png` is the new wave at full resolution across the middle of the
band, top to bottom in time.

In the old frames the whole band is lighter than the screen, the wave sits in
the middle of the band rather than on the strip, and by the last frames the
band is brighter than at the start. Three defects, all in the shader and its
geometry:

- The shader wrote straight colour beside a coverage alpha, but GTK 4.22
  composites a GLArea's canvas as `R8G8B8A8_PREMULTIPLIED`, so every pixel
  the ring only partly covered came out as colour + desktop × (1 − alpha).
- `origin()` measured the strip's landed edge down from the region's top; the
  shader compared it with a texture coordinate that runs up from the bottom.
  On this panel the ring started about 260 logical pixels above the strip.
- One Gaussian crest, at full strength and centred on the origin at age zero,
  crossed the band's height in about 120 ms with a one-sided highlight.

In the new frames nothing is drawn at the strike itself; an annulus of rings
grows out of the strip's outline, bends what is under it, and fades before the
far edge of the band. The crest/trough shading averages to nothing, which the
table shows in numbers.

## Mean change in brightness against the untouched screen

`age` is the fraction of the wave's life. "Band touched" is the share of the
band's pixels the surface draws anything on at all.

| age | old: mean brightness change | old: band touched | new: mean brightness change | new: band touched |
| ---: | ---: | ---: | ---: | ---: |
| 0.03 | +0.0957 | 100% | +0.0023 | 2% |
| 0.10 | +0.0620 | 100% | -0.0011 | 5% |
| 0.20 | +0.0241 | 100% | -0.0002 | 10% |
| 0.30 | +0.0532 | 100% | +0.0003 | 16% |
| 0.45 | +0.1415 | 100% | -0.0022 | 24% |
| 0.60 | +0.1759 | 100% | +0.0040 | 31% |
| 0.80 | +0.1780 | 100% | +0.0000 | 42% |

Brightness is on a 0..1 scale, so the old shader lifted the band by a tenth at
the strike and by nearly a fifth as it faded, everywhere at once; the new one
stays within half a percent of zero and touches only the water it disturbs.

## Limits

The screen is synthetic and the arithmetic is float on a CPU. This is evidence
of the wave's shape, timing and balance, and of the compositing arithmetic,
not a capture of the GPU's output or of the strip landing on the real desktop.
The GLSL compiling on the real GL context is checked separately: the daemon's
warmup compiles it six seconds after start and writes `decoration ripple
warmup:` to `~/.local/state/oldbook/decoration.log` if it fails.
