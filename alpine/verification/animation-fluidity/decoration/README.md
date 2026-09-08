# Decoration animation contention

The attachment watcher used its full 120 Hz GET_TREE budget whenever any
caption belonged to a floating window, including stationary windows and the
time spent behind the carousel. It now polls quiet attached geometry on a
60 Hz budget, resumes 120 Hz after geometry changes, and retains that budget
for a 250 ms settling tail. Title changes do not extend that tail. Sway emits
no continuous drag geometry events, so quiet attached polling remains bounded
to one nominal 60 Hz frame instead of using the 750 ms workspace fallback.

The watcher subscribes to binding-mode events and suspends geometry requests
while `window-switcher` owns input. Mode exit refreshes the latest tree
immediately, including changes received while suspended. IPC framing,
unchanged-tree suppression, one request in flight, reconnect and shutdown
handling remain in place.

The GTK handoff previously used ordinary idle priority 200, which runs after
GTK layout/redraw work. It now uses high idle priority 100 so the coalesced
geometry reaches GTK before the next redraw. `geometry-priority-red.log`
records a real GLib main-loop regression: an always-ready redraw source at
priority 120 prevented geometry delivery until the watchdog stopped the test.
The same test applies geometry first with the fix.

`red.log` records the two initial failing watcher regressions. `green.log`
records 51 passing decoration tests, including the real GLib ordering test,
title-only changes, sustained motion, fragmented IPC, reconnect and cleanup.
Installed PyGObject emits deprecation warnings about Python asyncio policy;
the warnings are preserved in the log.

`polling.json` compares production watcher threads against private Unix IPC
fixtures for one second after their initial 350 ms settling period. Each run
uses default production intervals. Moving fixtures change a floating child's
rectangle on every response. The measured GET_TREE request rates were:

| Fixture | Before | After |
| --- | ---: | ---: |
| Stationary attached window | 108.99/s | 56.44/s |
| Continuously changing geometry | 107.99/s | 100.98/s |
| Carousel mode | 108.99/s | 0/s |

These are IPC request rates under concurrent host load, not measured physical
frames or a compositor CPU speedup. Source hashes identify both watcher
versions. The baseline was copied from the working source before modification.

The private native run in `native-attachment/` passed the added carousel
suspension and mode-exit recovery checks, with geometry settling 190.8 ms after
exit. It subsequently failed the existing 250 ms hover-handoff requirement:
the expected window was already focused, while the previous caption remained
until approximately 253 ms. This run preceded the GTK priority change and ran
under substantial concurrent host load. Its failure, screenshots and runtime
log are retained. The timing requirement has not been weakened.

The final caption also retains its GTK controls and CSS during a hover handoff,
hiding and unrealizing the old native surface before attaching a fresh surface
to the next window. Construction profiling measured about 47.5 ms of warm CPU
work for destruction/recreation, versus 7.8 ms for the retained controls.
The current source passes all 52 decoration unit tests. The real GTK fixture
runs in its own child process so toolkit threads do not contaminate later
watcher timing checks.

`native-handoff-reuse-after-local-ai-stop/evidence.json` records all 37 native
checks passing with no surviving private processes. Hover handoffs completed
in 87–98 ms against the unchanged 250 ms limit. This run followed the local
Ollama shutdown, so changed host load contributed to wall-time improvement;
it is not a controlled attribution of that whole improvement to the code.

Repeat the focused tests and native check from the repository root:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_decoration*.py' -v
python3 alpine/tests/verify_decoration_attachment.py --output /tmp/decoration-attachment-check
```

`live-activation.json` records the subsequent live decoration-only restart,
matching verified source hashes and the daemon's nice -5 startup priority.
Recovery restores
`oldbook-decoration` and `decoration_watch.py` from the parent revision and
restarts that daemon; saved appearance and placement do not need changes.
