# Apple overview and launcher keys

The MacBook's engraved Mission Control and Launchpad keys now open the window
overview and application launcher. Pressing Mission Control again leaves the
overview; Launchpad also leaves it before handing off to the launcher. The
bindings suppress key repeat and shortcut help uses the keycap names.

| Keycap | Linux → XKB mapping | Default action | Overview action |
| --- | --- | --- | --- |
| Mission Control / F3 | `KEY_SCALE` 120 → `XF86LaunchA` | Show overview | Cancel overview |
| Launchpad / F4 | `KEY_ALL_APPLICATIONS` 204 → `XF86LaunchB` | Application launcher | Cancel and launch |

No plain `F3`, `F4`, or `Ctrl+Up` binding is added. Fn+F3/F4 therefore retain
their application behavior.

The September 7, 2026 hardware audit read vendor/product `05ac:0274` and
`hid_apple.fnmode=3` from sysfs. The installed 6.18.49 kernel module contains
F3→120 and F4→204 in `apple_fn_keys`; its matching device entry has quirks 5.
The [upstream kernel driver](https://raw.githubusercontent.com/torvalds/linux/v6.18/drivers/hid/hid-apple.c)
defines automatic mode and Fn selection. Local XKB `symbols/inet` maps those
event codes (plus the XKB offset of 8) to LaunchA/B. Exact local paths,
module hash, and source hashes are in `mapping-and-validation.json`. No physical
keyboard events were read or injected.

Validation passed: 4 focused unit tests, 22 existing shortcut discovery tests,
full Sway configuration validation, 8 initial private dispatch checks, and 8 final real
GUI checks. The dispatch
fixture loads the new mode block before the existing window-switcher block,
matching include order. Sway preserves both sets of bindings. Virtual key events
prove default dispatch, cancellation, launcher dispatch, mode reset, held-key
suppression, and the original Escape binding. Real Foot receives raw F3/F4 as
`1b4f52` / `1b4f53`, without desktop actions.

Both fixtures use an isolated HOME, XDG directories, D-Bus, and headless SwayFX.
The original run's two action helpers only record invocations; its evidence
remains at this directory's root under that earlier verifier hash. The final
`real/` run starts the production carousel daemon and invokes real Fuzzel dmenu
with one synthetic entry. It verifies the actual overview layer opens and
closes with Mission Control, then Launchpad unmaps the overview, restores
default mode, and maps Fuzzel. Escape cancels Fuzzel and returns focus to Foot;
the same warm carousel PID survives. The final run verifies renderer
`f5e822cd0833abacba9a70330bbfcbb3a8f3521f7dce9615188c60878c1e9a24`;
the earlier pre-fix run recorded `8fb593bd…`. Every loaded source hash is saved
in the corresponding evidence file and checked again at the end of its run.

The GUI fixture waits for the overview's active mode and visible caption pixels
before continuing, and keeps one virtual keyboard alive throughout the
F4/Escape handoff. Early attempts assumed an outdated cancellation code, sampled
before the mapped callback/paint, or replaced the virtual keyboard during the
handoff; their outcomes are retained in `historical-real-attempts.json`. The
[Fuzzel 1.14 release notes](https://codeberg.org/dnkl/fuzzel/raw/tag/1.14.1/CHANGELOG.md)
specify dmenu cancellation code 2, which the final run observes.

The final bindings close by returning to default mode; the controller handles
that mode event directly. They issue no separate delayed cancel process, which
could otherwise close the next overview after an immediate reopen. Launchpad
returns to default mode and starts the launcher. The earlier successful real
run using the old commands remains in `real-before-mode-fix/`; `real/` and
`final-validation.json` identify the corrected final bindings. Cached rendering
can legitimately finish in two draws, so the final screenshot barrier inspects
painted caption pixels instead of requiring an arbitrary number of draws.

`real/real-overview.png` and `real/real-launcher.png` show only the synthetic
window and menu. `private-key-fixture.png` contains only the synthetic terminal. `runtime.log`
retains the renderer PCI-info notice and Foot's virtual-keyboard focus warnings;
neither prevented the final checks from passing. The private GTK run also logs
unavailable PipeWire/RealtimeKit portal services, and its compositor teardown
logs a GDK display disconnect. Cleanup reports zero remaining private
processes. No live bindings were changed by this verification.

Reproduce from the checkout:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_apple_overview.py' -v
python3 -m unittest discover -s alpine/tests -p 'test_shortcut_sources.py' -v
/usr/bin/swayfx --validate --config alpine/desktop/.config/sway/config
python3 alpine/tests/verify_apple_overview.py --output /tmp/apple-overview-fresh
python3 alpine/tests/verify_apple_overview.py --real --output /tmp/apple-overview-real-fresh
```

The output directory must not already exist. Run the native check separately
from other compositor benchmarks. Source hashes are checked again before the
fixture reports success; its private processes are stopped in `finally`.
