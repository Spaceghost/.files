# Bar visualizer evidence — 2026-09-08

`bar-headless.png` is the production bar (live profile config and stylesheet,
tray removed, output `HEADLESS-1` at 1440×900) rendered in a private headless
SwayFX session while Pithos played on the real session bus: the ten-bar
`custom/cava` meter sits after the next-track control. The same harness
without the module reported the same "Bar configured (height: 40)" line, so
the module does not change the bar's height.

CPU over 20 s with a player active, from `/proc` utime+stime:

| Measurement | oldbook-cava-bar | cava | Waybar |
| --- | --- | --- | --- |
| Live session (`live-cpu.json`; the Waybar row sums every waybar process the user owned at the time, including other agents' private bars) | 0.45 % | 2.15 % | 1.25 % |
| Headless, gles2 software renderer (`headless-cpu.json`) | 0.40 % | 1.60 % | 3.15 % |
| Headless without the module (`headless-cpu-without-module.json`) | — | — | 0.75 % |

Percentages are of one core. With nothing playing the feeder stops cava and
costs a `playerctl status` call per second. The live physical bar was not
inspected by eye in this session (display off and locked at the time); the
JSON reload with `pkill -USR2` left exactly one feeder process attached to
Waybar's pipe.
