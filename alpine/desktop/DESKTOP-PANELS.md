# Desktop panels and scripture

Transparent Conky panels are arranged around the current wallpaper, and a
scripture search bar sits on the desktop for choosing what to read.

## How the arrangement works

`mbp-intel-conky layout` reduces the current wallpaper to two coarse grids: how
much detail each cell holds and how bright it is. Panels are then seated
greedily into the calmest cells, away from the middle of the picture where a
painting normally puts its subject, and away from the Waybar strip, the screen
edges and the scripture search bar. Text colours come from the active theme in
`alpine/themes/`, adjusted per panel until they clear a WCAG contrast ratio
against the region each panel actually covers, so the same palette stays
legible over a dark abbey and a bright snowfield alike.

Every layout is paired to its wallpaper. The placement is cached under
`~/.local/state/mbp-intel/conky/layouts/` against a key combining the image
bytes, the screen geometry, the theme and the panel set, so one painting is
always dressed the same way and is only re-analysed when one of those changes.
`mbp-intel-wallpaper` refits the panels whenever the desktop image changes.

Scripture search uses a 16-pixel margin when the bottom edge is free. A fullscreen
window, tiled window reaching the bottom, or fixed edge bar moves it to a
clearance position (at least 60 pixels). Floating captions do not displace it.
Larger fixed bars reserve their actual depth plus breathing room. The bar reads
Sway directly once a second, without launching polling subprocesses.

Conky stays in stable clearance positions, with at least 60 pixels at the bottom
and right. Window and fullscreen changes never trigger a Conky reflow or restart.
This avoids repeated placement searches and keeps the slow content intervals
intact. Conky margins compensate for the live Waybar top surface reported by
SwayFX, so planned wallpaper coordinates match rendered coordinates. Insets and
the search rectangle participate in the wallpaper layout cache.

Scripture favors the upper right and Coast to Coast favors the lower right.
The layouter can choose another position when the painting's subject or another
card occupies the preferred corner. The Scripture search bar follows the active
theme automatically, including theme changes while it is already running.

Panels are fully transparent: the window colour is `#00000000` and legibility
comes from the contrast pass plus a text shadow, never from a filled box.

## Content and refresh policy

Conky is reserved for slow information: date, Scripture, battery charge/status,
gallery notes, rotating text and future configured email. CPU, memory, processes,
storage, network and temperature telemetry belong in Waybar. Do not restore the
historical reactor, memory, storage or transmission cards.

`conky_policy.py` filters telemetry variables when loading the templates, before
wallpaper-cache lookup, and clamps panel and interval-command refreshes to
60–300 seconds. The source templates use 60 seconds for the display, 120 for
Scripture/gallery and 240 for rotating text. An explicitly requested Scripture
selection or artwork/theme change can redraw immediately. The guard does not
inspect the behavior of arbitrary external helper programs; new helpers must
also follow this policy. Email still needs a configured mailbox source.

## Controls

- **Super+Shift+G** switches the panels off and on.
- **Super+/** opens Bible-only search.
- **Super+Shift+/** searches Torah, Talmud and reflections, with Bible matches last.
- The gallery picker (**Super+G**) also offers *Desktop panels · switch on/off*
  and *Refit desktop panels to this painting*.
- **Click Scripture:** advance to the next verse or reflection.
- **Click Witness:** advance its quotation.
- **Click Coast to Coast:** advance the journal rotation.
- **Click Ghost Gallery:** show the next painting.

These clicks refresh the affected card immediately. They use Conky's native
mouse handling; application windows above a card keep their own pointer input.

```sh
mbp-intel-conky layout      # refit to the current wallpaper
mbp-intel-conky plan        # write configs without restarting the panels
mbp-intel-conky status      # on, off or stopped
mbp-intel-conky toggle
```

Panels are defined in `alpine/desktop/.config/conky/panels.json`. Each entry has
an `id`, a pixel `width` and `height`, an optional preferred edge, a `priority`
deciding who picks a spot first, an `enabled` switch and its Conky `text`. The
placeholders `{{iface}}`, `{{battery}}`, `{{hwmon}}`, `{{bin}}` and
`{{scripture}}` are substituted with the machine's actual hardware and helper
paths at layout time.

## Scripture

Click **History** on the Scripture heading to open saved passages, study material
and notes. It uses the heading's active theme font and accent; opening it keeps
the selected passage unchanged. Clicking the passage itself advances it.

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
mbp-intel-scripture panel                 # the desktop block
mbp-intel-scripture show 'Isaiah 53:3-6'
mbp-intel-scripture search Paul
mbp-intel-scripture select 'Psalm 23'
mbp-intel-scripture select-reflection job-answer
mbp-intel-scripture figures
```

References accept the usual spellings: `Isaiah 53`, `Isa 53:3-6`, `1 Cor 13:4`,
`II Timothy 1:7`, `Ps 23`, `Song 2:1`. Single-chapter books are cited by verse,
so `Jude 4` and `3 John 4` resolve the way they are normally written. With
nothing selected the desktop shows the reflection for the day, which walks the
whole set in turn.

**Super+/** searches only Bible verses. **Super+Shift+/** searches all bundled
collections: Torah, Babylonian Talmud, reflections, then Bible verses. Matching
preserves this order, making Bible results least prioritized. The desktop button
opens the Bible-only picker. Enter saves the selected passage and immediately
replaces only the Scripture Conky process, bypassing its cached command output.
The other panels keep running; background intervals remain 60/120 seconds.
SIGUSR1 alone does not reliably clear that cache in the installed Conky.

The English supplemental library includes all five Torah books (JPS 1917) and
37 Babylonian Talmud tractates (William Davidson), 87,327 segments. References
include `Torah Genesis 1:1` and `Talmud Berakhot 2a:1-2`; `Berakhot 2a` also
works. The selected passage retains its edition and source metadata. See
[`../assets/scripture/README.md`](../assets/scripture/README.md) for credits,
licenses and offline reproduction. The 33 curated reflections remain intact.

## Coast to Coast notebook

The rotating card reads SQLite, not an in-memory random list. The database is
`~/.local/share/mbp-intel/journal/entries.sqlite3` (or beneath `XDG_DATA_HOME`),
with private file permissions. Initial setup imports eight original Coast to
Coast lines and eight dated assistant-written notes about observed desktop work.
Existing custom `ghost_lines` are imported once before removal from the template.
After initialization, changing seed files or templates does not overwrite the
database. Three original-style quips alternate with one dated journal note, one
entry every four minutes; rotation state survives restarts. There is no automatic activity collection or network request.

The panel shows up to four body lines, with dates on journal notes; the database retains
the full text, source, creation time, enabled flag and last display time.

```sh
mbp-intel-journal show
mbp-intel-journal list
mbp-intel-journal add --text 'Today I finished arranging the desktop.'
mbp-intel-journal add --kind quip --text 'Moltar, bring the notebook.'
mbp-intel-journal disable 3
mbp-intel-journal backup ~/desktop-journal-backup.sqlite3
```

`list` prints complete records as JSON. New notes default to today's local date;
`--date YYYY-MM-DD` sets a date explicitly. Backup uses SQLite's consistent
backup API and refuses to overwrite an existing file. Restore a saved database
to the journal path while Conky is stopped, then start Conky. The personal live
database stays outside Fossil; the initial seed and code are versioned.
