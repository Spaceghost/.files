# The cat hearth, and what these pictures are not

Bed mode runs only while the session is locked, and an `ext-session-lock-v1`
surface covers everything: no layer-shell surface can be put above it. So the
only thing that can tell a locked machine's owner that it is deliberately
heating itself for a cat is the locker. `swaylock-effects` gained
`--indicator-panel` for that (`alpine/packages/swaylock-effects/README.md`), and
`alpine/desktop/.local/lib/oldbook/cat_panel.py` is what writes the panel.

## Where it goes, and why not where you would expect

The lock screen already has a clock at 40 % of the output height and a caption
card in the lower-left corner. On this 1440×900 logical panel the indicator's
strip starts at y=180 and the caption card is 560 wide and **252 tall for the
current painting** — a height that changes with every painting and every hour's
Scripture. That leaves 64 pixels of clear height under the ring, and a 620-wide
panel centred below the clock would land on the card.

So the hearth sits **above** the clock: 620×150 with a 14-pixel gap, which needs
164 of the 180 available and leaves a 16-pixel margin from the top of the
screen. `test_lock.py` asserts that it fits, against `lock_scene`'s own geometry
constants, so a future change to the indicator's radius or position fails a test
rather than pushing the panel off the screen. The locker falls back to placing
it below if there is ever not enough room above, because half a panel clipped
off the top would be worse than a panel in the second-best place.

**None of that has been seen.** The numbers are arithmetic on this repository's
constants, not a measurement of a lock.

## What is honest about these

**They are this repository's own renderer, not screenshots of a lock.** The
patched locker was built on `bak` and deliberately not installed, so no running
`swaylock-effects` has ever drawn one of these. What is proved here is what
`cat_panel.render` produces for a given cat record; what is *not* proved is that
the locker blits it where these say, that the cross-fade looks right, that the
panel appears at the moment bed mode arms, or that the damage rectangle is
correct on a real 2880×1800 output. Those need an install and one deliberate
lock, and that is the user's check.

No cat has been observed and no bed mode has ever run on this machine, which is
already written down under CAT-BED. Every temperature below is a number typed
into a synthetic record.

## The mapping, stated once

The hearth is a gauge, not a mood.

| What you see | What it is |
| --- | --- |
| Lit embers along the grate | The measured CPU temperature, on a scale from **30 °C** to the regime's own **abort** line, quantised to 28 cells |
| The `TARGET` mark | `thermal.REGIMES[regime]['cpu_target']` — where the controller aims |
| The `EASE` mark | `cpu_ceiling` — where the load is paused until the machine cools |
| The `STOP` mark, and the end of the scale | `abort` — where the sitting is abandoned and the fans go back |
| Flame height | The duty the controller is pushing right now, in whole blocks |
| `CPU / BATTERY / SKIN` with a second number | Each family's own reading against its own ceiling; a value within 3 °C of its ceiling is drawn in the accent |
| `FANS HELD` | The privileged fan hold is actually taken |

Two consequences worth saying out loud. The scale **ends at the temperature
where this feature gives up**, so nothing can be drawn as hotter than that, and
a machine past the abort line is not drawn at all because the sitting is over.
And an unreadable sensor lights **no** embers and prints `UNREADABLE` in the
alarm colour, because a sensor that will not answer is a stop condition, never a
cold one.

Closing the lid changes every number on the panel, because it changes the
regime: `closed-lid.png` shows the same kind of sitting under `abort 72 °C`
instead of `80 °C`.

## The states

| File | What it shows |
| --- | --- |
| `countdown.png` | The wait before any heat is made. The fire is laid and unlit: the marks, the ceilings and all three readings are already on screen, so what the machine is about to do is visible before it does it. `UNLOCK TO CANCEL` is the truth — unlocking clears `present`, which is the one gesture that cannot be mistaken for a keystroke |
| `warming.png` | A sitting under way, fans held, 57 °C against a 60 °C target |
| `hot.png` | Pushing hard at 68 °C, past the target and short of the ease line, with `SKIN 37° / 40°` in the accent because the palm rest is the constraint that is closest |
| `coasting.png` | 74 °C: past the ease line, so the load is off and the flames are out while the embers stay lit. That is the truth of the moment — the machine is hot and nothing is heating it |
| `closed-lid.png` | The strict regime. Same feature, tighter ceilings, and the panel says `LID CLOSED · STRICT` |
| `on-battery.png` | The still form. Bed mode is mains-only, so off mains the panel exists only to say why, with no cross-fade and a slower poll |
| `unreadable.png` | A skin sensor that stopped answering |

`evidence.json` records the palette, the geometry, and for each picture the
readings, the ceilings, the ember and flame counts and the file's SHA-256.

## Password entry

Nothing here reacts to a keystroke. The panel is a function of the cat record
and the clock: it is quantised to whole degrees and whole seconds, it is redrawn
only when one of those changes, and the locker eases between two of them on a
clock started when the file changed rather than when a key was pressed. While it
is up it asks the locker for `ring 0`, which removes swaylock's own arc and with
it the per-keypress highlight — one arc per key in one colour, one per backspace
in another — that is countable off a photograph. That is the one place this
change makes the lock screen measurably better rather than merely different.

The panel appearing at all is caused by keys being held, but that judgement is
`cat_presence`'s: five keys held together for two seconds plus a corroborating
signal, vetoed outright by three clean press-and-release events in ten seconds.
No typed password produces it.

## Reproducing

```sh
python3 -m unittest discover -s alpine/tests -p test_cat_bed.py
python3 -m unittest discover -s alpine/tests -p test_lock.py
```

`HearthTests` asserts the mapping above against `thermal.REGIMES` directly, so
the table in this file cannot drift from the code without a test failing.
