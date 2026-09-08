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

The build enables PAM and gdk-pixbuf (the compose effect needs it), and
disables shell completions so the stock ones stay untouched.

## Build without network

```sh
alpine/packages/swaylock-effects/build-offline --work /tmp/swaylock-effects-build
doas apk add --no-network /tmp/swaylock-effects-build/apks/oldbook/x86_64/oldbook-swaylock-effects-1.7.0.0-r0.apk \
    /tmp/swaylock-effects-build/apks/oldbook/x86_64/oldbook-swaylock-effects-doc-1.7.0.0-r0.apk
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
