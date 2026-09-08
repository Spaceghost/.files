# Lock screen redesign — 2026-09-08

## Request

The lock screen "should be awesome": the current painting blurred and gently
darkened so it reads as depth, a large clock and date, the amber ring only
while typing, a caption card with the painting's title and story, the hour's
Scripture and the Ghost Planet mark, a short fade-in and no grace period. The
LOCK-THEME contract stays: real readiness, serialized requests, stale process
and compositor identities rejected, palette-driven states.

## Design

- **Locker.** swaylock-effects 1.7.0.0, rebuilt as `oldbook-swaylock-effects`
  (`alpine/packages/swaylock-effects/`) so it installs as
  `/usr/bin/swaylock-effects` beside stock swaylock. Alpine's own package
  purges `swaylock`, which is the recovery route, so it was not used.
- **Readiness.** Option (a) from the task: `0001-ready-fd.patch` backports
  upstream swaylock's `-R/--ready-fd`, writing a newline once the
  `ext-session-lock-v1` locked event arrives. `oldbook-lock` keeps the same
  pipe protocol, process identity record and compositor identity check for
  both lockers. `swaylockd` hard-codes `/usr/bin/swaylock`, so the effects
  locker runs under `oldbook-lock supervise`, an internal supervisor that
  ignores catchable signals, restarts a signal-terminated locker up to five
  times without the readiness pipe, `--fade-in` or `--screenshots`, and exits
  with the locker's own status. The readiness record now names the locker.
- **Fallback.** `OLDBOOK_LOCK_BACKEND=auto|stock|effects` (default auto: effects
  when the binary exists). If scene preparation or the effects locker fails
  readiness, the same call continues with `swaylockd` and the stock
  arguments, so the machine is never left unlockable by a scene bug.
- **Scene.** `lock_scene.py` renders the painting at half the output size:
  cover-crop, three-pass box blur (≈ gaussian, radius ≈ width/110), slight
  desaturation and Gruvbox background tint, 0.68 exposure, radial vignette and
  a bottom scrim for the caption. The PNG is cached under
  `~/.cache/oldbook/lock/` (or `OLDBOOK_LOCK_CACHE`) keyed by painting hash,
  output geometry and scene version; the six newest are kept.
- **Dissolve.** `--screenshots --fade-in 0.4` makes swaylock-effects fade from
  the live desktop into the effect-applied frame; the scene is composed over
  that screenshot at `0,0;100%x100%`, so the desktop dissolves into the
  blurred painting. Effects run on the screenshot at buffer resolution, so the
  caption is positioned in physical pixels.
- **Clock.** swaylock-effects draws the clock inside the indicator.
  `0002-idle-colors.patch` adds idle colours; the idle ring, inside and line
  are transparent and the idle text is cream, so only the clock shows until a
  key is pressed, when the amber ring, key highlights and the verifying,
  wrong, cleared and Caps Lock palettes appear. Inter Display SemiBold, radius
  172, centred at 40% height.
- **Caption card.** Pango/cairo, 560 logical pixels wide, rendered at the
  output scale into the private lock runtime directory: eyebrow, painting
  title, first sentence of its story, the hour's Scripture reference and
  edition with the opening words in italic, and the Ghost Planet mark. The
  Scripture comes from `scripture_history.current()`, which reads the durable
  selection without advancing it. The card is cached by content so an
  unchanged hour skips Pango.
- **Security.** No grace period, empty passwords ignored, keyboard layout
  hidden. The desktop screenshot stays in the locker's memory only.

## Verification

- `alpine/tests/test_lock.py` (10 tests): palette arguments, readiness,
  concurrency, stale identity, nonprivate runtime, scene composition and cache
  reuse, no-painting degradation, effects-to-stock fallback, supervisor
  restart stripping first-run options.
- `alpine/verification/lock-screen/render-headless` locks a private headless
  SwayFX (pixman renderer, 2880×1800 at scale 2) with the real helper and
  captures desktop, idle, typing, backspace, cleared, Caps Lock and a warm
  relock; `evidence.json` records timings, hashes and the readiness record.
- Two isolated package builds produced byte-identical signed APKs.

## Limits

- The live session was not locked by this work: the display was off and
  locked by swayidle at first, then the user was at the machine. The first
  live lock is the user's check.
- Headless screenshots are software-rendered under heavy build load; frame
  pacing of the dissolve on the physical panel is unmeasured.
- Caps Lock state from a virtual keyboard did not reach the locker's xkb
  state in the headless capture, so the Caps Lock text was not observed; the
  colours are configured as before.
- Only the focused output's geometry sizes the caption; mixed-scale outputs
  would get one caption size.

## Rollback

`OLDBOOK_LOCK_BACKEND=stock` in the session environment, or
`doas apk del oldbook-swaylock-effects`, returns every path to swaylockd and
stock swaylock; `oldbook-lock` needs no other change. The previous helper is
the parent check-in of this commit.
