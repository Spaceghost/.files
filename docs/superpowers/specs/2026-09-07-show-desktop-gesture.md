# Four-finger show desktop

Swiping four fingers away clears the focused workspace; swiping four fingers
back returns every window to the position it left. Three-finger swipes keep the
workspace and window picker, and four-finger left/right still change workspace.

    bindgesture swipe:4:up   exec ~/.local/bin/mbp-intel-showdesktop show
    bindgesture swipe:4:down exec ~/.local/bin/mbp-intel-showdesktop restore

## How the windows appear to leave

No window is ever moved. Sway cannot place a tiled container at an arbitrary
position, and floating everything to animate it would not survive a round trip
through nested splits, tabs and fullscreen. Instead the workspace is swapped for
an empty one named `desktop`, which is exact and instant, and the movement the
user sees is a replay drawn over the top of it.

`grim` captures the output as a binary PPM, which costs about 55 ms against
1.6 s for the same frame as PNG and stays lossless, so the handover back to the
real windows is pixel-identical. The capture becomes one GTK4 `MemoryTexture`,
and each visible window is drawn as a card: the texture clipped to that window's
rectangle, with the corner radius and shadow from `swayfx/effects.conf` so a
card at rest cannot be told apart from the window beneath it.

The chosen animation is *slide to edges, refined*: each card leaves straight out
of its nearest output edge over 340 ms, scaling to 0.88 and blurring to 4 px on
the way, staggered 30 ms apart top-left first. The stagger is capped at 120 ms in
total so a crowded workspace does not crawl. Returning is the same path reversed
over 300 ms. A card's shadow fades in with its movement rather than being drawn
at rest, where it would double the shadow the compositor is already drawing for
the real window.

The two directions do not share a curve. A symmetrical ease-in-out slows a card
down at the moment it should be whipping off the screen, so leaving uses an
accelerating `cubic-bezier(0.4, 0, 1, 1)` and arriving a decelerating
`cubic-bezier(0, 0, 0.2, 1)`. Blur follows speed rather than distance —
`travel²` — so a card is barely blurred while it is still full size, and most
blurred once it is small and half off the screen.

## Holding sixty frames a second

The first working version ran the slide at roughly ten frames a second. Three
things were wrong, all measured from the frame clock rather than guessed:

- Every card sampled the **whole 2880×1800 capture** and clipped it, once per
  card per frame. Each card now owns a texture cut from the capture once.
- The shadow was `push_shadow`, which blurs whatever the card drew and so
  recomputed a full-screen gaussian every frame. `append_outset_shadow` on the
  rounded rectangle is the dedicated fast path and looks identical here.
- Uploading a card to the GPU and compiling the blur and shadow shaders both
  happen on a card's first real draw. Coming back, the cards start off screen,
  so that landed on the first frame of movement and cost it 116–136 ms. The
  overlay now renders the real card nodes once offscreen when it is realised.

Measured after the change, over three show and three restore cycles: median
frame 16.7 ms, maximum frame 16.7 ms, **zero dropped frames** in either
direction, against a median of 33 ms and single frames of 83–117 ms before.

The long-lived helper also had to stop holding onto the captures. The tick
callback and the child widget both reference the closure that owns the textures,
so an overlay left attached kept a whole screen of pixels per gesture: the helper
grew 43 MB a swipe and reached 1.1 GB in eight, with the swap latency climbing
with it. Removing the tick callback, detaching the child and dropping the
textures holds it flat at about 170 MB. The display-wide stylesheet is installed
once rather than stacked on every gesture.

## Why the swap is never visible

The overlay is a layer-shell surface on the overlay layer with an empty input
region, so it never takes a click or a key. Ordering is what keeps the swap
hidden:

- **Showing** waits until the overlay has actually been painted and presented,
  then swaps to the empty workspace behind it while the cards still sit exactly
  on the windows, holds three frames, and only then starts the slide.
- **Restoring** maps the overlay with the cards already off screen, slides them
  home, and swaps the real workspace back on the frame where the cards have
  landed and cover every window, waiting four more frames before tearing the
  overlay down.

GTK reports no presentation feedback under SwayFX here, so the wait falls back
to a 150 ms deadline after the first paint. SwayFX 0.6 does not fade layer
surfaces — verified with a solid-colour test surface, which appears in a single
frame — so that deadline covers surface mapping only. Three measured show cycles
show no frame of bare desktop before the cards move.

## Why a background helper

Importing GTK and initialising it costs about a third of a second, which put the
first frame of movement roughly 800 ms after the swipe. `mbp-intel-showdesktop
daemon` keeps that cost at login: `mbp-intel-session` starts one per Sway socket,
it holds a per-session lock so a reload cannot stack copies, and it exits with
Sway through a shutdown subscription. Gestures reach it over a private datagram
socket; if none is listening the command still does the work itself. The
workspace swap now lands 244 ms after the swipe, with movement about 50 ms
later. A swipe arriving mid-animation is dropped rather than queued.

## Edge cases

Sticky windows follow the workspace swap and stay on screen by themselves, so
they are left out of the card list to avoid drawing them twice. A fullscreen
window hides everything behind it and contributes the only card; a tabbed or
stacked container contributes only its visible tab. Windows clipped by the
output edge are clipped in the capture too, and a window entirely off the output
is skipped. An empty workspace is left alone. If the workspace is changed by
hand while the desktop is bare — four-finger left/right still works — the next
gesture discards the stale capture instead of restoring into the wrong place.
The workspace is addressed by number where it has one, because the workspace
daemon renames workspaces live and a captured name goes stale.

## Implementation and validation

- `alpine/desktop/.local/lib/mbp_intel/showdesktop.py` with the thin
  `alpine/desktop/.local/bin/mbp-intel-showdesktop` entry point, reusing
  `workspace_model` for view selection and `mbp-intel-workspaces` for Sway IPC.
- gtk4-layer-shell has to precede libwayland-client to interpose. Rather than
  re-exec under `LD_PRELOAD`, the module loads it with `ctypes.RTLD_GLOBAL`
  before importing `gi`, which is the in-process equivalent.
- The capture is a picture of the user's screen. It lives only in the private
  0700 runtime directory at 0600 and is deleted when the windows come back.
- 31 unit tests cover PPM parsing, card selection including sticky, fullscreen,
  tabbed and off-output windows, the capture crop and its contiguous fast path,
  exit geometry for every edge, stagger order, and the easing curves including
  the exit/return asymmetry. Run:
  `python3 -m unittest discover -s alpine/tests -p 'test_showdesktop.py'`
- Verified live on eDP-1: capture format timings, absence of a SwayFX layer
  fade, swap latency, and three show/restore cycles sampled for a flash.
  Evidence in `alpine/verification/show-desktop/`.
- Unrelated and pre-existing: two `test_shortcut_service` failures from the
  in-progress superhold migration.

## Recovery

Remove the two `bindgesture swipe:4:up`/`swipe:4:down` lines from
`sway/gestures.conf` and reload to disable the gesture; the earlier four-finger
expo bindings are the previous behaviour. Stop the helper by terminating
`mbp-intel-showdesktop daemon` and remove its block from `mbp-intel-session`. If a
session is ever left on the bare desktop, any normal workspace shortcut returns
to the windows, which were never moved.
