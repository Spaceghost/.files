# Desktop panels and scripture

Transparent Conky panels are arranged around the current wallpaper, and a
scripture search bar sits on the desktop for choosing what to read.

## How the arrangement works

`oldbook-conky layout` reduces the current wallpaper to two coarse grids: how
much detail each cell holds and how bright it is. Panels are then seated
greedily into the calmest cells, away from the middle of the picture where a
painting normally puts its subject, and away from the Waybar strip, the screen
edges and the scripture search bar. Text colours come from the active theme in
`alpine/themes/`, adjusted per panel until they clear a WCAG contrast ratio
against the region each panel actually covers, so the same palette stays
legible over a dark abbey and a bright snowfield alike.

Every layout is paired to its wallpaper. The placement is cached under
`~/.local/state/oldbook/conky/layouts/` against a key combining the image
bytes, the screen geometry, the theme and the panel set, so one painting is
always dressed the same way and is only re-analysed when one of those changes.
`oldbook-wallpaper` refits the panels whenever the desktop image changes.

Panels are fully transparent: the window colour is `#00000000` and legibility
comes from the contrast pass plus a text shadow, never from a filled box.

## Controls

- **Super+Shift+G** switches the panels off and on.
- **Super+/** summons the scripture search bar and gives it the keyboard.
- The gallery picker (**Super+G**) also offers *Desktop panels · switch on/off*
  and *Refit desktop panels to this painting*.

```sh
oldbook-conky layout      # refit to the current wallpaper
oldbook-conky plan        # write configs without restarting the panels
oldbook-conky status      # on, off or stopped
oldbook-conky toggle
```

Panels are defined in `alpine/desktop/.config/conky/panels.json`. Each entry has
an `id`, a pixel `width` and `height`, an optional preferred edge, a `priority`
deciding who picks a spot first, an `enabled` switch and its Conky `text`. The
placeholders `{{iface}}`, `{{battery}}`, `{{hwmon}}`, `{{bin}}` and
`{{scripture}}` are substituted with the machine's actual hardware and helper
paths at layout time.

## Scripture

The complete King James text ships in the checkout as
`alpine/assets/scripture/kjv.tsv.gz`: all 66 books and all 31,102 verses, one
tab separated record per line, so nothing is fetched at runtime.

`alpine/assets/scripture/reflections.json` holds curated reflections on Christ
and on what particular believers endured — Isaiah, Paul, Hosea, Job, Joseph,
Moses, David, Elijah, Jeremiah, Daniel, Ruth, Esther, Jonah, Habakkuk, Peter,
Stephen, Mary, John the Baptist and Thomas. Each names the trial, what it
means, and one concrete practice to act on. Every anchor verse is resolved from
the bundled text rather than quoted separately.

```sh
oldbook-scripture panel                 # the desktop block
oldbook-scripture show 'Isaiah 53:3-6'
oldbook-scripture search Paul
oldbook-scripture select 'Psalm 23'
oldbook-scripture select-reflection job-answer
oldbook-scripture figures
```

References accept the usual spellings: `Isaiah 53`, `Isa 53:3-6`, `1 Cor 13:4`,
`II Timothy 1:7`, `Ps 23`, `Song 2:1`. Single-chapter books are cited by verse,
so `Jude 4` and `3 John 4` resolve the way they are normally written. With
nothing selected the desktop shows the reflection for the day, which walks the
whole set in turn.

The search bar rests on the desktop layer and takes the keyboard only when
clicked or summoned. Typing searches the reflections by figure and the verse
text by words; Enter or a click sets what the desktop panel shows.
