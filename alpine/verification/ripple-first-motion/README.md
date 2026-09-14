# First departure ripple: reproduced and fixed

The user saw no ripple after the original departure change. That version's
native test allowed its first departure to produce zero frames. The stricter
test now requires the first departure and first return to render too.

Two failures were reproduced on 2026-09-13:

- A fresh process capturing the live 1440×300 logical band took 63.6ms for grim
  and 157.0ms for crop's lazy NumPy import. Subsequent crops took 3.6–4.2ms.
  Those live photographs were immediately deleted and are not archived.
- After warming NumPy, the isolated right-edge capture completed in about
  19ms, but GTK did not deliver the callback for another 409ms. No caption
  animation frame occurred during that interval. Raising idle priority did
  not solve it and was reverted: the clock had started before layout allowed
  the caption's first moving frame.

The fix warms cropping with one synthetic pixel and dates departure from the
first moving frame. The old dock is still photographed before the flight.
Repeated frame callbacks cannot reset the deadline. The existing 100ms late
capture cutoff and landing-contact timing remain intact.

## Verification

- [Failing regression](regression-before.log): two timing regressions fail.
- [Passing regression](regression-after.log): all 63 ripple tests pass.
- [Mapped checks](feature-checks.log): 304 tests, one existing skip, no failures.
- [Original first-capture failure](first-capture-failure.json).
- [Layout-delay trace](layout-delay-events.jsonl).
- [Successful native run](native/summary.json): first and subsequent departure
  and landing each render on both bottom and right edges; deliberately delayed
  300ms captures produce no wave. All GL draws report zero errors.

First-departure capture admission was 0.04ms after the moving-frame event on
both edges. The first actual GL draw followed at 227ms (bottom) and 98ms
(right) using software GLES. This is not a physical-display latency guarantee.

Synthetic screenshots: [first bottom departure](native/bottom-cold-departure.png),
[first right departure](native/right-cold-departure.png).

The [deployment record](deployment.json) records the new live daemon and source
hashes, unchanged settings, and removal of temporary instrumentation. The
native run preceded one comment-only clarification in the caption helper;
the executable change is identical. Existing unrelated caption font edits
remain outside this fix's scoped check-in. No user-triggered live transition
occurred in the observation window, so isolated screenshots are the visual
evidence rather than a claim that the user has confirmed the live result.

The native verifier waits for an observed startup warm-up event instead of a
fixed sleep and logs both cropping and callback delivery. GTK's
[idle callback documentation](https://docs.gtk.org/glib/func.idle_add.html)
describes why queuing work does not itself guarantee an immediate callback.
