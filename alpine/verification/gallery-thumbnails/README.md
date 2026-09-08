# Gallery thumbnails — headless evidence, 2026-09-08

Both images were rendered in a private headless SwayFX 0.6 session
(`WLR_BACKENDS=headless`, one 2880×1800 output at scale 2, the same geometry as
the MacBookPro11,5 panel) and cropped so no application window appears.

- `picker.png` — `oldbook-fuzzel --dmenu --no-sort --icon-theme Oldbook-Thumbnails
  --line-height 40` fed the picker's first page with four real gallery paintings
  from `alpine/assets/gallery/themes/gruvbox-dark/`; thumbnails came from the
  shared cache through the private icon theme. Halved to logical size.
- `badge.png` — Waybar 0.15 with the r10 `oldbook-art.so` instantiated four
  times: the real `oldbook-wallpaper status --thumbnail-height 44` (moon-landing
  painting on screen), a paused stub with the same thumbnail (dimmed), a
  generating stub (amber hourglass glyph) and a stub without a thumbnail
  (gallery glyph). The stylesheet is the live profile copy.

Fuzzel's dmenu mode ignored absolute PNG paths in the `\0icon\x1f` field while
rendering the same file through a desktop entry, which is why the cache is
published as an icon theme. The live panel was powered off and the session
locked during this work, so the physical bar and picker remain a pending visual
check; the harness lives in the session's temporary directory and is not
versioned.
