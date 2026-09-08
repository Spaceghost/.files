# Decoration frame budget

The caption keeps GTK’s display frame clock for movement and fades. Attached
geometry sampling now has a 120 Hz budget, including IPC and decoding time;
responses no longer incur another full polling interval afterward. Slow replies
never queue catch-up requests. The persistent connection, unchanged-tree
suppression, coalesced GTK delivery and 750 ms workspace refresh remain.

Moving a caption of unchanged size now updates its margins without repeatedly
calling GTK’s resize and size-request methods. GTK queues layout even for a
repeated resize request. The change preserves resizing, bottom/right placement,
compact controls, the theme gradient, rounding and the existing spring motion.

A delayed-compositor regression failed before the timing change and passed
following it. All 41 decoration unit tests passed on the final production source.
The passive native timing verifier observes the production tick callback, draw
signals and GDK estimated presentation; it does not add animation callbacks or
substitute a timer. Source hashes tie the measurements to the tested files.

On the final private 120 Hz output, the production caption averaged 63.467
animation callbacks and 62.842 draw events per second during held-pointer
movement. The draw signal’s 95th percentile duration was 9.051 ms; the movement
callback’s was 0.775 ms. No redundant resize calls occurred during movement.
The virtual 60 Hz output measured 52.971 callbacks and 52.516 draws per second.
These measurements establish capacity above 60 frames per second, not a
physical-display scanout guarantee or a controlled speedup ratio under the
machine’s concurrent workload.

The host panel reports 59.990 Hz, its nominal 60 Hz mode. The private output
uses hardware SceneFX/EGL (radeonsi/verde), not Pixman. Its refresh scheduling is
also different: [wlroots’ headless backend](https://gitlab.freedesktop.org/wlroots/wlroots/-/raw/0.20.2/backend/headless/output.c)
rearms its timer after a commit, adding rendering work to a 16 ms or 8 ms
wait. Therefore a virtual “60 Hz” result is not a direct physical panel FPS
measurement. GDK presentation timestamps are estimates, not scanout feedback.

Nine abandoned Conky test clients were also consuming about four CPU cores.
Each had UID 1000, parent PID 1, a deleted private test configuration and a
missing private Wayland socket. They ignored TERM and were stopped with KILL
after checking their identity again. Healthy live desktop clients were
preserved. The Conky verifier now waits for its own detached clients, escalates
if necessary and cleans them before its private compositor disappears. That
cleanup fix was included in the concurrent Conky check-in 5953911f92; 43 Conky
unit tests and six isolated process cleanup cases passed. No additional native
Conky run was performed for this performance change.

The final native attachment run passed all 25 unchanged assertions. Batched
IPC sampling captured 14 held-drag observations and intermediate movement,
settling in 109.6 ms. The original subprocess-based sampler missed intermediate
frames; that failed evidence is retained alongside the corrected sampler.

Only the live decoration helper was restarted. PID 26971 owns one caption on
eDP-1; saved bottom placement, opacity 0.67 and radius 7 are unchanged. Runtime
activation evidence is retained with the tests.

Timing evidence and reproduction commands are in
[decoration-framerate](../../../alpine/verification/decoration-framerate/README.md).

Recovery: restore only the caption daemon and geometry watcher from this
change’s parent, then restart `oldbook-decoration daemon`. Saved appearance and
placement settings do not need restoration. No compositor or bar restart is
required. Physical mixed-refresh/multiple-output scanout remains unmeasured.
