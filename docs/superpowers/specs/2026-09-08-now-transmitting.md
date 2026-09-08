# Now transmitting — 2026-09-08

## What

`oldbook-osd` grew a third surface beside the feedback pill and the screenshot
wash: a track card that slides in at the bottom right of the focused output when
the playing track changes, holds for four seconds, and slides out again.

The card carries the album art from the player's `mpris:artUrl` (cover-cropped
to a rounded 72-pixel square), an amber `NOW TRANSMITTING` eyebrow, the title in
cream, and the artist and album in the muted tone, on the same charcoal card the
notification centre uses. A track with no readable art gets a music glyph on a
surface tile instead. Long titles are trimmed with an ellipsis to the column.

The daemon watches `PropertiesChanged` for `org.mpris.MediaPlayer2.Player` on
the session bus at `/org/mpris/MediaPlayer2`, so any player announces itself,
Pithos included, with no polling. `oldbook-osd card --title ... --artist ...`
sends one by hand.

## Why the card stays out of the way

`Announcer` in `osd.py` holds the whole rule, so it is testable without a bus or
a display. A card appears only when the preference is on, the player is playing,
the desktop is unlocked and the notification centre is closed, and only when the
track differs from the last announcement (or twenty seconds have passed, so a
replayed track still announces). A suppressed announcement still counts as seen,
so the card does not ambush the user the moment they unlock or close the centre.

Centre visibility comes from SwayNC's own `SubscribeV2` signal with a
`GetVisibility` call at startup, which is push-based and costs nothing. Lock
state comes from the lock helper's readiness record, whose recorded process must
still exist. Opening the centre or locking mid-card dismisses the card from
wherever it has slid to, without a jump.

## Motion

`Card.offset_at` returns the distance off the right edge in pixels and nothing
else keeps time, so the drawing code samples it on the compositor's frame clock.
The slide eases out on the way in and in on the way out, cubic, settling exactly
on zero and on the full travel with no overshoot. The surface is wider than the
card by its whole travel, so the slide is a translation and never a resize, and
it unmaps as soon as the exit finishes. With desktop animations disabled the
card simply appears and disappears.

## Palette

The pill and the card both call `overlay_theme.read_palette` on every show, so a
runtime accent override from the reactive-palette work takes effect on the next
reading without restarting the daemon.

## Verification

`alpine/tests/test_osd.py` covers the message round trip, the tidying and
bounding of player text, the announcement rule in all its refusals, the slide
timing and its monotonicity, dismissal, the animation-disabled path, the
preference file and the stale lock record. 37 tests pass.

`alpine/tests/verify_osd.py` gained five card checks and passes all sixteen in a
private headless SwayFX session; evidence in `alpine/verification/now-transmitting/`.
The suppression rule was also seen live: with the session locked, a card
announcement mapped nothing. The card has not yet been watched sliding on the
physical panel, because the session was locked for the whole of this work.

## Rollback

Set `{"card": false}` in `~/.config/oldbook/osd.json` and restart the daemon, or
restore the previous `oldbook-osd` and `osd.py` from Fossil. Nothing else in the
desktop depends on the card.
