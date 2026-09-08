# High-quality still previews

The carousel keeps the full resolution supplied by the compositor's toplevel
capture source, replacing the former 35%-scale thumbnails. RGB captures are
lossless, and GTK uses trilinear sampling when angling or shrinking cards.
Each candidate gets one immutable snapshot per opening. Changes underneath,
title updates and revisiting a card do not recapture it; reopening does.

Completed capture Futures release their RGB payloads after texture delivery.
A separate requested-identity set prevents accidental live recapture while
retaining generation checks for late results. The decoder accepts up to 16 Mi
pixels, including full 4K/5K capture buffers; two capture workers remain the
limit. Closing and modifier release do not wait for capture completion.

Static card render nodes are reused during movement; preview arrival, changed
card content and theme updates invalidate them. The animation tracks elapsed
time without restarting its clock for each navigation key.

## Keyboard handoff fixes

Escape formerly combined asynchronous `exec oldbook-carousel cancel` with
synchronous `mode default`. The mode event already closed the current popup;
a delayed cancel process could then close a newly reopened popup. A private
native regression reproduced this by delaying only that cancel launcher by
0.75 seconds. Escape and the Apple overview key now return to default mode
without launching a cancel process. Launchpad returns to default mode and
starts the menu. Three immediate Escape/reopen cycles pass on these bindings.

A separate native trace showed a held Super gesture committing at 504 ms,
well before the actual release around 4.2 seconds. The old 50 ms check after
mapping could read an empty modifier mask before keyboard entry. The new check
waits for `GtkWindow.is_active`, performs one Wayland synchronization, then
waits for another idle callback so queued GDK focus events run first. It
rechecks active state, focus epoch, popup identity and lifetime before treating
an empty mask as a quick release. Closing cancels pending readiness callbacks;
normal key-release handling is preserved. On close, Wayland destruction also
completes before a separate Sway IPC focus request.

## Resolution evidence

Do not multiply `grim -T` by the display scale. Grim's toplevel path already
uses the supplied capture-buffer dimensions, and `-s 2` would interpolate
them. In this SwayFX/wlroots implementation, the separate capture output starts
at scale one and is sized to logical scene extents. Consequently a scale-two
physical display can still supply a logical-sized capture. The change retains
all those pixels; it does not claim access to the original client buffer.
See the [wlroots scene source](https://gitlab.freedesktop.org/wlroots/wlroots/-/raw/0.20.2/types/ext_image_capture_source_v1/scene.c),
[output defaults](https://gitlab.freedesktop.org/wlroots/wlroots/-/raw/0.20.2/types/output/output.c)
and [grim 1.5.0 source](https://gitlab.freedesktop.org/emersion/grim/-/archive/v1.5.0/grim-v1.5.0.tar.gz).

The private scale-two verifier compares each preview with a direct full
`grim -T` capture, checks omitted scale against explicit scale one, and checks
that source pixels cover the actual centered card's physical letterboxing.
It repaints a synthetic origin window from green to magenta: the open carousel
must retain green through repeated steps, and reopening must capture magenta.
Only synthetic private windows appear in screenshots and evidence.

`controller-red.log` reproduces downscaling, the former size limit and retained
Future payloads. Its initial green run covered 14 controller checks. The
current focus-barrier candidate passes all 34 carousel unit tests, including
delayed keyboard entry, quick release, focus loss after synchronization and
close-time cancellation. Exact current source hashes are recorded in
[`focus-barrier-evidence.json`](focus-barrier-evidence.json).

| Evidence stage | Observed result | Scope |
| --- | --- | --- |
| [`native-before-card-cache/`](native-before-card-cache/evidence.json) | 18 native checks passed | Earlier renderer, before card caching and the later focus fix |
| [`premature-modifier-commit-failure/`](premature-modifier-commit-failure/evidence.json) | Seven quality/persistent groups passed, then held-modifier commit failed | Cached quality/responsiveness sources before the focus barrier |
| [`escape-handoff-green/`](escape-handoff-green/evidence.json) | Eight native checks passed | Mode-only Escape close; all three immediate reopens survived |
| [`../apple-overview/real/`](../apple-overview/real/evidence.json) | Eight real GUI checks passed | Corrected Apple bindings, real carousel/Fuzzel handoff and application F3/F4; before the focus barrier |
| Current keyboard-focus barrier | 34 unit tests passed; native gestures not reached | Three focused attempts stopped during compositor or daemon readiness |

Those latest startup attempts observed host load 49.05 on eight CPUs. Their
`focus-*-startup-failure/` artifacts retain the failures, and every private
process was stopped. They neither verify nor reject the new gesture behavior;
native focus/release verification remains pending. The full 18-check native
suite has not passed on that final focus-barrier source. The earlier native
animation median of 19.115 ms does not establish 60fps or physical display
presentation rate. [`native-README.md`](native-README.md) preserves the detailed
source-by-source chronology and screenshot-barrier corrections.

Existing navigation evidence remains in `../carousel/` and
`../window-navigation/`. No preview images are stored by the production daemon.

## Live activation

[`activation.json`](activation.json) records the resumed activation check. The
first ten-second readiness observation expired, but the new daemon, PID 21698,
subsequently became ready. Verification resumed with that same process. The
checked theme reload completed in 8.160 seconds, removed no existing window
IDs, and retained workspaces 1, 2, 3, 4 and 10. The Apple configuration link was
installed and the `window-switcher` mode was present.

The selected Bellows Intercept theme matched its painting, the original ghost
palette was present, and all 24 actual theme configuration links matched that
profile. `waybar-state.css` is intentionally generated by the fullscreen dimmer
and is recorded as the runtime exception. The activation's source hashes match
the current focus-barrier candidate; final modifier-gesture validation remains
pending as described above.

## Recovery

`oldbook-carousel cancel` closes an overview. Restart its single-owner daemon
to load changed Python code. The former preview command used `-s 0.35` and the
renderer used unqualified texture sampling; restore those two changes to roll
back image quality. Keep the mode-only close bindings when rolling back visual
changes so a delayed cancel cannot target the next popup. No package change or
compositor replacement is required.
