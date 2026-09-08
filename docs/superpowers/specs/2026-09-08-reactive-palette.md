# The accent follows the painting — 2026-09-08

## What

The desktop keeps the active theme's colours, but its *accent* now follows the
painting on screen. When the gallery changes image, the new painting elects one
of the theme's own accent candidates and a companion colour, and the surfaces
that carry the accent retint without anything being restarted: the bar's focused
workspace, AI badge, clock and art-badge glow, and every overlay that reads the
shared palette (the feedback pill, launcher, Expo, lock screen, caption strip,
scripture bar, shortcut guide).

For Gruvbox Dark the candidates are the six decorative colours it declares:
yellow, orange, aqua, green, blue and purple. Red is deliberately excluded; the
desktop reserves it for urgency.

## Why this design

A colour lifted straight out of a painting almost never sits well against
charcoal chrome, and a theme is a designed set of colours rather than a swatch
pile, so the election never samples the canvas. It only ever chooses between
colours the theme already owns, and `read_palette` refuses any record naming a
colour the descriptor does not declare. That guard is what makes the feature
safe to leave on: the worst case is the accent the theme shipped with.

The analysis runs in OKLab, whose hue angles are perceptually even. Each pixel
counts by chroma times lightness, which discounts both the charcoal ground and
the near-black shadows that fill a chiaroscuro painting. Each histogram bin then
goes to whichever candidate sits nearest on the hue circle, and the largest
share wins.

The nearest-candidate partition replaced a first attempt that scored every
candidate with a von Mises kernel. The kernel quietly favoured whichever
candidate had the most neighbours: on this six-colour wheel yellow sits between
orange and green and collected weight from both, so it won paintings it had no
business winning, including an Antarctic station. A share is also a plain number
to read back later, being the fraction of the painting's colour nearest that
accent.

Two refusals keep it honest. A painting whose mean chroma is under 0.012 is
grey enough to have no opinion, and one where no candidate holds a third of the
colour is arguing with itself; both keep the declared accent.

## Where it lives

- `alpine/desktop/.local/lib/oldbook/painting_palette.py` — the analysis, with
  no GTK or numpy import at module scope so it costs nothing to import.
- `alpine/desktop/.local/bin/oldbook-palette` — `apply`, `show`, `clear`. It
  writes `~/.local/state/oldbook/palette-override.json` and
  `~/.config/waybar/waybar-accent.css`, skips a painting whose checksum it has
  already answered, and refuses to write through a symlink.
- `alpine/desktop/.local/lib/oldbook/overlay_theme.py` — `read_palette` applies
  the record when the descriptor allows it, and now always returns an
  `accent_secondary`.
- `alpine/themes/gruvbox-dark.json` — `"reactive_accent": true`. A theme opts
  out by setting it false; an absent key means enabled.

The record is honoured only for the theme that produced it, so switching themes
cannot leak the previous theme's accent, and a malformed or unreadable record
leaves the declared accent in place rather than blanking the palette.

## The bar's import order

Waybar's stylesheet hardcodes `#fabd2f` in the accent-bearing rules, so the
override sheet has to win by document order. GTK's CSS parser accepts an
`@import` anywhere at top level and keeps document order, which was confirmed
before relying on it: with the import at the end of the file the imported rule
comes last and wins; with it at the head the base rule wins. Both stylesheets
therefore import `waybar-accent.css` on their final line. `oldbook-session`
seeds the file before Waybar starts, exactly as it already does for
`waybar-state.css`, and Waybar's `reload_style_on_change` picks up rewrites.

## Verification

- `alpine/tests/test_reactive_palette.py`, 16 tests: synthetic warm, cool and
  neutral paintings elect the expected accents; every elected colour is one the
  theme declares; shares partition the histogram; a record from another theme,
  one naming an unowned colour, and a malformed one are all ignored; the
  descriptor opt-out works; the helper writes, skips repeated work and clears.
- `alpine/tests/verify_reactive_palette.py` renders the bar in a private
  headless SwayFX session and the pill through its display-free preview for two
  contrasting gallery paintings, and records the colour the badge *actually
  rendered*: `#ecb32e` under the firelit procession, `#7d9d90` under the
  Antarctic station. Evidence: `alpine/verification/reactive-palette/`.
- The whole gallery was swept during calibration: 23 paintings elect yellow,
  two orange and one blue. That distribution is honest rather than
  disappointing, because the theme's own image direction asks the generator for
  warm amber artwork; the Antarctic station is the collection's one genuinely
  cold picture and the accent follows it.
- The existing `test_overlay_theme` suite still passes unchanged.

### Not verified

The live panel was not photographed retinting. The helper ran on the live
session and wrote the real record and stylesheet while the desktop was
unlocked, but the session locked before the bar could be measured, and unlocking
it is not this agent's business. `test_ghost_branding` and
`test_application_theme_refresh` fail for both suites before and after this
change, because the theme-archive commit moved the `spaceghost` profile; the
Ghost badge itself was checked directly against both stylesheets and is intact.

Conky cards are unaffected: they read the theme descriptor rather than the
shared palette, and their per-painting contrast pass already adapts them.

## Rollback

`oldbook-palette clear` returns the desktop to the declared accent immediately.
Setting `"reactive_accent": false` in the theme descriptor disables the election
for every overlay. Removing the final `@import` line from both Waybar
stylesheets returns the bar to its hardcoded amber.
