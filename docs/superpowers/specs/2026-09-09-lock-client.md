# The lock client: a shader, a real indicator, and every other screen — 2026-09-09

## Request

Six things, in his words, gathered from several messages:

- *"I want the lock screen to be less blurred on the images."* Done separately:
  `lock_scene.BLUR_WIDTH_DIVISOR` is now a named constant at 190, giving a
  radius of 8 at the 1440-pixel working width instead of the 13 that made the
  painting into fog. It has a comment table of what each divisor reads like.
  Nothing below relitigates it.
- *"It'd be cool if they ran a nice neat shader that interacts with the trackpad
  input and key events."*
- *"When on power, it could be a qml scene like we already worked on."*
- *"On the lock screen, it uses a circle visualization. I want something far
  more spaceghost-y and incredible to see."*
- *"We're going to have power-awareness so plugged in or at least not low-power
  uses the shiniest ones."*
- *"I basically want all screens that aren't the desktop to have some cool thing
  to it, whether it's login lock or any other."*

This document is a menu, not a plan of record. Pick the indicator direction and
the route before anything is built.

## Where this starts

**The locker.** `oldbook-lock` waits for a real readiness handshake and then
gets out of the way. The scene is composed by `lock_scene.py` into two cached
PNGs — a blurred, darkened, vignetted painting and a Pango caption card — which
`swaylock-effects` 1.7.0.0 composes over a screenshot of the desktop it is
covering. Every pixel is cairo on `wl_shm`. There is no GL anywhere in the lock
path and no per-frame work at all except the clock's one repaint a second.

**The circle is not ours.** The ring is swaylock's own indicator: one
`cairo_arc` at radius 172, thickness 8, centred at (720, 360) logical. The only
things `indicator_arguments` can say about it are radius, thickness, position,
font, and about twenty colours across six states. It cannot be another shape.

**There is no QML in this repository.** All 351 check-ins, checked. The strong
candidate for what he remembers is `carousel_view.py` and `launchpad.py`:
GTK4/GSK fullscreen layer-shell scenes with an exact critically damped spring
(`spring_step`, frequency 40), a custom `do_snapshot`, and
`Gtk.EventControllerKey` / `EventControllerScroll` / `EventControllerMotion`
reacting to keys and trackpad scroll. A declarative-feeling scene graph driven
by exactly the two input classes he named. He says the QML work itself was done
on the alienware and lives on GitHub; that has not been found. These two files
are the closest thing here and are probably the right foundation.

**The only GLSL in the tree** is `.config/ghostty/shaders/cursor-smear.glsl` —
a fragment shader that draws a fading parallelogram behind a moving terminal
cursor, using `iTimeCursorChange` and `iFocus`. It is a good model for the
shape of this work: a short shader reacting to a discrete event with a 0.15 s
decay, not an ambient loop.

**The black gap is measured, and is not the fade.** With `WAYLAND_DEBUG`
protocol timestamps in a private headless session, the interval between
`ext_session_lock_manager_v1.lock()` and the locker's first committed buffer is
**70 ms with `--fade-in` and 94–103 ms without**. `--fade-in`'s first frame
paints the opaque screenshot copy and skips the composed ARGB scene at alpha
zero; without it, that first frame composites the scene, which pixman does far
more slowly. The gap scales with pixel count — **18 ms at a quarter of the
pixels** — because it is one cairo paint of a 2880×1800 shm buffer, which is
19.8 MiB. Any new client inherits this. How it is addressed is below.

**The hardware.** eDP-1 hangs off `card0`, which is `i915` — the Crystal Well
Iris Pro 5200. The Radeon R9 M370X on `card1` has no connected connector, so it
is not driving the panel and is not a lever. The panel is 2880×1800 at scale 2,
so 1440×900 logical and **5,184,000 physical pixels per frame**. `mesa-egl`,
`mesa-gles` and `mesa-gbm` are installed; GTK is 4.22.4 with gtk4-layer-shell
1.3.0; wlroots is 0.20.2 and wayland-protocols is 1.49, which carries
`ext-session-lock-v1` as staging.

**Two things that changed the ground since the last lock spec.**
`alpine/bin/remote-build` now builds packages on `alienware` or `bak` in a
throwaway Alpine container and signs them here, so patching or packaging
something is a real option again rather than twenty minutes of fan noise. And
`alpine/packages/swayfx/screen-corners.patch` calls
`wlr_output_lock_software_cursors(wlr_output, true)`, so every pointer movement
already costs a full-output recomposite — pointer-reactive effects are not free
on this machine, and the lock should probably hide the cursor entirely until
the pointer actually moves.

## The two routes

### (a) Patch swaylock-effects

We already carry two patches against it (`0001-ready-fd.patch`,
`0002-idle-colors.patch`), it builds reproducibly — two byte-identical signed
APKs are recorded in `verification.json` — and every security-critical piece is
written and exercised: PAM, xkb, per-output lock surfaces, the `locked` event,
the readiness pipe.

What it cannot do is a live shader. swaylock's whole surface model is a
`wl_shm` pool with cairo painting into it, re-blitted whole and damaged whole
every frame. At 19.8 MiB a frame that is a memcpy budget of roughly 1.2 GiB/s
to hold 60 Hz, before any drawing, which the measurements above say this
machine does not have. Adding EGL means linking `wayland-egl`, `EGL` and
`GLESv2`, creating a `wl_egl_window` per lock surface, replacing `render.c`'s
paint path, rendering text to an image surface and uploading it as a texture,
and adding a frame-callback repaint loop the program does not currently have.
Estimate 600–1000 lines across `main.c`, `render.c` and `seat.c`, and every
future rebase onto upstream becomes ours. That is not a patch; that is a fork
with a misleading name.

There is a smaller, much better version of (a), which is the recommendation
below. Call it **(a+)**: three changes, none of which need GL.

1. Drive repaints from a `wl_surface.frame` callback rather than only from
   events and the one-second clock timer.
2. Damage and repaint **only the indicator rectangle** instead of the whole
   surface. A 512×512 logical indicator at scale 2 is 1024×1024 physical, or
   4 MiB — about a fifth of the full surface, and it is the only region that
   changes.
3. Replace the `cairo_arc` with a drawing hook, so the indicator is our code.

Estimate ~400 lines against a codebase we already patch. It buys a fully
custom, 60 fps, input-reactive indicator drawn in cairo, with no new
dependencies, no EGL, and no change to the failure model. It does not buy a
fullscreen effect.

For the fullscreen *look* of a shader without a live one, swaylock-effects
already has `--effect-custom <path>`, which loads a `.so` exporting
`void swaylock_effect(uint32_t *data, int width, int height, int scale)` and
runs it once over the background at lock time. We do not even need the `.so`:
`lock_scene.render_background` is already a numpy pipeline that box-blurs,
desaturates, tints, vignettes and scrims, and its output is cached by painting
hash, geometry and `SCENE_VERSION`. A one-shot warp — a nebula displacement, a
chromatic split at the vignette edge, a starfield seeded from the painting's
own OKLab hue signature via `painting_palette` — is more numpy in that
function, costs nothing at lock time because it is cached, and bumps
`SCENE_VERSION` to 3. That is the honest low-cost answer to "shader look".

### (b) A bespoke `ext-session-lock-v1` client

This is what hyprlock, gtklock and waylock are. It owns the lock surface, the
PAM conversation, the xkb state and the renderer, and it is therefore the thing
standing between his session and anyone at the keyboard. That sentence is the
whole argument for doing it carefully and second.

Two sub-shapes:

- **(b1) C, from scratch**: `wayland-client`, the `ext-session-lock-v1` XML
  from wayland-protocols 1.49, `libxkbcommon`, `libpam`, EGL/GLES2. Roughly
  2000–3000 lines. Total control; the PAM and shm handling are ours to get
  right.
- **(b2) GTK4 on `gtk4-session-lock`**: wmww's companion library to
  gtk4-layer-shell, which gives a `Gtk.Window` an `ext_session_lock_surface_v1`
  role. If it works, the scene is written in exactly the idiom of
  `carousel_view.py` — a `Gtk.Widget` subclass with `do_snapshot`, springs,
  event controllers, and a `Gtk.GLArea` for the shader. That is the closest
  thing this repository can offer to "a QML scene like we already worked on",
  because it is the same declarative scene graph he is remembering.

  **`gtk4-session-lock` is not in Alpine.** `apk search` finds
  gtk4-layer-shell and its dev/doc/demo and hare bindings, and nothing else. It
  would need an APKBUILD of its own and a remote build, and it needs verifying
  against GTK 4.22 and wlroots 0.20 before anyone counts on it. If it does not
  pan out, (b) collapses to (b1), which is a much bigger job.

  Python's cost, stated plainly: the password must never live in a `str`, which
  is immutable and cannot be zeroed — it belongs in a `bytearray` that is
  overwritten. PAM must run in a forked child, not a thread, so a slow or
  blocking module cannot freeze the renderer. And PyGObject, GTK, GSK and Mesa
  all become part of the lock's trusted path.

### Recommendation

**Do (a+) now. Do (b2) afterwards, as a third locker at the top of the ladder,
only if he still wants the live shader once he has lived with (a+).**

Three reasons.

*The crash mode is not what it sounds like.* Under `ext-session-lock-v1`, a
lock client that dies without sending `unlock_and_destroy` does **not** fail
open — the compositor keeps the session locked and paints its abandoned-lock
colour, with no password prompt at all, until a replacement client takes the
lock. Failing stuck is safe and unusable. `oldbook-lock supervise` already
closes that window: it restarts a signal-terminated locker up to
`MAX_RESTARTS = 5` with `strip_first_run_options` removing `-R`, `--fade-in`
and `--screenshots`, because "restarts rejoin an already locked session". That
mechanism exists and works, and it is worth exercising under a locker we trust
before it is exercised under a new one.

*The fallback chain only helps before readiness.* `launchers()` tries the
effects locker, then `swaylockd` with stock swaylock. That covers a locker that
never reaches readiness. It does not cover one that dies at minute forty of a
lock — only the supervisor does. A second custom locker doubles the code that
can reach minute forty.

*Most of what he asked for is the indicator.* "Far more spaceghost-y and
incredible to see" is about the circle. (a+) delivers that in full at 60 fps
with no new trusted code. The fullscreen shader is the part he articulated
least and the part that costs most.

The staged plan at the end makes this concrete.

## What must never be lost

LOCK-THEME is the contract. Each guarantee, and how it survives whichever route
is taken.

**A real readiness handshake.** Readiness means the compositor sent
`ext_session_lock_v1.locked`, and nothing else. Not "my window mapped", not
"my process is running", not a matching process name. Any new client keeps
`-R/--ready-fd` byte-for-byte: write one newline to the inherited descriptor
the moment `locked` arrives, then close it. `oldbook-lock` does not change.

**Serialized concurrent requests.** Unchanged. `acquire_lock` takes an
exclusive `flock` on `oldbook-screen-lock/acquisition.lock` and holds it across
the whole launch, so two callers cannot race two lockers onto one session.

**Rejected stale identities.** Unchanged. `process_identity` records pid,
`/proc/<pid>/stat` field 20 (start time) and the boot id, and refuses a zombie
or a process owned by someone else. `compositor_identity` records the Wayland
socket's device, inode and ctime and requires it to be an owned socket directly
inside `XDG_RUNTIME_DIR`. Both are re-checked after the readiness byte arrives
and before `ready.json` is written. A new client must be launched *by*
`oldbook-lock` so that this record is written by the same code that writes it
today; a client that writes its own readiness record has thrown the guarantee
away.

**No grace period.** Not a flag defaulting to zero — absent. There must be no
code path in which a keypress or a pointer move within N seconds of locking
dismisses the lock.

**The power-key inhibitor for the locker's life.** Unchanged.
`inhibit_power_key()` spawns `elogind-inhibit --what=handle-power-key
--mode=block ... -- cat` reading a pipe, and passes the write end into the
launched process tree. The inhibitor releases when the last copy of that
descriptor closes, which is when the tree ends, however it ends. Two rules for
a new client: it must be launched under `oldbook-lock supervise` so the tree
lifetime is the locker's lifetime, and it must not close inherited descriptors
it does not recognise. A missing or refused inhibitor still locks — a live
power key is not a reason to leave the session open.

**A plain path that still locks.** Four layers, innermost first.

1. *In-process degradation.* The GL scene lives behind one boundary. Any
   failure — EGL init, shader compile, a GL error, a missing painting, an
   exception in a tick callback — switches to the still renderer and keeps the
   surface alive and committing. Nothing in the scene may raise into the main
   loop. If the failure happens before the first commit, degrade before
   committing; if after, degrade in place.
2. *A frame watchdog.* If the client believes it is animating and no frame has
   been committed for 2 s, drop to the still renderer. `grid_overlay` already
   does this shape with `WATCHDOG_MS = 420` for a stalled fade; the reasoning
   is the same, and the consequence here is worse.
3. *Supervisor restart.* `oldbook-lock supervise` restarts a signal-killed
   locker up to five times. Add one thing: the restart sets an environment
   variable forcing the plain rung, so a crash loop degrades instead of
   repeating. The window during which sway shows its abandoned-lock colour is
   the restart latency and should be measured, not assumed.
4. *The ladder below.* `launchers()` keeps swaylock-effects and stock swaylock
   beneath any new client, in that order, forever. `OLDBOOK_LOCK_BACKEND` grows
   a value for the new client and keeps `stock` meaning exactly what it means
   today.

And the two that exist outside all of this and should be written down where he
can find them: another VT reaches a themed rescue getty on tty2–tty6 — note
that APPLE-KEYS means the function row needs `Fn` — and `loginctl
unlock-session` from there ends a stuck lock.

**One more, not in the contract but worth pinning.** `--screenshots` means a
full-colour image of the unlocked desktop lives in the locker's memory for the
whole lock. That is true today and would be true of a new client. It is the
price of the dissolve; it should be a deliberate, written-down price, and the
buffer should be released once the dissolve completes rather than held for the
duration.

## The indicator

Three directions. Each is a complete answer for all six states the palette
already defines — idle, typing, verifying, wrong, cleared, Caps Lock — because
a design that only knows what "idle" looks like is not a design. Colours are
named as palette roles (`background`, `background_hard`, `surface`,
`foreground`, `muted`, `border`, `accent`, `accent_secondary`) so a generated
theme lands exactly rather than approximately. Pick one.

### 1. The Transmission

The caption card already signs off `󰊠 GHOST PLANET · COAST TO COAST`. The
identity is a radio station. So the indicator is a *carrier*, not a ring.

A single horizontal band across the middle third of the screen, roughly
1200×140 logical: an oscilloscope trace in `accent` over `background_hard` at
low alpha, with a thin `border` baseline. At rest the trace is nearly flat —
one or two logical pixels of amplitude — moving with the keyboard's own breath
from `air.json` rather than a clock of its own, so it is the same breath the
painting and the caption strip follow. Typing does not produce a blip per key;
it raises the carrier's noise floor, so the trace thickens and picks up
harmonics while you type and decays back over `air.py`'s twenty-second leak.
The clock sits above the band in Inter Display SemiBold; the date below it in
`muted`.

- **Verifying**: the trace snaps to a clean, still sine and the label reads
  `CHECKING SIGNAL`.
- **Wrong**: the carrier collapses to a dead flat line with a burst of static
  and `NO SIGNAL` in `foreground`, which is the role the current design already
  uses for failure.
- **Cleared**: the trace goes to `border` and flattens smoothly.
- **Caps Lock**: the trace inverts polarity and takes `accent_secondary`, with
  `CAPS` set in the band's left margin.

Cheap: a polyline over about 0.34 Mpix at scale 2, well inside cairo at 60 fps.
Works entirely within (a+).

### 2. The Ghost's Eye

An aperture, not a ring. Six or eight overlapping blades in `surface` with
`border` edges and an `accent` rim light, forming a hexagonal iris roughly 400
logical pixels across where the circle sits now. The painting is **sharp inside
the aperture and blurred outside it**, which turns the thing he asked for —
less blur — into the design rather than a setting. The clock sits inside the
pupil.

The aperture breathes with `air.json`, opening one or two percent on the
inhale. Typing widens it a hair and brightens the rim. Verifying closes it to a
slit. Wrong snaps it shut with a single shudder and takes the rim to
`foreground`. Cleared opens it fully and holds. Caps Lock lays a bar across the
pupil in `accent_secondary`.

Cost: one extra cached image — the painting cover-cropped and *unblurred* at
the aperture's size, about 800×800 physical, cached beside the blurred scene
under the same painting hash. The blades are one polygon path. On mains a
shader refracts the blade edges with a small radial chromatic offset; on
battery it is a hard clip and looks deliberate rather than cheap. The sharp
inner image works within (a+); the refraction needs (b).

### 3. Orbit

The Ghost Planet itself, as a dark limb low on the screen — `background_hard`
body, `border` limb, `accent` atmosphere at very low alpha — with its
terminator set by the real solar altitude from `astro.py` for the configured
location, and the moon's real phase as a small companion at its correct
illumination. Behind it a starfield seeded from the painting's OKLab hue
signature, so the sky belongs to tonight's picture.

The indicator is one satellite on an ellipse seen nearly edge-on. At rest the
point sits still at apoapsis and nothing moves. The trackpad tilts the orbit's
inclination — pointer position rotates the ellipse, scroll changes its radius —
so touching the trackpad visibly changes the geometry without touching the
lock. Typing adds orbital *speed*, so the point sweeps while you type and
coasts down afterward on the twenty-second leak.

- **Verifying**: the point completes one full revolution and the terminator
  flares.
- **Wrong**: the orbit decays, the point spirals in and burns up in a short
  streak in `foreground`.
- **Cleared**: the point returns to apoapsis on a spring.
- **Caps Lock**: a second point appears in a retrograde orbit in
  `accent_secondary`.
- **Correct**: the point crosses the terminator into daylight as the scene
  lifts — the only moment of the whole design that is allowed to be a flourish,
  because it happens exactly once and then the lock is gone.

Cost: planet and starfield are one cached texture; the orbit is a handful of
vectors. It is the most ambitious of the three and the only one that genuinely
wants the shader — an atmospheric scattering term on the limb, which is a dozen
lines of GLSL and looks like nothing else on the machine.

### A constraint all three must respect

The standing preference is that continuous ambient motion is not welcome by
default — a painting that breathes on a cycle has already made him feel unwell
once. So: **the painting never moves.** Motion is confined to the indicator, it
is small, and on every rung including mains the scene must settle to a still
frame and stop drawing entirely after 30 s with no input. Add a `lock` key to
`~/.config/oldbook/breath.json` beside `wallpaper` and `caption`, so there is
one obvious place to switch it off, and honour `gtk-enable-animations = false`
the way the OSD does.

## Input reactivity

**What actually reaches a lock surface.** The compositor gives lock surfaces
seat focus, so the client receives `wl_keyboard` enter/key/modifiers/repeat and
`wl_pointer` enter/motion/button/axis. Trackpad scrolling arrives as `wl_pointer
axis` with `axis_source = finger` and an `axis_stop` when the fingers lift; at
`wl_pointer` version 8 it also arrives as `axis_value120` in 1/120-detent
units, which is a genuinely smooth two-dimensional continuous input and is what
GTK exposes as smooth scroll deltas. That alone is enough to drive a shader.

Multi-finger swipe, pinch and hold would come through `zwp_pointer_gestures_v1`.
**Unverified**: whether wlroots 0.20 routes pointer gestures to a session-lock
surface. Test it before designing around it. There is no touchscreen on this
machine, so touch is not a consideration.

The client sees its own input and nothing else. It sees no other client's
events, no window titles, no notifications, no clipboard. It can read files as
the user, which is how the painting, the palette, the Scripture and
`air.json` reach it — noting that `air.json` is only fresh while the keyboard
light is actually breathing, `FRESH_SECONDS` is 0.5, and `oldbook-idle dim`
asks for one `last-breath` before the idle lock, so during an idle lock there
is a breath for about six seconds and then nothing. Design for its absence.

**What input may drive.**

*Pointer and trackpad: anything at all.* Position, velocity, scroll offset,
scroll velocity, gesture scale. None of it carries a secret. This is where the
expressiveness should live, and it is also the input he named first. One
practical caveat: `screen-corners.patch` forces software cursors, so every
pointer motion event already causes a full-output recomposite; a
pointer-reactive scene is paying that cost on top of its own.

*Keys: one scalar, and only one.* A key event increments a single energy value
by a fixed amount **regardless of which key it was**, and that value decays
continuously. The visualisation is a function of that scalar and nothing else.

**What is forbidden, and why.** The threat is not the client leaking to another
process; it is the screen leaking to a camera, a window, or a person behind
him.

- Never map a keysym to a colour, angle, position, glyph or sound. Not even to
  a random one — swaylock's ring already picks a random arc per keystroke, and
  the randomness hides *which* key, not *that* a key happened.
- Never make the character count readable. Today's design leaks it twice: the
  ring's `--key-hl-color` segments are countable, and `--bs-hl-color` is a
  *different colour*, so an observer can count the backspaces too. A new
  indicator must not reproduce that. This is the one place the redesign should
  be measurably better than what it replaces, not merely different.
- Never render password length as dots or asterisks. swaylock does not; keep
  it that way.
- Never leak inter-keystroke timing faithfully. Timing between keystrokes
  narrows a password search space measurably (Song, Wagner and Tian, USENIX
  2001), and a 60 fps video of the screen is a timing channel if the
  visualisation is a faithful impulse train.

**The concrete rule**, so this is testable rather than aspirational: the energy
scalar is quantised to 16 levels and smoothed with a time constant of at least
150 ms, with a floor high enough that one keystroke and three keystrokes 100 ms
apart produce the same visible response. *The test*: record the lock at 60 fps
while typing a known twelve-character password containing two backspaces, and
count the recoverable impulses in the video. If the count is recoverable, the
design has failed and must be smoothed further.

**What must still be shown**, because hiding it is its own failure: Caps Lock,
a non-default keyboard layout, the verifying state, and the wrong state. Those
are the states the user needs and an attacker already knows.

## Power awareness

`power_source.py` already publishes one posture for the whole desktop —
`mains`, `battery`, `battery-low`, `battery-critical` — from the same 25% and
10% thresholds the battery cue and the Waybar module use, event-driven from
udev with a slow backstop poll. The ladder already lists `'shaders': 'mains'`
and `'blur': 'battery'`. A hand-set override may only make things quieter.
Register `lock-scene` and read it; do not invent a second notion of low power.

| Posture | What the lock runs | Cost |
| --- | --- | --- |
| `mains` | The full scene: fullscreen fragment shader at 2880×1800, 60 fps, sharp painting inside the aperture, starfield, breath-linked idle motion | 5.18 Mpix/frame. A 60 fps budget means the shader must finish in **≤ 8 ms**, i.e. roughly 640 Mpix/s of fragment throughput on an Iris Pro 5200. Plausible for a shader of thirty-odd instructions per pixel; **must be measured, not assumed** |
| `battery` | No fullscreen shader. The custom indicator animates at 60 fps over its own damage rectangle. The painting is still and carries the baked one-shot warp from the cached background PNG | ≤ 4 MiB per frame at a 512×512 logical indicator, well under 1 ms |
| `battery-low` | The indicator animates **only on input** and settles to a still frame within 400 ms of the last event. No breath. The clock updates once a minute rather than once a second | Wakeups on input plus one a minute |
| `battery-critical` | A still image: the cached background PNG, the clock, the caption card, no timer but the minute clock. This is what stock swaylock already does, which is why it is also the recovery rung | One paint at lock time |

Two things the table does not say.

*Idle stops everything.* After 30 s with no input the scene settles and stops
drawing on **every** rung, mains included. swayidle turns the display off at
600 s anyway, and a lock screen animating to an empty room is the exact thing
the ambient-motion preference is about.

*The real cost is not the frame.* A 60 fps fullscreen composite holds the GPU
and the display pipeline out of every idle state for as long as the lock is up,
and on this machine the lock is usually up because he walked away. Guess, to be
replaced by a measurement: 2–5 W above a still lock. That is enough to matter
on a battery and it is exactly why the ladder exists.

The ladder can also select *which locker runs*, not only how it draws — a
mains-only client at the top of `launchers()` with swaylock-effects beneath it
is a small change to already-verified code. Whether that is wise is a real
question: it means two custom lockers to maintain and a lock whose appearance
depends on the cord, which may read as a bug rather than a feature. Worth
asking him.

## Every other screen that isn't the desktop

He asked for all of them. Most are further along than the request assumes —
here is where each one actually stands.

**Already fully themed, and the work is to *see* them, not to build them.** The
GRUB menu has a Ghost Planet theme with custom PF2 fonts compiled from
JetBrains Mono, an amber `󰊠 GHOST PLANET` title over a blurred crop of the
Space Ghost painting. The kernel console, the LUKS passphrase prompt and the
rescue gettys all take the theme's own sixteen colours through
`vt.default_red/grn/blu`, `vt.color=0x0F` and `fbcon=font:TER16x32`, generated
by `build-console-palette` from the selected theme's terminal palette. The
rescue getty has a rendered `/etc/issue` banner. **None of it has ever been
seen on a real boot** — `grub-emu` is not packaged, so the menu preview is a
simulation drawn by our own renderer. The single highest-value action for this
whole area is not a feature; it is one reboot with a camera. Cost: a reboot.

**The wlogout power deck** is done: five 22px-radius tiles with 92px Nerd Font
glyph icons over a SwayFX-blurred desktop, amber on hover, orange on press,
in the theme profile set. What it lacks is the lock's vocabulary — no painting,
no caption, no Scripture. Bringing the caption card and the current painting
behind the deck is a stylesheet and one background image, and it would make the
deck and the lock read as the same place. Cost: an afternoon. Note that
`wlogout` is not in `alpine/packages/world`, which is worth fixing regardless.

**The swaynag confirmation bars** — corrected from the request. They are not
stock grey and blue. `~/.config/swaynag/config` has been themed since yesterday
(Inter Medium 11, `#282828` ground, `#ebdbb2` text, a 3px amber underline for
`[warning]` and red for `[error]`, `layer=overlay`), it is mirrored into the
gruvbox-dark profile, and `test_theme_boundary.ConfirmationBars` asserts no
Gruvbox shade survives into another theme. What is actually missing is smaller
and duller than "stock colours": swaynag has **no render evidence at all** —
`verification/power-deck/README.md` names it as uncovered — and its *shape* is
still a flat bar with no character, which is all swaynag can be. If the deck
gets the painting treatment, the honest move is to stop using swaynag for these
three confirmations and let the deck ask for its own confirmation in place,
which also removes a binary that SwayFX is built without. Cost: a small
addition to `oldbook-power`, and one screenshot either way.

**The idle screensaver** already is the gallery: `oldbook-screensaver` hands
shuffled paintings to the background-fade daemon, which pans and zooms at
`SCREENSAVER_ZOOM = 1.06` over a 30 s hold with a 3 s crossfade, and glides
back to the exact painting on stop. It fires at 240 s, thirty seconds before
the dim and a minute before the lock. The one thing it could carry that it does
not is the caption — the painting's title and story as a quiet card, so a
drifting gallery says what it is showing. Cost: it can reuse
`lock_scene.render_caption` unchanged.

**The login screen does not exist**, deliberately: greetd autologins straight
into Sway on vt1, because the encrypted root passphrase is the real gate and a
second prompt buys nothing. The LUKS prompt *is* the login screen on this
machine, which is why the boot console work already treats it that way. Nothing
to build; worth writing down so it stops being asked.

**The genuinely unthemed remainder** is GRUB's own text console behind the `C`
key, whose `terminal-font` and `message-*` colours are set in `theme.txt` but
have never been seen. Cost: nothing, if the reboot happens with a camera.

## A staged plan

**Stage 1 — the indicator, on the locker we already trust.** Pick one of the
three directions. Add `0003-custom-indicator.patch` to
`alpine/packages/swaylock-effects`: frame-callback repaints, damage limited to
the indicator rectangle, and a drawing hook in place of the arc. Build it on
`bak` through `alpine/bin/remote-build`. Nothing about readiness, serialization,
identity, grace or the power-key inhibitor changes, and stock swaylock stays
beneath it. This ships on its own and is most of what he asked for. It also
fixes the countable-keystroke leak, which is worth doing whether or not
anything else here happens.

**Stage 2 — the baked shader and the black gap.** More numpy in
`render_background`: a displacement warp, a chromatic edge, a starfield from
the painting's hue signature. Bump `SCENE_VERSION` to 3 so the cache does not
serve the old look. Separately, cut the gap: present the first frame through
`wp_viewporter` from a quarter-size buffer — the existing measurement says
18 ms instead of 94 — and swap to full resolution on frame one. Add a 120 ms
ease-to-black before the *deliberate* lock, reusing `oldbook-idle`'s ramp, so
the remaining gap lands inside a dim that reads as intentional. The idle lock
is already dark by then.

**Stage 3 — decide whether (b) is still wanted.** With Stages 1 and 2 running,
ask him. If the answer is yes, the first task is not code: it is verifying that
`gtk4-session-lock` exists, builds on Alpine edge against GTK 4.22, and works
with wlroots 0.20's `ext-session-lock-v1`. If it does, (b2) is a scene written
in the `carousel_view.py` idiom with a `Gtk.GLArea`, and it is genuinely the
QML-feeling thing he remembers. If it does not, (b1) is C, and the estimate
triples.

**Stage 4 — the client, plain first.** Whatever (b) turns out to be, the first
version has no shader. It reaches readiness, passes every LOCK-THEME guarantee,
draws the still scene and the chosen indicator, and sits at the top of
`launchers()` with two lockers beneath it. Only once it has locked the machine
many times does the GL path go in, behind the degradation boundary and the
frame watchdog.

**Stage 5 — the other screens.** One reboot with a camera, in order to find out
what the boot chain actually looks like. Then the deck gets the painting and
the caption, the screensaver gets the caption, and the three confirmations move
out of swaynag and into the deck.

## Guesses, and what would settle them

Marked because six months from now it will not be obvious which of these were
measured.

- **Guessed**: 8 ms for a fullscreen shader at 5.18 Mpix on an Iris Pro 5200,
  and 2–5 W for running one. *Settled by*: writing the shader from
  `cursor-smear.glsl`'s shape, running it fullscreen through a throwaway
  `Gtk.GLArea` on eDP-1, and reading frame times and `power_supply` current.
- **Guessed**: that `gtk4-session-lock` exists, packages cleanly and works
  here. *Settled by*: an APKBUILD and one remote build.
- **Guessed**: that `zwp_pointer_gestures_v1` reaches a lock surface under
  wlroots 0.20. *Settled by*: a twenty-line client in the headless session.
- **Guessed**: that an unprivileged process authenticates through PAM here via
  `pam_unix`'s helper. It is how swaylock works, so it is very likely, but it
  has not been checked on this machine. *Settled by*: running the existing
  locker as an ordinary user, which happens every lock — confirm it rather than
  assume it.
- **Guessed**: the restart latency of `oldbook-lock supervise`, and therefore
  how long sway shows its abandoned-lock colour if the locker dies mid-lock.
  *Settled by*: killing the locker in the private headless session and timing
  the interval between its death and the replacement's first commit. This is
  the single most important unmeasured number in the whole document, because it
  is the length of time he would spend staring at a screen with no password
  prompt.

## Rollback

Nothing here is installed, so there is nothing to roll back. Each stage has its
own exit: Stage 1 is one patch removed from
`alpine/packages/swaylock-effects/APKBUILD` and a rebuild; Stage 2 is
`SCENE_VERSION` back to 2 and the cache cleared; Stages 3 and 4 are
`OLDBOOK_LOCK_BACKEND=effects` or `=stock` in the session environment, which
returns every path to the lockers that exist today.
