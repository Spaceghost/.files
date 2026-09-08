# Window Navigation Implementation Plan

> **For agentic workers:** Use the repository debugging, TDD and verification
> workflow. Assigned workers implement independent components; the root reviews
> integration and performs scoped Fossil commits.

**Goal:** Consistent window switching, a themed carousel, reliable expose
recovery and a predictable large-floating shortcut.

**Architecture:** One warm GTK4 controller combines a pure MRU/selection model
with per-window previews and a frame-clock renderer. Existing resize and
show-desktop helpers retain their responsibilities and expose focused actions.

**Tech stack:** Python 3, GTK4/GSK, gtk4-layer-shell, Sway IPC and grim -T.
**Spec:** ../specs/2026-09-07-window-navigation.md

## Shared constraints

- Preserve user windows, custom workspace names and unrelated working changes.
- STRATA stays on workspace 10 using Super+0; no actual workspace 0 is created.
- No outline borders; theme colors come from overlay_theme.read_palette.
- Keep physical Tab and Ctrl+Tab available to applications.
- Capture only exact foreign toplevels; never switch workspaces for previews.

## Selection model

Files: desktop/.local/lib/mbp_intel/window_switching.py and
tests/test_window_switching.py under alpine/.

- [x] Test mixed ordinary/agent candidates, interleaved global MRU, frozen
  cycling, reverse, identity reuse, close races and modifier-family release.
- [x] Implement window_candidates(tree), identity(candidate), FocusHistory,
  SwitchState and key_action/modifier_release_commits helpers.
- [x] Run `python3 -m unittest discover -s alpine/tests -p test_window_switching.py -v`.

## Carousel controller and surface

Files: desktop/.local/lib/mbp_intel/carousel.py, carousel_view.py,
desktop/.local/bin/mbp-intel-carousel and tests/test_carousel.py under alpine/.

- [x] Implement one per-Sway control socket/lock and focus-event subscription.
- [x] Share a frozen SwitchState between keyboard and persistent gestures.
- [x] Render nearby angled cards using GTK4 snapshot transforms and theme
  colors; animate selection using the frame clock, sleeping when settled.
- [x] Capture exact window previews asynchronously with
  `grim -T <foreign_toplevel_identifier> -s .35 -t ppm -`.
- [x] Verify cancellation before any capture completes and stale capture
  results cannot update another gesture. Dismiss the layer before commit.
- [x] Add a private native verifier exercising actual key events, MRU order,
  persistent carousel, closed windows, capture and compositor cleanup.

## Expose recovery

Files: showdesktop.py, mbp-intel-showdesktop, test_showdesktop.py and a private
native recovery verifier.

- [x] Reproduce stale hidden state on external workspace navigation.
- [x] Track expected internal focus events, cancel active overlays on external
  navigation, and clear hidden state while keeping the chosen destination.
- [x] Add restore-or-carousel; launch mbp-intel-carousel show only without a
  valid hidden session. Keep ordinary restore a no-op when already restored.
- [x] Test same-output and cross-output recovery and repeated gestures.

## Large floating size

Files: mbp-intel-resize, its unit tests and verify_centered_resize.py.

- [x] Reproduce missing near-full action; implement 90 percent usable geometry
  with 24 pixel minimum margins, fullscreen disable and floating enable.
- [x] Verify actual constrained size is centered; repeat is stable.
- [x] Exercise tiled/floating/fullscreen and a scaled offset output privately.

## Integration and activation

- [x] Bind Super/Alt+Tab and Shift variants to the shared switcher; add its
  transient mode with Escape recovery and start its warm daemon at login.
- [x] Bind Super+Shift+Space to mbp-intel-resize near-full and four-finger down
  to mbp-intel-showdesktop restore-or-carousel. Update shortcut help.
- [x] Run focused tests, private native checks and the Sway parser.
- [x] Inspect synthetic screenshots and retain exact source/runtime evidence.
- [x] Apply live bindings and restart only affected daemons; inspect Strata 10.
- [x] Review and commit exact paths with Fossil, preserving other pending edits.
