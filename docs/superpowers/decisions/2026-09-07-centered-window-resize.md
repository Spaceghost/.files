# Centered window resizing

Super+plus grows the focused window, and Super+minus shrinks it. Each step
changes both dimensions by 40 logical pixels, normally moving each edge by 20.
The unshifted equals key also grows; keypad Add/Subtract have matching bindings.

`mbp-intel-resize` uses Sway's native `resize set` so both dimensions are handled
in one operation, preserving the floating window center and respecting Sway's
minimum/maximum sizes. Separate grow-width/grow-height commands can abort at
one dimension's limit and leave the other unchanged. A nonblocking per-session
lock coalesces rapid key repeats instead of building a resize queue.

Tiled windows become floating. Their original center is restored using the
actual size after Sway's constraints, because plain `floating enable` otherwise
uses the application's natural size and centers it on the workspace. Fullscreen
is disabled when resizing. No focused application means no action. Integer
rounding can move the center by half a logical pixel at an odd size limit.

The bindings live in `alpine/desktop/.config/sway/local.d/resize.conf`; the helper
and include are deployed as managed HOME links. Only these new bindings were
installed in the live session; a complete desktop reload was unnecessary.

Recovery: remove the managed resize.conf include, reload Sway, and remove the
helper link if no longer needed. The selected-file deployment journal can also
roll back the two HOME links. Super+Space retains the normal floating/tiling toggle.

[Sway resize implementation](https://github.com/swaywm/sway/blob/1.12/sway/commands/resize.c)
provided the reference behavior; runtime evidence uses the installed SwayFX.

Validation: `python3 alpine/tests/verify_centered_resize.py` passes 14 checks
in private headless Sway: centered floating grow/shrink, the other window
unchanged, independent dimensions at minimum/maximum size, tiled/fullscreen
transitions, and six symbolic shortcut variants. Evidence and screenshot:
`alpine/verification/centered-resize/`. Sway syntax validation, Python compilation
and selected-file disposable HOME deployment also pass. The six bindings were
installed successfully into the live session. Physical Shift+= mapping and
reboot persistence were not observed; equals and explicit Shift+plus are both
bound to cover the grow key with or without Shift.
