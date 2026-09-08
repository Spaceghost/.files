# Animated Gruvbox cursors — 2026-09-08

## What

`Oldbook-Ghost` is a cursor theme that redraws only the two waiting shapes:
`watch` (and its `wait` and `clock` aliases) and `left_ptr_watch` (and its
`progress` and `half-busy` aliases). Both show an amber ring that turns once
every 672 milliseconds and breathes as it goes, over a dim charcoal track with a
dark halo so the amber still reads over a bright painting. The busy pointer keeps
the arrow, drawn in the same hairline cream-on-charcoal language as the Simp1e
set, with the ring tucked at its lower right.

Everything the theme does not draw comes from `simp1e-cursors-gruvbox-dark`
through `Inherits`, so the ordinary pointer, the text bar and the resize arrows
are exactly what the user already had.

- Generator: `alpine/bin/build-cursor-theme`
- Theme: `alpine/desktop/.local/share/icons/Oldbook-Ghost/`
- Tests: `alpine/tests/test_cursor_theme.py`
- Session check: `alpine/tests/verify_cursor_theme.py`
- Evidence: `alpine/verification/animated-cursors/`

## Why this shape

Simp1e's own spinner is a clock hand inside a circle; it is tidy but says nothing
about this desktop. An amber comet on a Gruvbox track matches the bar, the
caption strip, the feedback pill and the lock ring, and the breath ties it to the
keyboard light, which already breathes. Redrawing only the waiting shapes keeps
the change small and keeps the pointer the user is used to.

## Decisions worth recording

**The encoder is ours.** `xcursorgen` is not installed and the format is a magic
word, a table of contents and one image chunk per frame per nominal size, so
`build-cursor-theme` writes it directly and `decode()` reads it back for the
tests. Pixels are premultiplied ARGB32, which is exactly what a cairo ARGB32
surface already holds, so no conversion is involved.

**Four sizes, not two.** Simp1e ships 24, 32, 48 and 72, and the desktop asks for
48 on the internal panel because the configured size is 24 at scale 2. Matching
all four means every scale resolves to a drawn image instead of a resampled one.

**Aliases are copies, not symlinks.** `alpine/bin/deploy-home` enumerates regular
files and skips symlinks, so a symlinked alias would never reach `HOME`. Each of
the eleven names is written out in full. The bytes are identical, Fossil stores
one blob for all of them, and the working tree pays about nine megabytes.

**The busy pointer keeps Simp1e's hotspots.** The arrow tip lands on (2,2),
(3,3), (5,5) and (7,7) for the four sizes, the same pixels the inherited
`left_ptr` uses, so the pointer does not appear to jump when the shape changes.

## Verification

Eighteen unit tests cover the encoder round trip, a refused short pixel buffer, a
refused truncated file, foreign magic, the drawn geometry, hotspots, per-size
frame counts and delays, that consecutive frames actually differ, that no frame
is fully transparent, that every alias is byte-identical to its shape, that
nothing in the theme is a symlink, and that the checked-in theme carries all four
sizes and all twenty-four frames.

`verify_cursor_theme.py` starts a private headless SwayFX session with
`XCURSOR_THEME=Oldbook-Ghost`, `XCURSOR_SIZE=48` and `XCURSOR_PATH` pointed at
the checked-in tree; the session reached its socket, reported its seat and logged
no cursor complaint. The live session was reloaded and `oldbook-gtk-settings`
pushed the GTK cursor name.

Unverified: nobody has watched the cursor spin on the physical panel. A headless
session renders no pointer, so the animation is shown by the frame contact sheet
instead. The compositor's default search path was read out of the wlroots binary
rather than tested from a cold login: it builds `$XDG_DATA_HOME/icons` first,
which is where deployment puts the theme.

## Rollback

Set the six configuration lines back to `simp1e-cursors-gruvbox-dark`
(`sway/theme.conf` and both GTK `settings.ini` files, in the `alpine/desktop` and
`alpine/themes/profiles/gruvbox-dark` copies), restore `XCURSOR_THEME` in
`oldbook-sway` and `oldbook-session`, then `swaymsg reload` and
`oldbook-gtk-settings`. The theme directory can stay; nothing looks at it once it
is unnamed. Removing it entirely is `rm -r` on the icons directory plus a
deployment run.
