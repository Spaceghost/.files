# Bar visualizer (optional)

**Date:** 2026-09-08 · **Scope:** Waybar centre, additive and removable

The user marked this "maybe", so it is one module and one script, removable by
deleting `"custom/cava"` from `modules-center` in both `config.jsonc` copies.
Waybar 0.15 on this desktop is not linked against libcava, so the module is a
`custom` module fed by `desktop/.local/bin/oldbook-cava-bar`:

- cava runs with a generated private config (`$XDG_RUNTIME_DIR/oldbook/cava-bar.conf`,
  mode 0600): raw ASCII output, ten bars, 20 frames per second, stereo averaged
  to mono, `ascii_max_range = 7` so each value maps directly onto ▁▂▃▄▅▆▇█.
- One JSON line per changed frame; identical frames are not re-emitted.
- `playerctl status` is polled once a second. When nothing reports Playing,
  cava is terminated so the module costs nothing, and the module shows the
  `silent` class with empty text. Half a second of all-zero frames while a
  player is playing also collapses it, so gaps between tracks do not jitter.
- The feeder cannot outlive its bar: it asks the kernel for SIGTERM when its
  parent dies (`PR_SET_PDEATHSIG`), polls the module pipe once a second so a
  closed reader ends a silent feeder too, and its signal handler only unwinds
  so cleanup never runs inside an interrupted wait (a headless run had left one
  orphan blocked on a lock before this).
- No clicks, no tooltip: BAR-LAYOUT's music controls keep their actions and
  the meter sits after `mpris#next`. CSS colours it aqua like `#mpris`, and
  `.silent` drops padding and margin so the centre group does not reserve space.

`alpine/tests/test_cava_bar.py` checks the glyph mapping and config, and drives
the script with a fake `cava` and `playerctl` on PATH: bars appear while
"Playing", collapse on sustained silence, and the fake cava is stopped once the
player pauses. CPU cost and the rendered bar are recorded in
`alpine/verification/bar-visualizer/`.
