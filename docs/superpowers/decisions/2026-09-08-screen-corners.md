# Rounded physical output corners

The user requests rounded screen corners with nothing drawing over the cutouts.
Use a 20 logical pixel radius, independent of window decorations and themes.
Do not change usable area, window placement, input regions or panel geometry.

A layer-shell window cannot enforce this against later overlays or hardware
cursors. The SwayFX patch adds a final black, antialiased mask after SceneFX has
rendered the entire scene and software cursors. Both ordinary frames and output
configuration commits use this path. Render and software-cursor locks prevent
direct scanout and hardware cursors from bypassing the mask. The explicit-sync
presentation fence follows the final pass, not the preceding scene pass.

SPACEGHOST_SCREEN_CORNER_RADIUS is read at compositor startup (0 disables;
integer range 0–100). The desktop launcher supplies 20.
Stock Sway remains available through MBP_INTEL_STOCK_SWAY=1. A running compositor
cannot adopt a newly installed executable; activation requires a new session.
Never terminate the user's current compositor to activate this change.

Verification uses a separate runtime directory and headless output, with white
background, fullscreen client, a later overlay, cursor-at-corner, repeated damage,
scale, rotation, resize, reload and session lock. It must fail against the old
binary and pass against the packaged binary. This does not establish hardware
scanout or physical frame-rate behavior; those require a subsequent real login.

Implementation and signed-package evidence are in `alpine/verification/screen-corners/`.
Host lock: `alpine/packages/locks/01ffe0826b41138f957d.json`.
Desktop lock: `alpine/packages/locks/2a17df0fccf3c7b2a7ad.json`.
