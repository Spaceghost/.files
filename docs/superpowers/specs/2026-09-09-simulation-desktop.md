# The desktop as a simulation — 2026-09-09

## Request

Two messages, some days apart, that turn out to be the same request seen from
two distances.

- *"Is there any really cool features or effects or shaders we wanna start
  building and applying here? I want cool shit along the sides of windows
  wherever another window isn't and wherever conky isn't."*
- *"Using probably dragonruby or something lightweight enough to work even with
  battery at different levels, I want to rebuild my entire login/lock/desktop
  into running a simulation of sorts using a game engine. I don't want to lose
  anything and just theseus' ship the desktop into the gamesim."*

The second is the destination. The first is the first plank, and it is the only
part of this document that should be built before he has read the rest.

This is a menu and a survey, not a plan of record. It contradicts one finding in
[the lock client spec](2026-09-09-lock-client.md) — said plainly in *What the
lock means here* — and defers to it everywhere else.

## Ground truth, checked on this machine today

Some of what we assumed going in was wrong. Corrections first.

**DragonRuby is not here.** No binary on `PATH`, no directory, nothing under `/`
matching `*dragonruby*`, and no mention of it — or of Godot, LÖVE or raylib —
anywhere in the working tree. He owns
`dragonruby-game-toolkit-contrib` on GitHub, which is the licence-gated contrib
repository, so the licence is real; the runtime is not on this laptop.

**SDL2 is installed, but not the SDL2 anyone means.** `libSDL2-2.0.so.0` exists
and points at `sdl2-compat 2.32.72-r0`, a shim that reimplements the SDL2 ABI on
top of `sdl3 3.4.16-r0`. Real SDL2 (`sdl2`) is packaged but not installed. This
matters: a binary that dynamically links `libSDL2-2.0.so.0` will run here and
will actually be driven by SDL3's Wayland backend. Whether DragonRuby links the
system SDL2 or carries its own is **unverified** — it is not installed and
cannot be checked. It changes which shim tricks below are even possible.

**wlroots 0.20.2-r1 and `wlroots0.20-dev` are installed**; 0.19 is packaged but
not installed. SwayFX is 0.6, based on sway 1.12.0, on SceneFX 0.5-r0 (0.5-r1 is
built and archived and deliberately not installed). `wayland-protocols` is 1.49
and carries `ext-session-lock-v1` as staging;
`/usr/share/wayland-protocols/staging/ext-session-lock/` is on disk.
`wlr-layer-shell-unstable-v1.xml` is **not** on disk anywhere — gtk4-layer-shell
vendors its own copy — so a from-scratch C layer-shell client starts by fetching
a protocol file.

**The engines that are already installed, which nobody wrote down.**

| Thing | Version | Why it matters |
| --- | --- | --- |
| `gtk4.0` + `gtk4-layer-shell` | 4.22.4 / 1.3.0 | The scene engine this desktop already uses |
| `gtk-layer-shell` (GTK 3) | 0.10.1 | What `oldbook-osd` uses |
| `qt6-qtdeclarative` (QML) | 6.11.1 | `/usr/lib/qt6/bin/qml` runs QML files today |
| `qt6-qtwayland` | 6.11.1 | Ships `QtWayland.Compositor` as an installed QML module |
| `layer-shell-qt` | 6.7.4-r0 | **Installed**, pulled in by `superhold`. A Qt window can be a layer surface today |
| `qt6-qtshadertools` + `qsb` | 6.11.1 | Compiles GLSL for QML `ShaderEffect` |
| `PyQt6` (QtQml, QtQuick, QtOpenGL) | site-packages | Python can drive QML here |
| `mesa-egl` | 26.1.6-r1 | EGL/GLES for either toolkit |
| `mpvpaper` / `swaybg` | 1.8-r0 / 1.2.2-r0 | The two existing proofs of "an app as the background" |

And two more that are packaged but not installed: `gtk-session-lock 0.2.0-r0`
(edge/testing — a GTK **3** `ext-session-lock-v1` library) and `layer-shell-qt-dev`.

**The hardware, unchanged.** Core i7-4870HQ, 8 threads, 15.9 GB. eDP-1 hangs off
`card0`, `i915`, the Crystal Well Iris Pro 5200; the Radeon on `card1` has no
connected connector. The panel is 2880×1800 at scale 2, so 1440×900 logical and
**5,184,000 physical pixels per frame**. A full-output ARGB buffer is 19.8 MiB.

**The pinned contracts.** `alpine/FEATURES.md` holds **43** feature IDs, not the
forty we said. They are listed by name in *Theseus, taken seriously*.

**The layer map, which nobody had written down.** Every layer-shell surface on
this desktop, bottom to top. It is the map the first plank has to fit into.

| Layer | Namespace | Owner |
| --- | --- | --- |
| `BACKGROUND` | `wallpaper` | swaybg, spawned by sway's `output * bg`. Fallback only, never refreshed after a fade |
| `BACKGROUND` | `oldbook-background` | The crossfade daemon. **GTK 3** + `gtk-layer-shell`, one surface per output, exclusive zone −1, empty input region |
| `BACKGROUND` | `conky` | One `conky` process **per panel**, `own_window_type = 'desktop'`, `out_to_wayland` |
| `BACKGROUND` | `oldbook-decoration-band` | The invisible one-pixel exclusive-zone reservation |
| `BOTTOM` | *(mpvpaper default)* | `oldbook-video-background` and `oldbook-youtube`, both `--layer bottom` |
| `BOTTOM` → `TOP` | `oldbook-scripture` | The search bar, promoted to `TOP` only while focused |
| `TOP` / `OVERLAY` | `oldbook-decoration`, `waybar`, `swaync-*`, `launcher`, `logout_dialog`, `oldbook-osd`, `oldbook-flash`, `oldbook-card`, `oldbook-shortcuts`, `oldbook-carousel`, `oldbook-showdesktop`, `oldbook-launchpad`, `oldbook-mission-control`, `oldbook-agent-switcher`, `oldbook-watch` | Everything with focus or chrome |

Two things follow that are not obvious. **Conky is on `BACKGROUND`, not `BOTTOM`** —
so anything on `BOTTOM` draws *over* the reading cards unless it clips them out.
And the background layer is not free real estate: `background_fade.surface_order()`
watches it and will re-create its own surface (`raise_canvas`) if a `wallpaper`
surface lands above it, and will *restart Conky* if a `conky` surface lands
below it. It inspects only `layer == 'background'`, so a `BOTTOM` surface is
invisible to it — which is a reason to prefer `BOTTOM`, not merely an
observation.

The toolkit split, also undocumented: **GTK 4** for `carousel_view.py`,
`showdesktop.py`, `grid_overlay.py` (and its Launchpad and Mission Control
subclasses) and `watch_mode.py`; **GTK 3** for `oldbook-osd`,
`oldbook-background`, `oldbook-decoration`, `oldbook-scripture-bar`,
`agent_switcher.py` and `shortcut_overlay.py`. Both toolkits are already in the
session, on every rung.

**No `layer_effects` block exists for `oldbook-background`, `conky`, `wallpaper`
or mpvpaper.** Compositor-side blur and effects on the background layer are
unclaimed territory. Nothing in the repository passes `--glsl-shaders` to mpv
either, at either mpvpaper call site.

## The central constraint: SDL does not do layer-shell

Both SDL2 and SDL3's Wayland video drivers create an `xdg_surface` plus an
`xdg_toplevel`. Neither knows `zwlr_layer_shell_v1` exists. A DragonRuby window
is therefore an ordinary application window: it lives in the sway tree, it is
above the wallpaper and below nothing in particular, it takes focus, it has a
caption strip attached to it by `oldbook-decoration`, and it reserves layout
space. It cannot be the desktop background, and it cannot be a lock surface,
because `ext_session_lock_surface_v1` is a surface *role* assigned at creation by
a client that holds the lock — SDL has no path to it at all and never will.

There are four ways around this. Three of them are real and one is a trap.

**(1) A custom surface role from SDL, then assign the role yourself.** SDL3
exposes properties at window creation that let an application ask for a bare
`wl_surface` with no shell role attached, and then read back the `wl_surface`,
`wl_display` and `wl_egl_window` pointers. With those, the application gives the
surface the `zwlr_layer_surface_v1` role itself and drives its own
configure/commit cycle. This is the correct mechanism and I am fairly confident
it exists in SDL3 under names like
`SDL_PROP_WINDOW_CREATE_WAYLAND_SURFACE_ROLE_CUSTOM_BOOLEAN` and
`SDL_PROP_WINDOW_WAYLAND_SURFACE_POINTER`. **Unverified here** — `sdl3-dev` is
not installed, so no header on this machine names them. *Settled by* `apk add
sdl3-dev` on a build host and one grep.

The trap is what sits above it: **DragonRuby does not expose SDL window creation
to Ruby.** It creates its window internally, and the Ruby API has no property
bag to pass through. So even where SDL supports it, DragonRuby does not, unless
a Pro-tier C extension reaches around the runtime — which requires knowing how
its own SDL is linked, which is the unverified thing above.

**(2) An `LD_PRELOAD` shim over SDL.** Interpose `SDL_CreateWindow` and friends,
create the surface yourself, hand SDL a window it thinks it made. This works only
if the runtime links `libSDL2-2.0.so.0` dynamically. It is a genuinely nasty
thing to own: it breaks on every SDL and DragonRuby update, it has no test that
is not a live session, and when it fails it fails as a black rectangle.

**(3) Patch SDL3's Wayland backend.** Add a layer-shell path behind an
environment variable in `SDL_waylandwindow.c`. `alpine/bin/remote-build` makes
this a normal afternoon rather than twenty minutes of fan noise, and this
repository already carries four patches against SwayFX and two against SceneFX,
so the idiom is established. But it means the desktop's background depends on a
forked `sdl2-compat`/`sdl3` under **every other SDL application on the machine**,
which is a much larger blast radius than a compositor patch.

**(4) Do not use SDL.** Two toolkits already installed reach layer-shell without
any of this: GTK4 + `gtk4-layer-shell`, which this desktop uses in five places,
and Qt6 + `layer-shell-qt`, which this desktop already uses once, in
`superhold`. This is the answer, and the rest of the document assumes it.

**A fifth route, tempting and wrong, recorded so nobody spends a day on it.**
mpvpaper is already installed, already renders to `--layer bottom`, and mpv
accepts `--glsl-shaders`, which no call site in this repository currently uses.
That is a fullscreen fragment shader on the background layer for the price of one
command line. But mpv only runs the shader when it decodes a frame, so a still
image renders it once; making it continuous means a synthetic source like
`av://lavfi:color=...:r=60`, which is a video decoder running at 60 fps forever
to animate a backdrop that is not supposed to animate. It is the exact thing the
motion rule and the power ladder both exist to prevent. Worth knowing about for a
*one-shot* warp of the painting; not worth it for anything live.

**The honest summary: DragonRuby is the wrong engine for every tier that needs
layer-shell or `ext-session-lock-v1`, which is all three of them.** It is not
wrong because it is bad. It is wrong because the thing it is good at — a
self-contained 60 Hz game in a window — is not the shape of a desktop shell, and
the two engines that *are* that shape are already installed and already in use
here.

There is one place DragonRuby fits cleanly and it is worth saying so: **as a
game**, an ordinary window launched from Launchpad, and — if he wants the sim on
screen when he is not — as the idle screensaver, fullscreen on an empty
workspace. `oldbook-screensaver` already owns that moment. That reaches "a
Ghost Planet simulation running on my machine" with zero protocol work, and it
is reversible by not launching it.

## Three tiers

| | What it is | Where it draws | New trusted code | Reversible by |
| --- | --- | --- | --- | --- |
| **1. Backdrop** | A layer surface below every window that reads the layout and reacts to it | `BOTTOM` layer, one output | None. It can crash and the desktop is unchanged | One line in `oldbook-session` |
| **2. Session scenes** | The sim owns lock, idle, power deck, launcher, overview as scenes in one world | `OVERLAY` + `ext-session-lock-v1` | The lock. Everything else is recoverable | `OLDBOOK_LOCK_BACKEND=effects`, plus per-scene keys |
| **3. Compositor** | Windows are objects in the sim's scene graph; SwayFX is gone | Everything | All of it | A different `command` in `/etc/greetd/config.toml` |

### Tier 1 — the sim as backdrop

**What it buys.** Exactly the first request, and nothing is at risk. A surface on
the `BOTTOM` layer is above the painting and below every window, so "wherever
another window isn't" is not a computation, it is the surface's natural
visibility. "Wherever Conky isn't" *is* a computation, because Conky is on
`BACKGROUND`, one layer down — so the surface has to cut the reading cards out
of itself or it covers them. Sway IPC tells it where both are. It is themed by
`overlay_theme.read_palette` like everything else, it registers on the power
ladder, and it can be killed at any moment with no consequence beyond the effect
disappearing.

**What it costs.** Two things, one obvious and one not.

The obvious one: pixels. A fullscreen fragment pass at 5.18 Mpix and 60 fps is
311 Mpix/s, and one RGBA8 read plus one write is 8 bytes, so 2.5 GB/s of traffic
per pass before any texture sampling. The Iris Pro 5200 has 128 MB of eDRAM at
roughly 50 GB/s with DDR3-1600 behind it. One or two passes is comfortable.

The one that is not obvious, and which is the largest risk in this document:
**SceneFX keeps a pre-rendered optimized-blur buffer of everything below the
windows, and an animated backdrop invalidates it every frame.** Blur is
`blur_passes 1`, `blur_radius 4` — down, up, composite — and it runs for every
blurred window. Today that buffer is rebuilt only when something below a window
actually changes, which on a still painting is almost never. Put an animating
surface underneath and it is rebuilt 60 times a second, across the whole output,
for the whole session. The terminals are at 0.78 opacity and the caption strip at
0.67, so nothing is opaque enough for wlroots to cull the backdrop behind it
either. `alpine/packages/scenefx/README.md` describes exactly this buffer and its
damage arithmetic; the cost of dirtying it every frame is **not measured**, and
it should be measured before anything animates.

That single fact turns the standing preference against ambient motion from an
aesthetic rule into a performance rule, which is a pleasant coincidence.

**What it risks.** Covering the reading cards, which is the whole point of
"wherever Conky isn't" and is a clipping requirement rather than an
optimisation. An exclusive zone accidentally set to anything but zero, which
would move every window on the output — `oldbook-background` uses −1 and copying
it would be the easy mistake. `desktop_space.screen_space` counting the new
surface as an occupier and reflowing Conky, which `CONKY-READING` forbids
outright. And colliding with `oldbook-video-background`, which is the only other
tenant of the `BOTTOM` layer. All four are concrete and all four are cheap to get
right; see *The first plank*.

**What it forecloses.** Nothing. It is additive, it is one process, and it is the
only tier that can be abandoned without a story.

### Tier 2 — the sim owns the session surfaces

**What it buys.** One world instead of six programs. The lock, the idle
screensaver, the power deck, Launchpad, Mission Control and the shortcut guide
would share a scene graph, a palette, a spring, a physics step and a vocabulary,
so moving between them would read as moving through one place. That is genuinely
what he is asking for, and four of those six are *already* the same object:
`grid_overlay.Overlay` is one full-output layer-shell surface with a frame-clock
reveal, and `carousel_view.Popup` is its sibling. Tier 2 is substantially
"finish what is already half-built and add the lock."

**What it costs.** The lock, and only the lock, is a security boundary. The lock
client spec spends four thousand words on why, and none of it is relitigated
here. Everything else in tier 2 is a program that can crash into an unchanged
desktop.

The second cost is subtler: the six surfaces have genuinely different input
contracts. `WATCH-MODE` needs exclusive keyboard on `OVERLAY` and must fail
*closed and loudly*. `FEEDBACK-OSD` must take no focus and pass pointer input
through. `EXPOSE-LIFECYCLE` must survive external navigation ending it. Merging
them into one process means one bug can now reach all of them, and
`SESSION-OWNERSHIP` — one owner per compositor session, reloads must not stack
daemons — becomes six times as load-bearing.

**What it risks.** `LOCK-THEME` in full, plus `APPLE-KEYS`, `EXPOSE-LIFECYCLE`,
`WINDOW-SWITCHING`, `CAROUSEL-STILLS`, `SHORTCUT-HELP` and `WATCH-MODE`.
`CAROUSEL-STILLS` is the quiet hard one: aspect-correct per-window stills for
hidden workspaces, captured once per opening, without visiting or focusing them.
That works today. A rewrite that loses it loses something he explicitly pinned.

**What it forecloses.** Very little, if each scene migrates one at a time and
the old one stays behind it. It forecloses a great deal if the six move together.

### Tier 3 — the sim as the compositor

**What it buys.** The only thing the other two cannot: windows as objects. A
window that can be rotated, shaded, thrown, orbited, put on a shelf, folded into
a card that is the *actual live window* rather than a still of it. Mission
Control today shows captured images; under tier 3 it would show the windows
themselves, because they are scene nodes.

**What it costs.** DragonRuby cannot do this at all — it has no way to consume
wlroots or to be a Wayland server. The realistic candidates are two.

*(3a) More SwayFX patches.* This repository already carries four
(`bottom-titlebar`, `hover-raise`, `screen-corners`, `window-animations`) and two
against SceneFX. SwayFX is on wlroots 0.20 through SceneFX, and SceneFX is a
scene graph with blur, shadow and corner nodes. Inserting new node types, or a
criteria-driven rule that reparents a matched `xdg_toplevel`'s scene node, is the
idiom this repo has used four times and knows how to build, sign and verify.
This is not "the sim as compositor" in spirit, but it is 90% of what tier 3
actually buys, at a fraction of the cost.

*(3b) `QtWaylandCompositor` in QML.* This is installed —
`/usr/lib/qt6/qml/QtWayland/Compositor/` with `XdgShell`, `WlShell`, `QtShell`,
`PresentationTime` and `TextureSharingExtension`, drivable by `/usr/lib/qt6/bin/qml`
with no C++ at all. Every window becomes a `ShellSurfaceItem`, which is a
`QQuickItem`, which can be transformed, shaded with `ShaderEffect`, layered,
animated and hit-tested like any other QML object. It is genuinely the thing he
described, it is LGPL, and it is already on the disk. This is worth knowing even
if it is never used.

**What it risks.** The honest list, because it is the argument.

Every contract that is a *sway* behaviour rather than a helper's behaviour:
`WORKSPACE-IDENTITY`, `WINDOW-RESIZE`, `DROPDOWN-WINDOWS`,
`DECORATION-PLACEMENT` (exclusive zones and `arrange_workspace`'s floating
semantics), `MOTION` (SceneFX's blur reach arithmetic), `SCREEN-CORNERS` (a patch
against sway's output render path), `NOTIFICATION-PLACEMENT` (layer ordering),
`TERMINAL-SURFACE` (real compositor transparency), `EXPOSE-LIFECYCLE`,
`APPLE-KEYS`, `WATCH-MODE` — which says in so many words that this compositor
advertises no input-inhibitor protocol and that the guard is built around that
fact — and `CAT-BED`, which depends on the lock's readiness record. Plus
`PACKAGE-CLOSURE`, `BUILD-HOST` and `BAZZITE-REPLAY`, because a compositor is a
new package with a new closure that does not travel to Fedora.

And the one that is not in `FEATURES.md` at all: **roughly fifteen helpers speak
sway IPC.** `decoration.py`, `decoration_watch.py`, `decoration_placement.py`,
`desktop_space.py`, `background_fade.py`, `carousel.py`, `showdesktop.py`,
`grid_overlay.py`, `expo.py`, `mission_control.py`, `oldbook-conky`,
`oldbook-resize`, `oldbook-center`, `oldbook-dropdown`, `oldbook-strata` and
every verifier under `alpine/tests/`. They use `get_tree` (4), `get_outputs` (3)
including SwayFX's own `layer_shell_surfaces` extension with per-surface
`extent`, the `run_command` channel, and the event subscription. A replacement
compositor must speak all of that, bug-for-bug, or fifteen programs and twenty
contracts stop at once. **That is the real cost of tier 3, and it is not the
rendering.**

**What it forecloses.** The stock-Sway recovery route, which `PERSONAL-DESKTOP`
and `SESSION-OWNERSHIP` both pin, and which is the thing that makes every other
experiment on this machine safe.

## Theseus, taken seriously

He said *"I don't want to lose anything."* Forty-three contracts is what that
sentence means in practice. The rule that makes it achievable is one sentence:

> **A plank that cannot be reverted in one command is the wrong plank.**

Everything below follows from that.

**Tier 1 touches nine contracts and need break none of them.**

| Contract | What tier 1 must do |
| --- | --- |
| `CONKY-READING` | Two things. Clip the `conky` surfaces out of every effect, because `BOTTOM` is one layer *above* them. And add `oldbook-edges` to the skip list in `desktop_space.screen_space`, beside `conky`, `wallpaper` and `oldbook-scripture` — a full-output surface at the origin happens to match none of that function's three edge tests today, but relying on that accident is how Conky starts reflowing, which the contract forbids outright |
| `DECORATION-PLACEMENT` | Exclusive zone **0**, not −1. `oldbook-background` uses −1 and copying it is the easy mistake; the caption band owns the only reservation on this desktop and a second one would resize every window |
| `ARTWORK-CROSSFADE` | Stay on `BOTTOM` and out of the background layer entirely. `background_fade.surface_order()` inspects only `layer == 'background'`, so a `BOTTOM` surface never triggers its `raise_canvas()` or the Conky restart in `restore_cards()`. A background-layer surface would have to be added to `CARD_NAMESPACES`; do not go there |
| `MOTION` | Frame clock only, stop when idle, settle without overshoot, honour `gtk-enable-animations = false` |
| `POWER-POSTURE` | Register on the ladder and install a `~/.config/oldbook/power.d/` hook, so a posture change *stops* the effect rather than merely declining to start it next time |
| `SCREEN-CORNERS` | Nothing load-bearing within 20 logical pixels of an output corner; the mask is applied after the whole scene |
| `THEME-COMPLETE` | Every colour is a palette role from `overlay_theme.read_palette`, never a shade chosen by eye |
| `FEEDBACK-OSD`, `NOTIFICATION-PLACEMENT`, `BAR-LAYOUT` | Nothing. They are on `TOP` and `OVERLAY`; `BOTTOM` cannot reach them |
| `SESSION-OWNERSHIP` | One owner per compositor session, started by `oldbook-session` through `start_service`, holding a lock file the way `oldbook-osd` does |

**Tier 2 additionally puts seven at risk**, and they are the ones with teeth:
`LOCK-THEME`, `APPLE-KEYS`, `EXPOSE-LIFECYCLE`, `WINDOW-SWITCHING`,
`CAROUSEL-STILLS`, `SHORTCUT-HELP`, `WATCH-MODE`. The mitigation is that each is
one scene and each scene migrates alone, with the existing implementation still
installed and still reachable by an environment variable, for at least one full
week of ordinary use before the old one is removed.

**Tier 3 puts twenty at risk** and they are enumerated above. There is no
mitigation that makes that a single plank. If it is ever attempted it is
attempted as a *second* session entry in greetd — `command = "/usr/local/bin/sim"`
in a copy of `/etc/greetd/config.toml`, with `/usr/local/bin/sway` untouched and
one line away — and it is not the default until it has been the non-default for
a long time.

**The order such that the desktop works at every step.** Backdrop before scenes;
scenes before compositor; within scenes, the ones that can crash safely before
the one that cannot. Concretely: edges → screensaver → power deck → launcher →
overview → *stop and ask* → lock. The lock is last in every ordering and it
follows the lock spec's staging, not this document's.

## The engine question, answered

Four candidates. The recommendation is a split, because the tiers want different
things.

**DragonRuby.** Licence: owned, and it forbids redistributing the runtime, which
collides with `PACKAGE-CLOSURE`'s "exact signed APK bytes, source inputs,
identities, hashes" and with `BAZZITE-REPLAY`'s allowlist copy. Battery: its
contract is a 60 Hz `tick` with no documented event-driven idle mode, which is
precisely the wrong shape for a ladder whose whole purpose is to stop drawing —
though I have not run it and this is recollection, not measurement.
Layer-shell: no, without one of the three shims above. `ext-session-lock-v1`: no,
categorically. Language: mruby, a third language in a Python desktop. Installed:
no. **Recommendation: not for any tier. Yes for a game, and yes as the
screensaver, where an ordinary fullscreen window is the correct shape anyway.**

**GTK4 + GSK + gtk4-layer-shell.** This is the desktop's existing scene engine
and it is better than its reputation: `carousel_view.spring_step` is exact
critically damped motion at frequency 40, independent of refresh rate;
`grid_overlay.Overlay` is a complete full-output layer-shell scene with a
190 ms frame-clock reveal, a 420 ms stall watchdog, theme reload, and a single
owner per session; `do_snapshot` gives rounded clips, textures and shadows
without a cairo context per frame. It reaches layer-shell on every layer,
including `BOTTOM`. It reaches GL through `Gtk.GLArea`. It is Python, which is
what the rest of this desktop is written in. **Recommendation: tier 1, and every
tier-2 scene that is not the lock.** The first plank is a small diff against
`grid_overlay.Overlay`, not a new program.

**Qt6 / QML, via `qml` or PyQt6, with `layer-shell-qt`.** The surprise of this
survey. `layer-shell-qt 6.7.4-r0` is *already installed*, pulled in by
`superhold`, which means this desktop already ships a Qt layer-shell application
in production. QtQuick brings `ShaderEffect` with `qsb`-compiled GLSL,
`QtQuick.Shapes`, `QtQuick.Particles` and `QtQuick.Effects`, and PyQt6 with
`QtQml`, `QtQuick` and `QtOpenGL` is importable from the system Python. The lock
spec says "there is no QML in this repository," and that is true of the *source*;
it is not true of the runtime, which is complete. He remembers doing QML work on
the alienware, and that memory is not misplaced — this machine can run it today.
**Recommendation: this is the better engine for authoring shaders and for the
declarative scene he remembers enjoying. If the first plank turns out to be
mostly shader work rather than mostly geometry, build it here instead.** The cost
is honest but smaller than it looks: Qt is already in the session and already
themed — `superhold` carries its own `theme.py` and every theme profile writes
`qt6ct` colours — so what is actually new is that no `oldbook-*` helper is
written in it yet, and one would have to be the first.

**C against wlroots, or QtWaylandCompositor.** Only for tier 3, and only after
(3a) has been tried.

**Two sentences, if only two are read.** DragonRuby is the wrong engine for every
tier of this vision, because SDL creates an `xdg_toplevel` and can reach neither
layer-shell nor `ext-session-lock-v1`, and its fixed 60 Hz loop is the wrong
shape for a power ladder — but it is exactly right for a game, launched from
Launchpad or run as the screensaver. Build tier 1 in the GTK4/GSK idiom that
`grid_overlay.py` already is, because the surface, the spring, the watchdog, the
theme reload and the single-owner lock are already written and tested; keep
Qt6/QML in reserve as the better shader-authoring engine, knowing that
`layer-shell-qt` is already installed and already in production here.

## The first plank: the edges

`oldbook-edges` is one process per compositor session owning one layer surface
per output.

**The surface.** `BOTTOM` layer, namespace `oldbook-edges`, anchored to all four
edges, **exclusive zone 0**, keyboard mode `NONE`, and an explicitly empty input
region — `input_shape_combine_region(cairo.Region(), 0, 0)`, exactly what
`oldbook-background` already does — so clicks pass through to the Conky reading
cards, which have their own `lua_mouse_hook` actions. Add `layer_effects
"oldbook-edges" { blur disable; shadows disable; corner_radius 0 }` to
`alpine/desktop/.config/swayfx/effects.conf` so SwayFX does not try to frost a
transparent full-output surface.

`BOTTOM` rather than `BACKGROUND` for three reasons, none of them aesthetic.
Layer ordering against `BACKGROUND` is guaranteed by the protocol, whereas
ordering *within* the background layer is map order and Conky maps last.
`background_fade.surface_order()` inspects only `layer == 'background'`, so a
`BOTTOM` surface cannot trip its restack logic or make it restart Conky. And the
one thing already living on `BOTTOM` — mpvpaper, from `oldbook-video-background`
and `oldbook-youtube` — is opt-in and rare, and the two should refuse to run at
the same time anyway.

The consequence is that `oldbook-edges` draws **over** the Conky cards, which is
why clipping them out is a requirement of the design and not a refinement of it.

**The free region.** A new `oldbook-space` publishes it and nothing draws from
IPC directly. It writes `$XDG_RUNTIME_DIR/oldbook/space.json`: the output
rectangle, the list of occupied rectangles, and a **72×45 occupancy grid**. That
resolution is not arbitrary — `oldbook-conky` already analyses the painting on a
72×45 grid through `conky_layout.analyze_image`, so a cell is 20×20 logical
pixels and the two grids register exactly. An effect can then ask "is this cell
free, *and* is the painting calm here" in one lookup, which is how effect 4
below works.

Occupied means: any window rectangle from `get_tree`; any `layer_shell_surfaces`
entry with an `extent`, which covers Waybar, the caption strip, the Scripture bar
and **every Conky panel**, since each panel is its own `conky`-namespace surface;
minus `oldbook-edges` itself. `desktop_space.screen_space` already does exactly
this reduction to produce four margins; this is the same reading kept as a region
instead. No new writer is needed anywhere — Conky does not have to publish its
placements, because SwayFX already reports them with output-local extents.

**How it watches, and the one place polling is unavoidable.**
`decoration_watch.TreeWatch` already exists and already solves this, including
the part that is not obvious: *sway sends no events during a pointer drag*, so a
window being dragged emits nothing until it is dropped. `TreeWatch` answers that
with three rates — `ATTACHED_INTERVAL` 1/120 s while a float is moving,
`QUIET_ATTACHED_INTERVAL` 1/60 s, and `IDLE_INTERVAL` 0.75 s — plus two-stage
deduplication on the raw frame bytes and then on a stripped geometry tuple.

`oldbook-space` should reuse it **at the idle rate only**, never the attached
rates. The free region then settles about 750 ms after a drag ends and never
tracks the drag live. That is 1.33 `get_tree` round-trips a second at rest, it
is cheap, and it is also *correct*: `DECORATION-PLACEMENT` already establishes
the precedent that a correction "waits for the rectangle to hold still, because a
drag emits no events and correcting mid-drag would fight the pointer." An
edge effect chasing a dragged window at 120 Hz would be ambient motion wearing a
disguise. For scale, `oldbook-decoration` reports one caption update at 0.29 ms
warm; the space grid is comparable work.

**The motion rule, which is not negotiable.** *"ABSOLUTELY NO MORE BREATHING
PAINTINGS! NONE! NEIN!"* That rejection is already permanent in code:
`air.py` carries `IMMUTABLE_PREFERENCES = {'wallpaper': False}` with a comment
saying a switch that must always be off is better removed than defaulted, so the
wallpaper breath cannot be re-enabled by any file, toggle or caller. Treat that
as the standard.

Concretely, here: the only redraw sources are a sway layout event, a pointer
motion event, a palette change and a painting change. There is no frame clock
running at rest — both of `oldbook-background`'s tick callbacks return
`GLib.SOURCE_REMOVE` when nothing is moving, and this daemon must do the same.
Every animation is a bounded response to a discrete cause, settles with
`spring_step` and stops. `~/.config/oldbook/edges.json` gets a key per effect and
a master `enabled`, beside the existing `breath.json`, so there is one obvious
place to switch each one off. `gtk-enable-animations = false` skips every
transition and leaves the static form.

### Four designs, and a fifth

Each has a **full** form, a **cheap** form and a ladder rung. Colours are palette
roles so a generated theme lands exactly. All five draw only inside the free
region — which means clipped against the windows *and* against the Conky panels,
the Scripture bar, Waybar and the caption strip, because on `BOTTOM` the surface
is above every one of them.

**1. Edge charge — the rail.** Along every boundary between free space and an
occupied rectangle, a 3 logical-pixel line in `accent` at 0.18 alpha, with a
24 px falloff into the free side only and nothing on the occupied side. It is
static. When a window opens, closes, moves or resizes, a pulse runs along *that
window's* boundary from the corner nearest the change, at roughly 2600 logical
px/s, brightening the rail to 0.55 alpha over a 180 px arc and decaying to rest
over 320 ms. A workspace switch pulses every boundary at once. Nothing else
triggers it.

Geometry: the boundary is the outline of the free region, which falls straight
out of the occupancy grid as a marching-squares contour — about 200–400 segments
for a typical layout. Drawing is one stroked path plus a gradient parameterised
by arclength. Cost: a few thousand vertices, once per event, then 320 ms of
frame-clock work over a damage rectangle bounded by the changed window plus
24 px. *Cheap form:* the rail, no pulse. *Ladder:* pulse at `battery`, rail at
`battery-low`, nothing at `battery-critical`.

This is the direct answer to "cool shit along the sides of windows."

**2. Parallax starfield.** The free region carries stars in three depth planes —
roughly 140, 90 and 40 points, radii 1.0, 1.6 and 2.4 logical pixels, in
`foreground`, `muted` and `accent_secondary` at 0.10, 0.16 and 0.22 alpha —
seeded deterministically from the current painting's OKLab hue signature, so the
sky belongs to tonight's picture and is identical every time that painting comes
back. The stars never move on their own; there is no twinkle and no drift.
Pointer motion offsets plane 1 by 0.4% of pointer travel, plane 2 by 1.1% and
plane 3 by 2.4%, clamped to ±14 logical pixels, and each plane returns to zero on
a spring when the pointer stops. So depth exists only while he is moving the
pointer, which is the one motion he explicitly welcomed.

Cost: three textures, three translate nodes, one damage rectangle per motion
event. *Caveat, stated because it is the interesting one:* `screen-corners.patch`
calls `wlr_output_lock_software_cursors(wlr_output, true)`, so every pointer
motion **already** causes a full-output recomposite. Parallax rides a cost that
is already being paid — but it also dirties SceneFX's optimized-blur buffer,
which is not already being paid. Measure it here. *Cheap form:* one plane, no
parallax. *Ladder:* three planes at `mains`, one at `battery`, still at
`battery-low`, off at `battery-critical`.

**3. The shore — an isoline map of the free region.** Five contour lines at 12,
28, 52, 88 and 140 logical pixels from the nearest occupied edge, in `border` at
0.22, 0.17, 0.13, 0.09 and 0.06 alpha, clipped to free space. It draws the
*shape* of where the windows aren't, as a chart. Entirely static; when the layout
changes the old contours cross-fade to the new ones over 180 ms.

Geometry: a Euclidean distance transform over the 72×45 grid is 3240 cells and
takes microseconds in numpy, which is already a dependency. Full form uploads it
as a 72×45 R8 texture and samples it in a fragment shader, which gives smooth
isolines for free; the path form marches five contours and strokes them. *Cheap
form:* two contours, no cross-fade, path only. *Ladder:* shader at `mains`, paths
at `battery`, two contours at `battery-low`, off at `battery-critical`. The
shader rung gates on the ladder's existing `'shaders': 'mains'` entry, which
currently has **no consumer at all** — it is a reserved name waiting for exactly
this.

**4. The signal margin.** The desktop's identity is a radio station. In cells
that are free, unclaimed by Conky, *and* calm in `conky_layout`'s own detail
grid, lay a sparse field of dial graduations: a 1×7 logical-pixel tick every
20 px along the cell grid in `muted` at 0.14 alpha, with a taller 1×13 tick every
fifth. It reads as the minor graduations of a tuning scale running through the
empty parts of the screen. It never moves. On a **deliberate** gallery change —
not the twenty-minute timer, not the idle drift — the ticks re-seed with a 240 ms
wipe from the side the new painting arrived from, matching
`ARTWORK-CROSSFADE`'s 0.8 s deliberate-change fade.

Cost: a few hundred one-pixel rectangles in one snapshot node; one paint per
layout change. *Cheap form:* ticks only on the two edges with the most free
space. *Ladder:* runs at every rung including `battery-critical`, because one
paint per layout change is genuinely free.

**5. Window wake, if the others land.** A closing window leaves its outline in
`border` at 0.3 alpha, shrinking to nothing over 260 ms on `spring_step` at
frequency 40. An opening window gets the reverse. This is `window-ghosts`, which
is a **reserved name already on the power ladder at `battery` with no
implementation**. One caution: SwayFX's `window-animations.patch` already pops
windows in from 0.8 scale over 160 ms and out over 130 ms. The wake is the
backdrop's answer to that motion and must not double it — it should read as the
space remembering, not as a second animation of the same window.

### Registering on the ladder

Add `'desktop-edges': 'battery-low'` to `power_source.LADDER` and gate the
shader rungs on the existing `'shaders': 'mains'`. Install a hook in
`~/.config/oldbook/power.d/` so a change in posture reaches a running daemon.
`oldbook-power-mode allows desktop-edges` then answers by exit status, and
`oldbook-power-mode show` lists it among what is shed, which is where he will
look for it.

## What the lock means here

The lock client spec's recommendation stands and this document does not
supersede it: **do (a+) — a custom indicator inside swaylock-effects — before
anything bespoke.** A sim that owns the lock is that spec's route (b), and route
(b) is explicitly staged third, after (a+) has been lived with.

The failure mode that spec established is the reason, and it deserves repeating
in full because it is counter-intuitive: under `ext-session-lock-v1`, a lock
client that dies without sending `unlock_and_destroy` does **not** fail open. The
compositor keeps the session locked and paints its abandoned-lock colour, with no
password prompt at all, until a replacement client takes the lock. It fails
**stuck**: safe and unusable. A game engine's main loop dying at minute forty of
a lock produces a laptop that must be rescued from another VT with `loginctl
unlock-session` — and note `APPLE-KEYS`, so the function row needs `Fn`.
`oldbook-lock supervise` restarts a signal-terminated locker up to five times
with `strip_first_run_options` removing `-R`, `--fade-in` and `--screenshots`,
and that mechanism is the only thing standing between a mid-lock crash and that
outcome. Its restart latency is, per that spec, the single most important
unmeasured number on this machine.

**One correction to that document, made explicitly rather than silently.** It
says: *"`gtk4-session-lock` is not in Alpine. `apk search` finds gtk4-layer-shell
and its dev/doc/demo and hare bindings, and nothing else."* The GTK **4**
library is indeed absent. But `gtk-session-lock 0.2.0-r0` — wmww's GTK **3**
companion library — **is** packaged, in `edge/testing`. That matters for two
reasons. It removes the "does it even exist" risk from route (b2), at the price
of GTK 3 instead of GTK 4. And this desktop already runs a GTK 3 layer-shell
daemon in production: `oldbook-osd`, on `gtk-layer-shell 0.10.1`. So the cheapest
real bespoke locker here is GTK 3 + `gtk-session-lock` + `GtkGLArea`, written in
the `oldbook-osd` idiom, not GTK 4 in the `carousel_view` idiom.

That is a genuine trade and it should be put to him rather than decided here:
GTK 4's `do_snapshot` scene graph and springs, needing an APKBUILD and a remote
build for a library that may not work against GTK 4.22 and wlroots 0.20; or
GTK 3's plainer drawing model with the library already packaged and the house
style already established.

And note what is *not* on the table. `layer-shell-qt` gives Qt the layer-shell
role and nothing else; there is no packaged Qt equivalent of `gtk-session-lock`,
so `ext-session-lock-v1` from Qt means writing the protocol binding by hand.
This is the clearest case in the document of different tiers wanting different
engines: the lock is the one surface where the toolkit is chosen by which
library exists, not by which is nicer to author in.

Everything else in the lock spec is unchanged by this document: the readiness
handshake, `flock` serialization, process and compositor identity, no grace
period, the power-key inhibitor for the locker's life, the four-layer
degradation ladder, the input rules (pointer and trackpad may drive anything;
keys drive one quantised, smoothed scalar and nothing else), and the four-rung
power table.

## Login

There is no login screen, deliberately. `/etc/greetd/config.toml` autologins
`jack` into `/usr/local/bin/sway` on vt1 in both `initial_session` and
`default_session`, and its own comments say why: the encrypted root passphrase is
the real gate and a second prompt buys nothing. `BOOT-CONSOLE` treats the LUKS
prompt as the login screen and themes it accordingly.

So "rebuild the login" means the boot chain, and the boot chain is already
themed: a GRUB theme with PF2 fonts compiled from JetBrains Mono over a blurred
crop of the Space Ghost painting; sixteen console colours generated by
`bin/build-console-palette` from the active theme's terminal palette and passed
as `vt.default_red/grn/blu`, `vt.color=0x0F` and `fbcon=font:TER16x32`; a
rendered `/etc/issue` on the rescue gettys; and a non-default GRUB entry that
boots a Ghost Planet banner initramfs.

**What a sim cannot reach, and this is most of it.** GRUB runs before Linux —
no DRM, no GPU, no Wayland, nothing a game engine can address. The initramfs LUKS
prompt runs on the framebuffer console before any compositor exists; reaching it
means a Plymouth-class DRM splash, Alpine does not package Plymouth, and that is
its own project with its own risk of a machine that cannot be unlocked. The
kernel console and the rescue gettys are text mode by construction and their
value is that they still work when everything graphical does not.

**What a sim can reach** is the seam after greetd execs sway and before the
desktop is up. A *cold open*: the session's first act maps a fullscreen layer
surface, plays a bounded 600 ms opening — the same discrete, event-driven
vocabulary as everything else here, triggered by the one event of the day that is
unambiguously his, switching the machine on — and unmaps. It is entirely inside
tier 1's surface model, it holds no security property, and it can be deleted by
one line. That is the honest scope of "the sim owns the login."

**And the thing that outranks every idea in this section**: none of the boot
chain has ever been seen on a real boot. `grub-emu` is not packaged, so the menu
preview is a simulation drawn by our own renderer. One reboot with a camera is
worth more than anything proposed here.

## Migration order

Each plank is revertible by one command, and the desktop is complete after every
one of them.

| # | Plank | Revert |
| --- | --- | --- |
| 0 | `oldbook-space` publishes the free region to `$XDG_RUNTIME_DIR/oldbook/space.json`, driven by `decoration_watch.TreeWatch` at `IDLE_INTERVAL` only. Nothing draws. Verify by comparing its grid against `grim` captures of known layouts | Stop the service; nothing reads it |
| 1 | `oldbook-edges` maps the `BOTTOM` surface and draws **effect 4 only**, which never animates. This proves the layer order, the clipping of Conky and the bar, the empty input region (a reading card still takes its click), the zero exclusive zone, the theme wiring, and that Conky did not reflow | Remove one line from `oldbook-session` |
| 2 | Effect 1's rail, static. First thing that reads the layout | `edges.json` |
| 3 | Effect 3's shore, path form, with the 180 ms cross-fade. **First animation of any kind — measure the SceneFX blur cost here and stop if it is bad** | `edges.json` |
| 4 | Effect 1's pulse and effect 5's wake. Event-driven motion | `edges.json` |
| 5 | Effect 2's starfield and pointer parallax. First redraw on pointer motion; measure again | `edges.json` |
| 6 | The `mains` shader rungs, gated on the ladder's existing `shaders` entry | `oldbook-power-mode override battery` |

Plank 3 is the gate. If dirtying the optimized-blur buffer costs what it might,
the answer is not to abandon the plank — it is that every effect stays in its
static form, which is what he asked for anyway, and the pulses become the
exception rather than the rule.

## Guesses, and what would settle them

Marked, because in six months it will not be obvious which of these were
measured.

- **Guessed, and the most important**: that an animating `BOTTOM`-layer surface
  invalidates SceneFX's optimized-blur buffer every frame, forcing a full-output
  dual-Kawase pass at 5.18 Mpix for the life of the session. *Settled by*: a
  twenty-line GTK4 layer surface that alternates two colours at 60 fps, one
  blurred transparent terminal on screen, and `SWAYFX`/GPU frame times with and
  without it. This is a two-hour experiment and it decides the whole plank.
- **Guessed**: that SDL3 exposes a custom-surface-role window property and the
  `wl_surface`/`wl_egl_window` pointers. *Settled by*: `apk add sdl3-dev` on a
  build host and one grep of the headers.
- **Unverified**: whether DragonRuby links the system `libSDL2-2.0.so.0` or
  bundles its own. *Settled by*: `ldd` on the runtime, which requires installing
  it — on a build host, not here.
- **Recollection, not measurement**: that DragonRuby's `tick` is a fixed 60 Hz
  with no event-driven idle mode. *Settled by*: reading the contrib repo's docs,
  which he already has access to.
- **Settled while writing this**: Conky is on `BACKGROUND`, not `BOTTOM`
  (`own_window_type = 'desktop'`, namespace `conky`, one process per panel), so
  `oldbook-edges` on `BOTTOM` is reliably *above* it and must clip it out. The
  layer map in *Ground truth* is the record.
- **Guessed**: that a `BOTTOM`-layer surface and mpvpaper's `--layer bottom`
  surface coexist sanely when `oldbook-video-background` is running. Probably
  they should simply refuse to run together. *Settled by*: starting the video
  background with the edges daemon up.
- **Guessed**: that `layer-shell-qt 6.7.4` works against Qt 6.11.1 here beyond
  whatever `superhold` exercises. It is installed and something uses it, which is
  most of the way, but nothing has been tried on the `BOTTOM` layer. *Settled
  by*: twenty lines of QML and `qml -- file.qml` with
  `QT_WAYLAND_SHELL_INTEGRATION=layer-shell`.
- **Guessed**: that `gtk-session-lock 0.2.0-r0` from edge/testing builds and
  works against wlroots 0.20's `ext-session-lock-v1`. *Settled by*: one remote
  build and one headless lock, which is exactly the shape of evidence
  `alpine/verification/lock-screen/` already contains.
- **Not attempted**: any measurement of power draw. The lock spec's guess of
  2–5 W for a 60 fps fullscreen composite applies here too and applies for the
  whole session rather than for the length of a lock, which makes it worse.

## Rollback

Nothing in this document is installed, so there is nothing to roll back yet.

Each plank exits on its own: planks 2–6 are one key in
`~/.config/oldbook/edges.json`; plank 1 is one line removed from
`oldbook-session`; plank 0 is stopping a service nothing else reads. `apk` state
is untouched throughout — tier 1 as recommended installs no package.

Tier 2's exits are the ones the existing contracts already provide:
`OLDBOOK_LOCK_BACKEND=effects` or `=stock` for the lock, and the current binding
for each overview key.

Tier 3's only honest exit is `command = "/usr/local/bin/sway"` in
`/etc/greetd/config.toml`, which is why it must never be the only entry there.
