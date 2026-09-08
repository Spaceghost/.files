# Ghost Planet sound theme — 2026-09-08

## What

Six short cues, synthesized rather than sampled, and one player that is
constitutionally incapable of getting in the way.

| Cue | When | Shape |
| --- | --- | --- |
| `lock-engage` | the session locks | two notes falling shut over a low thump |
| `unlock` | the locker exits | the same fourth opening upward, brighter |
| `low-battery` | charge crosses 25 or 10 percent | two patient pulses, then a minor third down |
| `painting-change` | a deliberate gallery change | a four-note chime |
| `urgent-notification` | a Critical notification arrives | two firm blips a major third apart |
| `tick` | small acknowledgements | the shortest possible click |

- Generator: `alpine/bin/build-sound-theme`
- Cues: `alpine/desktop/.local/share/sounds/oldbook/*.wav`
- Player: `alpine/desktop/.local/bin/oldbook-sound`
- Battery watcher: `alpine/desktop/.local/bin/oldbook-battery-cue`
- Tests: `alpine/tests/test_sound_theme.py`
- Evidence: `alpine/verification/sound-theme/`

## Why synthesize

A downloaded sample set would be somebody else's desktop. These are a handful of
sine and triangle partials tuned around A3, with raised-cosine attacks and
exponential tails, laid over a bed of twice-lowpassed noise that reads as
late-night studio room tone. The whole set builds in under half a second from
about two hundred lines, weighs six hundred kilobytes, and carries no licence
question. Every cue normalises to -12 dBFS so nothing ever startles.

## Silence is the default failure

Every caller is a hook on something that matters more than a sound. So
`oldbook-sound` exits zero in every circumstance: a missing player, a missing
file, an unknown cue, a muted sink or a switched-off set are all silence rather
than failure, and playback is handed to a detached process so no caller waits on
the speakers. The master switch lives in `~/.config/oldbook/sound.json` and
defaults to on; `oldbook-sound off` silences the set and `toggle` acknowledges
itself with a tick.

`muted()` is deliberately conservative: it reports muted only when a mixer
answers and says so. An unreadable mixer is treated as unmuted, because failing
open is better than a desktop that mysteriously stops making sounds.

## The hooks

Four, each one line or two:

- `oldbook-lock` sounds `lock-engage` once the locker has actually reported
  readiness, and `unlock` when the supervised locker exits of its own accord.
  A `cue()` helper there swallows every error.
- `oldbook-wallpaper` sounds `painting-change` beside the crossfade, but only for
  a deliberate change. The twenty-minute timer and the session's startup refresh
  turn pages in silence.
- SwayNC's own `scripts` block matches `urgency: Critical` and runs the cue. This
  is declarative and, importantly, keeps the sound away from
  `oldbook-ai-notification-stream`, whose contract is about attributable AI
  attention and should not grow a second meaning.
- `oldbook-battery-cue` watches the same thresholds Waybar colours (25 and 10
  percent) because a panel module cannot run anything when it changes. It is
  edge-triggered: one cue per crossing, silence while the charge drifts inside a
  band, silence while charging, and rearmed once the battery climbs past 30.

## A bug the tests caught

The first `low-battery` and `painting-change` canvases were shorter than the
voices placed on them, so the last note was cut mid-decay and the file ended on a
step, which is an audible click. Rather than lengthening the two cues and moving
on, `place()` now refuses to lay a voice that would not fit, so the whole class
of mistake fails loudly at build time.

## Verification

Twenty-four tests: every cue is under a second and audible, normalisation lands
on exactly -12 dBFS without clipping, every cue opens and closes on silence, the
stereo widener preserves length, written files carry the expected wave header and
frame count, and the checked-in cues are present and playable. The player's
silences are each tested separately (switch off, muted sink, no player, missing
file, unknown cue), along with the paplay fallback, nonsense preferences and the
switch round trip. The battery edges are tested for falling into a band, drifting
inside it, falling further, charging, rearming, and a machine with two cells or
none.

Live: all six cues were played once through `oldbook-sound`, `pw-play` rendered
`unlock.wav` and exited zero with the sink unmuted at forty percent, SwayNC
reloaded and accepted the script block, and `oldbook-battery-cue --status` read
the real battery (77 percent, charging, quiet).

Unverified: nobody has yet heard a cue fire from its own hook, because that would
mean locking the session, waiting for the battery to fall, or provoking a
critical notification. The wiring is tested; the occasions have not arrived.

## Rollback

`oldbook-sound off` silences everything without removing a file. To take the
hooks out, drop the `cue()` calls from `oldbook-lock`, the `sound_cue()` call
from `oldbook-wallpaper`, the `scripts` block from the SwayNC configuration, and
the battery watcher's line from `oldbook-session`, then reload SwayNC and Sway.
