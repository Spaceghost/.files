# Decoration frame timing — 2026-09-07

These measurements use a private D-Bus session, temporary HOME and XDG
directories, and a headless SwayFX compositor. A private virtual pointer holds
and moves a synthetic floating Foot window for five seconds. Analysis excludes
the first half-second. No host windows or configuration are changed by the
verifier.

The observer wraps only tick callbacks installed by the daemon. It records the
GTK frame clock, draw and after-paint signals, rounded caption geometry, resize
calls, and GDK frame timings. It creates no additional animation source and
does not request redraws. The final run also measures draw and caption-update
duration. Exactly one caption must supply the analyzed frame stream.

| Source | Output refresh | GTK tick rate | Tick interval p95 | Draw rate | Resizes during movement |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 60 Hz | 33.004 Hz | 51.239 ms | 33.032 Hz | 148 |
| Optimized | 60 Hz | 52.971 Hz | 31.280 ms | 52.516 Hz | 0 |
| Minimal control | 60 Hz | 59.854 Hz | 17.004 ms | 59.865 Hz | 0 |
| Baseline | 120 Hz | 42.457 Hz | 42.641 ms | 41.556 Hz | 190 |
| Optimized | 120 Hz | 63.467 Hz | 25.333 ms | 62.842 Hz | 0 |
| Minimal control | 120 Hz | 110.251 Hz | 14.741 ms | 110.245 Hz | 0 |

The final production run exceeds 60 ticks and draws per second on the 120 Hz
virtual output. At that rate, median/p95 GTK draw duration is 4.629/9.051 ms;
caption-update duration is 0.190/0.268 ms. Movement no longer calls GTK resize
on every animation frame. The minimal control has one label, a constant size,
and two margin updates per tick; its complete source is included.

These are observations under the recorded host load, not guarantees that every
frame meets its deadline or measurements of physical display scanout. The
native renderer log identifies SceneFX EGL using `radeonsi, verde, ACO, DRM 2.51`.
Although the fixture retains `WLR_RENDERER=pixman` for consistent comparison,
SwayFX creates its SceneFX renderer directly and ignores that selector. The
older baseline/control description of a software renderer was inaccurate; no
renderer override was actually applied. The corrected JSON preserves that
original description under `packaging_notes.original_limitations`.

The [wlroots 0.20.2 headless backend](https://gitlab.freedesktop.org/wlroots/wlroots/-/blob/0.20.2/backend/headless/output.c)
rearms an integer-millisecond timer after committing. Rendering/commit work
adds to its 16 ms or 8 ms delay, so nominal output refresh is not a fixed
hardware vblank schedule. GDK presentation values are
[estimates derived from Wayland frame callbacks](https://github.com/GNOME/gtk/blob/3.24.52/gdk/wayland/gdkwindow-wayland.c),
not `wp_presentation` feedback.

The three JSON summaries preserve source SHA-256 hashes, output configuration,
host load, interval histograms, and missed-refresh-slot estimates. The compressed
JSON files retain all raw observations. Final renderer logs contain only the
synthetic test session. All seven optimized production hashes matched the
checkout when this evidence was packaged. The verifier subsequently clarified
the headless timer limitation and tightened pointer reply timeouts, including
partial lines; its timing observer did not change. The recorded verifier hash
identifies the version used during each run.

Reproduce with:

```sh
python3 alpine/tests/verify_decoration_framerate.py \
    --output /tmp/decoration-framerate-new-run --rates 60 120 --seconds 5
```

`--motion ipc` selects a separate semantic-event stress case; the measurements
above use the default held-pointer path, which emits no move events while held.

The final attachment verifier passed all 25 unchanged checks on these production
sources. A held drag produced 14 samples with intermediate caption positions
and settled in 109.6 ms. `attachment.json` records geometry, fullscreen and
control checks; three representative screenshots are retained here. The full
synthetic screenshot set is under
`/tmp/decoration-60fps-attachment-final-20260907/`.

The old sampler launched three `swaymsg` processes for each snapshot and missed
intermediate frames: it saw only the initial position at 62.4 ms and the settled
position at 149.5 ms. `attachment-sampling-before.json` preserves that failure.
The verifier now batches reads over a persistent socket, samples drag motion
every 4 ms, bounds pointer replies and cleans its process groups. No assertion
was removed or weakened.

`unit-tests.json` records 41 passing decoration unit tests and the polling
regression's failure before the fix. `conky-cleanup.json` records isolated
cleanup checks after nine orphan test clients were removed from the host.
The concurrent Conky check-in includes the cleanup correction.

`activation.json` confirms the updated live helper, one caption on the nominal
60 Hz panel, and preserved bottom placement, opacity 0.67 and corner radius 7.
