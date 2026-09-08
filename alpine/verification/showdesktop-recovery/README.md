# Show-desktop recovery — 2026-09-07

Show-desktop now watches workspace focus while its GTK animation runs and while
the desktop is bare. External navigation cancels the overlay and clears its
saved capture. The real windows stay on their original workspace throughout.
An empty destination keeps its workspace ID and focus; there is no detour that
could destroy it. When focus moves to another output, the captured output's
original workspace is restored while focus returns to the requested output.

The helper recognizes its own hide/restore focus events. A saved origin ID
survives workspace renaming. Graceful stop restores a bare desktop; a replacement
helper recovers state left by a crash. A gesture starts one replacement guard if
the login helper is absent, so an unattended one-shot hide cannot outlive its
workspace observer. `restore-or-carousel` restores hidden windows, or invokes
`~/.local/bin/oldbook-carousel show` when none are hidden. A returning gesture
queued during animation retains its restore meaning.

The [native evidence](evidence.json) passes 11 checks with real GTK4 layer-shell
overlays, private SwayFX and two synthetic Foot windows:

- Normal hide and restore preserve window identity, geometry and focusability.
- A bare return gesture invokes the carousel dispatcher exactly once; restoring
  hidden windows does not invoke it.
- External navigation preserves an empty destination and clears state/capture.
- Navigation before the hide swap, during hiding, and during restoration cannot
  be undone by a later animation callback.
- Navigation to another output restores the captured output and preserves the
  requested destination's focus.
- SIGTERM restores the origin and removes its capture.
- An absent helper starts one guard before hiding; recovery after SIGKILL
  restores its saved state without unexpectedly opening the carousel.

The native run compares all captured window IDs and rectangles after eight
recovery points and focuses each real fixture window. It observes destination
focus for 900 ms after cancellation, longer than either animation. The
[screenshot](recovered-windows.png) contains only those synthetic windows.
[Runtime](runtime.log) and [private bus](bus.log) logs retain observed warnings;
the IPC disconnect occurs during intentional helper termination.

All [48 focused unit tests](unit-tests.json) also pass; the
[full log](unit-tests.log) covers the existing card geometry and animation
curves plus lifecycle, missing-capture, failed-recovery and fallback behavior.
The animation curves and per-frame rendering work are retained. This run does
not make a new frame-rate measurement.

Tested showdesktop module SHA-256:
`378440a5cc986219a5bc9f3956e70e287a7bb867c776e16bf02bb07c81b0519e`.
Other source and verifier hashes are in the evidence. Exact source bytes were
copied into the private HOME before testing, so concurrent changes to shared
helpers cannot alter the test halfway through. All source hashes still matched
at the end. [Provenance](provenance.json) records artifact hashes and sanitation.

The fixture starts D-Bus under its private HOME/runtime and updates that private
bus's activation environment for Sway. Activated portal services are isolated
too. Cleanup targets tracked process groups and the exact private runtime marker.
The carousel GUI is replaced by an argument recorder in this test; its rendering
and interaction are verified separately. No real user capture, profile, host
gesture, live helper restart or desktop activation is part of this evidence.

To reproduce from the repository root with a new output directory:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_showdesktop*.py' -v
python3 alpine/tests/verify_showdesktop_recovery.py \
    --output /tmp/showdesktop-recovery-new
```

Run native compositor checks sequentially. The verifier requires SwayFX, Foot,
grim, GTK4/gtk4-layer-shell, Python GI/cairo and the D-Bus session utilities.

Recovery uses the state and capture under
`$XDG_RUNTIME_DIR/oldbook/showdesktop/`. A graceful helper stop restores a hidden
origin and removes those files; restarting the helper recovers state after a
crash. To revert the implementation, first let the current helper recover, then
restore [showdesktop.py](../../desktop/.local/lib/oldbook/showdesktop.py) and
[oldbook-showdesktop](../../desktop/.local/bin/oldbook-showdesktop) together.
Restore the four-finger-down binding to `restore` when reverting the new action,
then restart the helper. Window geometry and application profiles are untouched.
