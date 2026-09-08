# Shared window navigation

Super+Tab and Alt+Tab use one global recent-focus list across normal windows
and workspaces. Hold the initiating modifier to cycle, add Shift to reverse,
release to select, or Escape to cancel. The list is frozen for a gesture;
closing a window removes its identity and cannot select a reused container.
Ordinary Tab and Ctrl+Tab remain application keys.

Four-finger down restores an exposed desktop, or opens the persistent carousel
when there are no hidden windows. The carousel supports arrows, Tab, scrolling,
clicking, Enter and Escape. GTK4/GSK renders angled window previews with the
active theme and soft shadows. Animation uses the frame clock and stops when
settled. `grim -T` captures exact foreign toplevels asynchronously, including
hidden workspaces, without moving focus. These previews stay in process memory.

`oldbook-carousel daemon` tracks real focus events while idle and accepts
commands through a private, per-compositor datagram socket. Repeated starts
share one owner. Closing a popup synchronizes Wayland destruction before Sway
focus; mode takeover prevents a late modifier release from accepting a choice.
Pending preview results carry a generation and window identity. Neither slow
capture nor old results delay cancellation or change the next gesture.

## Evidence

- [Carousel native proof](../carousel/native/evidence.json) passes all 15 check
  groups using the production SwayFX executable, real synthetic key events and
  exact window captures. The retained [screenshot](../carousel/native/carousel-hidden-previews.png)
  shows Strata's hidden workspace preview. Final active frame interval median
  is 16.4385 ms across the recorded 95 callbacks. Compositor shutdown terminates
  the daemon; GTK's expected broken-display exit is recorded, with zero private
  processes surviving fixture cleanup.
- `native-baseline/` reproduces the original Super+Tab workspace bounce.
- `controller-*.log`, `selection-*.log`, `view-green.log` and
  `shortcut-tests.log` cover framing, capture lifecycle, MRU, closed/reused
  windows, modifier families, geometry, motion and shortcut descriptions.
- `sway-validation.log` and `shellcheck.log` cover the integrated configuration
  and the session startup shell script. Deployment was exercised in a
  disposable HOME.
- `activation.json` records the live daemons, loaded input modes and workspace
  numbers. Loading the new mode required one validated full Sway reload because
  runtime `include` and inline mode blocks are unsupported. Both helpers have
  one owner and the carousel starts closed. Workspace numbers remain
  1, 2, 3, 4, 10. All existing window IDs remain present. One window changed
  workspace/position during reload and moved again before conditional recovery;
  its newer position was preserved. `activated-source-sha256.json` pins the
  activated sources.
- [Near-full resizing](../near-full-resize/evidence.json) retains six unit and
  28 private native checks, including usable space, fullscreen and scaled
  output offsets. Super+Shift+Space invokes `oldbook-resize near-full`.
- [Expose recovery](../showdesktop-recovery/README.md) retains 48 unit and
  11 private native checks, including interrupted animations, empty workspace
  destinations, cross-output restoration and daemon recovery.

Screenshots contain synthetic private windows. No real application preview or
window title is part of this evidence. Physical keyboard/touchpad input and a
new login remain manual checks; synthetic Wayland input and the installed
bindings are checked separately. Frame timings from a private desktop do not
establish the physical panel's delivered frame rate.

## Recovery

Press Escape to leave a mapped carousel, or run `oldbook-carousel cancel`.
`oldbook-showdesktop restore` brings back a valid exposed desktop; restarting
its daemon also recovers same-session state. Both daemons use per-session
locks, so Sway reloads cannot stack copies. Strata remains numeric workspace
10, selected with Super+0 and displayed after 1–9.

The former Super+Tab binding was `workspace back_and_forth`; Alt+Tab used the
agent-only `oldbook-agent-switcher` helper. The previous resize shortcut was
`focus mode_toggle`. These are documented for rollback, not active defaults.
Restore the corresponding bindings and restart only the affected helpers to
roll back navigation behavior. Do not delete a show-desktop state file while
its captured output still displays the hidden desktop; restore it first.
