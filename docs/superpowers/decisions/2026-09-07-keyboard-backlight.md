# MacBook keyboard illumination controls

Use the already available `applesmc` LED device `smc::kbd_backlight` and
`brightnessctl` permissions to enable the keyboard light. Bind Sway's keyboard
illumination keysyms to a focused helper in a dedicated include. Permit these
lighting controls while locked. Preserve `hid_apple` auto mode and ordinary
Fn+F5/F6 application shortcuts.

Use brightnessctl's 10% relative steps, allow fully off, and save the selected
raw level in the user's state directory. A new Sway login restores it, including
an explicit zero. With no saved preference, retain an existing nonzero level or
enable 25%. A normal Sway reload does not reset it. Serialize helpers because
key repeat can overlap processes; write saved state atomically.

Keep display brightness, Caps Lock notification LEDs and kernel input mappings
outside this helper. No new package, root service or global Fn preference is
needed on the observed hardware. See
`alpine/verification/keyboard-backlight/README.md` for runtime evidence,
remaining physical checks and reversal instructions.
