# Floating decoration attachment

The focused floating window owns the existing interactive caption on each
visible workspace. Its bottom or right edge follows the saved placement setting,
matches the window's logical width or height, and follows moves and resizes.
The attached surface reserves no workspace space. Compact windows keep the app
menu available while hiding controls that would force the caption past the edge.

Any actual fullscreen container on that visible workspace moves the caption to
the output-wide bottom strip. Global fullscreen forces the bottom strip on every
output. Fullscreen on a hidden workspace does not affect another visible
workspace. Leaving fullscreen restores the saved placement and attachment when
the focused window floats. Tiled focus and empty workspaces use the saved
workspace edge. No forced placement is written into the settings file.

`decoration_placement.py` decides placement from an immutable tree snapshot.
Sway reports `fullscreen_mode=1` on ordinary workspace nodes; only actual
container flags establish fullscreen. The same correction applies to the
interactive controls, so an ordinary float offers entering fullscreen.

Attached captions use the top layer with exclusive zone -1. Coordinates are
relative to the complete output, including when its global origin is negative
or another panel reserves the top edge. Workspace captions retain the overlay
layer and existing reserved space. The saved theme, opacity and radius remain;
fullscreen tiled captions are square and floating captions retain rounding.

Sway emits no continuous floating move or resize events. `decoration_watch.py`
therefore keeps a persistent request socket and a separate event subscription.
Attached geometry uses a 120 Hz request budget; workspace-only polling and appearance
refreshes use 750 ms. The [frame-budget follow-up](2026-09-07-decoration-frame-budget.md)
includes IPC processing time in that budget and avoids redundant GTK resizing.
Unchanged trees are suppressed and pending GTK updates are
coalesced, so motion creates neither a subprocess per frame nor a stale queue.

GTK's display frame clock drives a critically damped geometry spring with a
45 ms response, preserving velocity when its target changes and settling exactly
without overshoot. Mode changes crossfade with a 90 ms response; retired surfaces
are removed within 220 ms, including when an output stops producing frames.
The global GTK animation preference disables these effects. Animation callbacks
stop when the caption is settled. Unit tests compare 60 Hz and 120 Hz trajectories.

The preference editor explains attachment and fullscreen behavior beside the
existing bottom/right setting. There is no additional preference to synchronize.

Validation: 40 focused unit tests and 25 private native SwayFX checks passed.
The native drag produced intermediate animated positions and settled before
mouse release. Tests cover exact geometry, small windows, reserved top-panel
space, fullscreen/restoration, rendered corner pixels, negative output origin,
and focus/workspace/destruction cleanup. See the [runtime evidence and
screenshots](../../../alpine/verification/decoration-attachment/README.md).
Simultaneous physical multi-output and mixed-refresh rendering remain untested.

Activation deployed only the six decoration executable/module links and
restarted only the live decoration helper. The live output has one caption;
saved bottom placement, 67% opacity and radius 7 remain intact. The deployment
backup is `~/.local/state/oldbook/backups/1788830210274135244`; the activation log
is `~/.local/state/oldbook/decoration/attachment-activation.log`.

Recovery: restore this change's decoration daemon, placement/watcher modules,
action-context correction and editor text from the parent check-in, then restart
only `oldbook-decoration daemon`. Saved placement, opacity and corner settings
do not need restoration.
