# On-screen feedback pill and screenshot flash

Recorded by `python3 alpine/tests/verify_osd.py --output <dir>` on 2026-09-08
in a private headless SwayFX 0.6 session (pixman renderer, 1440×900, the
pinned Yosemite painting as background, the repository `effects.conf` and
`local.d/screenshot.conf` included). `report.json` holds the surface records,
workspace rectangles, luma samples, Satty window record and the check results;
`sway.conf` is the private compositor configuration that was used.

- `pill-shown.png`: the 300×66 pill 0.2 s after `oldbook-osd show --kind volume
  --value 42`, cropped to the extent SwayFX reported on the overlay layer.
- `pill-fading.png`: the same region 1.22 s after the show, mid-fade.
- `pill-second-reading.png`: a microphone-off reading sent during a fade,
  which snapped the same surface back to full opacity.
- `flash.png`: the output while the cream wash was mapped after
  `oldbook-osd flash` (scaled to 480 px wide).
- `satty.png`: Satty opened floating on the private session with the
  repository profile (scaled to 480 px wide; the title bar is the private
  session's default border, which the production configuration disables).

Limits: pixman does not render the SwayFX blur and shadow, and a headless
frame is not physical scanout timing. The live daemon was started from a Sway
reload and mapped the pill on eDP-1 with the effects reported, but the laptop
display was powered off and locked at the time, so the physical look on the
internal panel is pending a display wake.
