# Launchpad and Mission Control — 2026-09-08

## What

The engraved Apple overview keys now open two written-from-scratch overlays
instead of borrowing other tools:

- **F4 (Launchpad)** — `oldbook-launchpad`: every application as a large icon
  over the current painting blurred, with type-to-search from the first
  keystroke, arrow and pointer navigation, paging with dots, and Enter or a
  click to launch. It replaces the Fuzzel application menu on this key; Super+D
  keeps that menu.
- **F3 (Mission Control)** — `oldbook-mission-control`: every workspace as a
  card of real window stills, the focused one outlined in amber, click or Enter
  to switch, arrow keys and the number keys to move, a drag of a still onto
  another card to move that window, and a final card that creates the next
  workspace. It replaces the window carousel on this key; Super+Tab and Alt+Tab
  keep the carousel untouched.

Both are singletons per compositor session, close on Escape or a second press of
their key, hold the keyboard only while mapped, and read the palette through
`overlay_theme.read_palette` so a generated theme restyles them.

## Why GTK 4 and gtk4-layer-shell

The two newest overlays on this desktop — the window carousel and the
show-desktop slide — already use GTK 4 with `Gtk4LayerShell`, and
`preload_layer_shell()` exists to interpose the library before libwayland. The
Gsk snapshot API gives rounded clips, textures, borders and opacity groups
without building a cairo context per frame, which is what the icon grid and the
still cards need. Following the existing choice also means one layer-shell
idiom in the codebase rather than two.

## Shape of the code

Pure logic is separated from anything that needs a display, so the tests never
open a compositor:

| File | Holds |
| --- | --- |
| `app_index.py` | Desktop-entry scanning, field-code stripping, fuzzy ranking |
| `grid_layout.py` | Icon-grid paging, workspace-card geometry, hit tests, arrow movement |
| `grid_overlay.py` | Shared layer-shell window, blurred background, reveal animation, singleton socket |
| `launchpad.py` | The icon grid and its keys |
| `mission_control.py` | The workspace cards, stills and drag-to-move |

Stills come from the carousel's own `capture_preview` (`grim -T <foreign
toplevel identifier>`), so a workspace is photographed without being visited or
focused, and there is exactly one capture implementation on the desktop. Icons
come from the GTK icon theme, which resolves to Oldbook-Gruvbox.

## Two safeguards found by accident

While checking the overlays on the live session, every measurement came back
saying the frame clock ticked once and stopped. The cause turned out to be
mundane: **swayidle had locked the session at 05:54, before the probes ran**, and
a lock surface covers everything beneath it. That is not a compositor defect and
nothing here should be read as one — but it exposed two real gaps, both now
closed:

1. **A stalled frame clock left the overlay invisible and undismissable.** The
   reveal animation sat at 0.011 while the surface held an exclusive keyboard
   grab, and the close message could not finish the fade. `WATCHDOG_MS` (420 ms,
   twice the fade plus margin) now settles the animation immediately if the
   frame clock has not progressed, so the overlay appears at once and always
   closes. A healthy frame clock always finishes first and cancels the watchdog.
2. **An overview key pressed behind the lock mapped an overlay nobody could
   see.** `session_locked()` reads the lock helper's readiness record and
   verifies the locker's process identity (pid plus start time, so a reused pid
   never counts), and `serve()` returns without mapping anything while a lock is
   live.

## Verification

`alpine/tests/test_grids.py` — 53 tests over the application index, field codes,
ranking, both grid geometries, arrow navigation, the workspace model, the reveal
curve and the lock guard.

`alpine/tests/verify_grids.py` renders both overlays in a private headless
SwayFX session with a private HOME, runtime directory and cache, opens two real
terminals on two workspaces so Mission Control has something to photograph,
types a query with `wtype`, and closes each overlay over its own control socket.
Evidence: `alpine/verification/launchpad-mission-control/`.

Live, on the physical panel: both executables were run, the surface mapped on
`eDP-1`, the control socket closed them and the processes exited, and the lock
guard was confirmed to refuse to open while the session was locked. **The
session was locked for the whole live window, so the overlays were never seen on
the physical screen and the fade, hover, drag-to-move and the engraved F3/F4
keys remain unobserved.** Those are the user's checks.

`sway --validate` passes on both entry configs. The Apple-key help text moved
with the bindings, and `test_apple_overview.py` was updated to match.

## Rollback

Restore `apple-overview.conf` from Fossil to put the carousel back on F3 and the
Fuzzel menu on F4; the overlays then sit unused until something calls them.
Delete the five library files, the two executables and the two test files to
remove them entirely. Nothing else on the desktop depends on them.
