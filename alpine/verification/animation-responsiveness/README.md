# Desktop animation responsiveness

The user requested immediate, smooth, high-priority animation, especially the
four-finger down gesture that opens the carousel. This directory retains
before/after timing, native checks and failures instead of treating a passing
unit test as a physical frame-rate measurement.

## Input and scheduling

Warm CLI commands use a small stdlib-only Unix datagram client. The show-desktop
daemon sends an opening command straight to the existing carousel daemon. A
missing owner still follows the normal recovery path. A controlled private
socket benchmark measured median command completion of 660.9 ms for the prior
CLI, 228.6 ms for the small CLI and 0.368 ms for the direct warm handoff. These
numbers include the loaded host's scheduling and are not gesture-to-pixel times.

The root-owned one-shot helper prioritizes ordinary compositor threads at nice
-10 and selected UI threads at -5. It validates the compositor socket and owned
process identities, leaves deliberate batch/realtime workers alone, and arms
reset-on-fork before a boost. A private real-process check confirms child and
exec'd applications start at nice 0. No new doas authorization was added.
See [scheduling evidence](ui-priority/README.md).

## Motion and caption work

Carousel motion starts elapsed time at the request, uses the full elapsed
frame time, preserves velocity, and settles exactly. The deterministic 60 Hz
probe advances reveal by 26.4% on its first frame; navigation settles at 267 ms,
versus 517 ms before. This demonstrates the timing model only.

Caption geometry is delivered before GTK redraw. The watcher halves stationary
polling and suspends it while the carousel owns input. Hover handoffs retain
GTK controls and recreate just the native surface. All 52 decoration tests and
37 private native checks pass; live caption activation records the verified
hashes. See [caption evidence](../animation-fluidity/decoration/README.md).

## Local inference

The user explicitly stopped local Ollama and chose the Alienware's GPUs. The
MacBook server and worker were stopped; an installed policy prevents the normal
launcher from restarting them. No Alienware endpoint was guessed or contacted.
See [runtime policy](ai-runtime-policy/README.md).

## Verification boundary and recovery

Earlier live timestamp probes collected no window imagery or private titles;
they recorded substantial rendering stalls while local inference was active.
Do not interpret faster analytic springs, command handoffs or headless callbacks
as evidence of sustained physical 60fps. Final rendering/lifecycle results and
any remaining gap must accompany activation.

Deployment uses exact managed HOME links with per-file recovery journals.
Restore the affected source revision and restart only the carousel, show-desktop
and caption daemons to undo their behavior changes. The priority helper's README
covers restoring prior scheduling without changing unrelated jobs. Saved theme,
caption placement, readings and personal databases are outside this change.
