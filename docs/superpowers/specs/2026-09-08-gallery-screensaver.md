# The idle gallery — 2026-09-08

## What

Four minutes into an idle session the desktop stops being a desktop and becomes
a slideshow. `oldbook-background` drifts slowly across the current painting,
about 1.06 of zoom over thirty seconds with the pan heading for a different
corner each time, then crossfades to the next painting and drifts again. When
the session wakes, or the dim stage arrives, it glides back to rest and
crossfades to exactly the painting it interrupted.

The idle sequence is now:

| Idle | Stage |
| --- | --- |
| 240 s | `oldbook-idle screensaver` starts the idle gallery |
| 270 s | `oldbook-idle dim` stops it, eases the display down, last breath |
| 300 s | the lock |
| 600 s | the display sleeps |

## Why this shape

The selection stays with the gallery and the animation stays with the daemon.
`oldbook-screensaver` loads the gallery through the tool that owns it, filters
for rotation-eligible paintings exactly as the timer does, shuffles them, drops
the one already on screen and hands the daemon a bounded list of absolute paths.
The daemon knows nothing about collections or themes; it cycles the list it was
given. That keeps one copy of the gallery rules and lets the protocol stay a
short validated datagram.

Nothing is saved. The screensaver never touches `current-wallpaper.png`, the
saved selection, the rotation deadline or the pause switch, so it runs happily
while rotation is paused and leaves no trace when it ends. The Conky cards keep
the layout they were given for the original painting, so no card reflows.

## The drift

`background_fade.ken_burns` returns the view transform for a segment. The pan is
always a fraction of the room the current zoom opens up, so a segment begins on
exactly the untouched painting and the picture covers the output at every
moment; there is no frame where an edge of the surface below could show. The
breath multiplies the same transform, so a drifting painting can still breathe.
Stopping interpolates from wherever the drift is back to rest over 900 ms.

## Verification

`alpine/tests/test_air.py` covers the protocol (absolute paths, a bounded list,
clamped timings, the round trip) the drift maths (identity at the start, pan
inside the room at every step, the zoom reached exactly, a refusal to zoom out)
and the candidate selection (only rotating paintings, never the one on screen, a
fallback when nothing rotates, a bounded list).

`alpine/tests/verify_desktop_breath.py --part screensaver` in a private headless
SwayFX session, eight checks passed: the daemon accepts the gallery, the painting
drifts and pans, it crossfades to the next painting, the shared painting link is
untouched throughout, the stop is accepted, the drift glides back to exactly
rest, and the interrupted painting comes back. Evidence in
`alpine/verification/gallery-screensaver/`.

Not verified: a real 240-second idle, and the physical frame pacing of the drift
on the panel. The headless renderer draws no blur.

## Rollback

Remove the `timeout 240 'oldbook-idle screensaver'` clause from the swayidle
command in `oldbook-session` and reload. `oldbook-screensaver stop` ends a run
immediately, and any painting change ends it as well.
