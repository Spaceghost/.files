# Pinned desktop features

These are the current behavioral contracts for the Spaceghost desktop. Preserve
them across theme changes, package updates, refactoring and recovery. A pin is
not a claim that every hardware scenario has been tested.

An explicit new user instruction can change a pin: update its contract and
record what it supersedes. Otherwise, ask about an actual conflict before
removing or changing a pinned behavior, and continue independent work while
waiting. Do not manufacture a conflict from an intentional replacement listed
below. Preserve unrelated work by other sessions; an already implemented fix
should be reviewed and integrated rather than overwritten or duplicated.

Each ID is stable. The linked source implements the contract; tests and retained
runtime evidence describe its verification boundary. A passing historical test
does not establish that a newer edit is installed or that a physical input was
tested. Keep personal state and user preferences separate from presentation.

Before editing, run `alpine/bin/check-features <path> ...` from `~/.files`.
Without paths it inspects pending Fossil changes, including new hidden files.
`--all` lists the complete index; `--feature GHOST-BRAND --run` runs that
feature's existing automated checks. Shared checks run once and any failure
makes the command fail. [feature-checks.json](feature-checks.json) is the impact
and check index; this document is the authority for desired behavior. Unmapped
paths and contracts without automated checks still require review and the
relevant native/visual checks. Neither the tool nor a passing test authorizes
removing a pin.

## Themes and desktop appearance

### THEME-COMPLETE

Every built-in and generated theme is a complete desktop design: palette,
typography, geometry, spacing, window treatment, launcher, widgets, application
styling and matching artwork. Switching must apply it across the desktop.
Shared controls, personal content, quiet-panel policy and saved decoration
preferences survive. The pointer set is part of the design: Oldbook-Ghost
redraws the waiting shapes as a turning amber ring and inherits every other
shape from the installed Simp1e Gruvbox set, so a theme switch never leaves the
cursor behind. Selecting the current theme must permit reapplication;
application failures must be visible instead of reporting an unqualified success.

- Implementation: [oldbook-theme](desktop/.local/bin/oldbook-theme),
  [desktop_theme.py](wallpapers/desktop_theme.py), [profiles](themes/profiles/),
  [cursor generator](bin/build-cursor-theme).
- Checks: [complete themes](tests/test_complete_themes.py),
  [theme switch](tests/test_theme_switch.py), [theme picker](tests/test_theme_picker.py),
  [application refresh](tests/test_application_theme_refresh.py),
  [cursor theme](tests/test_cursor_theme.py) with
  [drawn frames and a session load](verification/animated-cursors/README.md).
  [Recorded previews](verification/complete-themes/) cover selected themes;
  they do not prove every running application accepts every change immediately.

### GHOST-BRAND

Keep the original Ghost badge and its own white/purple/pink colors across themes.
The glyph stays centered in its button. Its original 21px presentation uses
white `#fff6ff`, purple/pink `#b765eb`, `#77369e`, `#ce579e`, and glow `#e3baff`;
hover uses `#d997ff`, `#a355d7`, `#f284bd`. This is an explicit branding exception
to theme recoloring, not permission to stop theming other controls.

- Implementation: [Waybar CSS](desktop/.config/waybar/style.css),
  [profile rendering](wallpapers/desktop_theme.py).
- Checks: [branding regression](tests/test_ghost_branding.py),
  [native restoration evidence](verification/ghost-branding/README.md).
  Restoring source/profile branding alone does not prove the live bar reloaded it.

### LOCK-THEME

The lock dissolves from the desktop into the current painting blurred, darkened
and vignetted, with a clock and date on an idle-invisible ring, a caption card
(painting title and story, the hour's Scripture, Ghost Planet mark), and the
amber ring, key highlights, verification, failure, cleared and Caps Lock states
in the active validated palette. No grace period. swaylock-effects runs under
the helper's own supervisor with the ready-fd handshake; stock swaylock under
swaylockd remains the automatic fallback. Lock acquisition must wait for actual
readiness, serialize concurrent requests and reject stale process/compositor
identities; a matching process name is insufficient.

A locked session ignores the power key. The MacBook's power key sits beside
Backspace and elogind powers the machine off on a short press, counting each
autorepeat of a held key as another press, so the locker is launched holding a
`handle-power-key` block inhibitor and holds it for exactly as long as it lives,
however it ends. The inhibitor comes from whichever login manager the host runs
— `elogind-inhibit` here, `systemd-inhibit` on the Bazzite replay — and its
`PowerKeyIgnoreInhibited` must stay `no` for that to hold. A missing or refused inhibitor must never prevent locking: a
power key that still works is not a reason to leave the session open. The
several-second hold the SMC turns into a hardware power cut sits below Linux
and stays out of reach.

- Implementation: [oldbook-lock](desktop/.local/bin/oldbook-lock),
  [lock scene](desktop/.local/lib/oldbook/lock_scene.py),
  [coexisting swaylock-effects](packages/swaylock-effects/README.md).
- Checks: [lock regressions](tests/test_lock.py),
  [headless lock evidence](verification/lock-screen/README.md),
  [recorded settings/theme work](PROGRESS.md#2026-09-07--theme-aware-desktop-decoration-settings-and-native-tools).
  Headless captures are not a physical lock; the first live lock after this
  change remains the user's check.

### BAR-LAYOUT

Keep workspace controls on the left, previous/play-pause/next music in the
middle, and desktop/status controls on the right. Window titles belong in the
decoration, not a resurrected center title subbar. Preserve helpful, characterful,
valid GTK tooltips and native modified clicks. Music actions target the displayed
player; Pithos supports delayed single-click playback, double-click open,
right-click show/hide, middle-click tired and Super+middle-click ban.
The optional `custom/cava` signal meter sits after the media controls, has no
clicks or tooltip, collapses when silent, stops cava when nothing plays, and is
removable by deleting it from `modules-center`.

- Implementation: [Waybar config](desktop/.config/waybar/config.jsonc),
  [Pithos controls](desktop/.local/bin/oldbook-pithos), [native artwork module](packages/waybar-art/art.c).
- Checks: [Pithos tests](tests/test_pithos_controls.py),
  [music verifier](tests/verify_waybar_music.py), [bar recovery](tests/test_bar_ipc_recovery.py),
  [recorded bar interactions](verification/waybar-reactivity/README.md).

### DECORATION-STYLE

Use a blended, translucent themed gradient with no outline pixel border.
Retain app icon, readable title, window state, helpful hover text and interactive
window/workspace controls. Bottom is the saved default; right-edge placement
remains available. The preference editor exposes placement, opacity and corners
beside editable JSON, validates changes and refuses stale overwrites. Preserve
the user's saved values, currently bottom / 0.67 opacity / radius 7. Caption
typography follows the active theme's design typeface (Inter Medium for Gruvbox
Dark) one point above the terminal size, left-aligned with Ghost Observatory
padding; a theme without a design font keeps the terminal font.
The accent wash behind the brand button follows the keystroke breath alone,
between 0.06 and 0.22 alpha on its own stylesheet provider; the plain breath,
the last breath and a stopped worker leave the strip at its resting value.

- Implementation: [decoration helper](desktop/.local/bin/oldbook-decoration),
  [settings editor](desktop/.local/bin/oldbook-decoration-settings),
  [preferences](desktop/.config/oldbook/decoration.json).
- Checks: [decoration tests](tests/test_decoration.py),
  [settings verifier](tests/verify_decoration_settings.py),
  [interactive strip evidence](verification/decoration-context/).
  The initial contextual-menu work explicitly left some tmux/media actions unprobed.

### DECORATION-PLACEMENT

Attach the caption to the focused ordinary floating window without reserving
workspace space. Actual fullscreen on its visible workspace forces the workspace
bottom caption; global fullscreen applies on every output. Hidden-workspace
fullscreen does not interfere. Restore the saved edge afterward. Fullscreen tiled
captions have square corners; ordinary/floating captions retain chosen rounding.
Console and monitor drop-downs preserve the preceding ordinary caption. Tile/float
handoffs are immediate and must not leave overlapping caption surfaces.

- Implementation: [placement](desktop/.local/lib/oldbook/decoration_placement.py),
  [caption model](desktop/.local/lib/oldbook/decoration.py).
- Checks: [placement tests](tests/test_decoration_placement.py),
  [attachment verifier](tests/verify_decoration_attachment.py),
  [immediate transitions](verification/decoration-transition/README.md),
  [monitor exclusion](verification/decoration-monitor/README.md).
  Physical mixed-output/hotplug behavior remains a separate check.

### MOTION

Aim for at least 60fps, smooth continuous motion, preserved velocity and exact
settling without overshoot. Use display frame clocks; stop animation when idle.
Avoid redundant resize/layout work and unbounded update queues. Honor disabled
desktop animations. Do not trade away high-quality still previews silently.
React on the first available frame and prioritize compositor/UI work under load.
Child applications and background jobs must retain ordinary scheduling priority.

- Implementation: [decoration motion](desktop/.local/lib/oldbook/decoration_motion.py),
  [watcher](desktop/.local/lib/oldbook/decoration_watch.py),
  [carousel renderer](desktop/.local/lib/oldbook/carousel_view.py),
  [bounded scheduling helper](bin/oldbook-ui-priority).
- Checks: [motion tests](tests/test_decoration_motion.py),
  [watcher tests](tests/test_decoration_watch.py),
  [frame-rate evidence](verification/decoration-framerate/README.md),
  [carousel timing limits](verification/carousel-quality/native-README.md).
  Headless callbacks/draws are not physical scanout: sustained physical 60fps,
  mixed refresh and every workload are not proven.

### NOTIFICATION-PLACEMENT

Notifications appear over ordinary windows without moving/resizing them, taking
terminal focus or sliding out a panel. Keep notification surfaces on TOP below
overlay stay-on-top chrome, with no exclusive zone. Only an explicit action opens
compact history. The empty host stays transparent; style actual cards rather
than blurring/shadowing/clipping the entire hosting surface. The control center
carries the playing MPRIS track with album art, sound and brightness sliders and
a quick-action grid above the history; those widgets are additive and never
change popup placement or the bar's notification clicks.

- Implementation: [SwayNC config](desktop/.config/swaync/config.json),
  [SwayFX effects](desktop/.config/swayfx/effects.conf).
- Evidence: [notification placement](verification/notifications/),
  [host transparency diagnostic](verification/notification-overlay/),
  [control-center widgets](verification/swaync-widgets/) rendered by
  [verify_swaync_widgets.py](tests/verify_swaync_widgets.py).
  These are layer-shell popups with the requested nonintrusive behavior,
  not ordinary Sway-managed floating containers.

## Windows, workspaces and input

### WORKSPACE-IDENTITY

The 0 key selects numeric workspace 10, Strata, after 1–9. Only the dedicated
Strata–Fossil window is anchored there; recover it there without stealing focus
during background startup. Create named workspaces immediately with titlecase
labels. Active number/name are bold and bright; inactive numbers remain bold,
names regular, and process suffixes regular/subdued. Keep original application
identities and prevent accumulating title suffixes.

- Implementation: [workspace model](desktop/.local/lib/oldbook/workspace_model.py),
  [defaults](desktop/.local/lib/oldbook/workspace_defaults.py),
  [Strata](desktop/.local/bin/oldbook-strata), [native labels](packages/waybar-art/help.c).
- Checks: [workspaces](tests/test_workspaces.py), [defaults](tests/test_workspace_defaults.py),
  [Strata](tests/test_strata.py), [creation evidence](verification/workspace-ready/README.md),
  [titlecase](verification/workspace-titlecase/README.md), [workspace ten](verification/workspace-ten/README.md).

### WINDOW-SWITCHING

Super+Tab and Alt+Tab share all normal windows across workspaces in true recent
focus order. Freeze the list while held; Shift reverses, release selects and
Escape cancels to the origin. Quick taps alternate the last two windows.
Ordinary Tab/Ctrl+Tab remain application keys. Preserve native keyboard grabs,
close-before-focus ordering, stale-command protection and single-owner recovery.
Agent navigation remains separately available on Super+i / Super+Shift+i.

- Implementation: [controller](desktop/.local/lib/oldbook/carousel.py),
  [switching model](desktop/.local/lib/oldbook/window_switching.py).
- Checks: [selection](tests/test_window_switching.py), [controller](tests/test_carousel.py),
  [responsiveness](tests/test_carousel_responsiveness.py),
  [native navigation](verification/window-navigation/README.md).
  Retain newer race/failure evidence; an earlier passing run does not certify a later candidate.

### CAROUSEL-STILLS

The themed angled carousel uses actual per-window, aspect-correct high-quality
still images, including hidden workspaces, without visiting or focusing them.
Capture once per candidate per opening; changes underneath, title changes and
revisiting a card do not refresh it. Reopening does. Keep all pixels supplied by
the capture provider, use trilinear sampling and discard image memory on close.
Capture failure has an honest fallback; input never waits for image generation.

- Implementation: [capture/controller](desktop/.local/lib/oldbook/carousel.py),
  [renderer](desktop/.local/lib/oldbook/carousel_view.py).
- Checks: [controller](tests/test_carousel.py), [geometry](tests/test_carousel_view.py),
  [quality evidence](verification/carousel-quality/README.md).
  Full provider resolution need not equal a Retina client's physical buffer;
  enlarging a capture artificially is not higher quality.

### EXPOSE-LIFECYCLE

Four-finger up clears the desktop; down restores exposed windows, or opens the
persistent all-workspace carousel when nothing is hidden. The persistent view
supports arrows, Tab/Shift+Tab, scrolling, card clicks, Enter and Escape. External
navigation ends expose safely, restores captured content where needed and
preserves the destination the user chose. Do not replay stale geometry later.

- Implementation: [showdesktop](desktop/.local/lib/oldbook/showdesktop.py),
  [gesture bindings](desktop/.config/sway/gestures.conf).
- Checks: [lifecycle](tests/test_showdesktop_lifecycle.py),
  [showdesktop](tests/test_showdesktop.py), [native recovery](verification/showdesktop-recovery/README.md).
  Synthetic gesture commands do not prove physical trackpad recognition.

### WINDOW-RESIZE

Super+Shift+Space exits fullscreen, enables floating, resizes to 90% of usable
workspace space with at least 24 logical pixels of breathing room, and centers.
Repeated presses reapply the same size, not a toggle. Preserve existing centered
plus/minus resize and center/raise controls. Pointer dwell raising waits one
second on the same eligible floating window and cancels stale targets.

- Implementation: [resize](desktop/.local/bin/oldbook-resize),
  [center](desktop/.local/bin/oldbook-center), [bindings](desktop/.config/sway/local.d/resize.conf).
- Checks: [resize tests](tests/test_centered_resize.py),
  [native geometry](verification/near-full-resize/README.md),
  [center](verification/center-window/README.md), [dwell](verification/hover-raise/README.md).
  Packaged dwell behavior was verified privately; its recorded activation still
  required a new graphical login to replace the running compositor.

### APPLE-KEYS

The engraved Mission Control/F3 key opens or closes Mission Control, the
workspace overview; Launchpad/F4 opens or closes the Launchpad application grid
and exits an overview first. This supersedes F3 meaning the window carousel and
F4 the Fuzzel launcher, both of which keep their own bindings. Fn+F3/F4 remain
application function keys. Preserve Caps Lock as Escape, including with Shift.
Keyboard illumination controls retain off/brightness preferences across login;
Sway reload does not reset them. Do not change hid_apple mode incidentally.

- Implementation: [Sway input](desktop/.config/sway/config),
  [Apple overview bindings](desktop/.config/sway/local.d/apple-overview.conf),
  [keyboard light](desktop/.local/bin/oldbook-keyboard-backlight).
- Implementation: [Launchpad](desktop/.local/lib/oldbook/launchpad.py),
  [Mission Control](desktop/.local/lib/oldbook/mission_control.py),
  [shared overlay](desktop/.local/lib/oldbook/grid_overlay.py).
- Checks: [Apple mapping](tests/test_apple_overview.py), [grids](tests/test_grids.py),
  [headless renders](verification/launchpad-mission-control/README.md),
  [native overview](verification/apple-overview/README.md),
  [keyboard-light evidence](verification/keyboard-backlight/README.md).
  Distinguish synthetic native key events from physical engraved-key tests.

### KEYBOARD-GLOW

The MacBookPro11,5 exposes one whole-keyboard Apple SMC light, range 0–255;
do not promise individual key or RGB control. Preserve F5/F6 and locked-session
brightness controls, including fully off and ordinary Fn function keys.
Shift+F6 toggles a gentle six-second breath; Shift+F5 restores steady light.
Ctrl+XF86KbdBrightnessUp adds a typing rise effect that brightens on keypress and
then decays with no extra user input; Ctrl+XF86KbdBrightnessDown starts bright
and decays toward dark while you type and returns toward bright when you pause.
Ctrl+Shift+XF86KbdBrightnessUp adds a sustained-typing mode that only reacts
when average typing speed stays above about 22 WPM; slow typing leaves the light
at its decayed level. Ctrl+Shift+XF86KbdBrightnessDown adds an
inverse sustained mode: it starts bright and only darkens while typing remains
above that threshold, then recovers as you pause. The device remains whole-keyboard
Apple SMC output.
Option/Alt+XF86KbdBrightnessUp adds an ambient mode that follows the Apple SMC
light sensor (`/sys/devices/platform/applesmc.*/light`): bright keys in a dark
room up to the saved peak, off in daylight, with log-scale smoothing, a hysteresis
band and a short fade so the light never flickers. It persists like the other
modes, F5/F6 still move the peak, and it is refused when no sensor is readable.
Option/Alt+Shift+XF86KbdBrightnessUp adds `breathe-air`: a continuous breath
whose lungs start a quarter full at about seven seconds per cycle, take a fixed
sip from every keystroke up to full (three seconds per cycle at full amplitude),
leak back toward the quiet baseline with a twenty-second time constant while
idle, and keep a continuous phase so no keystroke ever jumps the light.
Keep the same controls and same
mode persistence rules as the existing features.
While any breathing mode runs, the worker publishes the breath itself to
`$XDG_RUNTIME_DIR/oldbook/air.json` about twenty times a second: mode, lung
volume, phase, the normalised brightness of the curve and the tempo, with one
closing record when it stops. It is the desktop's shared clock for the breath;
a record older than half a second counts as no breath at all. Publishing never
changes a saved level or mode, and the typing and ambient modes publish nothing.
The Ghost control deck exposes the same controls with useful descriptions.
While breathing, F5/F6 adjust the saved peak; off stops the animation.
Keep the selected level and mode across logins and leave them alone on reload
or theme changes. Animation samples must never replace the saved brightness.
One worker controls the physical keyboard, uses elapsed time, skips redundant
writes and restores the chosen level on shutdown or compositor loss. Keep the
Caps Lock attention indicator and display backlight separate.
Shortly before the idle lock, `oldbook-idle dim` eases the display down to about
20% and asks for one `last-breath`: a short rise, a long fall to fully dark, then
dark until activity. The last breath is a runtime overlay, never a saved level or
mode; keys that are off by preference stay off; any explicit key or `restore`
ends it, and `oldbook-idle undim` restores the display unless it was adjusted
meanwhile. The keyboard's saved level and mode survive the whole cycle.

- Implementation: [keyboard light](desktop/.local/bin/oldbook-keyboard-backlight),
  [bindings](desktop/.config/sway/local.d/keyboard-backlight.conf),
  [control deck](desktop/.local/bin/oldbook-control),
  [idle stage](desktop/.local/bin/oldbook-idle), [session](desktop/.local/bin/oldbook-session).
- Checks: [state and lifecycle](tests/test_keyboard_backlight.py),
  [idle dim](tests/test_idle_dim.py),
  [hardware evidence](verification/keyboard-breathing/README.md),
  [ambient and last-breath evidence](verification/keyboard-ambient/README.md).
  A 60Hz update target and sysfs readback do not prove optical refresh timing;
  the kernel can coalesce writes. Suspend/resume and physical keypresses need
  their own observation.

### SHORTCUT-HELP

Hold Super alone for half a second for a contextual, themed shortcut guide;
release or another key dismisses it. A fresh Super press also closes it without
immediate reopening. Scrolling must not steal keyboard focus. Keep it hidden
while locked/inactive; preserve personal trigger/settings and existing application
profiles. Tooltips and help must describe the current controls, with character.

- Implementation: [guide launch](desktop/.config/sway/local.d/shortcuts.conf),
  [shortcut helper](desktop/.local/bin/oldbook-shortcuts),
  [shortcut sources](desktop/.local/lib/oldbook/shortcut_sources.py),
  [local guide package](packages/superhold-guide/manifest.json).
- Checks: [hold](tests/test_shortcut_hold.py), [service](tests/test_shortcut_service.py),
  [sources](tests/test_shortcut_sources.py).
  Verify the actual service launch path; the portable wrapper and installed
  full guide are distinct implementations in this checkout.

### CLIPBOARD

Preserve Wayland clipboard integration and history, including copy/paste through
the supported terminal/tmux workflow. Keep personal clipboard data out of the
repository and package payloads; changing a theme must not erase it.

- Implementation: [clipboard helper](desktop/.local/bin/oldbook-clipboard),
  [bindings](desktop/.config/sway/local.d/clipboard.conf).
- Checks: [clipboard tests](tests/test_clipboard.py), [native verifier](tests/verify_clipboard.py).

## Terminals and session services

### TERMINAL-SURFACE

Super+Enter opens Ghostty; Foot remains available, including the system monitor.
Use real terminal/compositor transparency with theme-aligned colors and typography,
not wallpaper imitation. Preserve explicit surface/opacity preferences and themed
selection/cursor/ANSI colors. Refresh existing terminal colors without killing
shells, tmux sessions or running programs. New shells outside tmux show the
Space Ghost splash once; Ghostty carries the bloom and cursor-smear shaders.

- Implementation: [preferred terminal](desktop/.config/sway/local.d/terminal.conf),
  [Ghostty](desktop/.config/ghostty/config), [Foot](desktop/.config/foot/foot.ini),
  [live terminal refresh](desktop/.local/bin/oldbook-refresh-terminal-theme).
- Checks: [terminal theme](tests/test_terminal_theme.py), [theme derivation](tests/test_theme_switch.py),
  [terminal chrome](tests/test_terminal_chrome.py), [transparency evidence](verification/workspace-chrome/),
  [splash and shader renders](verification/terminal-chrome/).
  Saved font settings and runtime per-window font zoom are distinct.

### DROPDOWN-WINDOWS

Super+backtick toggles a persistent Ghostty console; Super+tilde toggles an
independent persistent btop monitor in Foot. Summon either on the current
workspace on the first press; hide only when already there. Preserve process
identity through hide/show and separate lifecycle. Dock below the bar at 94%
output width and 52% height, bounded by available space.
Neither is pinned to Strata and neither takes over the ordinary caption.

- Implementation: [drop-down helper](desktop/.local/bin/oldbook-dropdown),
  [bindings](desktop/.config/sway/local.d/dropdown.conf).
- Checks: [native console/monitor](verification/console-monitor-foot/README.md),
  [cross-workspace recall](verification/dropdown-current-workspace/README.md),
  [caption exclusion](verification/decoration-monitor/README.md).

### TMUX-CONTROLS

Every theme loads the shared personal tmux controls: Ctrl+A prefix/double-prefix
literal, established split/navigation/resize keys, one-based windows/panes,
prefix+0 for window 10, vi copy mode, mouse/clipboard/focus integration and 10,000
scrollback lines. Preserve pane-title forwarding and discovery of agents inside
custom-ID tmux terminals. Do not reintroduce a plugin manager to restore controls.

- Implementation: [shared tmux config](desktop/.config/tmux/oldbook.conf),
  [app identity](desktop/.local/lib/oldbook/app_identity.py).
- Checks: [app identity](tests/test_app_identity.py), [agent switcher](tests/test_agent_switcher.py),
  [tmux title decision](../docs/superpowers/decisions/2026-09-07-tmux-decoration-titles.md).
  Existing tmux panes retain their previous scrollback limit until recreated.

### SESSION-OWNERSHIP

Use the OpenRC/Wayland session and one owner per compositor session for desktop
helpers. Reloads must not stack bars, notification services, media services,
shortcut guides or animation daemons. Preserve the configured physical output,
audio/backlight/screenshot controls and stock-Sway recovery route. No automatic
video background or inferred location/night-light policy: the night light runs
only while an explicit `~/.config/oldbook/location.json` exists, and a user stop
persists across reloads. AI attention indicates
only attributable, unvisited targets; ordinary or retained notices do not light
Caps Lock, and clearing one target must not clear the others.

- Implementation: [session](desktop/.local/bin/oldbook-session),
  [notification LED](desktop/.local/bin/oldbook-notification-led),
  [video helper](desktop/.local/bin/oldbook-video-background).
- Checks: [session](tests/test_session.py), [notification stream](tests/test_ai_notification_stream.py),
  [LED](tests/test_notification_led.py), [video](tests/test_video_background.py).
  A reload test is not a fresh-login, suspend/resume or hardware-hotplug test.

### FEEDBACK-OSD

Volume, mute, microphone, display brightness and keyboard-light changes show
one themed pill at the bottom centre of the focused output: a Nerd Font glyph,
label, amber bar and percentage from the active palette, on the overlay layer,
reserving no space, taking no keyboard focus and passing pointer input through.
It holds about 1.1 seconds, fades on the display frame clock without overshoot
and stops rendering when hidden; disabled desktop animations skip the fade.
Screenshots keep their three fixed modes and, only after the capture is saved,
flash a short cream wash and click the shutter; a missing daemon, player, sound
or annotator never fails a capture. The key helpers report through the socket
client only and never start the daemon; the session owns one daemon per
compositor session. Permission and missing-device errors remain notifications.

- Implementation: [oldbook-osd](desktop/.local/bin/oldbook-osd),
  [state model](desktop/.local/lib/oldbook/osd.py),
  [audio](desktop/.local/bin/oldbook-audio), [brightness](desktop/.local/bin/oldbook-brightness),
  [screenshot](desktop/.local/bin/oldbook-screenshot),
  [Satty profile](desktop/.config/satty/config.toml).
- Checks: [feedback tests](tests/test_osd.py), [shutter tests](tests/test_screenshot_shutter.py);
  `oldbook-osd preview` renders the pill without a display. Live capture evidence is recorded in
  [the design note](../docs/superpowers/specs/2026-09-08-osd.md); a headless
  render does not prove physical frame timing or the compositor blur.

## Gallery and durable reading content

### AMBIENT-DISPLAY

The panel may follow the Apple SMC light sensor: a dark room settles it at a
fifteen percent floor, never off, and a bright one takes it to full, on a
log-scale curve with a hysteresis band and a short eased fade that settles
exactly. It is opt-in, off by default, and remembered in the user's own
preference file. A brightness the user sets by hand while it is on is kept, and
its distance from the curve is learned as a lasting offset that shifts the whole
curve including its ceiling. The daemon writes nothing while `oldbook-idle`
holds display state or while a live lock readiness record exists, and abandons a
fade if either becomes true or the level changes underneath it. Automatic
changes are silent; only the user's own on and off show the pill.

- Implementation: [ambient display](desktop/.local/bin/oldbook-ambient-display),
  [sensor and curve](desktop/.local/lib/oldbook/ambient_light.py),
  [command deck](desktop/.local/bin/oldbook-control), [session](desktop/.local/bin/oldbook-session).
- Checks: [ambient display tests](tests/test_ambient_display.py).
  Fake-sensor tests and the live pause rules are not a proof of an eased fade on
  the physical panel or of a real change in room light.

### SOUND-CUES

Six short synthesized cues mark the lock engaging, the lock releasing, a battery
crossing a warning threshold, a deliberate gallery change, a critical
notification and small acknowledgements. Nothing is sampled or downloaded; the
set is generated locally and normalised to a quiet fixed level. Sound is never
load-bearing: a missing player, a missing file, a muted sink or a switched-off
set is silence rather than failure, playback is detached so no caller waits, and
every hook stays one or two lines. The master switch defaults to on and lives in
the user's preferences. The battery cue is edge-triggered, once per crossing, and
silent while charging. Urgent notifications are matched declaratively by the
notification daemon, never by the AI attention stream, whose meaning is separate.

- Implementation: [cue synthesis](bin/build-sound-theme),
  [player](desktop/.local/bin/oldbook-sound),
  [battery watcher](desktop/.local/bin/oldbook-battery-cue),
  [notification match](desktop/.config/swaync/config.json).
- Checks: [sound tests](tests/test_sound_theme.py),
  [waveforms and levels](verification/sound-theme/README.md).
  Levels and exit codes are measured; no cue has yet been heard firing from its
  own occasion, and whether the set is pleasant is the user's judgement.

### GALLERY-ACTIONS

Left-click opens the gallery; right-click advances; middle-click pauses; scroll
browses. Super+left generates artwork, Shift+left edits prompts, Super+Shift+left
creates a random complete theme and Super+Shift+right prompts for a theme.
Preserve the searchable existing-theme picker, prompt-created names, image
paging, explicit deletion flow, help and command deck. New actions are additive;
ordinary artwork selection remains distinct from choosing a desktop theme.
Painting rows carry a cached rounded thumbnail and the bar badge shows the
painting on screen; a missing thumbnail falls back to plain text or the glyph,
never to a blocked menu or bar.

- Implementation: [gallery](desktop/.local/bin/oldbook-wallpaper),
  [native click handling](packages/waybar-art/art.c),
  [thumbnail cache](desktop/.local/lib/oldbook/thumbnails.py).
- Checks: [manual artwork](tests/test_manual_artwork.py), [picker](tests/test_gallery_picker.py),
  [new themes](tests/test_new_themes.py), [prompt editor](tests/test_gallery_prompts.py),
  [thumbnails](tests/test_thumbnails.py), [headless renders](verification/gallery-thumbnails/).

### GALLERY-ACTIVATION

Every gallery themed-generation command applies the exact theme used for its
painting, then selects that exact saved painting on success. This includes
existing themes and the theme chosen at the start if the desktop changes during
generation. Unthemed artwork changes only the painting. Nonactivating/manual
save-only and daily jobs do not switch the desktop. Failed activation keeps the
saved artifact and reports the failure; it must not repaint to retry activation.
New-theme completion names the theme and previews the actual saved painting.

- Implementation: [generator activation](wallpapers/generate.py).
- Checks: [themed artwork](tests/test_themed_artwork.py), [new themes](tests/test_new_themes.py),
  [completion notices](tests/test_theme_completion_notification.py),
  [retry behavior](tests/test_generation_retries.py).
  Mocked provider tests do not request paid images or establish live activation.

### ARTWORK-ARCHIVE

All workspaces share the painting/timer; keep 20-minute rotation and pause state.
Use the active/unthemed rotation filter without hiding other saved art from manual
browsing. With an explicit location the timer alone may prefer nocturnes about
3:1 after sunset; it never excludes a painting or touches manual navigation.
Preserve prompts, provenance, exact PNG hashes, fresh scene/mix history,
one daily reservation, the single generation lock and bounded 2/4/8-second retry
waits. Checkpoint only the generated pair and required descriptor; retry a failed
checkpoint without regenerating. Existing images are reproducible bytes; fresh
AI output is not deterministic.

- Implementation: [gallery policy](wallpapers/gallery.json), [generator](wallpapers/generate.py),
  [prompt catalog](wallpapers/prompt_catalog.py).
- Checks: [wallpapers](tests/test_wallpapers.py), [checkpoints](tests/test_wallpaper_checkpoint.py),
  [fresh scenes](tests/test_fresh_scenes.py), [retries](tests/test_generation_retries.py).

### ARTWORK-CROSSFADE

Painting changes crossfade on the frame clock (0.8 s for a deliberate change,
1.6 s for the timer, an optional radial reveal from a screen position) through
the background-layer daemon; Sway's own background is only the fallback and is
never refreshed after a fade. The daemon starts on what swaybg shows, re-creates
its surface when a respawned swaybg covers it, restores desktop cards it
displaced, and exits with the session. Manual browsing, the pause state and the
shared painting link are unchanged.
The painting also follows the keyboard's breath, swelling from 1.000 to 1.006
at rest and up to 1.018 at full lungs and settling exactly back; the swell only
ever enlarges, so no edge can show. While the session is idle the daemon drifts
slowly across each painting and crossfades to the next, then glides back to rest
and to the painting it interrupted; the gallery's saved selection, deadline and
pause switch are never written by that path. `~/.config/oldbook/breath.json`
switches the swell and the caption pulse off.

- Implementation: [oldbook-background](desktop/.local/bin/oldbook-background),
  [fade model](desktop/.local/lib/oldbook/background_fade.py),
  [gallery apply](desktop/.local/bin/oldbook-wallpaper), [session](desktop/.local/bin/oldbook-session).
- Checks: [daemon tests](tests/test_background.py), [gallery hooks](tests/test_background_gallery.py),
  [headless crossfade evidence](verification/background-crossfade/README.md).
  Headless proof is not physical frame pacing; hotplug and a fresh login are unobserved.

### CONKY-READING

Conky is a quiet reading display, not telemetry. Preserve disabled-card choices,
stable placement and caption clearance; do not reflow on focus/fullscreen changes.
Keep date, Scripture, gallery notes and text; battery is allowed, configured email
is welcome, and the masthead's offline sunrise/sunset/moon line appears only for
an explicit `~/.config/oldbook/location.json`. No CPU, memory, processes,
disk/network I/O or thermals: Waybar owns those. Background refresh is 60–300
seconds, except hourly Scripture. Preserve native reading-card click actions;
Scripture search may adapt to free space.

- Implementation: [runtime policy](desktop/.local/lib/oldbook/conky_policy.py),
  [layout](desktop/.local/lib/oldbook/conky_layout.py), [panels](desktop/.config/conky/panels.json),
  [sun and moon](desktop/.local/lib/oldbook/astro.py), [masthead helper](desktop/.local/bin/oldbook-astro).
- Checks: [policy](tests/test_conky_policy.py), [layout](tests/test_conky_layout.py),
  [sun and moon](tests/test_astro.py),
  [clicks](tests/test_conky_clicks.py), [desktop space](tests/test_desktop_space.py),
  [native click evidence](verification/conky-clicks/README.md).
  [Persistent requirements](AGENTS.md) apply to every theme and rebuild.

### JOURNAL

Keep desktop text in the personal SQLite journal, with full entries, backup and
export. Preserve all eight original Coast to Coast lines, three quips per note,
four-minute rotation and one-time legacy import. Never replace it with JSON/random
lines, invent dated experiences or collect private activity automatically. The
personal database is not a repository artifact.

- Implementation: [journal](desktop/.local/lib/oldbook/desktop_journal.py),
  [CLI](desktop/.local/bin/oldbook-journal).
- Checks: [journal tests](tests/test_desktop_journal.py), [persistent policy](AGENTS.md).

### SCRIPTURE

Super+/ focuses an editable Bible search in the existing desktop search bar;
typing and results stay in that bar without opening a picker window. This
supersedes the earlier button that launched Fuzzel. Release its keyboard grab
after selection, cancellation or focus loss. Super+Shift+/ searches all
collections with Bible results after Torah, Talmud and reflections. Selection displays immediately
and holds for an hour. Preserve complete passages, attribution, continuous
passage→reflection→practice presentation, offline sources and prior study text.
Reading history is a separate durable personal SQLite database: append notes,
research and drafts without replacing old material. Rebuildable study records
belong outside the Fossil database. New study generation uses the Alienware's
GPUs, grounded in retained sources/provenance; never cloud fallback or private
journal content. Do not start Ollama or model workers on this MacBook Pro. An
unavailable Alienware endpoint does not authorize local CPU fallback. This
supersedes the earlier MacBook-local generation workflow. Preserve other Conky
cards and their intervals during refresh/recovery.
History is a clickable text link on the Scripture header line, in the active
card font and accent color. It opens saved reading without advancing the passage;
the passage itself keeps its click-to-advance action. This supersedes the separate
History button beside the desktop search bar.
Right-click on the Scripture card returns to the passage shown before the current
one, one step per click along the reader's own path: a return after Next goes
back to where Next started, and returning past a repeated passage does not loop.
Each return is appended to history as a new hour-long selection; no saved entry
is edited or removed. Other cards ignore right-clicks.

- Implementation: [Scripture modules](desktop/.local/lib/oldbook/scripture.py),
  [card clicks](desktop/.local/lib/oldbook/conky_click.lua),
  [inline search bar](desktop/.local/bin/oldbook-scripture-bar),
  [history](desktop/.local/lib/oldbook/scripture_history.py),
  [generation](desktop/.local/lib/oldbook/scripture_generation.py).
- Checks: [selection](tests/test_scripture_selection.py), [history](tests/test_scripture_history.py),
  [inline search](tests/test_scripture_search.py),
  [inline keyboard verification](tests/verify_scripture_inline.py),
  [study](tests/test_scripture_study.py), [local generation](tests/test_scripture_generation.py),
  [local runtime lifecycle](tests/test_scripture_local.py),
  [runtime policy](tests/test_scripture_runtime_policy.py),
  [header clicks](tests/test_conky_clicks.py), [header visual proof](verification/scripture-header/README.md),
  [native/history evidence](verification/scripture-history/README.md),
  [local model provenance and replay](verification/scripture-local-generation/README.md).
  Controlled-clock hourly tests do not substitute for a physical hour of observation.

## Installation, recovery and packaging

### CODEX-PACKAGING

Install the complete native Codex bundles through the Cascadia testing APK;
no npm/Node package installation. Preserve CLI, app-server, both code-mode hosts,
resources, rg/bwrap and responses proxy. Use available local executables/cache
before fetching replacements. Keep the upstream GNU zsh as a preserved artifact
and Alpine zsh in both executable shell slots. Do not edit authentication state.
Account for /usr/local/bin launchers shadowing APK-owned /usr/bin tools.

- Implementation: [APKBUILD](packages/cascadia/testing/codex/APKBUILD),
  [package/build contract](packages/cascadia/testing/codex/README.md),
  [standalone rollback](packages/codex/README.md).
- Evidence: signed artifact/source hashes and offline extraction/launch checks
  in [manifest](packages/cascadia/testing/codex/manifest.json).
  Upstream binary restoration is not a claim to compile Codex from source.

### DEPLOY-RECOVERY

Deployment uses per-file managed links and durable journals, backs up conflicts,
supports exact scoped changes, is idempotent and preserves unrelated files.
Real interrupted or malformed deployment journals must block unsafe replacement
and remain recoverable. Unrelated database-backup manifests must not block theme
switching or be treated as deployment rollback state. Never mark a foreign
backup restored just to bypass the guard.

- Implementation: [deployer](bin/deploy-home).
- Checks: [deployment/recovery tests](tests/test_deploy.py).
  Disposable-HOME proof is separate from live application refresh; preserve real
  backup contents and compare exact owned paths before activation.

### BAZZITE-REPLAY

The desktop reaches other machines through the Bazzite replay profile, which
copies the portable pieces of `alpine/desktop` onto a Fedora/systemd HOME from
an explicit allowlist and rewrites what cannot travel: repository anchors, the
Waybar art module, and the lock, which names the image's stock swaylock because
Bazzite carries neither swaylockd nor swaylock-effects. Alpine APKs, OpenRC
services, native musl binaries and the Apple SMC helpers stay behind. Preserve
`preview`, `check`, `apply` and `rollback`, the immutable per-revision overlay
and the shared deployment journal.

Behavior the replay is meant to keep must be pinned in its own right rather than
assumed from the Alpine side. A locked session ignores the power key on both:
the transform must leave the inhibitor intact and `check` must require
`systemd-inhibit`, which is what supplies it where there is no elogind.

- Implementation: [replay profile](../bazzite/bin/oldbook-bazzite-profile),
  [Bazzite notes](../bazzite/README.md),
  [session units](../bazzite/desktop/.config/systemd/user).
- Checks: [replay profile tests](tests/test_bazzite_profile.py).
  A replay applied on this machine is not a Bazzite host; manual locking,
  swayidle and the session units remain the user's check on the real machine.

### PACKAGE-CLOSURE

Keep exact signed APK bytes, source inputs, identities, architectures, hashes and
recovery locks in the local Fossil archive. Preserve all pre-existing installed
packages when updating one component; avoid broad upgrades as a shortcut. Keep
repositories HTTPS and testing tagged; retain explicit local personal-repository
entries. Archive matching build inputs and verify custom offline rebuilds.
Full Fossil backups carry UV artifacts; a Git export alone does not.

- Implementation: [package archive](bin/package-archive), [current lock](packages/current-lock),
  [restoration guide](packages/RESTORE.md), [repository backup](bin/backup-repository).
- Checks: [package archive](tests/test_package_archive.py),
  [source archive](tests/test_source_archive.py), [Fossil bootstrap](tests/test_fossil_bootstrap.py).
  Distinguish existing-host architecture identity from noarch repository indexing.

### BUILD-HOST

Compile packages on a build host, not on this MacBook. `alienware` and `bak`
carry the work; this machine ships the package directory, the far side builds it
in a throwaway Alpine container, and only the finished APK comes back. Both
machines are x86_64, so this is a native build on faster hardware rather than
cross-compilation, and the container supplies the musl sysroot and `-dev`
packages `abuild` needs. An unreachable build host is a reason to stop and say
so, never permission to fall back to this laptop's CPU.

The signing key never leaves this machine. The build host signs with a key it
generates for itself and that signature is replaced here. An APK v2 signature
covers the control segment alone, so re-signing is one SHA-1 over a few hundred
bytes and leaves the identity apk records as `C:` untouched; the re-signed bytes
are deterministic. The signature segment must not carry a tar end-of-archive
marker, which would hide the control and data segments and make apk reject the
package as inconsistent.

- Implementation: [remote builder](bin/remote-build), [guide](../docs/REMOTE-BUILD.md).
- Checks: [signature, policy and host selection](tests/test_remote_build.py).
  Container execution on the far side is not exercised by these checks; an
  actual remote build is separate evidence.

### PERSONAL-DESKTOP

The personal Cascadia package/command is named **spaceghost-desktop**. Keep the
runtime dependency closure and system launchers separate from this checkout's
HOME overlay and private history/credentials/radio policy. Preserve standalone
component recovery and the stock-Sway fallback. Do not present a payload-only
disposable-root installation as a verified fresh hardware boot.

- Implementation/evidence: [Cascadia package decision](../docs/superpowers/decisions/2026-09-07-personal-desktop-package.md)
  and the linked Cascadia checkout/release inputs.
- Limits: public Pages/production signing, maintainer-script activation and fresh
  hardware boot remain separate from the recorded signed offline payload proof.

### SCREEN-CORNERS

Round each SwayFX output with a 20 logical pixel black corner mask, independent
of the theme and window decoration radius. Apply it after the complete scene,
including overlays, fullscreen surfaces, session locks and the software cursor;
disable direct scanout and hardware cursors while enabled. Preserve usable area,
input routing and window/panel geometry. Do not introduce idle redraw loops.
Allow SPACEGHOST_SCREEN_CORNER_RADIUS=0 at startup to disable it and retain the
stock-Sway recovery entrypoint. Activation requires a new compositor session;
never close the current desktop merely to load a new executable.

- Implementation: [output mask patch](packages/swayfx/screen-corners.patch),
  [desktop launcher](desktop/.local/bin/oldbook-sway).
- Native checks: [private compositor verifier](packages/swayfx/verify-screen-corners).
- Evidence: [screen corner verification](verification/screen-corners/).
  Headless renderer proof does not establish physical frame rate or DRM scanout.

### BOOT-CONSOLE

Every text-mode screen is Gruvbox from the first frame: the initramfs LUKS
passphrase prompt, kernel messages and the rescue gettys on tty2–tty6. The
palette, the cream-on-charcoal default attribute and the kernel's Terminus 16x32
are kernel parameters appended to GRUB_CMDLINE_LINUX_DEFAULT; the rescue banner
is a rendered /etc/issue. Installation is idempotent, backs up every replaced
file, regenerates grub.cfg into a temporary file and keeps it only when the
stock entry still boots the same kernel, initramfs, root and crypt parameters
plus exactly the managed tokens and stays first. The Ghost Planet banner
initramfs is an additional non-default GRUB entry built from the versioned
patched init; /boot/initramfs-lts and mkinitfs.conf stay untouched. Nothing
here reboots, switches VTs or loads a font into a live console.

- Implementation: [installer](bin/install-boot-console),
  [console logic](system/boot/boot_console.py), [palette](system/boot/console-palette.json),
  [rescue banner](system/boot/issue.template), [banner initramfs](system/mkinitfs/).
- Checks: [boot console tests](tests/test_boot_console.py),
  [boot console record](../docs/superpowers/specs/2026-09-08-boot-console.md),
  [LUKS prompt record](../docs/superpowers/specs/2026-09-08-luks-prompt.md).
  A generated grub.cfg and a listed initramfs are not a boot: the visual result
  stays unverified until the next physical boot.

## Superseded choices and evidence limits

These replacements are already decided; do not ask the user to choose again.

| Earlier state | Current contract |
| --- | --- |
| Center window-title subbar | Music occupies the center; captions carry window titles (`BAR-LAYOUT`). |
| Bottom placement replacing the side entirely | Bottom default with right edge retained (`DECORATION-STYLE`). |
| Caption outline or fullscreen rounded bottom corners | Blended borderless surface; fullscreen tiled corners square (`DECORATION-PLACEMENT`). |
| Tile/float crossfade with overlapping surfaces | Immediate handoff; animate continuous motion (`MOTION`). |
| Notifications as a sliding/opaque overlay host | Transparent, unreserved TOP popups below overlay chrome (`NOTIFICATION-PLACEMENT`). |
| Strata on workspace 6, then workspace 0 | Numeric 10 on the 0 key; only Strata is pinned there (`WORKSPACE-IDENTITY`). |
| Uppercase-only reserved workspace names | Titlecase display with compatible native emphasis (`WORKSPACE-IDENTITY`). |
| Foot as the preferred console/default terminal; shared monitor process | Ghostty default/console and independent Foot monitor (`TERMINAL-SURFACE`, `DROPDOWN-WINDOWS`). |
| Old Expo cards as the sole overview | Workspace picker and later all-window carousel have distinct roles (`EXPOSE-LIFECYCLE`, `WINDOW-SWITCHING`). |
| Low-resolution or live carousel previews | Full-provider-resolution still images once per opening (`CAROUSEL-STILLS`). |
| Every theme recolors the Ghost badge | Original Ghost branding is explicitly preserved (`GHOST-BRAND`). |
| Per-workspace painting timers or automatic Conky focus reflow | Shared painting/timer and stable quiet cards (`ARTWORK-ARCHIVE`, `CONKY-READING`). |
| Compact 6px corners, 3/4 gaps, edge-hugging bar islands, terminal-font captions | Ghost Observatory geometry: 22px corners, 6/7 gaps, floating pill islands, Inter captions (`THEME-COMPLETE`, `DECORATION-STYLE`); the bar centre and Ghost badge stay as pinned. |
| swaynag logout prompt on Super+Shift+E; fuzzel session menu on the battery | wlogout power deck with confirmations kept for log out, reboot and shut down (`SESSION-OWNERSHIP`, `BAR-LAYOUT`). |
| JSON/random desktop notes, telemetry cards or lost old study text | Durable reading/journal contracts (`CONKY-READING`, `JOURNAL`, `SCRIPTURE`). |
| npm Codex or partial CLI-only installation | Complete native APK and preserved tool/resource layout (`CODEX-PACKAGING`). |
| Compiling packages on the MacBook | Remote build on `alienware`/`bak` with local signing (`BUILD-HOST`). |
| Personal package named oldbook-desktop | spaceghost-desktop (`PERSONAL-DESKTOP`); old artifacts are recovery history. |

The current requests do not establish an unresolved preference conflict. Actual
limits remain explicit above: physical 60fps, physical input/hotplug/login,
application-specific live refresh, selected contextual actions and fresh boot.
Do not satisfy those limits by silently dropping a feature or relabeling a
historical test as current proof. [PROGRESS.md](PROGRESS.md) and linked evidence
retain chronology; this file states which behavior must survive.
