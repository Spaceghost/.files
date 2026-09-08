# Ghost Observatory in production

The Ghost Observatory concept (`alpine/themes/concepts/ghost-observatory/`)
rendered windows as exhibits: generous corners, deep soft shadows, floating bar
islands and captions in Inter beneath each window. Its visual language is now
the deployed Gruvbox Dark desktop.

## What changed

- SwayFX (`swayfx/effects.conf`, both copies): `corner_radius 22` with
  `smart_corner_radius disable` (gaps are always shown, so every window stays
  rounded), shadow blur 34 with offset 0 10 and the concept's shadow colours,
  blur noise 0.012 and brightness 0.94, inactive dim 0.02, 18-pixel radii for
  the bar and launcher layers.
- Sway (`sway/config`): gaps inner 6, outer 7. `theme.conf` (both copies)
  carries `font pango:Inter Medium 11`, left-aligned titles and 18/7 titlebar
  padding for the native-caption fallback used by stock Sway.
- Waybar (`style.css`, both copies): pill islands with an 18-pixel radius and
  a deeper shadow, 11-pixel module and workspace pills, a 12-pixel Ghost badge
  shape (its colours are untouched, `GHOST-BRAND`), 16-pixel tooltips. The
  shared desktop template now uses the same `.modules-left, .modules-right`
  island structure as the live profile, so generated themes inherit the look.
  `config.jsonc` (both copies) floats the bar with 6/10-pixel margins at
  34 pixels tall.
- Launcher (`fuzzel.ini`, both copies): 18-pixel radius.
- Theme descriptor (`gruvbox-dark.json`): design radius 22, spacing 6, and the
  renderer's design schema now allows radii up to 24 and rounds both generated
  bar islands.
- Captions (`oldbook-decoration`): the strip uses the active theme's design
  typeface when the descriptor declares one, one point above the terminal size
  (Inter 10.5pt for the saved JetBrains Mono 9.5pt), medium weight, left-aligned
  titles, letter-spaced state text, 28-pixel minimum height and roomier padding.
  A theme without a design font keeps the terminal font. Placement, opacity and
  radius preferences are untouched.

## Deliberately not adopted

- No `#window` module: music keeps the bar centre (`BAR-LAYOUT`).
- No native per-window titlebars: the oldbook-decoration strip keeps the saved
  bottom / 0.67 / radius 7 preferences and its placement contract
  (`DECORATION-STYLE`, `DECORATION-PLACEMENT`); the caption typography and
  spacing were applied to the strip instead.
- The amber Ghost badge from the concept stylesheet (`GHOST-BRAND`).
- The 20-pixel screen corner mask stays independent (`SCREEN-CORNERS`).

## Verification

`alpine/themes/preview` (new) renders the deployed profile, bar, caption daemon
and three Foot cards in a private headless SwayFX session over the pinned
Yosemite painting; `alpine/verification/ghost-observatory/` holds the tiled
and floating-caption screenshots with binary and artwork hashes. Decoration,
complete-theme, theme-switch, theme-picker, gallery-picker and feature-contract
tests pass; both Sway entry configurations validate. `test_ghost_branding`
and `test_new_themes` fail before and after this change because they expect
the archived `spaceghost` theme and `gallery/delaware.png` (archived on
2026-09-08 by an earlier session), not because of this work.

The live session was locked with its display powered off, so the reload was
applied without a physical look; the Waybar JSON (margins, height) still needs
a bar restart on the live session, and the physical frame rate with the larger
shadow radius is unobserved.

## Recovery

Every value is a plain configuration edit; `fossil diff` on the listed files
shows the previous compact geometry (6-pixel corners, 3/4 gaps, 13-pixel bar
islands). The caption daemon falls back to the terminal font automatically if
the theme descriptor loses its design font.
