# Painting thumbnails: gallery picker rows and the bar badge — 2026-09-08

## What

- **Gallery picker rows** (`oldbook-wallpaper pick`, and the multi-delete list)
  show a rounded thumbnail of each painting beside its title. Pages with
  thumbnails use 40-pixel rows so a picture reads as a picture; text-only
  menus keep the shared 28-pixel geometry.
- **Bar badge** (`cffi/art`, package `oldbook-waybar-art` 1.0.0-r10) shows the
  painting on screen as a 22-pixel-high rounded thumbnail instead of the
  gallery glyph. Paused rotation dims it; while a painting is being generated
  the amber hourglass glyph replaces it; without a thumbnail the original glyph
  returns. Every click, scroll and modifier action, the tooltip and the CSS
  state classes are unchanged (GALLERY-ACTIONS, GHOST-BRAND untouched).
- **Shared cache** `alpine/desktop/.local/lib/oldbook/thumbnails.py`: GdkPixbuf
  scaling plus a cairo rounded-corner clip, written atomically with private
  permissions under `~/.cache/oldbook/thumbnails/`, keyed by the painting's
  SHA-256 (from the sidecar when known), height, radius and shape. Nothing is
  written inside the checkout. `oldbook-wallpaper status --thumbnail-height N`
  reports the cached path in its JSON for the panel's scale factor.

## Why an icon theme

Fuzzel 1.14's dmenu icon protocol (`text\0icon\x1f<name>`) resolves names
through the icon theme; an absolute PNG path renders nothing in dmenu mode
(verified headlessly; the same path works in a desktop entry). The cache is
therefore exposed as the single `thumbnails` directory of a private
`Oldbook-Thumbnails` theme under `~/.local/share/icons/`, whose `index.theme`
inherits the desktop icon theme from GTK settings plus Papirus and hicolor.
The picker passes `--icon-theme Oldbook-Thumbnails` only for pages that carry
thumbnails, so ordinary icon names keep resolving and text-only menus are
unaffected. The theme directory and cache are disposable and recreated on
demand.

## Verification

- `python3 -m unittest discover -s alpine/tests -p 'test_thumbnails.py'` (9)
  and `-p 'test_gallery_picker.py'` (6): cache naming, atomic private files,
  rounded alpha corners, square crop, reuse without re-render, unreadable
  inputs, warm-up, icon theme creation/idempotence, picker rows carrying icons
  with plain-text selection, and the status thumbnail field.
- Headless SwayFX (2880×1800 at scale 2) renders of the picker with real
  gallery paintings and of the badge in rotating, paused, generating and
  no-thumbnail states: `alpine/verification/gallery-thumbnails/`.
- Two network-isolated builds produced byte-identical signed r10 APKs
  (`packages/waybar-art/verification.json`); `apk verify` passed; the APK is
  archived as a Fossil unversioned artifact and installed; the live Waybar was
  restarted with the new module mapped.
- Not verified: the live bar and picker on the physical panel (the display was
  powered off and the session locked during this work). Pre-existing:
  `test_manual_artwork.py` fails to import because its fixture
  `alpine/assets/gallery/delaware.png` moved to `alpine/archive/` in the theme
  archival commit; unrelated to this change.

## Rollback

Reinstall the archived r9 APK (`fossil uv export sha256/46659510…/oldbook-waybar-art-1.0.0-r9.apk`,
then `doas apk add --no-network`) and restart Waybar; restore the previous
`oldbook-wallpaper` and stylesheet revisions with `fossil revert -r <parent>`
on those paths. Removing `~/.cache/oldbook/thumbnails/` and
`~/.local/share/icons/Oldbook-Thumbnails/` discards every generated file.
