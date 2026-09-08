# Ambient keyboard glow

The MacBookPro11,5's Apple SMC exposes its ambient light sensor at
`/sys/devices/platform/applesmc.768/light` as `(left,right)`; on this model the
left slot carries one 10-bit reading and the right slot stays 0. The keyboard
light remains the single whole-keyboard `smc::kbd_backlight` channel that the
KEYBOARD-GLOW contract already describes.

## Ambient mode

`oldbook-keyboard-backlight ambient` (Option/Alt+F6, the control deck's
**Ambient glow** entry) makes the existing worker follow the room:

- Every two seconds the worker reads the sensor and takes the brighter of the
  two values. Readings are smoothed on a log scale with an exponential moving
  average (weight 0.5), and a new target is only chosen when the smoothed value
  moves more than 0.15 log units from the value that produced the current
  target. A lamp switching on or a cloud passing settles within a few samples;
  sensor jitter produces no change at all.
- The mapping is macOS-like: at or below a reading of 3 the keys sit at the
  saved peak; at or above 240 they are off; between the two a smoothstep on the
  log scale gives a gentle curve.
- Each retarget fades over 1.2 seconds from wherever the previous fade was, so
  the light never jumps. Writes are skipped when the integer level is unchanged
  and the loop idles at four checks per second once settled.
- The mode persists in `keyboard-backlight-mode` like breathing and the typing
  modes; F5/F6 still adjust the saved peak and retarget immediately; Shift+F5 or
  the deck's steady entry returns to steady light. The action is refused when no
  sensor is readable, leaving the previous mode in place. `status` reports the
  sensor path and the current reading.

## Upstream

`wluma` cannot use this sensor because it is not an IIO device. A branch adds an
`[als.applesmc]` backend (configurable `path`, `(l,r)` parsing, brighter slot,
raw reading scaled as lux for its predictor), documented in its README and
covered by unit tests; the pull request records exactly what was built and
tested on this machine. The local ambient mode does not depend on it.

## Verification

`alpine/tests/test_keyboard_backlight.py` covers sensor validation, status,
peak adjustment, the mapping's monotonic shape, `(l,r)` parsing and a synthetic
50-second run: dark room holds the peak, daylight fades to off, darkness fades
back, no frame moves more than eight units, and the saved level file is
byte-for-byte untouched. Live readings and the hardware run are recorded in
`alpine/verification/keyboard-ambient/README.md`.
