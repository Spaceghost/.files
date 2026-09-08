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

## Whole-keyboard breathing

The user clarified that “breathing” means the keyboard illumination. The
MacBookPro11,5 exposes one `smc::kbd_backlight` LED with a maximum of 255 and
no multicolor or per-key interface. Linux's applesmc driver registers one LED,
places one brightness byte in `backlight_state`, and schedules a work item
writing the `LKSB` SMC key. Fade the whole keyboard together; do not claim
individual-key control. The existing brightness permission remains sufficient.

Use one Python worker with direct sysfs writes, a six-second cosine cycle
between 12% of the chosen peak and the peak, and a 60Hz scheduling target.
Skip identical rounded values and missed deadlines; the SMC work queue can
coalesce updates, so requested updates are not proof of optical refresh rate.
Keep state writes out of the animation loop. The existing brightness file
continues to store the intended level, while a sibling mode file records
steady/breathing. Theme changes and Sway reloads do not reset these choices.

Shift+F6 toggles breathing and Shift+F5 returns to steady light. The control
deck also exposes them. F5/F6 adjust the chosen peak while breathing; reducing
it to zero or toggling the light off ends breathing. This extends the existing
keys without changing their engraving/Fn interpretation. Return to the latest
saved brightness on worker exit, including a concurrent manual off decision;
do not restore an old animation sample or overwrite newer user input.

Two new typing modes now use the same keyset in lock-aware combinations:

- `Ctrl+XF86KbdBrightnessUp` (`typing`): each keypress brightens the glow and
  then decays back toward dark when typing stops.
- `Ctrl+XF86KbdBrightnessDown` (`typing-dark`): each keypress darkens the glow
  from full-bright, then recovers when typing pauses.
- `Ctrl+Shift+XF86KbdBrightnessUp` (`typing-wpm`): only sustained typing above
  ~22 WPM moves the anchor brighter; slower input only lets the glow continue
  decaying.
- `Ctrl+Shift+XF86KbdBrightnessDown` (`typing-dark-wpm`): only sustained typing
  above ~22 WPM moves the glow dimmer; slower input lets it recover toward
  bright.

Serialize short hardware/state operations separately from worker ownership.
Detect the originating Sway connection ending and release ownership cleanly.
No kernel trigger, privileged service, new package or Caps Lock LED changes
are needed. See `alpine/verification/keyboard-breathing/README.md` for the
actual hardware readback, verification limits and steady-light recovery.
