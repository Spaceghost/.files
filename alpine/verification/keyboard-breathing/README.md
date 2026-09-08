# Keyboard breathing — 2026-09-07

Enabled a six-second whole-keyboard breathing cycle on the MacBookPro11,5.
The existing `smc::kbd_backlight` exposes one 0–255 brightness channel, with
neither per-key nor multicolor controls. Its brightness file is writable by
the existing `input` group. No new package, root service or kernel trigger
was needed. The Linux [applesmc driver](https://raw.githubusercontent.com/torvalds/linux/v6.18/drivers/hwmon/applesmc.c)
registers one LED and queues one SMC `LKSB` brightness update.

## Controls and persistence

- **Shift+F6:** toggle breathing using the engraved illumination key without Fn.
- **Shift+F5:** return to steady light at the chosen brightness.
- **F5/F6:** dim/brighten; while breathing, change its peak. Zero stops breathing.
- **Ghost button → Keyboard glow:** breathing, steady, brighter, dimmer and off.
- CLI: `oldbook-keyboard-backlight breathe`, `steady`, `up`, `down`, `toggle`,
  `restore`, or JSON `status`; `oldbook-control keyboard` opens its menu.

The selected peak remains in `~/.local/state/oldbook/keyboard-backlight`;
`keyboard-backlight-mode` remembers steady/breathing. Login restores these
preferences. Reload and theme switching leave them alone. A 60Hz elapsed-time
loop fades between 12% of the peak and the peak, omits duplicate integer writes,
and skips missed deadlines. Animation frames never save the transient level.
The worker watches its connected Sway peer, retains exclusive ownership, and
restores the latest chosen level when stopped. Different active sessions do
not silently claim the same worker.

## Recorded checks

[live.json](live.json) records the real device before activation, a complete
cycle with readback **31–255**, unchanged saved brightness and modification
time, steady restoration to **255**, and reactivation. Two subsequent restore
commands reused one worker, PID **4259**. Both new runtime Sway bindings received
success acknowledgements. Existing source/install symlinks expose the helper,
control deck and persistent configuration immediately.

[unit-tests-final.log](unit-tests-final.log) records **18 passing tests** using
temporary LED files and Unix sockets: brightness/off behavior, pulse shape,
unchanged preferences, concurrent commands, singleton ownership, rapid
steady-to-breathing handoff, and a dead compositor leaving a stale socket.
[unit-lifecycle-red.log](unit-lifecycle-red.log) retains the earlier meaningful
failures before the lifecycle corrections. An intermediate fixture failure
used a mocked process without a replacement worker; the final test creates
an actual synthetic service thread and checks its readiness.

The existing **22 shortcut-source**, **4 Apple-key**, and **9 feature-index**
checks passed. Three menu scenarios verified steady/breathing controls and
absent-device handling. Python compilation and Sway configuration validation
passed. [validation.json](validation.json) records source hashes and boundaries;
[verify-live.py](verify-live.py) is the explicit hardware-writing activation
probe, not part of unattended unit discovery. Running it requires the effect
to be stopped first and deliberately leaves breathing enabled on success.

Readback is not optical measurement. The kernel may coalesce brightness writes;
this does not prove physical 60Hz light modulation. Physical engraved-key
presses, real logout/login, and suspend/resume were not exercised. These limits
do not affect the observed whole-keyboard control interface.

## Return to steady light

Run `oldbook-keyboard-backlight steady` or press Shift+F5. This stops the worker
and restores the latest chosen peak, including an explicit zero. Use `toggle`
or dim to zero to turn the light off. The previous saved brightness was 255;
the verification retained it. Caps Lock attention and display brightness use
separate helpers and devices.
