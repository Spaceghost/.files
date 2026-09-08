# Immediate decoration placement when changing window mode

The user reported slow, jumpy decoration when changing a tiled window to
floating. The daemon still crossfaded workspace/window attachment-mode changes:
it kept the old surface for up to 220 ms and mapped the new caption at opacity
zero. Hover focus handoffs already avoided this behavior.

An isolated trace of the unmodified daemon reproduced the problem with both
plain `floating enable` and `mbp-intel-resize shrink`. The window itself completed
one geometry change, and the caption received only one target. The old and new
caption surfaces overlapped throughout the fade; no extra resize/recenter jump
was reproduced in those scenarios.

Mode changes now use the same immediate replacement policy as hover handoffs:
destroy the former surface, prepare all new controls and geometry before mapping,
and start at full window opacity. The user's configured background opacity is
still applied by CSS. Same-window dragging and resizing keep their existing
geometry spring. Edge-only appearance changes keep their existing fade.

In the isolated before/after check, plain float attachment settled in about
22 ms instead of 231 ms; centered-resize attachment settled in about 91 ms
instead of 305 ms. Both replacements mapped at full opacity without overlapping
old/new captions. These are private compositor measurements under the current
host workload, not physical-display scanout timings.

Evidence lives in `alpine/verification/decoration-transition/`; reproduce with
`python3 alpine/tests/verify_decoration_transition.py --output /tmp/transition-check`.
The 41 decoration unit tests, Python compilation, and all 28 native attachment
checks passed on the final daemon, including hover, dragging, fullscreen,
tile/float controls, output origins, and workspace changes.

Activated by restarting only the live decoration daemon, with exactly one
caption per active output afterward. Its source hash matches the measured fix.
Saved bottom placement, 0.67 background opacity, and 7 px radius were preserved.

Recovery: restore only `alpine/desktop/.local/bin/mbp-intel-decoration` from the
parent of this check-in and restart only `mbp-intel-decoration daemon`. Saved
placement, opacity and corner radius do not need restoration.
