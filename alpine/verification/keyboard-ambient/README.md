# Keyboard last breath and ambient glow — 2026-09-08

Live checks on the MacBookPro11,5 (`smc::kbd_backlight`, 0–255; Apple SMC
light sensor `/sys/devices/platform/applesmc.768/light`; `gmux_backlight`
0–1023). Both runs used the real hardware through the session's Sway socket so
the worker's ownership record matches the desktop session.

## Stray LED trigger

Before the checks the keyboard light's kernel trigger read `[nand-disk]`
([trigger-before.txt](trigger-before.txt)); the file is root-owned and had been
modified at 02:32 the same night. With a foreign trigger the helper refuses
every animated mode, which explains the dark keyboard and the stopped
breathing worker found on arrival (saved level 255, saved mode breathing,
brightness 0, `running: false`). No udev rule, boot script or checked-in tool
sets that trigger, so it was returned to `none`, the driver default. The source
of the stray write was not identified.

## Ambient mode on the real LED

[ambient-live-probe.py](ambient-live-probe.py) constructs the helper with the
real LED but private state and runtime directories and a fake sensor file, so
the user's saved preference files were never read or written. Saved peak 255.
[ambient-live.json](ambient-live.json) records the readings every quarter second:

- fake reading `(2,0)` for eight seconds: the keys held **255**;
- `(600,0)`: **255 → 193 → 99 → 58 → 7 → 3 → 0** across successive two-second
  samples, each step a 1.2-second fade, dark by 14 seconds;
- `(1,0)`: **0 → 65 → 121 → 191 → 235 → 248 → 255**, full by 27 seconds;
- worker stop wrote the private saved level (255); the hardware was then put
  back to the level found before the probe (0).

The real sensor read `(10,0)` throughout; the room was not changed physically.

## Idle stage end to end

[idle-live.json](idle-live.json) records `oldbook-idle dim`, 2.4 seconds of
readings, `oldbook-idle status`, `oldbook-idle undim`, and the keyboard status
around the cycle, run while the display was on:

- `dim` returned `dimming` after 0.83 seconds (the last-breath request waits
  for the worker to own the light), so `swayidle -w` is not held for the ramp;
- display **1023 → 988 → 888 → 740 → 614 → 448 → 310** over the first 2.2
  seconds toward the 205 target; the runtime record showed
  `original: 1023, target: 205, ramp: true`;
- keyboard **0 → 40 → 87 → 140 → 191 → 231 → 252 → 255** as the last breath
  rose over 1.5 seconds; status showed `overlay: last-breath`, `running: true`;
- `undim` returned `restored` in 0.43 seconds: display back at **1023**, the
  keyboard's `restore` cleared the overlay and breathing resumed (readings
  48, 40, 34, 31, 33, 38, 46 around the waveform's trough);
- saved level **255** and saved mode **breathing** were unchanged throughout.

The cycle was kept short because the user was at the machine; the full
6-second fall to dark and the hold were exercised on the synthetic clock in
`test_keyboard_backlight.py`, not physically.

## Unit checks

`test_keyboard_backlight.py`: 28 tests (20 existing plus last-breath shape,
resume of breathing after `restore`, keys-off preference, explicit actions
clearing the overlay, sensor validation, status and peak adjustment, mapping
shape and `(l,r)` parsing, and a 50-second synthetic ambient run).
`test_idle_dim.py`: 9 subprocess tests against a synthetic backlight and a
fake keyboard helper. `test_shortcut_sources.py` (22) and `test_session.py`
passed; `sway --validate` accepted the configuration with the new binding.

## Limits

The running swayidle still carries the previous command line; the new
`timeout 270` stage takes effect at the next graphical login or when the idle
daemon is restarted deliberately. Readback is not optical measurement, and the
physical Option+F6 chord, a real 270-second idle, suspend/resume and a genuine
change of room light were not observed.
