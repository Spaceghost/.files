# Ghost Observatory production render

Rendered on 2026-09-08 by `alpine/themes/preview` in a private headless SwayFX
session (`WLR_BACKENDS=headless`, GLES2 on `/dev/dri/renderD128`) with the
deployed Gruvbox Dark profile, the production Waybar configuration and
stylesheet, the oldbook-decoration caption daemon, and three Foot cards showing
synthetic copy over the pinned Yosemite painting. `evidence.json` records the
compositor and artwork hashes and the gaps read from the shared Sway config.

- `production.png`: two tiled cards and one floating card with a tiled window
  focused; the caption strip sits at the workspace bottom in Inter Medium.
- `production-floating.png`: the floating card focused; the caption attaches
  beneath it with the saved rounding.

This is a headless render of the real compositor, not a physical-screen or
frame-rate test. The live session was locked with its display powered off when
the configuration was reloaded, so the physical look remains to be confirmed.
