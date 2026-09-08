# Dim before lock and the keyboard's last breath

Thirty seconds before swayidle locks the session, the desktop now behaves like
a MacBook that is about to sleep: the display eases down and the keyboard light
takes one last breath. Activity brings both back exactly as they were.

## Behaviour

- `swayidle` (started by `oldbook-session`) gains a stage at 270 seconds:
  `timeout 270 'oldbook-idle dim' resume 'oldbook-idle undim'`, ahead of the
  unchanged 300-second lock and 600-second display-off stages.
- `oldbook-idle dim` records the current backlight level in
  `$XDG_RUNTIME_DIR/oldbook/idle/display.json`, asks the keyboard light for a
  `last-breath`, and returns immediately so `swayidle -w` is never blocked. A
  detached worker then eases the panel from its current level to 20% of the
  maximum over 1.5 seconds with a cosine curve, writing only changed values.
- `oldbook-idle undim` cancels any ramp still running, restores the recorded
  level with a 0.3-second ease-up, and runs `oldbook-keyboard-backlight restore`.
- The keyboard's `last-breath` is a runtime overlay in
  `$XDG_RUNTIME_DIR/oldbook/keyboard-backlight-overlay`: from the visible level
  it rises to the saved peak over 1.5 seconds, falls to fully dark over 4.5
  seconds, then holds dark. The single worker animates it at 60 Hz and drops to
  four checks per second once dark. `restore` or any explicit keyboard-light key
  clears the overlay; the saved level and mode are never written by the overlay.

## Edge cases

- Resume during the ramp: `undim` takes the same lock, marks the ramp cancelled,
  restores the display, and the worker exits at its next step.
- A manual brightness change during the dim window: the worker notices that the
  hardware no longer matches its last write, stops, and marks the record
  `adjusted`; `undim` then leaves the user's level alone.
- Display already at or below 20%: no ramp, nothing to restore; the keyboard
  still breathes.
- Keys off by preference (saved level 0): the last breath does nothing, so an
  idle machine never lights a keyboard the user switched off.
- The lock itself, suspend hooks and the display-off stage are unchanged; the
  keyboard stays dark through the lock until activity triggers `restore`.
- Stale records from a dead worker are replaced; no saved preference file is
  touched by any part of this stage.

## Verification

- `alpine/tests/test_idle_dim.py` drives the CLI against a synthetic backlight
  and a fake keyboard helper: prompt return, eased ramp, mid-ramp cancel,
  manual adjustment, already-dim, no display, duplicate dim, stale record, status.
- `alpine/tests/test_keyboard_backlight.py` runs the worker on a synthetic clock
  for the last breath: rise, fall, hold, bounded idle checks, unchanged saved
  files, resumption of breathing after `restore`, keys-off preference, and
  explicit actions ending the overlay.
- Live checks on the MacBookPro11,5 are recorded in
  `alpine/verification/keyboard-ambient/README.md`.

## Recovery

Remove the `timeout 270 … resume …` pair from the swayidle command in
`oldbook-session` to disable the stage; the helper is otherwise inert. If a
dim is ever left behind, `oldbook-idle undim` restores the display and keyboard,
and `oldbook-keyboard-backlight restore` alone clears a stuck last breath.
