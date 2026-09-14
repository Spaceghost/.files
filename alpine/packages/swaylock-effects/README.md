# swaylock-effects beside stock swaylock

`oldbook-swaylock-effects` rebuilds jirutka's swaylock-effects 1.7.0.0 so it
can live next to Alpine's stock `swaylock` 1.8.6 instead of replacing it. The
Alpine `swaylock-effects` package `provides="swaylock"` and purges the stock
locker, which is the recovery route `oldbook-lock` falls back to; this package
installs `/usr/bin/swaylock-effects`, `/etc/pam.d/swaylock-effects` and a
`swaylock-effects(1)` manual and nothing else. `swaylockd` still supervises
stock swaylock only; the effects locker is supervised by `oldbook-lock`.

Two local patches are applied on top of the pinned upstream tarball:

- `0001-ready-fd.patch` backports upstream swaylock's `-R, --ready-fd <fd>`:
  a newline is written to the descriptor and it is closed the moment the
  compositor confirms the session lock. `oldbook-lock` keeps its readiness
  handshake unchanged for both lockers.
- `0002-idle-colors.patch` adds `--ring-idle-color`, `--inside-idle-color`,
  `--line-idle-color` and `--text-idle-color`. Without them the idle indicator
  keeps the typing colours, so the clock could not sit on an invisible ring.
- `0003-indicator-panel.patch` adds `--indicator-panel <path>`: a drawing hook
  for the indicator area, repaints driven by the `wl_surface.frame` callback
  while something is animating, and damage limited to the panel's own
  rectangle. It is stage 1 of `docs/superpowers/specs/2026-09-09-lock-client.md`
  and its first consumer is the cat hearth (`cat_panel.py`), which is the only
  thing that can show a locked session that the machine is deliberately warming
  itself: a session lock surface covers everything, so nothing but the locker
  can draw above it.

  **The hook takes data, never code.** Under `ext-session-lock-v1` a locker that
  dies without `unlock_and_destroy` does not fail open, it fails *stuck*: the
  compositor stays locked with no password prompt until a replacement client
  takes the lock. A `dlopen`'d renderer would put that one segfault away, and a
  segfault cannot be caught, so the panel is a PNG plus a short list of `key
  value` lines that the locker validates and blits. It refuses anything that is
  not a small, private, plain-ASCII regular file owned by the caller; it names
  its image by basename beside itself, so no path can leave that directory; it
  clamps every number before it reaches cairo; it uses cairo's own PNG reader
  rather than the gdk-pixbuf format-sniffing stack; and it forgets a panel whose
  wall-clock stamp has gone stale, so a writer that dies takes its own panel off
  the screen. Every one of those refusals ends in "draw no panel", which is the
  lock screen exactly as it was before the flag existed. Nothing in the patch
  touches `pam.c`, `password.c`, `password-buffer.c`, `comm.c` or `seat.c`, and
  `alpine/tests/test_lock.py` asserts that it never will.

  While a panel is up it may ask for `ring 0`, which hides swaylock's own arc,
  its borders and its per-keypress highlight. That highlight is one arc per key
  in one colour and one per backspace in another, so it is countable off a
  photograph; a panel drawing the indicator area has no business leaving it
  there. The panel itself is a function of the cat record and the clock and of
  nothing else.

The build enables PAM and gdk-pixbuf (the compose effect needs it), and
disables shell completions so the stock ones stay untouched.

## Build

Compilation belongs on a build host, not on this laptop:

```sh
alpine/bin/remote-build build --host bak swaylock-effects
```

The APKs land in `~/.cache/oldbook-apks`, signed here with the local key.
Installing is a separate, deliberate step, and it replaces the binary that is
holding the user's screen:

```sh
doas apk add --no-network ~/.cache/oldbook-apks/oldbook-swaylock-effects-1.7.0.0-r1.apk \
    ~/.cache/oldbook-apks/oldbook-swaylock-effects-doc-1.7.0.0-r1.apk
```

**The risk of that command, plainly.** It overwrites `/usr/bin/swaylock-effects`
while a lock may be running. A locker already on screen keeps its own mapped
binary, so an install does not disturb a live lock; the first lock *after* it is
the one that runs new code, and if that binary were broken the session would
lock into a compositor showing its abandoned-lock colour with no prompt. Two
things already stand under that: `oldbook-lock supervise` restarts a
signal-killed locker up to five times, and `launchers()` falls back to stock
`swaylock` under `swaylockd`, which this package deliberately never replaces.
The recovery route if both fail is another VT (`Fn` plus the function key on
this keyboard, see APPLE-KEYS) and `loginctl unlock-session`. Install when there
is time to lock once on purpose and watch what happens, not on the way out.

## Build without network, on this machine

Kept for the case where no build host is reachable. It compiles here, which is
a thing to do deliberately rather than by habit:

```sh
alpine/packages/swaylock-effects/build-offline --work /tmp/swaylock-effects-build
doas apk add --no-network /tmp/swaylock-effects-build/apks/oldbook/x86_64/oldbook-swaylock-effects-1.7.0.0-r1.apk \
    /tmp/swaylock-effects-build/apks/oldbook/x86_64/oldbook-swaylock-effects-doc-1.7.0.0-r1.apk
```

The pinned source is a Fossil unversioned artifact; the builder exports it
when no tarball sits beside the recipe, and refuses a tarball whose SHA-256
differs from `manifest.json`. Building needs `linux-pam-dev` in addition to
the desktop's existing `cairo-dev gdk-pixbuf-dev libxkbcommon-dev meson samurai
scdoc wayland-dev wayland-protocols`. The recipe runs as the desktop user
inside `doas unshare --net` with the user's private abuild key.
`verification.json` records two byte-identical signed builds; `manifest.json`
records the exact APK identities and archived artifacts.

## Verify

`alpine/verification/lock-screen/render-headless --output /tmp/lock-preview`
locks a private headless SwayFX session with the real `oldbook-lock` helper,
captures the desktop, idle, typing, backspace, cleared and Caps Lock states,
then starts a second private session to time the warm cache. The live session
is never locked by the script.
