# The desktop breathes with the keyboard — 2026-09-08

## What

The keyboard light's breathing modes now drive the rest of the scene. While the
keys breathe, the painting swells and settles with them, and while you are
filling the lungs yourself with keystrokes, the caption strip's accent glows in
time. Nothing else moves: the typing and ambient keyboard modes leave the
desktop perfectly still.

- **The air file.** `oldbook-keyboard-backlight`'s single worker publishes
  `$XDG_RUNTIME_DIR/oldbook/air.json` twenty times a second while a breathing
  mode is running: `mode` (`breathing`, `breathe-air`, `last-breath`), `volume`
  (how full the lungs are), `phase`, `breath` (the normalised brightness of the
  curve at this instant), `tempo_seconds` and `updated`. One final record with
  `mode: off` is written when the worker stops, however it stops.
- **The painting.** `oldbook-background` scales its surface around the centre
  by 1.000 to 1.006 at rest and up to 1.018 at full lungs, following `breath`.
- **The caption.** `oldbook-decoration` moves the accent wash behind the brand
  button between 0.06 and 0.22 alpha, but only for `breathe-air`.
- **The switch.** `~/.config/oldbook/breath.json` holds `wallpaper` and
  `caption` booleans, both true by default, with a command-deck entry
  (**Desktop breath**) that toggles the pair.

## Why this shape

One publisher, many readers. The breath is a physical thing the keyboard already
computes; recomputing a similar curve in each surface would drift out of phase
within seconds. A small file in the session runtime directory is the cheapest
shared clock available: readers stat it and only parse when it changed, so the
idle cost is a stat every 300 ms and the busy cost is a parse per published
frame.

Staleness is the safety rule. A worker that is killed cannot always write its
closing record, so a record older than half a second counts as no breath at all
and every reader settles back to rest. That also means a reader can never be
stuck holding the painting open.

## Motion

Both readers smooth the 20 Hz feed to their own frame clock with
`air.Smoother`, an exponential approach that caps a long frame gap, snaps to the
target inside a tolerance and reports when it has settled. The background
daemon's motion tick removes itself once the breath is at rest and no drift is
running, so an idle desktop schedules no frames. The caption quantises its alpha
to 24 steps, which turns a 60 Hz animation into a few stylesheet updates a
second on a provider holding one rule.

## Verification

`alpine/tests/test_air.py`, 51 tests: the record format and its staleness rules,
the scale and alpha maths and their ceilings, the smoother's settling and
overshoot behaviour, the stat-gated watcher, the preferences, the drift maths,
the screensaver protocol, and the real worker on a synthetic clock and synthetic
LED files, asserting the published rate, the phase continuity, the filling lungs,
the quickening tempo, the closing record and the silence of the typing modes.

`alpine/tests/verify_desktop_breath.py --part breath` and `--part caption` in a
private headless SwayFX session: the painting measured at exactly 1.000, 1.018,
1.006 and back to 1.000, the preference holding it still, and the caption strip's
average colour brightening only for the keystroke breath. Evidence and frames in
`alpine/verification/desktop-breath/`.

Live: the background daemon was restarted onto the new code after aligning
Sway's own background with the painting on screen, so nothing flickered, and a
synthetic air record made the live painting swell to 1.018 and settle back to
1.000. The caption daemon was restarted onto the new code. The user's keyboard
light was off throughout and its saved level and mode were never written, so the
physical impression of the breath on the 2880x1800 panel is still unobserved.

## Rollback

Remove the `breath.json` preference or set both keys false to stop the motion
without touching code. To revert entirely, restore `air.py`,
`oldbook-keyboard-backlight`, `oldbook-background` and `oldbook-decoration` from
Fossil and restart the background and caption daemons; the air file is runtime
state and disappears with the session.
