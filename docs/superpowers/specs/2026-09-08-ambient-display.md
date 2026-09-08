# Ambient display brightness — 2026-09-08

## What

`oldbook-ambient-display` follows the room with the panel backlight, the way the
keyboard glow already follows it. It is opt-in, off by default, and it stands
down whenever anything else has a claim on the display.

- `alpine/desktop/.local/lib/oldbook/ambient_light.py` is the shared, pure
  logic: sensor discovery and parsing, the log-scale smoothing, the hysteresis
  band, the room curve, the learned offset and the cosine ease.
- `alpine/desktop/.local/bin/oldbook-ambient-display` is the daemon:
  `on`, `off`, `status` and `run`.
- Preferences live in `~/.config/oldbook/ambient-display.json`
  (`{"enabled": bool, "offset": float}`), outside the repository.

## The curve

The sensor is `/sys/devices/platform/applesmc.*/light` and reads `(left,right)`;
newer MacBooks put one ten-bit value in the left slot, so the reading is the
larger of the two. It is sampled every two seconds.

Readings are converted to a log scale, because perceived brightness is
logarithmic: the step from a candle to a lamp matters far more than the step
from a bright office to a brighter one. Samples are smoothed towards the new
value at a half-weight rather than snapped, and a hysteresis band of 0.15 log
units keeps a passing cloud or a hand near the sensor from starting a fade. When
the room really has moved, the panel eases to its new level over 1.2 seconds
with the same cosine ease the rest of the desktop's motion uses, settling
exactly.

The display and the keyboard want opposite things from the same number: a dark
room wants a bright keyboard and a dim screen. So a dark room settles the panel
at a floor of fifteen percent, never off, and a sunlit desk takes it to full.

## Learning what the user actually likes

The daemon remembers the last value it wrote. If the brightness has changed to
something else by the next sample, the user moved it, and their choice stands.
The difference between what they chose and what the curve wanted is taken as a
lasting offset, clamped to plus or minus forty percent and saved. From then on
the room still moves the panel, but around the level they like.

The whole difference is taken rather than a fraction of it: the user moved the
display deliberately, and the next room change should start from what they chose
rather than drift back towards the curve. The offset shifts the ceiling too, so
somebody who keeps turning the panel down gets a dimmer screen in every room and
not just in dark ones.

## Standing down

Two other things own the display at times, and neither is argued with:

- The idle stage before the lock. `oldbook-idle dim` ramps the panel down and
  keeps runtime state at `$XDG_RUNTIME_DIR/oldbook/idle/display.json`; while
  that file exists the daemon does nothing at all. This matters more than it
  looks: the idle dimmer decides on resume whether to restore the display by
  comparing the current level with the one it last wrote, so a stray write here
  would make it conclude somebody else moved the panel and leave it dim.
- A locked session. A live readiness record at
  `$XDG_RUNTIME_DIR/oldbook-screen-lock/ready.json`, whose recorded process is
  still alive, means a locker is on screen and nothing is written.

A fade in flight also abandons itself if either becomes true, or if the level
changes underneath it.

## Feedback

Automatic changes are silent, which is the point: a screen that announced every
cloud would be worse than one that never moved. `on` and `off` show the pill,
because those are the user asking for something, and the brightness keys keep
the pill they already had through `oldbook-brightness`.

## Verification

Thirty unit tests in `alpine/tests/test_ambient_display.py` against a fake
sensor and a fake backlight: parsing both sensor forms, the curve's floor,
ceiling, monotonicity and logarithmic shape, the offset's clamp and its effect
on the ceiling, smoothing and hysteresis, the fade settling exactly without
overshoot, both pause rules, a dead lock record not pausing anything, learning
from a hand-set level and leaving that level alone, and a missing or corrupt
preference file reading as off.

On the machine: the real sensor was read through the daemon (a reading of 10 in
a dim room, a computed target of thirty-six percent), and both pause rules were
exercised against real live state, because the session happened to be dimmed by
the idle stage and locked at the time. The daemon refused to write, which is
exactly the contract.

**Unverified:** an eased fade on the real panel, and a real change in room light.
The session was locked and held at the idle dim level throughout, and writing to
the backlight then would have confused the idle dimmer's own restore. The first
time the mode is switched on in an unlocked session is the real check.

## Rollback

`oldbook-ambient-display off` writes `enabled: false`; the running worker
notices within one sample and exits, leaving the brightness wherever it stands.
Deleting `~/.config/oldbook/ambient-display.json` forgets the learned offset as
well. Nothing else on the desktop depends on the daemon.
