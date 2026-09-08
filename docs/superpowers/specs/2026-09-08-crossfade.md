# Wallpaper crossfade — 2026-09-08

## What

`oldbook-background` is a small GTK3 + gtk-layer-shell daemon that owns one
opaque surface per output on the **background** layer and crossfades between
paintings instead of letting Sway cut from one swaybg image to the next.

- `oldbook-wallpaper` sends every image change (timer tick, next/previous,
  picker selection, `select` from generation and theme activation, `refresh`
  after a reload) to the daemon over a session-scoped datagram socket
  (`$XDG_RUNTIME_DIR/oldbook/background-<session>.sock`). The timer eases across
  in 1.6 s; a deliberate change answers in 0.8 s. `--from X,Y` on
  `next`/`prev`/`select`/`refresh` reveals the painting from that logical
  position with a soft radial edge instead of a plain fade.
- The daemon draws on the display frame clock with a cubic ease-out that
  settles exactly on 1.0 and never overshoots, then drops the previous pixels
  and stops rendering (MOTION). A change that arrives mid-fade bakes what is on
  screen into the starting frame, so motion stays continuous. Pointer input
  passes straight through (empty input region). Images are decoded and scaled
  off the main loop; the reply protocol acknowledges immediately and reports
  `settled` when the fade finishes, so a powered-off output (no frame
  callbacks) never stalls the socket, only the visible motion.
- Startup reads the image swaybg is showing (from Sway's own swaybg command
  line, matched by the compositor pid in the socket name) and fades from it to
  `~/.local/share/oldbook/current-wallpaper.png`, so a login or daemon start
  never flashes.
- When no daemon answers, `oldbook-wallpaper` falls back to Sway's `output bg`
  exactly as before: stock Sway sessions, headless checks, the lock and Conky
  (which read `current-wallpaper.png`) are unaffected.

## Why the daemon must own the stacking order

SwayFX lists an output's `layer_shell_surfaces` **top-first**, and within one
layer the newest surface is on top (verified with two overlapping surfaces and
a screenshot). Sway respawns swaybg on every `output bg` command and on every
reload, and that new surface lands above the daemon. Therefore:

1. `oldbook-wallpaper` does **not** refresh Sway's `output bg` after a fade;
   Sway keeps showing whatever it showed at login, purely as a fallback.
2. The daemon checks the order before each fade, on Sway `output` IPC events,
   at startup and every 15 s (`OLDBOOK_BACKGROUND_CHECK_SECONDS`). When a swaybg
   surface is above it, it re-creates its window with the same pixels (no seam)
   and retires the covered one once the new one maps.
3. Conky's cards are background-layer surfaces too. A daemon that starts into a
   running session (or re-creates its surface outside a wallpaper change) lands
   above cards created earlier; it then asks `oldbook-conky restart` to put them
   back on top. During a wallpaper change the gallery already refits the cards
   afterwards, so no extra restart happens then.
4. `oldbook-video-background` (mpvpaper, created later) still wins while it
   plays; the scripture bar lives on the bottom layer and is never affected.

## Session ownership

`oldbook-session` starts the daemon (single owner through a session flock)
before the gallery's `refresh`, waiting up to two seconds for it to answer so
the restore fades instead of cutting. The daemon exits on Sway's `shutdown`
event and on SIGTERM.

## Verification

- `alpine/tests/test_background.py`: fill geometry, easing and settling,
  request validation and clamping, the reply protocol against a fake daemon,
  stacking classification, swaybg discovery from a fake `/proc`.
- `alpine/tests/test_background_gallery.py`: `oldbook-wallpaper` prefers the
  daemon, falls back to Sway when it is absent or refuses, uses the slower
  timer duration, and limits `--from` to image changes.
- `alpine/tests/verify_background_crossfade.py --output DIR`: private headless
  SwayFX session with three real paintings — swaybg only; a card created before
  the daemon; the startup fade; a timed fade photographed early, part-way and
  settled with blend estimates against reference renders; a respawned swaybg
  covering the surface and the daemon healing above it with the card restored;
  `raise`; and the fallback after `quit`. Evidence is kept under
  `alpine/verification/background-crossfade/`.
- Live session: the daemon started into the running desktop showed the current
  painting without a flash, one `next` faded and `prev` faded back, and the
  cards returned on top. Physical frame pacing of the fade is not measured.

## Rollback

Stop the daemon with `oldbook-background quit` (or remove its block from
`oldbook-session` and reload); `oldbook-wallpaper` immediately returns to
`output bg` cuts. No package, kernel or system file is involved.
