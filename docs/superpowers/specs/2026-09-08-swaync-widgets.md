# SwayNC control-center widgets — 2026-09-08

## What

The notification control center now carries four widgets above the compact
history, in this order: title, do-not-disturb, **mpris**, **volume**,
**backlight**, **buttons-grid**, notifications.

- **mpris** shows the playing MPRIS player (Pithos) as a card: album art as a
  blurred backdrop plus a rounded cover, title, artist/album, previous,
  play/pause, next. `show-album-art: when-available`, `autohide: true` so the
  card disappears when nothing is playing.
- **volume** is the output level with a per-application drawer (application
  icons, no labels) behind the `󰅀` / `󰅃` button; the empty drawer says
  "Nothing on the air".
- **backlight** controls `gmux_backlight` (the MacBookPro11,5 panel) with a
  floor of 40/1023 so the slider cannot black out the display.
- **buttons-grid** holds six quick actions, three per row: Lock
  (`oldbook-lock`), Deck (`oldbook-control`), Next art (`oldbook-wallpaper next`),
  and three toggles whose state is refreshed every time the panel opens:
  Hold art (`oldbook-wallpaper pause`, checked while rotation is paused),
  Mic off (`oldbook-audio mic-mute`, checked while the default source is muted)
  and Cards (`oldbook-conky toggle`, checked while the desktop panels are on).

## Why

The stylesheet already carried rules for these widget classes, so the only
missing piece was enabling them and styling the elements SwayNC 0.12 (GTK 4)
actually renders. This is additive: notification placement, the transparent
host, the compact history and the bar's left/right click behaviour are
unchanged (NOTIFICATION-PLACEMENT).

## Command quoting

SwayNC runs every button and update command through `/bin/sh -c "<command>"`,
then splits that string with `g_shell_parse_argv`. Commands therefore must not
contain double quotes; `~` expands because a shell runs them, and single quotes
are safe. The first draft wrapped commands in `sh -c '... "..." ...'` and
SwayNC logged `unterminated quoted string`; the checked-in commands use single
quotes only.

## Styling

Both copies were updated identically: `alpine/desktop/.config/swaync/style.css`
(shared source rendered into new profiles) and
`alpine/themes/profiles/gruvbox-dark/.config/swaync/style.css` (the live link).
The desktop copy also gained the profile's transparent-list rules so the two no
longer diverge. Album-art size and per-app icon size are set through the GTK 4
`:root` variables SwayNC's default stylesheet defines.

## Verification

`alpine/tests/verify_swaync_widgets.py` renders the real config in a private
headless SwayFX session with a private D-Bus bus, a fake MPRIS player with local
album art, and two synthetic notifications, then screenshots the open panel and
checks SwayNC's widget load log. Evidence: `alpine/verification/swaync-widgets/`.
The live session accepted `swaync-client -R` and `-rs`; the live visual check is
pending because the display was powered off and the session locked while this
was done.

## Rollback

Restore the previous `config.json` (widgets: title, dnd, notifications) and the
previous stylesheets from Fossil, then `swaync-client -R && swaync-client -rs`.
