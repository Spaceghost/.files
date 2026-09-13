# The rice, catalogued

Everything on this desktop that exists to be looked at, in one place: the
SwayFX glass, the control deck, the gallery and its crossfade, the reading
cards, the lock screen, the boot console, the keyboard glow, the terminals.
Each entry says what it looks like, how to trigger it, where to tweak it, how
to switch it off, and where the evidence lives. Paths are relative to
`alpine/`; design notes for the two 2026-09-08 rounds are under
[`../docs/superpowers/specs/`](../docs/superpowers/specs/) and the behaviour
contracts live in [FEATURES.md](FEATURES.md).

Three words recur in the evidence notes. **Live** means seen on the physical
2880×1800 panel. **Headless** means rendered in a private SwayFX session with
the real configuration and photographed with grim; it proves layout and
behaviour, not blur (the pixman renderer has none), frame pacing or sound.
**Next boot** means the change is installed but the screen it changes has not
been shown since. Nothing below claims a physical check that was not made.

Most application files exist twice: the shared source under
`desktop/` and the authored copy under `themes/profiles/gruvbox-dark/`.
`readlink ~/.config/<path>` tells you which one is live; keep edits identical
in both, or run `oldbook-theme sync` after editing the desktop copy.

![The desktop after the Ghost Observatory adoption, rendered headlessly](verification/ghost-observatory/production.png)

## Keys and pointer, on one page

| Do this | Get this |
| --- | --- |
| `Super+Enter`, `Super+D` | Ghostty with the Space Ghost splash; the application launcher |
| Hold `Super` for half a second | Contextual shortcut guide (Hold to Help); release or press a key to dismiss |
| `Super+Shift+D`, click the Ghost badge | The command deck |
| `Super+G` | Painting picker with thumbnails; `Super+Ctrl+Left/Right` previous/next painting, crossfaded |
| `Super+Shift+P` | Pause or resume the twenty-minute rotation |
| `Super+Shift+G` | Desktop reading cards off and on |
| `Super+/`, `Super+Shift+/` | Scripture search in the desktop bar, Bible only or every collection |
| `Super+Shift+N`, click the bell | Notification centre: track card, sliders, quick actions, history |
| `Super+Escape` | Lock: the desktop dissolves into the blurred painting |
| `Super+Shift+E`, click the battery | Power deck: lock, suspend, log out, reboot, shut down |
| `Super+Tab`, `Alt+Tab` | Window carousel with still previews, recent order |
| Mission Control (F3) | Every workspace as a card of live window stills; drag a still to move that window |
| Launchpad (F4) | The application grid over the blurred painting; type to filter |
| `Super+E`, three fingers up | Expo, the workspace and window picker |
| Four fingers up / down | Clear the desktop / restore it, or open the carousel when nothing is hidden |
| Three or four fingers left / right | Next or previous workspace |
| Four-finger pinch in | Application launcher |
| `Super+1`…`9`, `Super+0` | Workspaces Ghost, Orbit, Lab, Signal, Lounge, 6–9, and Strata on 10 |
| Super + backtick, `Super+~` | Drop-down console (Ghostty), drop-down monitor (btop in Foot) |
| `Super+Space`, `Super+Shift+Space` | Float; float at 90% of the workspace, centred |
| `Super+=`, `Super+-`, `Super+C` | Grow or shrink from the centre; centre and raise |
| `Super+Ctrl+B` | Return the caption strip to the bottom edge |
| `Super+Shift+V` | Clipboard history picker |
| `Super+i`, `Super+Shift+i`, `Super+N` | Next AI window; agent menu; agent picker, the best Codex and Claude first with model and effort named |
| `Print`, `Shift+Print`, `Ctrl+Print` | Screenshot with flash and shutter click, then Satty |
| Volume, mic and brightness keys | The change shows on the bottom-centre pill |
| `F5` / `F6` | Keyboard light down / up, also while locked |
| `Shift+F6` / `Shift+F5` | Slow breath / steady light |
| `Ctrl+F6`, `Ctrl+F5` | Typing pulse; typing shadow |
| `Ctrl+Shift+F6`, `Ctrl+Shift+F5` | The same two, gated by sustained typing speed |
| `Alt+F6` | Ambient glow from the room's light |
| `Alt+Shift+F6` | Breathe on air: keystrokes fill the lungs, and the painting swells with them |
| `Caps Lock` | Escape; the key's LED becomes the AI attention light |
| Artwork badge: left, right, middle, scroll | Picker; next painting growing out of the click point; pause; browse. Super+click paints; Shift+click edits prompts; Super+Shift+click invents a theme |
| Rest on a workspace button | A peek of that workspace's windows, one still and title each |
| Hover CPU, network, sound, battery | Drawers slide out with memory and thermals, radio and firewall, microphone, brightness and keep-awake |
| Caption strip: left, middle, Shift+right | Window picker; float toggle; the decoration editor |

## Take the tour

Everything below exists to be looked at, so here is the order it takes to look
at it. The right-hand column is the honest one: most of the second 2026-09-08
round was verified in private headless sessions while the panel was off or the
session was locked, so **first sighting** means nobody has watched it on this
screen yet and you are the first.

### Right now, with one key or one click

| Do this | Watch for | Seen before? |
| --- | --- | --- |
| Super+N, Enter, Enter | The best Codex, its model and effort on the line, opens where you used it last, straight on its prompt with no trust screen | First sighting |
| Super+Shift+D, Theme, New theme · describe it here, a few words, Enter | A notice that the design has started, then the whole desktop restyles the moment it lands; GRUB and the boot console follow in the background and say so | First sighting |
| Mission Control (F3) | Every workspace as a card of real window stills, the focused one outlined in amber; drag a still onto another card to move that window | First sighting |
| Launchpad (F4), then type | Every application over the blurred painting, filtering from the first keystroke, page dots underneath | First sighting |
| Rest the pointer on a workspace button | After a third of a second, a peek of that workspace's windows beneath the bar | First sighting |
| Right-click the artwork badge | The next painting grows out of the exact point you clicked | Crossfade seen once live; the reveal from a click is a first sighting |
| `Super+Shift+N` or click the bell | The track as a card with blurred album art, sound and brightness sliders, six quick actions | Reloaded live, never looked at |
| Tap a volume or brightness key | The pill at the bottom centre, amber bar, gone in about a second | Mapped live while the display was off |
| `Print` | A cream flash, the shutter click, then Satty | First sighting; the click has not been heard in place |
| `Super+Escape` | The desktop dissolves into the blurred painting: clock, caption card, the hour's Scripture | First sighting |
| `Super+Shift+E` or click the battery | Five charcoal power tiles over the blurred desktop | First sighting |
| `Super+G` | The painting picker with a rounded thumbnail on every row | Seen live |
| Focus a floating window, then a tiled one | The caption strip flies home and rings leave its edge across the lower screen | The first version was seen live; the rebuilt wave is a first sighting |
| Open a new terminal | The Space Ghost splash beside the painting | Seen live |
| Skip a track in Pithos | A card slides in at the bottom right for four seconds | First sighting |
| `oldbook-palette show` | Which accent this painting elected, and why | Command output only |
| `oldbook-astro status` | Today's sunrise, sunset and moon | Command output only |
| `oldbook-sound unlock` | One of the six synthesized cues | Each played once, quietly, during the build |

### With a mode switched on

| Do this | Watch for | Seen before? |
| --- | --- | --- |
| `Alt+Shift+F6`, then type for a while | The keys breathe deeper as your typing fills the lungs, and the painting swells in time | The swell was driven live by a synthetic record; the real keyboard driving it is a first sighting |
| `Alt+F6`, then cover the sensor beside the camera | The keys rise as the room darkens | The sensor was read live; a real room change is a first sighting |
| `oldbook-ambient-display on`, then change the light | The panel eases to the room, and learns any level you set by hand | First sighting |
| Command deck → Night light, after sunset | The display warms | wlsunset is running; the evening ramp has not been watched |

### By waiting at the desk

| Do this | Watch for | Seen before? |
| --- | --- | --- |
| Idle four minutes | The paintings begin to drift and cycle, and restore exactly on return | A two-second run only |
| Idle four and a half minutes | The display eases to a fifth, the keyboard takes one last breath | Sysfs readings only |
| Idle five minutes | The lock screen arrives on its own | First sighting |

### At the next login

| Do this | Watch for | Seen before? |
| --- | --- | --- |
| `Super+1`…`Super+0` | The whole desktop slides sideways, towards the number you asked for | First sighting; needs SwayFX r4, which loads at login |
| Open and close any window | It grows into place, and shrinks away | First sighting |
| Make the desktop wait | The pointer becomes an amber Ghost ring, turning and breathing | First sighting |

### At the next reboot

| Do this | Watch for | Seen before? |
| --- | --- | --- |
| Power on | Three seconds of Gruvbox GRUB menu with the Ghost wordmark | First sighting |
| Let it boot | The LUKS passphrase prompt in Gruvbox, in Terminus 16×32 | First sighting |
| Hold `Shift` or `Esc`, pick the Ghost Planet entry | A masthead above the passphrase prompt | Never booted |
| `Ctrl+Alt+F2` | A rescue getty with the Ghost Planet banner | First sighting |

## Compositor

**Glass, corners and shadows.** SwayFX 0.6 (a local package with the
screen-corner patch) draws two-pass blur behind translucent surfaces, 22-pixel
window corners with `smart_corner_radius` off so gaps keep every window
rounded, 34-pixel soft shadows offset ten pixels down, a two-percent dim on
unfocused windows and no outline pixel anywhere. Bars and launcher layers get
18-pixel corners, the power deck and the OSD get blur behind them by layer
namespace. Tweak `desktop/.config/swayfx/effects.conf` (and the profile copy);
Sway itself keeps gaps at 6 inner and 7 outer in `desktop/.config/sway/config`.
Off: `OLDBOOK_STOCK_SWAY=1 sway` at the next login, or edit the values. The
Ghost Observatory geometry is the 2026-09-08 change; the compact 6-pixel
corners and 3/4 gaps are one `fossil diff` away. Evidence: headless renders in
[verification/ghost-observatory/](verification/ghost-observatory/README.md);
the physical frame rate with the larger shadow radius is unobserved.

**Rounded screen.** The output itself is masked with 20-pixel black corners
after the whole scene is drawn, including overlays, fullscreen surfaces, the
lock and the software cursor. It comes from `packages/swayfx/screen-corners.patch`
and `oldbook-sway` exports `SPACEGHOST_SCREEN_CORNER_RADIUS`; set it to `0`
before starting Sway to disable the mask. Evidence and limits:
[verification/screen-corners/](verification/screen-corners/README.md).

**Fullscreen etiquette.** While a window is fullscreen the bar fades to
30 percent and comes back on hover; `oldbook-waybar-dim` writes one imported
stylesheet only when the state changes. Off: remove its block from
`oldbook-session`. Evidence: [workspace-chrome](verification/workspace-chrome/fullscreen.png).

**Window and workspace motion.** SwayFX r4 carries
`packages/swayfx/window-animations.patch`: windows grow into place as they open
and shrink away as they close, layout changes glide instead of snapping, and
switching workspace slides the whole desktop sideways, the arriving workspace
entering from the side its number lies on. Floating windows travel with it from
a recorded base position, and an interrupted switch settles both workspaces
before the next one starts, so no stale offset can strand a window. Fullscreen
transitions are deliberately left unanimated. Each kind carries its own
duration in `desktop/.config/swayfx/animations.conf`: `animation_open_ms` 160,
`animation_close_ms` 130, `animation_move_ms` 140, `animation_workspace_ms` 220
and `animation_workspace_style slide|fade|both`. Off: `animations disable` in
that file, or delete it. The running compositor never sees those commands:
`oldbook-sway` validates the installed binary against the file at login and
only then includes it, so an older SwayFX starts exactly as before. **Next
login:** the patch is installed but the session predates it. Evidence:
[verification/swayfx-animations/](verification/swayfx-animations/README.md),
thirty-two frames proving by colour that a slide separates the two workspaces
horizontally where a fade does not, with idle cost measured at zero.

### Why the blur is one pass

**Corrected.** The reach arithmetic below was wrong by a factor of two, and the
cause it names was wrong too. SceneFX reaches `2^(blur_passes + 1) *
blur_radius`, so one pass at radius 4 is 16 pixels rather than 8 — it never did
fit inside the 13 pixel gap. And reaching past the gap was not the defect: the
smear was SceneFX skipping its own damage compensation, because a guard compared
the damage region's *bounding box* to the output instead of its coverage, and a
software-cursor rectangle plus any distant repaint made that box output-sized
while almost nothing was damaged. Upstream fixed it a week after the 0.5 tag;
`alpine/packages/scenefx` carries the fix. One pass is kept because it is
cheaper, not because it fits.

#### The original reasoning, left for the record

Blur reaches roughly `blur_radius * 2^blur_passes`. At radius 4 and two passes
that is about 16 pixels, and the gap between two tiled windows is 13, so the
blur was sampling three pixels into the neighbouring window. With focus
following the pointer, crossing between two terminals repainted that neighbour
and the blur re-ran against a half-updated scene, smearing along the vertical
edges. Only the vertical ones: above and below sit Waybar and the decoration
strip, which are layers with `blur_xray enable` and therefore a static backdrop
that cannot go stale. One pass reaches about 8 pixels and stays inside the
channel, so the blur only ever samples wallpaper.

If you want the softer two-pass blur back, widen the channel to match rather
than the other way round: `gaps inner 17` restores a 16-pixel reach safely.

### Animation first

Jack: "I need animation to take absolute priority." The machine runs agents,
builds and watchers beside the desktop, and under that load a flight went
choppy even with the compositor's threads at nice -10, because the kernel's
autogroups rank sessions before threads: the desktop's session got one fair
share against each agent's, whatever its own threads said. `oldbook-ui-priority`,
the root helper that `oldbook-session` and each drawing daemon ask through doas
once at start, now does three things, each bounded to processes it can prove
are the desktop's and reset in anything they fork. The compositor's render
thread runs SCHED_RR at the lowest realtime priority; children return to
ordinary scheduling by SCHED_RESET_ON_FORK, and the kernel's realtime throttle
keeps even a spinning thread from taking the machine. The panels, the notifier,
the shortcut guide, the reading cards and the daemons that draw run at nice
-15, the compositor's helper threads at -10. And the desktop's own session
groups are weighted at nice -20, so against any other session they get about
ninety-nine parts in a hundred of a contended core; a daemon started by hand
in a terminal never drags that terminal's group up with it. Check:
`doas oldbook-ui-priority --check --session "$SWAYSOCK"` prints every desktop
thread's policy and every group's weight. Off: `doas chrt --other -p 0 <tid>`
returns a thread, `echo 0 | doas tee /proc/<pid>/autogroup` a group, and
removing the helper from `/usr/local/sbin` stops it being asked. Evidence: the
live `--check` output after applying it, 2026-09-13; how the flight feels under
load is his to judge.

## Control deck bar

The Waybar at the top is a 34-pixel floating strip with 6-pixel margins, split
into a left island, a bare centre and a right island (`desktop/.config/waybar/config.jsonc`,
`style.css`, both copies). CSS reloads on save; JSON needs
`pkill -USR2 -u "$(id -u)" -x waybar`. The [panel actions](desktop/.config/waybar/README.md)
table lists every click.

**Ghost badge.** The white, purple and pink Space Ghost glyph is the one
element no theme may recolour (`GHOST-BRAND`). Left opens the command deck,
right the launcher. Evidence: [verification/ghost-branding/](verification/ghost-branding/base.png).

**Artwork badge.** The badge shows a 22-pixel rounded thumbnail of the painting
on screen; paused rotation dims it, a running generation swaps in the amber
hourglass, and a missing thumbnail falls back to the gallery glyph. It is the
native module in `packages/waybar-art/art.c` (package `oldbook-waybar-art`
r10), fed by `oldbook-wallpaper status --thumbnail-height` and a debounced
watch on `current-wallpaper.png`. Tweak `#custom-art` in `style.css`; roll back
by reinstalling the archived r9 APK (see the [spec](../docs/superpowers/specs/2026-09-08-thumbnails.md)).
Evidence: headless states in [verification/gallery-thumbnails/badge.png](verification/gallery-thumbnails/badge.png),
confirmed live on the panel.

![Artwork badge states: rotating, paused, generating, no thumbnail](verification/gallery-thumbnails/badge.png)

**Workspace labels.** Workspaces 1–5 are Ghost, Orbit, Lab, Signal and Lounge;
the active number and name are bold and bright, the largest displayed
application is appended after a middle dot in a quieter weight, and Codex or
ChatGPT windows earn a star. The ✦ button jumps to the next AI window. Tweak
`desktop/.local/lib/oldbook/workspace_model.py`; names are in `sway/config`.
Evidence: [workspace-ready](verification/workspace-ready/README.md).

**Workspace peek.** Rest the pointer on a workspace button for 350 ms and a
popover opens beneath the bar with that workspace's windows: a rounded still
above a shortened title, one card each. Leaving closes it; a window whose
capture failed keeps its place as a plain tile, and a workspace with nothing on
it opens nothing. The stills come from the carousel's own capture provider
through `desktop/.local/bin/oldbook-window-stills`, cached under
`~/.cache/oldbook/stills/`, spawned asynchronously so the bar never waits.
Tweak `PEEK_DWELL_MS` and `PEEK_HEIGHT` in `packages/waybar-art/help.c` and
rebuild, or the `popover#oldbook-peek` rules in both stylesheets. Off:
reinstall the archived r10 APK. Evidence:
[verification/waybar-popovers/](verification/waybar-popovers/README.md)
(a native fixture under a private X server); the popover has not been opened on
the panel.

**Music centre.** Previous, play/pause with the track, and next sit directly on
the bar while an MPRIS player exists; the track accepts play/pause, previous,
next and five-second seeks, and Pithos gets delayed single-click playback,
double-click open, right-click show/hide, middle-click tired and Super+middle
ban. Evidence: [waybar-music](verification/waybar-music/music.png),
[pithos-controls](verification/pithos-controls/music.png).

**Signal meter.** A ten-bar spectrum from cava follows the media controls
while something plays, collapses after half a second of silence and stops cava
entirely when nothing plays; it has no clicks or tooltip and costs about four
percent of one core with music. Feeder: `desktop/.local/bin/oldbook-cava-bar`.
Off: delete `"custom/cava"` from `modules-center` in both `config.jsonc`
copies. Evidence: [verification/bar-visualizer/](verification/bar-visualizer/README.md)
(headless render, live bar strip seen).

**Drawers and tooltips.** CPU, network, sound and battery are groups that slide
out on hover: memory, thermal core and root storage; radio and firewall state;
the microphone; brightness and keep-awake. Every module carries a Space Ghost
tooltip that says what each click does. The clock keeps Los Angeles time with
a scrollable calendar. Tweak the `group/*` entries in `config.jsonc`.

## Gallery

**Paintings.** The gallery is Space Ghost and Zorak dropped into landscapes,
histories and suspiciously familiar paintings, generated through the Codex
login: one daily attempt by cron and more on request (`oldbook-wallpaper
generate`, Super+click on the badge). Scenes, insertions and mediums in
`wallpapers/prompts.json` combine so no subject repeats; the shared guidance
carries hard reverence limits. Every PNG lives under `assets/gallery/` with a
sidecar recording prompt, hash and provenance. The [gallery guide](wallpapers/README.md)
has the whole workflow. Evidence of the pipeline lives beside each painting.

**Rotation.** All workspaces share one painting and one twenty-minute timer;
`Super+Shift+P` or the badge's middle click pause it. Timer choices mix the
active theme's collection with unthemed art; manual browsing reaches every
collection. Tweak `wallpapers/gallery.json`.

**Crossfade.** `oldbook-background` owns a surface on the background layer,
above Sway's swaybg, and eases between paintings on the frame clock: 1.6 s
for the timer, 0.8 s for a deliberate change, and `--from X,Y` on `next`,
`prev`, `select` or `refresh` reveals the new painting from that point with a
soft radial edge. It starts on the image swaybg is showing so logins and
reloads fade instead of cutting, re-creates its surface when a respawned
swaybg covers it, and asks the desktop cards to return on top. Off:
`oldbook-background quit` returns the gallery to plain cuts until the next
login; remove its block from `oldbook-session` to keep it off. Evidence:
seven headless frames in [verification/background-crossfade/](verification/background-crossfade/README.md);
one live `next`/`prev` faded on the panel; physical frame pacing is unmeasured.

![Crossfade caught part-way in a private SwayFX session](verification/background-crossfade/04-fade-part-way.png)

**The desktop breath.** While the keyboard is in a breathing mode, the painting
breathes with it. The keyboard's single worker publishes its lung state to
`$XDG_RUNTIME_DIR/oldbook/air.json` twenty times a second, with a closing
record when it stops; `oldbook-background` swells the picture from 1.000 to
1.006 at rest and up to 1.018 once your typing has filled the lungs, composing
the swell into any running crossfade and settling back to exactly the untouched
image. In breathe-on-air mode the caption strip's amber wash pulses with the
same number, quantised to twenty-four steps so a 60 Hz breath costs a few
stylesheet updates a second. Both readers stat the file and release the frame
clock the moment nothing moves. Shared logic:
`desktop/.local/lib/oldbook/air.py`. Off: `~/.config/oldbook/breath.json`, or
**Desktop breath** in the command deck; either half can be stopped alone.
Evidence: [verification/desktop-breath/](verification/desktop-breath/README.md),
where the headless session measured 1.000, 1.018, 1.006 and 1.000 exactly. A
synthetic record made the live painting swell and settle, but the keyboard
light was off throughout, so the real breath driving the picture is unwatched.

![The painting at rest and at full lungs](verification/desktop-breath/02-full-lungs.png)

**The idle gallery.** Four minutes idle and the desktop becomes a slideshow:
`oldbook-screensaver` hands the background daemon a shuffled list of
rotation-eligible paintings, and it drifts about 1.06 of zoom across each one
for thirty seconds before crossfading to the next, the pan always a fraction of
the room the zoom opens so no edge can show. Any activity glides it back to
rest and to the painting it interrupted. The shared painting link, the saved
selection, the deadline and the pause switch are never written, so it runs even
while rotation is paused. Off: drop the `timeout 240` clause from the swayidle
line in `oldbook-session`. Evidence:
[verification/gallery-screensaver/](verification/gallery-screensaver/README.md);
a two-second live run drifted and restored, but a real four-minute idle has not
been watched.

![The gallery drifting mid-screensaver](verification/gallery-screensaver/02-drifting.png)

**Picker thumbnails.** `Super+G` lists every painting with a rounded thumbnail
beside its title on 40-pixel rows, then the gallery actions. Fuzzel resolves
dmenu icons through the icon theme, so the cache under
`~/.cache/oldbook/thumbnails/` is published as a private `Oldbook-Thumbnails`
theme. Library: `desktop/.local/lib/oldbook/thumbnails.py`. Off: delete the
cache and the theme directory; rows fall back to text. Evidence:
[verification/gallery-thumbnails/picker.png](verification/gallery-thumbnails/picker.png)
(headless), confirmed live.

**Themed collections and new themes.** `themes/current` names the collection
the timer and the daily painting use; each descriptor under `themes/<id>.json`
carries a palette, an image style and the design fields (font, radius,
spacing, opacity, bar and widget edges). Super+Shift+click on the badge invents
a complete random theme and applies it at once; Super+Shift+right-click asks
for a description. Both run `oldbook-theme create`, the same workshop the
command deck's theme menu opens, and neither paints anything: a theme is not a
painting. The eighteen earlier themes are preserved under `archive/`.
Evidence: [gallery-themes](verification/gallery-themes/launcher.png),
[launcher-themes](verification/launcher-themes/gallery-paged.png).

**When the painter is asked.** Painting spends Codex image credits and stops
when they run out, so it has a switch of its own in
`~/.config/oldbook/painting.json`: `scheduled` for the hourly job's daily
painting, `debut_painting` for a first painting after a new theme. Both ship
off, so nothing is painted unless asked for by name -- Generate new artwork,
Paint in an existing theme…, Super+click on the badge, `generate.py --manual`
-- and those always paint. Library `wallpapers/painting_policy.py`. Off: it
is off; set either key to `true` to switch that kind back on. The keyless
Pollinations API was tried as a free painter and rejected: one model, output
capped near 968x608 and a watermark despite `nologo`. Evidence:
`tests/test_painting_policy.py`; the schedule is not installed on this
machine, so nothing scheduled has been watched either way.

**Nocturnes after dark.** With a location file in place (see Sun and moon),
the timer draws night paintings with three times the weight of the rest
between sunset and sunrise, never excluding anything and never touching manual
browsing. A sidecar may say `"time_of_day": "night"`; otherwise whole words
such as night, moon, dusk, candle or aurora in the title or story qualify.
Logic: `desktop/.local/lib/oldbook/nocturne.py`. Off: remove the location
file. Evidence: seeded weighting in `tests/test_astro.py`; a full night of live
rotation has not been watched.

**Video background.** `oldbook-video-background FILE` plays a muted loop
beneath windows with mpvpaper; the command deck offers a picker and a stop.
Nothing starts automatically.

## Desktop reading cards

Transparent Conky cards are seated on the calm parts of each painting by
`oldbook-conky layout`, which scores the wallpaper's detail and brightness,
keeps clear of the bar, the edges and the scripture bar, and tunes each card's
text colour until it clears a contrast ratio over the pixels it covers. The
placement is cached per painting. They are reading, not telemetry
(`CONKY-READING`): `Super+Shift+G` hides them, the gallery picker refits them,
and `desktop/.config/conky/panels.json` (both copies) defines them. The
[panels guide](desktop/DESKTOP-PANELS.md) covers the policy and the clicks.

**Masthead.** The weekday in bold, the date, "Ghost Planet · Coast to Coast",
and since 2026-09-08 a sun-and-moon line: sunrise and sunset glyphs and times,
the moon's phase glyph, name and lit fraction, refreshed every five minutes by
`oldbook-astro panel` from an explicit location file. Evidence:
[verification/sun-and-moon/masthead-headless.png](verification/sun-and-moon/masthead-headless.png)
(headless); the card was refitted live but not photographed.

![Masthead card with the sun and moon line](verification/sun-and-moon/masthead-headless.png)

**Scripture.** A passage, its citation, a reflection and a practice, advancing
hourly from the bundled King James text, Torah, Talmud and curated
reflections. Click advances, right-click steps back along your own path, the
**History** link opens saved reading and notes. The desktop search bar takes
`Super+/` (Bible) and `Super+Shift+/` (every collection) and holds a manual
choice for an hour. Evidence: [scripture-selection](verification/scripture-selection/after.png),
[scripture-header](verification/scripture-header/README.md).

**Witness, Ghost Gallery, Coast to Coast, Power.** Quotations from outside
(click advances), the current painting's story, the rotating journal (three
quips per dated note, four-minute cadence, a personal SQLite database behind
`oldbook-journal`), and the battery bar. Evidence:
[desktop-journal](verification/desktop-journal/panels.png),
[conky-policy](verification/conky-policy/panels.png).

## The rice card

Features land faster than anyone remembers them: a paragraph here, a contract
in FEATURES.md, and then a wait for someone to read the right file. The rice
card is the desktop saying it itself — a quiet Conky card listing what was
added most recently, newest at the top, from
`~/.config/oldbook/rice.json`. A new feature is one new entry at the top of
that file and nothing else.

Conky has no hover, so the description is not a tooltip: it is the card's own
lower half, and it always describes the **selected** row. The pointer moves the
selection rather than pointing at it. Left-click steps forward, right-click
steps back, the middle button ticks an entry off as tried, the wheel turns a
page, and the header **Try** link runs the entry — or posts a notification with
the full description when it is something only you can do, like a keybinding or
the lock screen. Running counts as trying, so Try ticks it; middle-click takes
that back.

The card's height never changes. Short pages and short summaries are padded,
because a description block that resized would move the legend out from under
the pointer between clicks. Per-row hit testing was rejected on the same
grounds: the only precedent for pixel geometry here estimates line height from
the font size, which is close enough to place the Scripture History link and
not close enough to pick one row out of five.

Refresh is 300 seconds, there is no telemetry on it, and at battery-critical
the description block sheds while the list of names stays. It sits below
`ghost` in the placement order so every existing card keeps first pick of the
space — the tradeoff being that a busy wallpaper can leave it out entirely.
Off: delete the `rice` card from `desktop/.config/conky/panels.json`.

## Notifications

**Placement.** SwayNC popups sit on the top layer with no exclusive zone, so
nothing moves or loses focus; the empty host is transparent and only the cards
are styled. Config `desktop/.config/swaync/config.json`, style in both
`style.css` copies. Evidence: [verification/notifications/](verification/notifications/compact-history-card.png),
[notification-overlay](verification/notification-overlay/popup.png).

**Control centre.** `Super+Shift+N` or the bell opens INCOMING TRANSMISSIONS:
an "Off the air" switch, the playing track as a card whose blurred album art
is its own backdrop, the output volume with a per-application drawer, the
panel brightness slider with a floor that cannot black out the display, and a
grid of six quick actions (Lock, Deck, Next art, and the toggles Hold art, Mic
off and Cards, refreshed each time the panel opens), then the compact history.
Widgets are additive; remove any name from `widgets` in `config.json` and run
`swaync-client -R`. Evidence: [verification/swaync-widgets/](verification/swaync-widgets/README.md)
(headless with a fake player); the live panel reloaded but was not
photographed.

![Notification centre with the media card, sliders and quick actions](verification/swaync-widgets/control-center.png)

**Attention light.** Codex and Claude completions or approvals light the Caps
Lock LED through `oldbook-notification-led` until the window is visited;
ordinary notices never light it. Off: remove its launch from `oldbook-session`.

### The strip no longer moves your text

The strip used to reserve its own space, and the reservation travelled with
focus: a floating window took the caption with it and released the workspace
band, a tiled window took the band back. With the pointer choosing focus that
happened on every border crossing, and a headless run of the real daemon
measured the cost — the tiled terminal resized by 39 pixels, two or three rows
of its grid, twice per pass of the mouse.

The two jobs are separate now. An invisible one-pixel surface holds a fixed
exclusive zone on the saved edge and never changes for focus, mode, content or
fullscreen. The caption reserves nothing and draws at exactly the pixel it
always did. Set `"reserve_band": false` in `~/.config/oldbook/decoration.json`
and the band disappears entirely, leaving the strip overlaying windows — also
jump-free, just covering content instead of sitting beside it.

### The strip merges into its window

Attached along the bottom, the strip and the window read as one shape rather
than two objects touching. SwayFX cannot square a single window's corners —
`corner_radius` is global whatever criteria you give it — so the strip does the
work: it climbs exactly the theme's corner radius over the window, which is the
height of the arc the compositor clipped away, squares its own top corners, and
fills those two clipped corners in the colour its own first row already carries.

Nothing of the window is covered. The only pixels added are the ones the
rounding removed, and those rows are kept out of the strip's input region, so
clicking there still reaches the window underneath. The radius comes from the
same theme value the compositor's own is generated from, so a theme switch moves
both together. And because the window itself is never modified, detaching,
moving to another window, going fullscreen or killing the daemon all restore its
corners by simply drawing nothing.

### Floating windows stay out of the band

An exclusive zone only instructs tiling. Sway clamps a floating drag against
nothing at all, and it re-fixes floating coordinates only when a workspace's
*origin* moves — which a bottom reservation never does, since it changes the
height. So every float already on screen when the band appeared sat on top of
it, permanently, with nothing that would ever move it back.

A float that settles inside the band is now moved the smallest distance that
clears it, never past the far side of its workspace, so a window too tall to fit
goes as far up as it can and stops. It waits for the rectangle to hold still
first: a drag emits no events, and correcting mid-drag would fight the pointer
at frame rate. Fullscreen views are meant to cover the band and are left alone,
as are the drop-downs, which park themselves.

### Repository, tabs and powerline

The place segment names the repository and how the checkout stands, for Fossil
as readily as git: a branch glyph, a dot for uncommitted work, a check when
there is nothing to report, arrows for what has not moved. Fossil is read
straight out of its own SQLite rather than forked, which is also where "behind"
comes from — and "ahead" appears only where a sync URL exists, so a repository
that has never synced is not accused of being behind hand.

Tabs come only from sources that are real: tmux's window list, and sway's own
tabbed and stacked containers. No Wayland protocol exposes another
application's tabs, so a browser's are not invented, and the sway container
answer is usually the more useful one anyway.

As the strip narrows it gives up whole ideas in a fixed order rather than
letting the text be cut: other tabs' names, then the tab count, then the
repository's standing, then the branch, then the directory. Where you are and
what you are in never go.

Powerline separators are a setting, default off — `"powerline": true`, or the
checkbox in the settings editor at Shift+right-click. They are only markup, so
they cost one layout parse and nothing else, but they read well only while a
theme keeps its surfaces apart, which is why they are opt-in.

Everything that costs a process runs on a worker thread while the caption keeps
the last answer, and all of it sheds on the `window-context-detail` rung, asked
four times less often off mains. One caption update costs 0.29 ms warm.

## Notification cards

A notification is a card and nothing around it paints. That is the whole design,
and it is also the fix for the grey rectangle that used to appear around a
hovered notification: swaync gives the row the full width of the output, so the
old `.notification-row:hover` background drew a slab across the desktop with
nothing to justify it. Rows, backgrounds and group containers are transparent
now; the card owns the ground, the 14px corner, the shadow and a three-pixel
urgency rail down its left edge.

The rail is the only thing urgency changes. Low takes the border colour and
drops the bold summary, normal takes the accent, critical takes red and warms
the card ground a shade — one change, not a second shouting colour. Hovering
lifts the card by a step of ground and a deeper shadow over 120ms, and the close
button is invisible until the pointer is on the card, then red only under the
pointer itself.

Every other state is drawn too: action buttons as pills that press to accent,
the inline reply entry with an accent caret and focus border, grouped messages
under a quiet header whose collapse and close-all controls stay ghosted until
hover, the progress bar as accent on a border-coloured trough, the app icon in
accent, rounded images, and an empty history that says so in the border colour
rather than showing a blank box.

Every colour in the stylesheet is a palette role — the thirteen the theme
declares, plus the three the renderer special-cases. That is deliberate: the
theme renderer maps declared values to the active theme's colours and snaps
anything off-palette to whichever role sits nearest, so a sheet full of
hand-picked shades themes approximately. This one themes exactly. Off:
`~/.config/swaync/style.css` is a link into the checkout; delete it and swaync
falls back to its own default styling.

## Windows

**Caption strip.** Window titles live in `oldbook-decoration`, a translucent
gradient strip at the workspace's bottom edge (saved: bottom, opacity 0.67,
radius 7) that attaches to a focused floating window and follows it. Since
2026-09-08 it uses the theme's design face, Inter Medium a point above the
terminal size, left-aligned, with letter-spaced state text and a 28-pixel
minimum height. Left click opens the window picker, middle click toggles
floating, Shift+right-click opens `oldbook-decoration-settings`, `Super+Ctrl+B`
returns it to the bottom. Tweak `~/.config/oldbook/decoration.json` through the
editor. Landing in its band, the strip strikes the water; that is its own
entry, [below](#the-strip-strikes-the-water). Evidence:
[decoration-context](verification/decoration-context/bottom-strip.png),
[decoration-framerate](verification/decoration-framerate/README.md),
[ghost-observatory](verification/ghost-observatory/production-floating.png).

**Window carousel.** `Super+Tab`, `Alt+Tab`, the Mission Control keycap or a
four-finger swipe down open an angled carousel of every window across
workspaces in true recent order, with aspect-correct still captures taken once
per opening without visiting them. Hold to browse, Shift reverses, release
selects, Escape returns home; quick taps alternate the last two windows.
Evidence: [carousel-quality](verification/carousel-quality/README.md),
[window-navigation](verification/window-navigation/README.md).

**Expo and show desktop.** `Super+E` or three fingers up opens the Fuzzel
workspace and window picker; four fingers up clears the desktop and down
restores it (or opens the carousel when nothing is hidden). Evidence:
[gestures](verification/gestures/expo.png), [show-desktop](verification/show-desktop/midflight.png).

**Launchpad and Mission Control.** The engraved Apple keys open two GTK 4
layer-shell overlays written for this desktop, both drawn over the current
painting blurred through the lock scene's cache, both singletons that hold the
keyboard only while mapped. Launchpad (F4) is a paged grid of every application
with the Oldbook-Gruvbox icons, filtering from the first keystroke with a
ranking that prefers contiguous and word-start matches, page dots when it
overflows, Enter or a click launching through the entry's Exec with field codes
stripped. Mission Control (F3) is a grid of workspace cards carrying the
carousel's own window stills, the focused workspace outlined in amber, with
click, arrow, number-key and drag-to-move handling and a card that creates the
next workspace. A stalled frame clock is caught by a 420 ms watchdog rather
than leaving an invisible surface holding a grab, and neither opens at all
behind the session lock. Files:
`desktop/.local/lib/oldbook/{launchpad,mission_control,grid_overlay,grid_layout,app_index}.py`;
commands `oldbook-launchpad` and `oldbook-mission-control` take `toggle`,
`show` and `close`. Tweak the density in `grid_layout.py` (`ICON_CELL`, the
margin fractions) and the fade in `grid_overlay.py` (`REVEAL_MS`,
`SCALE_FROM`). Off: restore `desktop/.config/sway/local.d/apple-overview.conf`
from Fossil, which returns the carousel to F3 and the Fuzzel menu to F4; the
carousel keeps `Super+Tab` and `Alt+Tab` either way. Evidence:
[verification/launchpad-mission-control/](verification/launchpad-mission-control/README.md);
the session was locked for the whole live window, so neither has been seen on
the panel.

![Mission Control, rendered headlessly](verification/launchpad-mission-control/mission-control.png)

![Launchpad filtering on a typed query](verification/launchpad-mission-control/launchpad-search.png)

**Sizing and raising.** `Super+=` and `Super+-` grow or shrink from the centre,
`Super+Shift+Space` floats at 90 percent with breathing room, `Super+C` centres
and raises, and a floating window raises itself after the pointer rests on it
for a second. Evidence: [near-full-resize](verification/near-full-resize/near-full.png),
[center-window](verification/center-window/centered-raised.png),
[hover-raise](verification/hover-raise/README.md).

**Drop-downs and Strata.** Super+backtick summons a persistent Ghostty
console and `Super+~` a btop monitor in Foot, docked below the bar at 94
percent width on the current workspace; `Super+0` is workspace 10, Strata,
where the local Fossil review browser lives. Evidence:
[ghostty-dropdown](verification/ghostty-dropdown/live.png),
[console-monitor-foot](verification/console-monitor-foot/monitor.png),
[strata](verification/strata/desktop.png).

### The strip strikes the water

When the caption strip lands in its band -- flying home from a floating
window, or crossing to the other edge on `Super+Ctrl+B` or
`oldbook-decoration toggle` -- a train of rings leaves its own outline and
crosses the lower third of the screen in under a second. What bends is a
photograph of the screen taken at the landing, refracted in a fragment shader
rather than drawn over, so text and windows warp and settle as if under water;
nothing is drawn where the water is still, so the live desktop shows through
everywhere the wave is not. A strip the width of the screen sends a straight
front up the band with arcs only at its ends. The first version (2026-09-09)
lightened the whole band and started its ring in the middle of the band rather
than at the strip; both were shader defects, fixed on 2026-09-13 and taken
apart in [ripple-water](verification/ripple-water/README.md).

Tweak: the `ripple` object in `~/.config/oldbook/decoration.json` --
`source` (`bar`, the strip's outline, or `point`, a stone dropped at the middle
of its edge), `duration` in seconds, `reach` (how far across the band the front
gets by the end), `spacing` and `strength` in logical pixels (between crests,
and at the deepest bend), `shade` (how much a crest catches the light). The
limits are `LIMITS` in `desktop/.local/lib/oldbook/ripple.py`, a wrong value is
reported by the settings editor rather than drawn, and a change is heard by
the next landing rather than the next daemon. Preview a candidate without
striking the desktop: `python3 verification/ripple-water/render.py . '{"strength": 20}'`.
Off: `"ripple": {"enabled": false}`; it also stays quiet with desktop
animations off, and it sheds at battery-low, since it sits on the power ladder
as `landing-ripple` beside the other small motions. The surface is exempted from SwayFX's corner radius, shadow and
blur (`layer_effects "oldbook-ripple"` in `swayfx/effects.conf`). The band is
photographed on the strip's final approach, a few pixels before it settles,
so the wave begins on the landing frame itself; a picture that is not in hand
within two frames of the landing is dropped rather than shown late. Evidence:
[ripple-water](verification/ripple-water/README.md) (offline render, numpy,
not a compositor); the live strike since the rewrite awaits a look.

## Input and Apple keys

**Gestures.** Three or four fingers left and right change workspace, up and
down drive Expo or show-desktop, a four-finger pinch opens the launcher; two
fingers stay with the application. `desktop/.config/sway/gestures.conf`; the
[gesture guide](desktop/GESTURES.md) has the table.

**Engraved keys.** F3 opens Mission Control, F4 opens Launchpad and leaves an
overview first, F5 and F6 move the keyboard light, all without Fn; Fn keeps the
function keys. This supersedes F3 meaning the window carousel and F4 the Fuzzel
menu, both of which keep their own bindings. Caps Lock is Escape (Shift
included). Evidence: [apple-overview](verification/apple-overview/private-key-fixture.png),
[launchpad-mission-control](verification/launchpad-mission-control/README.md).

**Hold to Help.** Hold either Super alone for half a second and a scrollable
overlay lists the focused application's shortcuts, the active Sway mode and
the tmux and system controls, without taking focus; release or press a key to
dismiss. It is the standalone [Hold to Help](../projects/hold-to-help/README.md)
package, themed from the Qt palette. Tweak `desktop/.config/hold-to-help/config.toml`.
Evidence: [superhold-guide-dev1](verification/superhold-guide-dev1/guide-dark.png).

**Keyboard glow.** One whole-keyboard Apple SMC light, one worker, and a
family of modes that persist across logins (`desktop/.local/bin/oldbook-keyboard-backlight`,
bindings in `desktop/.config/sway/local.d/keyboard-backlight.conf`, all of them
also in the command deck's Keyboard glow menu):

- `F5` / `F6` step the level, down to fully off, even while locked.
- `Shift+F6` breathes on a six-second cycle; `Shift+F5` returns to steady.
- `Ctrl+F6` brightens on each keypress and decays; `Ctrl+F5` starts bright and
  darkens as you type; the `Ctrl+Shift` variants react only above about 22
  words per minute.
- `Alt+F6`, **ambient**, follows the room through the SMC light sensor: keys
  at the saved peak in the dark, off in daylight, a smooth log-scale curve in
  between, retargeting only when the smoothed reading moves and fading over
  1.2 s so nothing jumps. The same sensor is the subject of an upstream pull
  request adding an `applesmc` backend to wluma (details in the
  [ambient spec](../docs/superpowers/specs/2026-09-08-ambient-glow.md)).
- `Alt+Shift+F6`, **breathe on air**: the breath starts shallow and slow at
  about seven seconds a cycle, every keystroke adds a sip of air that deepens
  and quickens it towards three, and idle lungs leak back over about twenty
  seconds. Continuous phase and half-second volume smoothing keep the light
  from ever jumping. While it runs the painting swells and the caption glows
  with it (see [the desktop breath](#gallery)).
- The idle stage's **last breath** (below) is an overlay, never a saved level.

Evidence: [keyboard-breathing](verification/keyboard-breathing/README.md),
[keyboard-ambient](verification/keyboard-ambient/README.md) with live sensor
readings. A 60 Hz target is not a measured optical refresh.

**Ambient screen.** The panel can follow the same sensor in the opposite
direction: a dark room settles it at a fifteen percent floor, never off, and a
sunlit desk takes it to full, on a log-scale curve with a 0.15-unit hysteresis
band and a 1.2-second cosine ease. It never argues. Set the brightness by hand
and your level stands, with the distance from the curve kept as a lasting
offset that shifts the ceiling too, so a habit of dimming gives a dimmer screen
in every room. Nothing is written while the pre-lock dim holds the display or
while the session is locked, and automatic changes are silent: only `on` and
`off` show the pill. It is opt-in and off by default:
`oldbook-ambient-display on|off|status`, or **Ambient screen** in the command
deck. Curve in `desktop/.local/lib/oldbook/ambient_light.py`, learned offset in
`~/.config/oldbook/ambient-display.json`. Off: `oldbook-ambient-display off`;
delete the preference file to forget the offset. Evidence: thirty tests against
a fake sensor and backlight, and a live run where the real sensor read 10 in a
dim room for a target of thirty-six percent and both pause rules refused to
write. No fade has been seen on the panel.

**Clipboard.** `Super+Shift+V` opens the history picker; `Super+Ctrl+Shift+V`
deletes an entry. Evidence: [clipboard](verification/clipboard/history-menu.png).

## Feedback

**The pill.** Volume, mute, microphone, display brightness and keyboard light
changes show a 300×66 capsule at the bottom centre of the focused output: a
Nerd Font glyph, label, amber bar and percentage from the active palette, on
the overlay layer with no reserved space, no focus and pointer pass-through,
held 1.1 s and faded on the frame clock. `oldbook-osd` is the daemon;
`oldbook-osd show --kind volume --value 40` drives it; `oldbook-osd preview
--output pill.png` renders it without a display. Off: remove its block from
`oldbook-session`; the key helpers then fall silent rather than fail. Evidence:
[verification/osd/](verification/osd/README.md) (headless); the live daemon
mapped the pill on the panel while the display was off, so the physical blur,
shadow and fade await a look.

![The feedback pill](verification/osd/pill-shown.png)

**Now transmitting.** When the track changes, a card slides into the bottom
right of the focused output for four seconds: the album art cover-cropped to a
rounded square, an amber NOW TRANSMITTING eyebrow, the title in cream, the
artist and album beneath, in the notification centre's card style. No readable
art falls back to a music glyph. The daemon watches `PropertiesChanged` on
`org.mpris.MediaPlayer2.Player`, so any player announces itself without
polling, and the whole suppression rule sits away from the bus and the display:
a card appears only for a genuinely new track, on a playing player, with the
desktop unlocked and the notification centre closed. A suppressed announcement
still counts as seen, so nothing ambushes you at unlock, and locking mid-card
dismisses it from wherever it has slid to. `oldbook-osd card --title … --artist
… --art …` drives it by hand; `oldbook-osd preview-card --output card.png`
renders it without a display. Off: **Now transmitting** in the command deck, or
`{"card": false}` in `~/.config/oldbook/osd.json`. Evidence:
[verification/now-transmitting/](verification/now-transmitting/README.md); the
lock suppression was confirmed live, the card itself has not been seen.

![The now-transmitting card](verification/now-transmitting/card-shown.png)

**Shutter.** After grim writes a screenshot the output flashes a cream wash for
120 ms, `pw-play` clicks the freedesktop camera shutter, and Satty opens with a
Gruvbox profile (Enter copies and closes, Ctrl+S overwrites; Swappy remains the
fallback). Tweak `desktop/.local/bin/oldbook-screenshot` and
`desktop/.config/satty/config.toml`. Off: uninstall `sound-theme-freedesktop`
to silence it, `satty` to return to Swappy. Evidence: [osd/flash.png](verification/osd/flash.png),
[osd/satty.png](verification/osd/satty.png); the sound has not been heard live.

## Bed mode, also for the cat

While the session is locked, the desktop can notice that a cat is lying on the
keyboard and be nice to her: it runs the machine deliberately warm and holds the
fans down, so she has somewhere heated to sit. `oldbook-cat show` reports what it
currently sees; `oldbook-cat stop` disables it and restores the fans directly.

Detection is deliberately reluctant. Five keys held together for two seconds is
necessary and never sufficient — one corroborating signal is also required: a
connected patch of neighbouring keys, no clean keystroke anywhere in five
seconds, a trackpad contact area above 45 percent of that device's own maximum,
or three keys in autorepeat. Three clean press-and-release events within ten
seconds veto the whole judgement however much else agrees. And it never
publishes a cat at all unless the lock's own readiness record names a live
process, because an unlocked session is a person and a person is never warmed.

The safety is the feature. Three sensor families are all required — package and
core temperature, the battery, the palm rest — and a sensor that cannot be read
is a stop rather than a zero. The fans are always handed back **before** load is
cut, by construction and by test. A closed lid gets a stricter set of ceilings,
and an unknown lid is treated as closed. It runs on mains only, sits for at most
three hours, rests ten minutes after a stop, and latches off for the session
after a second one.

The fan hold is the dangerous part, so it is released four independent ways: the
pipe closing when the daemon dies however it dies, a heartbeat measured on
`CLOCK_BOOTTIME` so a suspend counts against it, the holder's own reading of the
temperature, and a restorer forked before any write into its own session so that
killing the holder's whole process group still restores. Heat and hold share a
fate — the load is `PR_SET_PDEATHSIG` children on the same pipe — so the worst
reachable state is quiet fans on an idle machine.

If a cat was seen within the last thirty seconds and the lid closes, an elogind
`handle-lid-switch` inhibitor keeps the machine awake under the stricter
ceilings, released the instant that window lapses.

## Catbed mode

`Super+Shift+Escape` holds every key and every pointer event away from the
session while the desktop stays completely visible and completely running. It
exists so the machine can be watched while a cat sits on the keyboard. It is a
cat guard and not a lock, it says so on screen, and `Super+Escape` is untouched.

Leaving is a **hold, not a chord**: the same keys held for one second with *no
other key down*. That last rule is the actual defence — a settled cat holds a
handful of neighbouring keys and never exactly one, so the chord alone would be
reachable by accident and the clean-hold requirement is not. And leaving is
the user's alone; nothing ends catbed mode for him. The cat getting up does
not: the cat watcher only reads whether the guard is up. The screen lock takes
the keyboard and hands it back at the password while the guard waits, holding
the pointer and the mode. A Sway reload resets the binding mode and the guard
re-enters it. And the `watch` mode carries no exit chord at all, because a
settled cat holds five keys at once and any chord Sway answers is one she can
produce. While it is up the guard holds what the lock holds — the power,
suspend and hibernate keys and SysRq — from `~/.config/oldbook/catbed.json`.

There is no input-inhibitor protocol on this compositor, which is why it is
built the way it is: a transparent overlay surface on every output takes the
pointer, exclusive keyboard interactivity takes the keys, and a Sway `watch`
mode that binds nothing takes Sway's own bindings — without that last part a
cat lying across `$mod+Shift+q` still reaches it. The mode block carries one
`set` line and nothing else, because Sway only creates a mode from a line
inside its block; an empty block is no mode, and no mode means no catbed mode.

Being unable to get out is the failure that matters, so there are three ways
back: the mode is restored before the surfaces come down, a watchdog pipe
restores it if the guard is killed outright, and `oldbook-watch stop` from a
terminal or over SSH restores it unconditionally. If the compositor refuses to
hand over input, nothing changes and a critical notification says plainly that
input was **not** parked.

## Idle and lock

**Stages.** swayidle runs three: at 270 s the display eases to 20 percent
over 1.5 s and the keyboard takes one last breath (rising to its peak, then
falling to dark over 4.5 s); at 300 s the session locks; at 600 s the display
switches off. Activity restores the display level and keyboard exactly.
Helpers: `oldbook-idle dim|undim`, `oldbook-keyboard-backlight last-breath`.
Off: remove the `timeout 270` pair from the swayidle line in `oldbook-session`.
Evidence: tests in `tests/test_idle_dim.py` and live readings in
[keyboard-ambient](verification/keyboard-ambient/README.md).

**Lock screen.** `Super+Escape` dissolves the desktop over 0.4 s into the
current painting blurred, darkened and vignetted, with an Inter Display clock
and date on a ring that stays invisible until you type, when the amber ring
and key highlights appear; a caption card in the lower corner carries the
painting's title and first sentence, the hour's Scripture reference and its
opening words, and the Ghost Planet mark. No grace period, empty passwords
ignored. The locker is `swaylock-effects` rebuilt as `oldbook-swaylock-effects`
beside stock swaylock, with the readiness handshake backported so
`oldbook-lock` keeps its serialised, identity-checked acquisition and falls
back to swaylockd and stock swaylock inside the same call. Scenes are cached
under `~/.cache/oldbook/lock/`; `oldbook-lock prerender` warms the cache. Off:
`OLDBOOK_LOCK_BACKEND=stock`, or `doas apk del oldbook-swaylock-effects`.
Evidence: [verification/lock-screen/](verification/lock-screen/README.md)
(headless idle, typing, cleared, Caps Lock, relock); the live session has not
yet been locked with the new design, so your first `Super+Escape` is the check.

![Lock screen, idle, rendered headlessly](verification/lock-screen/idle.png)

## Power deck

`Super+Shift+E` or a left click on the battery opens wlogout over the blurred
desktop: five charcoal tiles with Nerd Font glyphs (lock, suspend, log out,
reboot, shut down; keys `l` `u` `e` `r` `s`, Escape closes) that turn amber on
hover or focus. Suspend locks first; log out, reboot and shut down ask on a
Gruvbox swaynag bar. `oldbook-power` is the script, `desktop/.config/wlogout/`
the layout and style, `bin/build-wlogout-icons` rasterises the glyphs. Off:
uninstall wlogout or delete the config directory and the fuzzel session menu
returns automatically. Evidence: [verification/power-deck/](verification/power-deck/README.md)
(headless); the binding, the battery click and a physical tile press await a
look.

![Power deck rendered headlessly](verification/power-deck/power-deck.png)

## What the strip says

    10 Strata · ghostty › nvim · ~/.files   alpine-oldbook  ·  2/3 edit, logs


The caption used to repeat the window title, which for a terminal is usually
the directory or nothing at all. It now answers three questions at a glance:
where you are, what is running, and where it is running.

    10 Strata · foot › tmux › claude · ~

The workspace identity comes first, without the live window hint the strip is
already showing you. For a terminal the process chain follows, read out of
/proc the way you would say it aloud, so Foot and Ghostty are told apart on
sight and tmux never hides what is inside it — the pane's real program comes
from tmux itself, because that program is a child of the tmux server and no
walk from the window's own process would ever reach it. Last is the directory
and, in a checkout, the branch: `~/.files (alpine-oldbook)`, from Git's HEAD
file or from Fossil.

Only terminals are walked. Every other window keeps the title it chose, since
descending a browser lands in a content process that is neither the program on
screen nor anywhere you have been, and answers `cwd` with somewhere inside
/proc. The full window title stays in the tooltip on hover, so nothing that was
readable before stopped being reachable. On battery-low the tmux and Fossil
questions stop being asked and the line falls back to the emulator and the
directory; the chain itself is plain file reads and never sheds.

When the process chain lands on a Claude Code or Codex session, the strip adds
one more segment: `foot › tmux › claude !`, the exclamation drawn from the same
stepped alphabet `oldbook-rebuild`'s waiting language uses. It means that
session's own notifier has a live, unexpired record saying it is waiting on a
permission or your attention — read from `$XDG_RUNTIME_DIR/oldbook/claude
-events` or `codex-events`, matched to this window by tty or tmux pane, the
same routing `oldbook-notification-led` already trusts. Codex additionally
names its own run state in its title, which shows as a single still spinner
frame when nothing is waiting; Claude names no equivalent state of its own, so
a Claude window that is not waiting carries no glyph rather than a guessed
one. Nothing here spins on a clock — the glyph is redrawn only when a real
record appears or disappears, the same rule the strip's own loading language
keeps everywhere else. Switch it off with `agent_status: false` in
`~/.config/oldbook/decoration.json`.

## Power posture

The desktop asks one question about the cord and every effect gets the same
answer. `oldbook-power-mode show` prints it: the posture (mains, battery,
battery-low, battery-critical), the charge, any hand-set override, and exactly
what is being shed right now. `oldbook-power-mode ladder` prints the whole
table — what still runs at each rung — and `oldbook-power-mode allows <effect>`
answers by exit status, so a shell helper can ask in one line.

The rungs use the thresholds the battery cue already uses, 25 and 10 percent,
so the amber Waybar battery and the desktop going quiet happen together rather
than at two different numbers. Unplugged, the shaders, the gallery drift and
the generator stop first; at 25 percent the blur, cava, the rotation and the
keyboard breath follow; at 10 percent only the reading cards, the corners, the
cues and the letterpress remain. An effect nobody registered keeps running,
which is the deliberate default: the ladder is a list of things that shed, not
a permit list.

Waking is event-driven. udev already announces a plug or an unplug, so the
service sleeps until the kernel speaks, with a one-minute backstop for the
charge drifting down inside a rung. Hold a posture by hand with
`oldbook-power-mode override battery-low` — it can only make the desktop
quieter than the hardware asks, never louder — and release it with `override
auto`. Hooks in `~/.config/oldbook/power.d/` run on every change with the new
posture as their argument, which is how an effect stops rather than merely
declining to start next time. Off: stop the service and every helper falls back
to reading the supplies directly, so nothing breaks, it simply stops reacting.

## Terminals

**Ghostty and Foot.** Both run at 78 percent opacity with the Gruvbox
sixteen-colour palette, four-pixel padding (three in the derived profile copy)
and an amber cursor; Foot recolours live windows without closing them
(`oldbook-refresh-terminal-theme`). Ghostty additionally runs two shaders:
`warm-bloom.glsl` lifts bright amber and cream pixels through an eight-tap
ring, and `cursor-smear.glsl` draws a parallelogram from the previous cursor
cell to the current one, tinted with the cursor colour, retreating over
150 ms; both animate only while focused. Files under
`desktop/.config/ghostty/shaders/`, enabled by `custom-shader` lines in both
config copies. Off: delete those lines. Evidence:
[terminal-chrome](verification/terminal-chrome/ghostty-cursor-smear-slowed.png)
(headless, slowed shader); both shaders loaded live on the GPU.

**Splash.** The first interactive shell in a new terminal (never in tmux) runs
`oldbook-splash`: fastfetch beside the Space Ghost painting, drawn through
Ghostty's kitty file medium or a libsixel stream in Foot (a text ghost
elsewhere), with Gruvbox keys, the Fossil branch, the painting on screen, the
hour's Scripture reference and the track on air. `OLDBOOK_SPLASH_LOGO=none`
silences it; `oldbook-splash` shows it again. Config
`desktop/.config/fastfetch/config.jsonc` and the guard in both `.zshrc` copies.
Evidence: [splash-ghostty-kitty.png](verification/terminal-chrome/splash-ghostty-kitty.png),
[splash-foot-sixel.png](verification/terminal-chrome/splash-foot-sixel.png),
both confirmed live.

![The splash in Ghostty](verification/terminal-chrome/splash-ghostty-kitty.png)

**Prompt, shell, tmux.** Starship shows user, host, directory, the Fossil
branch with a glyph, git status and slow-command timing in Gruvbox colours;
zsh colours `eza` and completion listings from the same palette with no
framework; tmux keeps its status at the top, amber for the session name and
the active pane border, charcoal tabs. Files: `desktop/.config/starship.toml`,
`desktop/.zshrc`, `desktop/.tmux.conf`.

**Neovim.** A hand-rolled statusline with a mode-coloured block, file and
modified dot, the Fossil or git branch refreshed asynchronously, diagnostics,
filetype and position, plus a winbar, thin `▏` splits and a blank end of
buffer; no plugin manager. Both `init.lua` copies. Evidence:
[neovim-chrome-foot.png](verification/terminal-chrome/neovim-chrome-foot.png)
(headless only).

**btop and cava.** btop uses the `spaceghost` theme with rounded boxes and
braille graphs on a transparent background; the standalone cava draws a
green-to-orange gradient. Files under `desktop/.config/btop/` and
`desktop/.config/cava/config`.

## Launchers and menus

**Fuzzel.** Every desktop menu is Fuzzel with icons, 18-pixel corners, a
48-column width and colours passed in from the active palette by
`oldbook-fuzzel`; `desktop/.config/fuzzel/fuzzel.ini` holds the geometry.
Evidence: [launcher-themes](verification/launcher-themes/gruvbox.png).

**Command deck.** `Super+Shift+D` or the Ghost badge: applications, Expo,
window switch, decoration placement, the gallery, YouTube and the video
background, Ghostty, the reactor, transmissions, the sound studio, the
keyboard glow menu, **Night light**, the firewall, notifications, the Fossil
checkout, the session menu and help. Script: `desktop/.local/bin/oldbook-control`.

**YouTube.** A launcher entry searches and plays through yt-dlp and mpv as a
floating picture-in-picture or pinned behind the desktop. Evidence:
[youtube](verification/youtube/pip-mode.png).

**Agent picker.** `Super+N`: the best Codex and the best Claude lead the
list, each line naming its model, its effort and that it trusts everything —
`✦  New Codex · gpt-6-astra · ultra · trusts all`. Enter, then Enter on the
directory the list opened on because you used it last, and the prompt is ready
to type into, the tool's own trust screen already answered on its behalf. Two
*choose model and effort…* lines ask from the lists in
`desktop/.config/oldbook/agents.json`, first entry preselected; `lead`, `quick`
and `remember_workdir` there say which presets lead, which Super+Ctrl+N starts
and whether the directory memory is on, and `"trust": false` on a preset
brings its trust screen back. Script: `desktop/.local/bin/oldbook-agents`.
Evidence: [agent-launcher](verification/agent-launcher/menu.json).

## Sun and moon

An explicit `~/.config/oldbook/location.json` (copy
`desktop/.config/oldbook/location.example.json`: name, latitude, longitude,
timezone) is the only source of location; nothing is inferred or fetched.
With it, `astro.py` computes sunrise, sunset, civil twilight and the moon's
phase offline from the NOAA equations and a low-precision lunar series,
verified against published times within minutes. The masthead shows the line,
`oldbook-sun-light run` execs wlsunset with the coordinates so the display
warms after sunset (`toggle` or the deck's Night light stops it, and a stop
survives reloads), and the gallery prefers nocturnes at night. `oldbook-astro
status` prints today's figures. Off: delete the location file. Evidence:
`tests/test_astro.py`, [verification/sun-and-moon/](verification/sun-and-moon/README.md);
the physical colour ramp has not been watched through an evening.

## Boot chain

**Theme switches reach the boot chain automatically.** `oldbook-theme use`
used to regenerate the console palette file and stop there, printing a
reminder to run `bin/build-grub-theme` and `doas bin/install-boot-console` by
hand afterward. It no longer stops: every switch renders the GRUB theme and
installs it for real, so gruvbox-dark is no longer the one theme whose GRUB
menu and boot console actually match what is selected everywhere else. A
theme does not count as complete while any boot-time surface still needs an
unenforced follow-up command. A failed render or install carries the tool's
own stderr rather than a generic label, and rolls itself back the same way a
manual run already did; nothing forces a bad `grub.cfg` through. **Next
boot:** verified live, not simulated — switched through catppuccin-mocha and
monochrome-test with this wiring active and read `desktop-color` back from the
installed `/boot/grub/themes/ghost-planet/theme.txt` on the real boot
partition, then switched back to gruvbox-dark and confirmed it matched again.

**Ghost Planet GRUB menu.** The boot menu shows for three seconds over a
graded, blurred crop of the current painting, with an amber selection bar, the
Ghost wordmark, a subtitle, a countdown and a help line. GRUB draws menus in
its own bitmap format and `grub-mkfont` is not packaged, so
`system/grub/grub_theme.py` writes PF2 directly from glyphs rendered with
Pango: a 32-pixel face for the title and entries and a 20-pixel one for the
chrome, 216 glyphs each, covering ASCII, Latin-1, light box drawing and the
ghost at U+F02A0 the desktop already brands itself with. The stock 16-pixel
font is about two millimetres of text on this panel. The background is 1280×800
and heavily blurred on purpose, since GRUB decodes it on the CPU before the
menu appears and blurred content upscales invisibly; the painting is graded
rather than pasted, warmed towards amber and held back where the text sits.
Entry titles are unchanged, because renaming them means changing
`GRUB_DISTRIBUTOR` and with it the identifiers `set default` selects. Rebuild
with `bin/build-grub-theme`, install with `doas bin/install-boot-console`. Off:
`--remove-theme`. **Next boot:** `grub-emu` is not packaged and nothing was
rebooted, so the picture in
[verification/grub-theme/](verification/grub-theme/README.md) is drawn from the
committed theme by our own renderer, not by GRUB. The first install failed and
rolled itself back over a whitespace-strict menu check, which is the safety net
working as designed.

![The GRUB menu, simulated from the committed theme](verification/grub-theme/menu-preview.png)

**Console palette and font.** The GRUB command line now carries the sixteen
Gruvbox console colours (`vt.default_red`, `vt.default_grn`, `vt.default_blu`),
a cream-on-charcoal default attribute (`vt.color=0x0F`) and the kernel's
built-in Terminus 16×32 (`fbcon=font:TER16x32`), so the passphrase prompt,
kernel messages and the rescue gettys share the palette from the first frame.
The gettys on tty2–tty6 print a Ghost Planet masthead from `/etc/issue`.
Sources under `system/boot/`, installer `bin/install-boot-console`
(idempotent, backs up to `/var/backups/alpine-rice/boot-console-<ns>/`,
regenerates `grub.cfg` into a temporary file and keeps it only after
`grub-script-check` and a structural proof that the stock entry is unchanged).
Off: `--rollback <backup dir>`. **Next boot:** nothing here has been seen yet;
the [system guide](system/README.md) has the commands.

**Ghost Planet initramfs.** A second, non-default GRUB entry boots
`/boot/initramfs-lts-ghost`, the stock mkinitfs init plus one guarded block
that prints a Gruvbox masthead before the LUKS prompt; `/boot/initramfs-lts`
and the default entry are untouched. Press an arrow during the one-second menu
to try it; `--remove-ghost` withdraws it; rerun the installer after a kernel
upgrade. **Next boot:** never booted. Design and adoption steps:
[luks-prompt spec](../docs/superpowers/specs/2026-09-08-luks-prompt.md).

## The theme reaches past the session

Picking a theme used to stop at the edge of the running session. The lock
already followed the palette and there is no login screen to follow it — greetd
autologins straight into Sway, deliberately, because the LUKS passphrase is the
real gate — so what a theme switch actually missed were the power deck and
everything that happens before the compositor exists.

The power deck joins the file set: wlogout's stylesheet now lives in the
reference profile, so it is recoloured like any other surface, for generated
themes as much as authored ones. One shade had to move. Its pressed-button
`#d79921` belongs to no palette role, and the renderer snaps an off-palette
value to whichever role sits nearest — which for that shade is *green*. It now
takes the orange role deliberately rather than landing on green by accident.

`console-palette.json` is generated rather than authored. Its sixteen VT
colours come from the selected theme's own Foot palette, the same file
Ghostty's colours derive from, so the terminals, the console, the initramfs
LUKS prompt, the rescue gettys and the GRUB menu cannot drift apart.
`build-grub-theme` takes the three extra shades the ANSI sixteen do not carry
from whichever theme the palette document names, and `install-boot-console`
refuses outright to publish a palette the selection has already moved past.

Because those files live under `/etc` and `/boot`, switching theme cannot
finish the job on its own. `oldbook-theme use` regenerates the versioned
palette and then tells you the two commands that publish it:

```sh
alpine/bin/build-grub-theme                    # repaint the menu, ~6s, no compiler
doas alpine/bin/install-boot-console           # publish to /etc and /boot
```

The confirmation bars follow too. `oldbook-power` raises a swaynag bar before
logging out, rebooting or shutting down — the last screen of a session, and the
one most likely to be left stock. It was already Gruvbox, but hardcoded outside
the theme file set, so it alone kept those colours whatever theme was chosen.
Adding it to the reference profile was the whole fix; its values carry no
leading `#` and the renderer maps them anyway.

Gruvbox Dark is byte-for-byte what it always was — the generated document
equals the committed one exactly — which is the proof this generalised the
boot chain rather than restyling it.

## Theming system

**Descriptor and profiles.** `themes/gruvbox-dark.json` is the source of the
palette, the image style for new paintings and the design fields (Inter,
radius 22, spacing 6, opacity 0.78, bar on top, widgets on the right, launcher
width 48). `oldbook-theme list|use|sync` switches complete themes: the
authored profile under `themes/profiles/gruvbox-dark/` is linked into HOME,
missing application files are rendered from the shared desktop copies by
`wallpapers/desktop_theme.py`, and a matching painting is selected. Every
theme must be complete (`THEME-COMPLETE`); palette-only themes are rejected.
The [theme guide](themes/README.md) explains live recolouring and the
preserved profiles. Evidence: [theme-review](verification/theme-review/gruvbox-dark.png),
[complete-themes](verification/complete-themes/astronomers-vigil.png) (an
archived generated theme, kept as proof of the pipeline).

**The theme workshop.** `Super+Shift+D`, **Theme**, **New theme · describe it
here**, a few words, Enter: the description is typed into the deck's own
prompt and `oldbook-theme create` designs a complete theme from it as text --
Codex, then Claude, then the Alienware's own model, whichever answers first --
and applies it the moment it is saved. Every profile file, the pointer shapes
and the power deck's tiles are rendered from the descriptor; the nearest
installed Simp1e pointer set is chosen for its palette and a folder icon set
of its own is built into its profile, because a model cannot know what is
installed here and the run that was asked stopped on "Invalid theme design
cursors". **New theme · surprise me** needs no description. No painting is
asked for on the way (see *When the painter is asked* under Gallery), so a
theme arrives whether or not anybody's image credit does. The visible desktop
switches at once; GRUB, the console and the passphrase prompt are published in
the background by `oldbook-theme boot-chain` and announce a failure with the
installer's own words. Off: choose a shipped theme from the same menu; the
workshop rows do nothing until picked. Evidence:
[verification/theme-workshop/](verification/theme-workshop/README.md), where
the Alienware designed *Scriptorium Shadows* into a scratch checkout in nine
minutes and every profile file rendered from it; the deck prompt itself and a
real switch have not been watched under a hand.

**The accent follows the painting.** The theme's colours stay where they are,
but its accent moves with the artwork. Each new painting is reduced to a
weighted hue signature in OKLab, every pixel counting by chroma times lightness
so the charcoal ground and the chiaroscuro shadows do not vote; every histogram
bin then goes to whichever of the theme's own accent candidates sits nearest on
the hue circle, and the largest share wins along with a companion. Nothing is
sampled from the canvas, red stays reserved for urgency, a neutral painting
keeps the declared amber, and the Ghost badge never changes. The election lands
in `~/.local/state/oldbook/palette-override.json`, which `read_palette` honours
only for the theme that produced it and only for colours that theme declares,
so the pill, launcher, Expo, lock screen, caption strip and scripture bar
retint on their next render; the bar picks it up through a small
`waybar-accent.css` imported last so it beats the hardcoded amber. Library
`desktop/.local/lib/oldbook/painting_palette.py`, helper `oldbook-palette
apply|show|clear`. Off: `oldbook-palette clear`, or `"reactive_accent": false`
in `themes/gruvbox-dark.json`. Sweeping the gallery elects yellow twenty-three
times, orange twice and blue once, which is honest for a collection whose image
direction asks for warm amber. Evidence:
[verification/reactive-palette/](verification/reactive-palette/README.md),
where the badge rendered `#ecb32e` under the firelit procession and `#7d9d90`
under the Antarctic station; the live panel has not been photographed
retinting.

![The bar under a warm painting and a cool one](verification/reactive-palette/bar-cool.png)

**Icons, cursor, toolkits.** `Oldbook-Gruvbox` is Papirus with warm gold
folders rebuilt offline by `bin/build-icon-theme`; GTK 3 and 4 use
`adw-gtk3-dark` with a semantic Gruvbox palette in `gtk.css`, Qt 6 a matching
`qt6ct` palette also installed system-wide, and LXQt a named `Gruvbox-Dark`
palette for Hold to Help. Files under `desktop/.config/gtk-3.0/`, `gtk-4.0/`,
`qt6ct/` and `desktop/.local/share/`.

**Animated cursors.** The waiting pointer is an amber ring that turns once
every 672 ms and breathes as it goes, over a dim charcoal track with a dark
halo so it reads over a bright painting; the busy pointer keeps a hairline
arrow with the ring at its lower right, on Simp1e's own hotspots so nothing
jumps. Twenty-four frames at 28 ms across four nominal sizes (24, 32, 48, 72)
so the panel's 24-at-scale-2 request lands on real pixels. `bin/build-cursor-theme`
draws them with cairo and writes the Xcursor container itself, since xcursorgen
is not packaged; every shape not redrawn is inherited from
`simp1e-cursors-gruvbox-dark`. The theme is `Oldbook-Ghost`, named in
`sway/theme.conf`, both GTK `settings.ini` files, their profile copies and
`oldbook-sway`. Off: name `simp1e-cursors-gruvbox-dark` again in those places
and reload. Evidence: [verification/animated-cursors/](verification/animated-cursors/README.md),
a contact sheet of the frames; a headless session draws no pointer, so nobody
has watched it spin.

![The wait cursor's frames](verification/animated-cursors/frames.png)

## How the terminal waits

Every long helper used to invent its own waiting noise or make none at all:
`package-archive` counted every fiftieth APK, `remote-build` printed one line
and then went silent for the length of a compile, `check-features --run` let
seventeen unittest processes talk over each other. There is one vocabulary now,
with three words and no more.

A **segmented bar** (`▰▱`) for work with a known total, settling exactly on it.
A **stepped spinner** (`▖▘▝▗`) for work with no total, which advances only when
the caller reports a step — a spinner waiting on a silent process shows a still
glyph, so nothing here can become ambient motion. And a **step list** for
multi-phase work, where each finished phase keeps its line and takes a result
mark from the `+ = ! x` alphabet `oldbook-rebuild` already uses, so the desktop
has one answer to "did it work".

There is no timer, thread or frame clock anywhere in it. A repaint happens
because the caller reported work, is capped at ten a second, is skipped when
the line has not changed, and stops in the same instant the work does. Colour
is the active theme's roles. A pipe, a set `NO_COLOR`, a dumb or Linux-console
`TERM`, a stream that is not UTF-8, a battery, or `OLDBOOK_LOADING=plain` all
fall back to the same plain stepped lines with no escape codes and no redraw.
Progress goes to stderr wherever stdout is parsed, and the per-item lines those
callers already printed are byte-identical to what they were.

## Sound

The desktop is nearly quiet, and never load-bearing: a missing player, a
missing file, an unknown cue, a muted sink or the switch turned off are all
silence rather than failure.

**Ghost Planet cues.** Six sounds are synthesized offline by
`bin/build-sound-theme` into `desktop/.local/share/sounds/oldbook/`: the lock
engaging and opening, a battery crossing 25 or 10 percent, a deliberate gallery
change, a critical notification and a small interface tick. Sine and triangle
partials with soft attacks and exponential tails over filtered room tone, none
longer than 0.92 s, all normalised to −12 dBFS, nothing sampled. `oldbook-sound
<cue>` plays one through `pw-play` at a fixed low gain, detached;
`oldbook-sound list` names them. The hooks are one line each: `oldbook-lock`
after real readiness and after the locker exits, `oldbook-wallpaper` beside the
crossfade for deliberate changes only, SwayNC's own `scripts` block on
`urgency: Critical` so the AI attention stream stays silent, and
`oldbook-battery-cue` watching the thresholds Waybar only colours, edge
triggered and quiet while charging. Off: `oldbook-sound off`, or **Sound cues**
in the command deck. Evidence:
[verification/sound-theme/](verification/sound-theme/README.md); all six were
played once on the speakers during the build, but no cue has yet fired from its
own occasion.

**Everything else.** The camera shutter after a screenshot comes from
`sound-theme-freedesktop`; Pithos provides the music the bar, the cava meter,
the notification centre and the splash refer to. The power deck makes no sound.

## Verification ledger

| Item | Live on the panel | Headless render | Not yet seen |
| --- | --- | --- | --- |
| Agent picker lines, trust pre-acceptance | both tools' trust screens, and their absence once the record was written, in a private tmux server | the lines, printed | the Fuzzel menu itself under a hand |
| Theme workshop | | the Alienware designed a theme into a scratch checkout; the profile rendered complete; every switch step ran against stubs | the deck prompt, a real switch, the background boot publish |
| Ghost Observatory geometry | reload applied | yes | corners, shadows and frame rate by eye |
| Artwork badge thumbnail | yes | yes | |
| Signal meter | bar strip seen | yes | |
| Crossfade | one next/prev | yes | frame pacing, hotplug, fresh login |
| Picker thumbnails | yes | yes | |
| Sun and moon line | refitted | yes | eye check, a full night of nocturnes, the wlsunset ramp |
| Notification centre widgets | reloaded | yes | eye check |
| Feedback pill and flash | pill mapped while the display was off | yes | look, sound |
| Lock screen | | yes | the first live lock, Caps Lock text, dissolve pacing |
| Dim before lock, last breath | sysfs readings | | eye check of the ramp |
| Ambient glow | live sensor readings | | a covered sensor over minutes |
| Breathe on air | | | landing; check the mode name |
| Power deck | | yes | binding, battery click, tile press |
| Splash and shaders | yes | yes | Neovim chrome, drop-down console reflow |
| Boot console, LUKS prompt, banner entry | | | everything, until the next boot |
| Window and workspace animations | | yes, by colour | everything, until the next login |
| Launchpad and Mission Control | | yes | both overlays, the fade, hover and drag |
| Desktop breath | a synthetic record swelled the painting | yes, measured exactly | the real keyboard driving it |
| Idle gallery | a two-second run | yes | a real four-minute idle |
| Reactive accent | the helper ran and wrote the record | yes, two paintings | the bar retinting by eye |
| Now transmitting card | lock suppression confirmed | yes | the card itself |
| Workspace peek | | native X fixture | the popover on the panel |
| Animated cursors | theme selected, session reloaded | frame contact sheet | the ring turning |
| Sound cues | all six played once | waveforms | any cue firing from its own occasion |
| GRUB menu | | simulation, not GRUB | everything, until the next boot |
| Ambient screen | sensor read, both pause rules refused to write | | an eased fade, a real room change |
| Landing ripple | the first version, before the rewrite | offline numpy render of the shader, not a compositor | the rebuilt strike by eye |

Two gaps are worth stating plainly, neither of them from these rounds.

**The package lock is stale.** The installed database records waybar and
waybar-openrc 0.15.0-r4, pinned by content hash in `/etc/apk/world`, but only
r3 exists in the repositories, the caches and the Fossil artifact store, so
`bin/package-archive snapshot` refuses to write a new lock rather than record a
closure it cannot reproduce. No source was lost: the recipe under
`packages/waybar/` is intact, and it is the built artifact that is missing.
Rebuilding r4 from that recipe, or reconciling the world pin with the archived
r3, unblocks the snapshot.

**The full test suite is a gate again.** `python3 -m unittest discover -s
alpine/tests` runs 1342 tests green. It was not, for a while: about sixty tests
named fixtures another session archived, seven thumbnail tests failed only when
the suite shared one Python process with the new GTK 4 grid tests, and thirteen
Bazzite tests broke on the lock-screen rewrite. The fixtures now look in
`archive/themes/` when a theme has been retired, the thumbnail renderer accepts
whichever Gdk the process already loaded, the Bazzite profile names stock
swaylock through `acquire_lock`, and the Scripture bar test runs with a private
state directory so the elected accent cannot reach in from the live desktop.

The earlier features carry their own evidence directories under
[verification/](verification/) and their contracts in [FEATURES.md](FEATURES.md);
[PROGRESS.md](PROGRESS.md) keeps the chronology and its honest gaps.
