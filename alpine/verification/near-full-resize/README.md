# Near-full floating window resize

`oldbook-resize near-full` makes the focused window float, exits fullscreen,
and centers it inside the current workspace's usable rectangle. Each edge
keeps five percent of the available dimension, with a minimum 24 logical pixels.
Repeated calls keep the same geometry; application size constraints are honored
and the actual resulting size is centered.

Six focused unit checks passed after four expected regression failures against
the old helper. The private native Sway run passed all 28 checks: 14 existing
centered grow/shrink and key checks, plus 14 near-full checks across floating,
tiled and fullscreen starts, repeated use, reserved top-bar clearance, an
unrelated window, and a scaled output at a nonzero offset. The final synthetic
screenshot shows a 1036×612 window centered in a 1152×680 usable workspace on the
scaled output.

The verifier now starts D-Bus after isolating HOME/XDG directories, retains
compositor logs, waits for the exact initial setup geometry, and cleans up its
owned process groups. Earlier fixture failures and the scope of keyboard
verification are recorded in `evidence.json`. No host window was resized and no
live desktop service was restarted.
