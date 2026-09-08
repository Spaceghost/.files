# Background crossfade evidence

Recorded by `alpine/tests/verify_background_crossfade.py` in a private headless
SwayFX session (pixman renderer, 1280×720, no Xwayland) on 2026-09-08. Three
real Gruvbox gallery paintings took part: A is the login image swaybg shows,
B the shared painting, C the requested one. `evidence.json` lists every
capture with its stacking order (top first), its mean pixel distance from
reference fill renders of A, B and C, and for the fade frames the blend value
that best explains the capture. The PNGs are 480×270 copies of the captures.

| Frame | Shows |
| --- | --- |
| `01-card-before-daemon` | swaybg painting A with a Conky-style card created before the daemon |
| `02-daemon-shows-current` | the daemon after its startup fade: B, with the card restored on top |
| `03-fade-early` | the timed fade to C shortly after it started (blend ≈ 0.08) |
| `04-fade-part-way` | the same fade part-way through (blend ≈ 0.78) |
| `05-fade-settled` | C, exactly settled |
| `07-healed-above-swaybg` | C again after `output * bg A` respawned swaybg above the daemon and the daemon re-created its surface; card back on top |
| `09-fallback-after-quit` | swaybg's A showing through once the daemon quit |

All twelve checks in `evidence.json` passed. Captures under load took two to
seven seconds each, so the timed fade used the daemon's 20 s maximum; the
production fades are 0.8 s (manual) and 1.6 s (timer). This proves stacking,
blending and recovery in a private compositor; it does not measure physical
frame pacing on the laptop panel.
