# MacBook keyboard backlight verification

The live MacBookPro11,5 exposed `smc::kbd_backlight` through `applesmc` on
Linux `6.18.49-0-lts`. It was initially off (`0/255`). The existing
`brightnessctl` LED udev rule grants group `input` write access; Jack already
belongs to that group. The light now starts at `64/255` (25%). No packages,
root configuration, kernel parameters or input mappings were changed.

`hardware.json` records actual LED writes and readback, state persistence and
concurrent adjustment checks. The checks used a temporary `XDG_STATE_HOME`,
then restored the final hardware level to 64; the real saved preference is 64.
The initial check expected a 26-unit percentage delta, then was corrected to
the observed brightnessctl relative step of 25 units at a maximum of 255.

The internal keyboard advertises F5, F6, Fn and all three illumination events.
Its loaded `hid_apple` mode remains `3` (auto). Linux's
[Apple keyboard driver](https://github.com/torvalds/linux/blob/v6.18/drivers/hid/hid-apple.c)
maps this product (`05ac:0274`) through `apple_fn_keys`: F5/F6 produce keyboard
illumination down/up in media-first mode, and Fn restores ordinary F5/F6.
This mapping follows driver configuration and advertised capabilities;
physical keypresses were not recorded or tested. The generic LED interface is
documented in the [kernel LED guide](https://docs.kernel.org/leds/leds-class.html).

ShellCheck and `sh -n` passed for `oldbook-keyboard-backlight`. All 22 existing
`test_shortcut_sources.py` tests passed after adding readable helper labels.
The isolated fragment passed Sway's parser. After the separately coordinated
full SwayFX config reload, `wtype -k XF86KbdBrightnessDown` dispatched through
the live binding and changed both hardware and saved state from 64 to 39;
`XF86KbdBrightnessUp` restored both to 64. No input events were read.
An actual locked-session keypress and a new graphical login remain unverified;
the helper's restore command was exercised directly, including a saved zero.

The scoped deployment journal is
`~/.local/state/oldbook/backups/1788836879559921079`. To undo the two new live
links, run `alpine/bin/deploy-home --target "$HOME" --rollback` with that backup
path, then reload Sway. To return hardware to its original off state, run
`brightnessctl --class=leds --device=smc::kbd_backlight --min-value=0 set 0`.
Removing the binding fragment prevents the saved level being restored at login.
