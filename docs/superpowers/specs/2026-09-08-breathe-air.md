# Breathe on air

The user asked: "Can we breathe where any keystrokes I do add 'air'?" The
`breathe-air` keyboard-light mode answers it inside the existing single worker.

## Behaviour

- The lungs hold a volume between a quarter and full. At rest the breath is
  shallow and slow: from 12% of the saved peak up to a quarter of the way to
  the peak, about seven seconds per cycle.
- Every keystroke read from the same evdev sampling the typing modes use adds a
  fixed sip (6% of full), capped at full. The visible volume follows the target
  with a half-second smoothing, so a burst of keys deepens the breath rather
  than snapping it.
- Idle lungs leak toward the quiet baseline with a twenty-second time constant.
- Volume scales the amplitude and shortens the period linearly from seven
  seconds at rest to three seconds when full. The phase accumulates
  continuously from the elapsed time and the current period, so a change of
  tempo never jumps the light.
- The mode persists like breathing and the typing modes, F5/F6 move the saved
  peak, Shift+F5 returns to steady light, and the worker still writes only
  changed integer levels and restores the saved level on shutdown or
  compositor loss. No animation sample ever touches the saved files.

## Controls

Option+Shift+F6 (`Mod1+Shift+XF86KbdBrightnessUp`), the control deck's
"Breathe on air" entry, or `oldbook-keyboard-backlight breathe-air`.

## Verification

`test_keyboard_backlight.py` drives the worker on a synthetic clock with
scripted keystrokes: the resting breath tops out at about a third of the peak
with a seven-second period, fifteen keystrokes bring the next crests near the
peak about three seconds apart with no frame moving more than 5% of the peak,
the crests decay over the following minute, and the saved level file is
untouched. The live check is recorded in
`alpine/verification/keyboard-ambient/README.md`.
