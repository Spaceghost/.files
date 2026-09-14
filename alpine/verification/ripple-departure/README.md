# Caption departure ripple

The native probe ran on 2026-09-13 in a private 1200×800 SwayFX headless
session with OpenGL ES 3.2 Mesa 26.1.6, using llvmpipe. Its HOME, XDG paths,
Wayland connection, terminal content and settings were temporary. No live
desktop was photographed or reconfigured. Source snapshots were deleted with
the temporary session; [summary.json](native/summary.json) records source
hashes and confirms the installed helper resolves to the checkout source.

Run again with a new output directory:

```sh
python3 alpine/tests/verify_ripple_departure.py --output /tmp/ripple-departure-check
```

The command exited 0. The observer wraps the real daemon's Ripple methods,
records GTK mapping and caption motion callbacks, and checks actual GLES draw
results. It preserves the real grim source photographs as lossless PNGs.
Only the rejection cases alter capture timing, adding 300ms after the real
shutter returns. Source, shader, power policy and motion timing are unchanged.

The focused regression command ran 61 tests: [before the fix](regression-before.log)
four departure checks failed, and [after the fix](regression-after.log) all
passed. The broader [feature checks](feature-checks.log) passed 302 tests in
18 suites with one duplicate GTK child probe skipped. Existing SQLite
ResourceWarnings were unrelated to the changed departure path.

| Edge / event | Ripple surfaces | GL draw callbacks | Capture admission age | First GL draw age |
| --- | ---: | ---: | ---: | ---: |
| Bottom departure | 1 | 31 | 91.0ms | 187.4ms |
| Bottom landing | 1 | 48 | 34.0ms | 82.9ms |
| Right departure | 1 | 31 | 83.8ms | 193.5ms |
| Right landing | 1 | 46 | 55.4ms | 117.5ms |
| Bottom departure, delayed capture | 0 | 0 | Rejected | — |
| Right departure, delayed capture | 0 | 0 | Rejected | — |

Every observed GL draw returned success with `glGetError() == 0`. Each
departure plan used the exact previously docked caption rectangle, each
transition retained one caption after settling, and every ripple disappeared
after its duration. Bottom and right departure photographs still show the
caption docked; the visible waves contain no displaced caption ghost in this
run. Motion callbacks had begun before grim returned, so callback timing alone
does not locate the shutter: the preserved source pixels are the evidence.

- Bottom: [departure](native/bottom-departure.png),
  [source photograph](native/bottom-departure-shutter-0.png),
  [landing](native/bottom-landing.png).
- Right: [departure](native/right-departure.png),
  [source photograph](native/right-departure-shutter-0.png),
  [landing](native/right-landing.png).
- Raw observations: [bottom](native/bottom-events.jsonl),
  [right](native/right-events.jsonl), [runtime log](native/runtime.log).

The existing 100ms cutoff admits captures before constructing the GTK ripple;
it does not bound GL preparation or the first rendered frame. Software
rendering added the latency shown above. The first departure in each fresh
daemon was dropped before any ripple mapped, during the cold crop/import
path; both outcomes and the following warm-up landing are retained in the
summary. The measured transitions then reused that naturally warmed daemon.
This proves real rendering and capture rejection in isolation, not physical
scanout latency, 60fps on the live desktop, or ghost avoidance under every
possible screencopy delay.

The existing installation symlink points at this source. The separate
[live reload record](live-reload.json) shows only the decoration daemon was
restarted, remained alive after eight seconds, and kept the settings hash
unchanged without new logged errors. No live transition was forced and no live
screenshot was retained. A read-only live grim attempt timed out while the output was powered
off; no wake, focus change or binding-mode change was sent. That check makes
no claim about physical display timing or ghosts.

The follow-up [native restart probe](native-restart/summary.json) reproduces
the sleeping output's initial 200×200 caption allocation. With the private
HEADLESS-1 output powered off, restarting the real daemon placed that initial
allocation at the correct attachment coordinates. Powering only HEADLESS-1 on
completed the expected 540×56 allocation in 35.7ms, exactly matching the
synthetic floating window's width and bottom seam. No production code change,
live display operation or screenshot was needed for this probe:

```sh
python3 alpine/tests/verify_ripple_departure.py --restart-power-off --output /tmp/ripple-restart-check
```

For the scoped Fossil check-in, the ripple changes were applied to a clean
checkout separately from the existing caption font edits in the shared tree.
All 61 ripple tests also passed there; see
[clean check-in regression log](clean-checkin-regression.log). Native/live
source hashes above identify the shared tree actually observed, including
those existing font edits; the ripple check-in does not absorb those edits.
