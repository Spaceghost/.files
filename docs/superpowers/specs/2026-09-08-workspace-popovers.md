# Workspace peek and the click-origin reveal — 2026-09-08

## What

Two additions to the native bar module, released as `oldbook-waybar-art` r11.

**Workspace peek.** Resting the pointer on a workspace button for 350 ms opens a
popover under the bar holding that workspace's windows: one card per window, a
rounded still above a shortened title. Leaving the button closes it. Crossing
into the button's own label does not, so the peek does not flicker while the
pointer moves within the button.

**Click-origin reveal.** A right-click on the artwork badge now passes the point
it landed on to `oldbook-wallpaper next --from X,Y`, so the crossfade daemon's
radial reveal grows the next painting out of the badge instead of fading the
whole screen evenly. Every other pointer action on the badge is untouched.

## Where the stills come from

`oldbook-window-stills` is a new helper that imports `carousel.capture_preview`
rather than growing a second capture engine, so a still in the bar and a card in
the window switcher come from the same compositor call and the same limits. It
enumerates the workspace's windows through the existing Sway IPC helpers,
captures the ones it has no image for, and writes rounded PNGs into
`~/.cache/oldbook/stills/`, keyed by the window and the height asked for, with
private permissions and an atomic rename. Hovering the same workspace twice
costs one Sway query and nothing else. The cache never enters the checkout.

The C side spawns the helper asynchronously and builds the popover when it
answers, so the bar's main loop never waits on a capture. A helper that fails,
prints nothing, prints nonsense or reports no windows opens no popover at all.

## Why a popover, and why it is discoverable

GTK popovers attach to the button and follow it, which is what a peek under a
workspace should do; a tooltip cannot hold images with captions. The open
popover is published on its button under `oldbook-workspace-peek`, so the test
fixture can find it without reaching into the module's private binding record.

## The reveal origin

GDK reports root coordinates relative to the layer surface, which is the bar, so
the click point is translated into the toplevel and the toplevel's own origin is
added back. The result is a point on the badge, accurate to the bar's margin,
which is invisible in a reveal that spans the whole screen.

## Verification

`tests/workspace-peek.c` drives the feature under a private X server with a
private HOME and a scripted stills helper: 24 checks covering the dwell, the
card structure, title shortening, the failed-capture card, closing, inferior
crossings, unnumbered labels, four kinds of broken helper, and two shutdown
orders. Both isolated package builds were byte-identical, the APK is archived in
Fossil, and the running Waybar maps the new library. The peek has not been
watched opening on the physical panel: the session was locked throughout.

`verify-workspaces-headless` in this package fails before and after this change,
because it loads the archived `themes/spaceghost.json`. That is the same
pre-existing breakage as `test_ghost_branding`, not a regression here.

## Rollback

Install the archived r10 APK and restart Waybar; the badge, its clicks and the
workspace label emphasis return to their previous behaviour. Deleting
`~/.cache/oldbook/stills/` only costs the next hover its captures.
