# Restore the original ghost badge

The command-deck badge again uses its original 21px white ghost, purple gradient,
lilac glow and pink-violet hover colors from Fossil revision `3c38d567bc`.
It retains the centered 36px minimum width and zero padding introduced later.
Corner shapes, margins, outlines, surrounding controls and each theme's design
are unchanged.

The glyph is still U+F02A0 in the ordinary Waybar `custom/ghost` module.
No image asset, native artwork helper or APK rebuild is involved. The base
stylesheet and 19 existing theme styles were reviewed; 19 files changed because
Space Ghost Violet already carried the requested styling. `style-changes.json`
records before/after hashes and verifies that everything outside the two ghost
selectors is byte-identical.

`alpine/wallpapers/desktop_theme.py` now preserves those exact authored selectors
while recoloring the rest of a generated Waybar stylesheet. Existing profiles
were updated explicitly because `ensure_profile()` preserves authored files.
The tests cover existing profiles, three distinct generated palettes, and
neighboring selectors that must continue to recolor normally.

Validation on September 7, 2026:

- Three focused tests first failed with 23 failed subcases, then passed.
- All three complete-theme rendering/deployment tests passed.
- Two real private Waybar renders passed with the exact base and active
  Waxen Meridian stylesheets. Both screenshots show the restored badge;
  the fixtures contain only synthetic text.
- No private processes remain. No host refresh or input command was issued.

The 21px font has a natural bar height of 35px with the existing margins; Waybar
therefore raises the requested 32px fixture height to 35px. This is recorded in
`runtime.log` and each layer's extent in `evidence.json`. The first two fixture
attempts incorrectly assumed the layer namespace was `waybar`; the configured
name is `top`. Their cleanup/results remain in `fixture-history.json`.

Reproduce from the checkout:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_ghost_branding.py' -v
python3 -m unittest discover -s alpine/tests -p 'test_complete_themes.py' -v
python3 alpine/tests/verify_ghost_badge.py --output /tmp/ghost-badge-fresh
```

Use a fresh output directory and run separately from other compositor tests.
The private fixture checks that purple badge pixels have painted before taking
the screenshots, then verifies the source stylesheet hashes again.
