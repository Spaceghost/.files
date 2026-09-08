# Carousel still-preview quality

These runs use private SwayFX, D-Bus, HOME/XDG directories, virtual keyboard
and synthetic Foot windows. They do not capture or change the host desktop.
The original carousel evidence remains unchanged in `../carousel/`.

The fixture output is 2880×1800 at scale 2 (1440×900 logical). Direct
`grim -T` capture supplies 720×900 pixels for half-width windows and
1440×900 for full-width windows in this compositor. Omitting `-s` and
using `-s 1` agree. The preview keeps every supplied pixel; output scale
does not make this provider expose double-resolution client buffers.
Those sources exceed the centered card's physical letterboxed image sizes
of 624×780 and 1248×780, respectively.

`native-before-card-cache/` passed all 18 checks, including the existing
keyboard/MRU/lifecycle suite. The real fixture changes from green to magenta
while its preview remains green. The next gesture captures the magenta image.
The matching `still-preview-held.png` and `still-preview-next-gesture.png`
screenshots were reviewed visually. All private processes stopped.
Its active animation frame interval median was 19.115 ms; this is measured
headless behavior, not a guarantee of a particular physical display rate.

Earlier attempts are preserved rather than overwritten:

- `provider-assumption-failure/` rejected the incorrect assumption that
  toplevel capture dimensions equal logical window dimensions times output
  scale. The direct provider comparison replaces that assumption.
- `shutdown-message-failure/` passed all 17 checks preceding shutdown,
  then rejected an alternate expected GDK disconnect message at process
  exit 1. The final verifier accepts either known disconnect message only
  after the actual daemon exits, and still requires zero private survivors.
  This run's animation median was 32.869 ms.
- `cache-paint-failure/` captured the initial card while status already
  selected Strata. Its later `failure.png` shows the correct centered Strata
  image. The verifier now waits, for at most 12 seconds, until at least 98%
  of the central card region matches the expected fixture color. A matching
  neighbor cannot satisfy this check. Vectorized exact color counting avoids
  scanning millions of pixels with Python loops; all four preserved image
  counts matched the earlier results exactly. The central region check also
  rejects the stale image and accepts the later correct image.
- `cache-key-sequence-failure/` passed all seven quality/persistent checks,
  then the observer missed the second held-Tab selection. The 120-second
  persistent keyboard remained alive throughout this 36.6-second run, and
  one wtype device owned the full modifier/key/release sequence. The fixture
  performed a blocking workspace IPC request, with a four-second timeout,
  before observing a selection whose scheduled duration is only 1.2 seconds.
  Its retained data cannot distinguish a missed transition from a lost key.
  The verifier now continuously samples selection transitions every 5 ms and
  uses its existing nonblocking focus subscription between selections. The
  real key delays and required C→A→C order are unchanged.
- `escape-reopen-failure/` reopened a persistent gesture after Escape had
  closed the previous one, but the new gesture closed after two frames.
  The retained bindings issue asynchronous `exec ... cancel` together with
  synchronous `mode default`. The controller already dismisses when that
  mode change arrives, allowing the delayed cancel command to target the
  next gesture. The native result is consistent with this ordering race;
  it has no action trace proving the exact arrival sequence.

`escape-handoff-red/` then reproduces that race deterministically with real
Escape and a 0.75-second startup delay applied only to the private binding
launcher's cancel command. The second reopened gesture is cancelled by the
previous Escape. `escape-handoff-green/` passes all eight checks on the fixed
bindings: Escape returns to default mode, and the controller's mode event
closes the current popup without spawning a cancel process. All three
immediate reopen cycles survive. The same fix applies to Apple overview keys;
Launchpad returns to default mode before launching the menu. Both runs retain
their original bindings and source hashes, and both cleaned up every private
process. The two focused unit tests also went red to green, including actual
mode-event dispatch through the controller.

Every run records source hashes and retains its original logs and results.

`premature-modifier-commit-failure/` records a distinct remaining issue after
the Escape fix. Continuous sampling shows a held Super gesture opening at
103 ms and committing at 504 ms, before the real release around 4.2 seconds.
The next Tab starts a new gesture with the committed window first in MRU.
This establishes an actual premature commit rather than an observer missing
the second selection. The run had already passed all seven quality checks.

The focus fix replaces the map-time 50 ms modifier guess with actual keyboard
entry (`GtkWindow.is_active`), one Wayland synchronization, and a final idle
after queued GDK focus events. Active state, focus epoch, popup identity and
lifetime are checked before interpreting an empty modifier mask. The normal
key-release path remains unchanged. All 34 carousel unit tests pass, including
delayed focus, an already-released quick tap, focus loss after synchronization,
and cancellation on close. `focus-barrier-evidence.json` records exact hashes.

Native focus verification has not yet reached a gesture. Three focused runs
stopped in daemon startup, duplicate-daemon startup, and compositor readiness,
respectively; their `focus-*-startup-failure/` directories preserve each result.
At that point observed host load was 49.05 on eight CPUs with compilation and
other applications running. All private processes stopped. These startup
failures neither prove nor disprove the new focus behavior; physical display
frame rate remains unverified.
