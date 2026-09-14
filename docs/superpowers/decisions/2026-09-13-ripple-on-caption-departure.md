# Ripple when the caption leaves its dock

Jack asked that `ripple.py` also apply when the bar moves away from the bottom.
The caption's existing wave ran only when a returning strip contacted its dock;
attaching to a floating window explicitly skipped capture and contact.

Lifting a settled caption out of the bottom or right dock now sends the same
rings from the outline it leaves behind. Capture begins before the first moving
frame, and the wave is dated from departure. The flight does not wait for the
photograph; the existing 100 ms cutoff drops slow captures. A return flight
still photographs its final approach and starts the wave on first contact.
Attaching to the window does not produce another wave, and reversing a flight
that has not reached the dock does not count as a fresh departure.

This extends the landing-only event policy without changing the water shader,
theme settings, bottom/right dock geometry, snapshot crop, power ladder or
one-wave-per-output rule. It does not add new positions to the caption editor.

Regression tests exercise the production flight and capture callbacks, including
both dock edges on an offset output, the departure timestamp, late capture
rejection, cancellation, policy gates and preserved landing contact. Native
evidence and its limits are recorded in
`alpine/verification/ripple-departure/README.md`.
