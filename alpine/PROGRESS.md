# Oldbook verification

Verified on Alpine edge x86_64, MacBookPro11,5, 2026-09-07.

## Eyecandy round — 2026-09-08

Eighteen additions were built in one pass by parallel agents, each with its own
check-in, design note under `docs/superpowers/specs/2026-09-08-*.md`, tests and
evidence directory. The display was powered off and the session locked for the
first half of the work, so most visual proof is from private headless SwayFX
sessions; the physical checks that remain are listed with each item. The whole
catalogue, with controls and rollback for every piece, is in [RICE.md](RICE.md).

- **Notification centre widgets.** The SwayNC control center now carries the
  playing MPRIS track with album art and controls, the output volume with a
  per-application drawer, the gmux_backlight slider with a 40/1023 floor, and six
  quick actions (lock, command deck, next painting, hold rotation, mic off,
  desktop cards) whose toggles refresh each time the panel opens; both stylesheet
  copies gained Gruvbox rules for the GTK 4 widget elements. `verify_swaync_widgets.py`
  rendered the real config in a private headless SwayFX and D-Bus session with a
  fake MPRIS player and two synthetic notifications (`verification/swaync-widgets/`);
  the live swaync accepted config and CSS reloads. SwayNC wraps button commands
  in `/bin/sh -c "..."`, so the commands avoid double quotes. The live look
  waits for the user's next click on the notification glyph.
- **On-screen feedback and screenshot shutter.** `oldbook-osd` draws one themed
  300×66 pill at the bottom centre of the focused output for volume, mute,
  microphone, display brightness and keyboard light: overlay layer, no reserved
  space, no focus, pointer pass-through, a 1.1 s hold and a frame-clock fade that
  unmaps the surface when done; disabled animations skip the fade. Screenshots
  flash a cream wash and click the freedesktop shutter only after the capture is
  written, then open Satty with a Gruvbox profile (Swappy fallback). Message
  validation, timing, the quiet client, the runtime guard and the
  audio/brightness/screenshot wiring are covered by 18 new tests; a private
  headless SwayFX run recorded the pill mapping, the unchanged workspace
  rectangle, the fade, the flash and Satty floating (`verification/osd/`). The
  live daemon started from a reload and mapped the pill on eDP-1 with the SwayFX
  effects reported; the physical look and the sound remain unobserved, and
  pixman evidence does not show blur.
- **Gruvbox boot console.** Every text-mode screen now inherits the Gruvbox
  palette, a cream-on-charcoal default attribute and the kernel's Terminus 16x32
  through kernel parameters on the GRUB command line; the rescue gettys print a
  Ghost Planet `/etc/issue` masthead. `alpine/bin/install-boot-console` rewrites
  `/etc/default/grub` idempotently, backs up every replaced file under
  `/var/backups/alpine-rice/boot-console-*`, regenerates grub.cfg into a
  temporary file and keeps it only after `grub-script-check` and a structural
  proof that the stock entry still boots the same kernel, initramfs, root and
  crypt parameters. 16 unit tests, a dry run, a real install and an idempotent
  re-run passed. No reboot was performed; the visual result is unverified until
  the next boot. The consolefont service stays disabled.
- **LUKS prompt and banner initramfs.** The passphrase prompt is printed on the
  kernel console after the palette parameters apply, so it is already Gruvbox.
  A versioned copy of the mkinitfs init with one guarded masthead block builds
  `/boot/initramfs-lts-ghost` (init member proven byte-identical, modules
  present, file list compared with the stock archive) and is published as an
  additional, non-default GRUB entry derived from the stock entry;
  `/boot/initramfs-lts` and mkinitfs.conf are untouched. Withdraw with
  `--remove-ghost`; rerun after kernel upgrades. The entry has not been booted;
  select it from the one-second GRUB menu to test.
- **Power deck.** Super+Shift+E and the battery module open `oldbook-power`, a
  wlogout 1.2.2 layer-shell deck of five Gruvbox tiles (lock, suspend behind a
  verified lock, log out, reboot, shut down) over the SwayFX-blurred desktop,
  falling back to the command deck menu without wlogout. Log out, reboot and
  shut down confirm on a Gruvbox swaynag bar. Glyph tiles are rasterised from
  the Nerd Font by `build-wlogout-icons`. Evidence: `verification/power-deck/`
  headless render; ShellCheck and both Sway validations passed. The display was
  off during the work, so the binding, battery click and tile actions await a
  physical check.
- **Ghost Observatory adopted.** Production now uses the concept's 22px corners,
  34px shadows, 6/7 gaps, 18px floating bar islands, tooltips and launcher, and
  Inter Medium captions on the decoration strip (theme design font, one point
  above the terminal size, left-aligned); the descriptor records radius 22 /
  spacing 6 and the renderer accepts up to 24. The centre title, native
  titlebars and amber badge were not adopted per BAR-LAYOUT, DECORATION-* and
  GHOST-BRAND. `alpine/themes/preview` renders the deployed chrome headlessly;
  evidence in `verification/ghost-observatory/`. Decoration and theme suites
  pass; `test_ghost_branding`/`test_new_themes` still reference archived assets.
  Live reload applied with the caption daemon restarted; the Waybar JSON reload
  happened later in the round and the physical look remains pending.
- **Gallery thumbnails and art badge.** Gallery picker rows and the bar's
  artwork badge now show rounded thumbnails of the paintings. A shared
  GdkPixbuf/cairo cache under `~/.cache/oldbook/thumbnails/` is published as a
  private `Oldbook-Thumbnails` icon theme because Fuzzel's dmenu icon protocol
  resolves theme names, not paths (absolute paths verified to render nothing).
  The native badge asks `oldbook-wallpaper status --thumbnail-height` for a
  scale-sized PNG and follows `current-wallpaper.png` link changes through a
  debounced file monitor; paused dims, generating shows the hourglass, missing
  thumbnails fall back to the glyph. r10 of `oldbook-waybar-art` built twice
  byte-identically offline, was archived, installed and mapped into the
  restarted bar. 9 thumbnail-library tests and 6 picker tests pass; headless
  SwayFX renders of the picker and all four badge states are under
  `verification/gallery-thumbnails/`, and both were confirmed on the physical
  panel once it woke. A live picker check was killed by a `timeout` wrapper and
  left the picker on screen for about half a minute before it was closed; no
  selection was made. The pre-existing `delaware.png` fixture move still breaks
  `test_manual_artwork`, `test_new_themes` and `test_themed_artwork`.
- **Lock screen.** swaylock-effects 1.7.0.0 is rebuilt as
  `oldbook-swaylock-effects` and installed beside stock swaylock, with a
  backported `--ready-fd` and new idle-colour options; two isolated builds were
  byte-identical and the inputs are archived. `oldbook-lock` supervises it
  itself, keeps the readiness and identity checks, and falls back to swaylockd
  and stock swaylock inside the same call. The lock dissolves from the desktop
  into the blurred, vignetted painting with an Inter Display clock, a caption
  card (title, story, the hour's Scripture, Ghost Planet mark) and an amber ring
  only while typing; no grace period. Scene and caption are cached; quiet
  cold/warm lock timings were 1.0 s. All 10 lock tests pass. A private headless
  SwayFX session locked with the real helper produced `verification/lock-screen/`.
  The live session was not locked by the agents (it was locked by swayidle, then
  in use), Caps Lock text was not observed headlessly, and physical dissolve
  pacing is unmeasured; the user's next Super+Escape is the live check.
- **Sun and moon.** Added offline NOAA sunrise/sunset/twilight and low-precision
  lunar phase in `astro.py`, driven only by an explicit
  `~/.config/oldbook/location.json` (example shipped, live file kept out of
  Fossil). The masthead card shows one sunrise/sunset/moon line every 300 s;
  `oldbook-sun-light` runs wlsunset from the configured coordinates with a stop
  that survives reloads and a command-deck toggle; the automatic timer prefers
  nocturnes about 3:1 after sunset without excluding any painting. Eighteen
  tests pass against published times; Conky was refitted live and the card
  rendered headlessly (`verification/sun-and-moon/`). A full night of weighted
  rotation, the physical colour ramp and an eye check of the card remain
  unobserved.
- **Bar visualizer (optional).** `oldbook-cava-bar` feeds a `custom/cava`
  ten-bar meter after the media controls, stops cava when nothing plays,
  collapses after half a second of silence, and cannot outlive its bar (pipe
  poll, PDEATHSIG, unwinding-only signal handler). Four tests with fake
  cava/playerctl pass; headless renders show the bar height unchanged; cost with
  music is about 4 % of one core across feeder, cava and Waybar redraws
  (`verification/bar-visualizer/`). Remove by deleting `custom/cava` from both
  `modules-center` lists.
- **Terminal chrome.** New shells outside tmux greet with a fastfetch splash
  beside the Space Ghost painting (kitty file medium in Ghostty, libsixel in
  Foot, text ghost elsewhere) with Gruvbox keys, the Fossil branch, the current
  painting, the hour's Scripture and the track on air, once per terminal.
  Ghostty gained warm-bloom and cursor-smear shaders, animated only while
  focused, and Neovim a hand-rolled Gruvbox statusline, winbar and thin splits
  with no plugins, all in both config copies. Fourteen unit tests pass; headless
  SwayFX renders and brief live 2× checks confirmed the splash and shader
  loading (`verification/terminal-chrome/`). A transient Ghostty config banner
  appeared during the minutes between the shader lines and the deployed shader
  files; the live config validates clean now. The Neovim chrome and the
  drop-down console's post-resize image placement remain unobserved live;
  `test_application_theme_refresh.py` still expects the archived spaceghost
  profile.
- **Wallpaper crossfade.** Paintings now crossfade: `oldbook-background` owns a
  background-layer surface above swaybg and eases between images on the frame
  clock, 0.8 s for a deliberate change and 1.6 s for the timer, with an optional
  radial reveal from a screen position. It starts on the image swaybg shows and
  fades to the shared painting, so logins and reloads no longer cut. SwayFX
  lists layer surfaces top-first and respawns swaybg above everything on each
  reload; the daemon detects a covering swaybg before each fade, on Sway output
  events and every 15 s, re-creates its surface seamlessly and puts displaced
  Conky cards back on top. `oldbook-wallpaper` falls back to `output bg`
  whenever the daemon is not answering. Eighteen unit checks and a twelve-check
  private headless SwayFX run with real paintings passed (evidence:
  `verification/background-crossfade/`); one live `next`/`prev` faded and
  restored the painting with the pause state kept. Physical frame pacing,
  hotplug and a fresh login remain unobserved.
- **Dim before lock and the keyboard's last breath.** Added `oldbook-idle`: a
  swayidle stage 30 s before the lock eases the display to 20% in a detached
  worker and gives the keyboard one last breath (rise, long fall, hold dark)
  through a runtime overlay in the single keyboard worker; resume cancels the
  ramp, restores the display unless adjusted meanwhile, and restores the saved
  keyboard level and mode. Nine subprocess tests and eight synthetic-clock
  keyboard tests cover cancel, manual adjustment, already-dim, no-display, stale
  records and the overlay's shape; a short real dim/undim cycle on the MacBook
  recorded display 1023 → 310 → 1023 and keyboard 0 → 255 → breathing resumed
  with saved 255/breathing untouched (`verification/keyboard-ambient/`). The
  running swayidle keeps the old command line until the next login; a real
  270-second idle and suspend/resume remain unobserved.
- **Ambient keyboard glow and the wluma pull request.** Option+F6 selects an
  ambient keyboard mode driven by the Apple SMC light sensor with log-scale
  smoothing, hysteresis and 1.2-second fades between the saved peak in the dark
  and off in daylight; it persists like the other modes, F5/F6 still move the
  peak, and it is refused without a readable sensor. A fake-sensor run on the
  real LED with private state went 255 → 0 → 255 without touching preferences.
  A stray `nand-disk` trigger found on the LED (a root write at 02:32 of unknown
  origin) was reset to `none`. Upstream, max-baz/wluma#179 adds an
  `[als.applesmc]` backend with auto-selection, docs and tests; fmt, clippy and
  165 tests passed locally and the release binary read the live sensor. The
  Rust toolchain and dev headers installed for that build were removed again
  afterwards so the package lock stays a desktop closure; `~/src/wluma` keeps
  the branch and the built binary. A real room-light change, the physical chord
  and the older two-value sensor format were not observed.
- **Breathe on air.** Option+Shift+F6 selects `breathe-air`: lungs start a
  quarter full at seven seconds per cycle, every keystroke from the typing
  modes' evdev sampling adds a fixed sip up to full (three seconds per cycle),
  idle lungs leak back over a twenty-second time constant, and continuous phase
  plus half-second volume smoothing keep the light from ever jumping. A
  90-second synthetic run with scripted keystrokes and an eight-second live run
  at rest (31 → 87 → 31) passed; keystroke inflation on hardware was not
  observed.
- **Consolidation.** The shared hooks (session services, gallery crossfade and
  nocturne calls, control-deck entries, bar modules, effects, contracts and the
  check index) were reviewed together: both Sway entry configs validate, both
  Waybar configs parse, the effects copies are identical, the check index is
  consistent, and the full unit suite ran 1,076 tests with a clean PATH and no
  failures. The keyboard light now reports level changes through the feedback
  pill. The complete catalogue is [RICE.md](RICE.md). The running swayidle
  was restarted so the idle dim stage applies now; the second open leaf from
  another session's Bazzite fix was merged back into the branch.

## Radio preparation and desktop repairs — 2026-09-07

- Bluetooth is now software-blocked by a Bluetooth-only eudev rule. Independent
  checks preserved the live WLAN association, addresses and routes. Status
  reads still work; direct `/dev/rfkill` writes are restricted to root with no
  user ACL. Existing wheel `nopass` doas authority remains unchanged.
- All 63 radio tests passed, including real process/socket timeout cases,
  hardware/software block combinations, adapter replacement and stale recovery
  records. The eudev parser was exercised in private mount/network namespaces
  with read-only sysfs and an inert positive-match rule. Actual deployment then
  verified Bluetooth soft=1 and WLAN soft=0 without changing Wi-Fi owners.
- Root-private permission/Bluetooth journals preserve recovery data. Source,
  installed hashes, state checks and recovery instructions are in
  `security/radio/permissions-verification.json`, `bluetooth-verification.json`
  and `BLUETOOTH.md`. No live rollback or reboot/suspend test was performed.
- The full WLAN controller remains staged. Its command, WPA, transaction and
  lock waits are bounded, but persistent DHCP ownership/renewal and home/hotspot
  IPv6 transitions still need implementation and isolated verification. WPA
  reload can disconnect and scan; the proposed blocked migration is documented
  in `security/radio/NETWORK-MIGRATION.md`. Exact trusted SSIDs remain pending.
- Restored the video-background launcher and two missing library links. The
  calendar now uses Gruvbox colors; existing gestures and help controls remain.
  Only Waybar was reloaded. Evidence: `verification/desktop-integration.json`;
  desktop check-in `73582991425`. Unproven test-compositor cleanup was deferred.
- The existing lock still matches all 1,079 installed package identities,
  `/etc/apk/world` and repository configuration. This pass adds no packages and
  makes no new bootable-image or physical radio-silence claim.

## Hold to Help and interactive firewall — 2026-09-07

- **Hold to Help 0.1.0** is installed as signed main/doc APKs and runs locally
  through the preserved `oldbook-shortcuts` command. The original GTK source
  remains for rollback. Workspace Python edits take effect on service restart.
- Super remains the half-second hold trigger; physical Caps is configurable
  without changing Caps-to-Escape. Existing shortcut sections, custom profiles,
  pointer scrolling, release/chord cancellation and focus behavior are retained.
- Qt supplies palette, fonts and style. Local qt6ct and native LXQt settings
  both select Gruvbox Dark, Inter and Oldbook icons; LXQt palette/font changes
  reached a running test application. The app does not force a desktop theme.
- All 108 package tests and three LXQt checks passed. Native private Sway/X11
  checks cover monitor changes, no keyboard focus, scroll, fast chords,
  Caps-to-Escape, repeat keys, lock suppression, singleton and bounded failures.
  The installed Wayland library passed again. Physical user hold after unlock
  and a complete LXQt desktop session remain unobserved.
- Two isolated builds produced identical signed APKs from identical source
  archives. Source and all 1,079 APK identities are in Fossil; lock
  `packages/locks/10265f085b5a34747518.json` restored into an empty directory
  with networking disabled. Restored CLI and native library loading passed.
  This proves a package/filesystem restore, not a bootable disk image.
- The new daemon is running, sees two keyboards, and stays hidden while locked;
  the old daemon exited. See `verification/hold-to-help.json` and its native
  preview. CMake sources, GPL license, examples, manual, contribution guide and
  release tool are under `projects/hold-to-help`; no public upload was made.
- OpenSnitch and the permanent packet gate are **active and enabled for boot**.
  A fresh non-root program caused a real prompt and a Deny decision; IPv4/IPv6
  filtering plus fresh authenticated Codex/curl access passed. All 28 saved
  rules and popup defaults were preserved. Broad root/443 grants still skip
  prompts; an unlocked human Allow click and reboot remain untested. Evidence:
  `security/firewall/interactive-verification.json`, commit `e63360f71a`.
- Radio hardening remains staged pending the trusted-network identity and
  physical checks recorded below; this work makes no new radio-silence claim.

## Desktop and automation

- Live Sway loads the linked HOME overlay; Space Ghost artwork and the floating
  Waybar control deck were inspected on the 2880×1800 display at scale 2.
- GTK, Qt, Foot, Fuzzel, notifications, shell, editor and monitoring tools share
  the violet palette. A proper cursor theme and Inter/Nerd fonts are installed.
- Five gallery assets have saved prompts and hashes. Rotation runs every twenty
  minutes. Cron uses the existing ChatGPT login with Luna for one daily attempt,
  exclusive execution, a fifteen-minute timeout and no automatic generation retry.
- A real noninteractive Codex run produced American Ghostic successfully.
- SwayFX 0.6 is installed beside stock Sway; `sway` selects its user configuration
  at the next desktop login. Two offline builds produced identical signed APKs;
  Intel and AMD headless renderers passed. Physical session takeover remains untested.
- Lock readiness passed both fault tests and a real isolated SwayFX session;
  repeated requests validated the same ready process/compositor record. Password
  entry and physical suspend/resume remain untested.
- Deployment preserves existing files and supports durable interrupted-operation
  recovery. Configuration validation and all 51 desktop/build Python tests passed; see local logs.

## Reproduction

- Imported 89 upstream commits into Fossil; work remains on `alpine-oldbook`.
  The upstream AGENTS.md was preserved. The requested contributor guide was
  created only after confirming `/home/jack/AGENTS.md` did not exist.
- Package lock: `packages/locks/87e87c6dff57a2af1664.json`.
  All 909 installed package identities matched signed archived APKs.
- Exported fresh from Fossil and restored all 909 packages with networking
  disabled. Names, versions, native architectures and control identities matched.
  This is filesystem/package verification, not a bootable disk image.
- Three Codex 0.153.4 musl archives preserve complete CLI/app-server layouts,
  code hosts, bwrap, ripgrep and the response proxy. The incompatible bundled
  GNU zsh is retained while the executable slot uses the locked Alpine zsh.
- Six source/runtime archives export with verified hashes. OpenSnitch and SwayFX
  source rebuilds succeeded offline with byte-identical independently built APKs.
  A source rebuild of every upstream Alpine package is not claimed.
- Private credentials and signing keys remain outside Fossil. Copy the complete
  database, including unversioned artifacts, when moving machines.

## Security integration remains separate

The OpenSnitch package and permanent packet gate passed isolated TCP/UDP,
IPv4/IPv6, allow/deny and daemon-failure tests. The staged radio controller
rejects WPA errors and verifies software blocking. This desktop check-in does
not establish that the live host firewall/radio policy is enforced, nor does it
claim physical RF silence, trusted location from an SSID, or tested boot/suspend
radio behavior. Continue the separate security integration before making those
claims.

## Workflow decisions

Use Fossil equivalents for the repository's Git-oriented workflow instructions.
Carry forward the user's authorization for the settled purple/rebuild design.
Keep changes reviewable and preserve unrelated work in this shared checkout.

## OpenSnitch follow-up and Caps Lock notifications

- The OpenSnitch external-output-queue monitor regression is fixed: a stale
  output interception marker no longer substitutes for a missing DNS rule.
  The r1 package build and isolated IPv4/IPv6 TCP/UDP packet tests passed;
  package-level evidence is in `packages/opensnitch/verification.json`.
  Live host firewall activation remains pending.
- Caps Lock now sends Escape in the active Sway session and saved configuration.
  The original notification helper followed retained SwayNC messages; the
  subsequent AI attention changes are recorded below. Five original helper tests,
  Sway validation, ShellCheck and
  disposable HOME deployment passed. Live keymap and LED readback, duplicate
  startup and SIGTERM cleanup were verified without clearing existing messages.
- Evidence and decisions: `docs/superpowers/specs/2026-09-07-caps-notifications.md`.
  Reboot persistence and physical LED/hotplug observation remain unverified.

## Workspace application names and AI integration

- Added largest-displayed-app workspace labels, preserving numeric navigation,
  the five original themed names and custom workspace bases. Codex in displayed
  tmux panes and recognized ChatGPT windows receive a star; the AI button and
  Super+i / Super+Shift+i provide switching and launchers.
- Added supported Codex completion and approval callbacks through SwayNC and the
  existing Caps Lock light, with private expiring pane/TTY routing records.
  The selective installer was applied with an exact private backup; Codex
  0.153.4 successfully loaded the resulting configuration.
- Configuration validation, ShellCheck and disposable HOME deployment passed.
  Isolated real-Sway area, resize, tabs, fullscreen, numeric navigation, manual
  rename, singleton, hostile label and graceful restore checks passed.
- Live labels, singleton startup, notification routing, event cleanup and LED
  readback passed. All 116 shared-checkout tests and 97 isolated-patch tests passed. Both test notifications
  were closed by their exact IDs; existing notifications remained present. Panel
  screenshots and results are saved under `verification/workspace-apps*`.
  Design and recovery details:
  `docs/superpowers/specs/2026-09-07-workspace-apps.md` and the linked Codex notes.
- The user confirmed the requested Codex hook setup. New Codex processes load
  the callbacks; the established hook definitions and trust are preserved.
  ChatGPT browser response completion
  cannot be inferred from window titles. Reboot persistence remains unverified.

## Pithos keyring

- GNOME Keyring installed; default encrypted collection created via desktop
  prompt. Live secret store/read/delete and Pithos default-collection connection
  passed. All 949 APKs in snapshot 8ca6ff2e0e60e4427ae7 verified.
- Pandora sign-in/playback and reboot/unlock remain unverified. No PAM changes.
  Details: `docs/superpowers/specs/2026-09-07-pithos-keyring.md`.

## Gruvbox Dark and additive artwork controls

- Applied Gruvbox across window chrome, Foot, Waybar, GTK 3/4, Qt 6, launcher,
  notifications, lock screen, tmux, shell, Neovim, btop and Cava. Removed window,
  panel and popup outlines following feedback. Existing Foot terminals received
  all 21 palette updates without closing applications. Both Sway parsers and
  app-specific parser/render checks passed; the shared suite passed 123 tests.
- Preserved click, right-click, middle-click, scroll and tooltip help. Added
  Command/Super+left-click and gallery generation commands. Nine real isolated
  pointer/keyboard checks passed. The native musl artwork widget rebuilt twice
  offline into byte-identical signed APKs.
- Generation retains daily limits and shared locking, saves a PNG/provenance
  pair in Fossil, and selects the exact finished image. Added safe themed and
  general collections; manual browsing still reaches all legacy artwork while
  timer rotation mixes the active theme with general images. Real Gruvbox
  Yosemite generation, checkpoint and activation succeeded.
- The matching cursor is installed. Warm gold folder icons rebuilt offline
  from locked Papirus input into 885 byte-identical output files; GTK icon
  lookup/rendering passed. Previous Spaceghost application configurations are
  preserved under `themes/profiles/spaceghost/`.
- Physical SwayFX takeover remains for the next normal login; the running
  stock Sway session cannot acquire blur/shadows through a reload. Current
  active window outlines are zero-width, including existing windows.

## STRATA and workspace defaults

- Super+6 opens/focuses the local Fossil review browser. First recognized app
  instances receive default placement once; existing/manual placements and
  extra instances remain free. The initial independent artwork arrangement was
  superseded by the user's request for one shared desktop image.
- Compact bar/window spacing, title decorations and live Foot transparency
  applied. Six distinct wallpapers and concurrent-launch reuse verified.
- Sway/Foot parsers, disposable deployment and focused tests passed. The full
  197-test run had one session-startup timeout; isolated rerun passed. Reboot
  persistence remains unverified. Details and recovery: 
  `docs/superpowers/specs/2026-09-07-strata-workspaces.md`.

## Shared painting, video backgrounds and Ghostty

- All workspaces now use the global painting, pause setting and timer. The
  previous individual artwork selections remain saved but inactive. The shared
  Space Ghost Yosemite painting and current symlink were verified; switching
  workspaces no longer selects a different image.
- Sway uses inner gaps 3 and outer gaps 4; Foot uses padding 4×4 and opacity 0.78.
  Existing Foot colors/opacity were refreshed safely. Padding takes effect in
  newly opened Foot windows; existing terminals were not restarted.
- Added `oldbook-video-background` and its command-deck picker. Playback loops
  without audio on the bottom layer, visible through transparent terminals.
  Stop targets the recorded process group and reveals the existing painting.
  Four focused tests and actual isolated mpvpaper playback/stop passed using a
  generated throwaway clip. No user video was supplied or started live.
- Installed Ghostty from explicitly tagged testing, with matching colors and
  opacity. The command deck and application launcher expose it; Foot remains
  the normal terminal binding. Ghostty's parser and disposable HOME deployment
  passed. Isolated native Wayland Unicode rendering and measured transparency
  passed with a fixed, content-free screenshot.
- Exact video/Ghostty APKs, identities and hashes are archived. Snapshot
  `0e1e8733a3ab9504808a` covers all 955 installed packages. Its earlier 952
  identities were unchanged; the three Ghostty additions passed signed APK,
  installed identity and Fossil export/hash checks. Full restore and reboot
  were not exercised for this incremental snapshot.
- Runtime evidence: `verification/shared-wallpaper.json`,
  `verification/terminal-video-layout.json`, `verification/video-background-headless.json`
  and `verification/ghostty*`. Usage/recovery: `packages/mpvpaper/README.md` and
  `packages/ghostty/README.md`.

## AI attention and transparent desktop monitor

- Caps Lock remains Escape. The active LED helper stays off without pending
  AI attention and flashes until each target window is focused or closed.
  Multiple provider windows remain independently pending. Opening the
  notification center acknowledges only alerts with no known target window.
  A reconnect regression prevents stale visibility from clearing later alerts.
- Codex callbacks are preserved and Claude notification hooks are installed
  with private backup/rollback. Ghostty and Claude are recognized; Claude now
  appears in workspace AI labels and the AI switcher. The LED and workspace
  services restarted successfully, the keymap still reports `CAPS=Escape`, and
  LEDs read zero. Focus changed during concurrent activity, so focus preservation
  is not claimed for that restart.
- Generic browser ChatGPT/Claude notices remain unsupported here because
  SwayNC supplies no validated site origin. Native provider notifications work;
  page titles never create attention. Browser response completion is unverified.
- Waybar puts the current-window/media capsule against the right status group.
  Outer ends stay square, while inner corners are rounded. A bottom-layer
  Unicode monitor shows CPU, memory, temperature, network, disk and uptime.
  It passes clicks through and reserves no desktop column.
- After mpv configures video output and starts playback, the video helper reloads
  only matching Waybar processes in the same Wayland session. Real isolated
  playback, monitor-through-Foot rendering, replacement, focus and stop/restore
  checks pass. Thirty focused attention tests, five video tests, independent
  reviews, native parsers, the 235-test shared suite and the 228-test isolated
  patch suite pass. Physical LED
  observation and reboot remain unverified.
- Evidence: `verification/ai-attention-led.json`, `verification/waybar-monitor*`,
  `verification/waybar-top.png` and `verification/video-monitor-headless*`.
  Indicator recovery: `docs/superpowers/specs/2026-09-07-ai-attention-led.md`.

## Square bar and terminal playlist player

- Removed all Waybar CSS corner radii and the SwayFX Waybar layer radius.
  Stock Sway and SwayFX parsers passed; live cropped screenshot is
  `verification/square-bar/bar.png`.
- Foot-only playlist playback is not implemented. Foot has no native video
  background option; the existing mpvpaper helper targets the whole desktop.
  A terminal-scoped renderer/compositor design is required. Pending: oldbook
  and watchlist playlist URLs, whether Delete affects YouTube or a local queue,
  and approval of the end-of-video Delete/Rewatch/Keep & Next design.

## Contextual shortcuts on a Super hold

- Enabled a non-focusable, scrollable overlay after either Super key is held
  alone for 500 ms. App shortcuts come first, Sway second, then applicable
  terminal/tmux/system controls. Releasing Super or pressing another key hides
  it; normal chords continue to work. App profiles explicitly show partial
  coverage, and Codex provides its `/keymap` browser entry.
- All 191 tests pass on the fixed committed export plus this feature, including
  62 shortcut tests. Independent specification/quality reviews, Sway validation,
  disposable deployment, focus/input/scroll/fullscreen/multiple-output checks
  and real include handling pass. The shared checkout run hit seven unrelated
  notification tests while their helper was being removed by another task.
- Live service is active with two read-only keyboard devices. Six files deployed
  using journal `~/.local/state/oldbook/backups/1788782412724579771`; duplicate
  startup preserves the daemon. Existing live Sway config was not reloaded.
- Abrupt compositor shutdown can make native GTK exit before writing final
  status; the process exits, resources close, and stale identities are rejected.
- Physical hold observation, real keyboard hotplug, VT switching and reboot
  persistence remain unverified. Usage/recovery: `SHORTCUTS.md`; runtime evidence
  and screenshot: `verification/contextual-shortcuts.{json,png}`.

## YouTube desktop player

- Launcher-controlled workspace-1 background/PiP player implemented. Local
  queue decisions, EOF hold, pause and position retention passed isolated
  compositor checks; public YouTube metadata and stream decoding succeeded.
- Original ghost button restored as requested. User playlist URLs/private
  sign-in and reboot checks remain pending. No remote playlist deletion.
  Details: `docs/superpowers/specs/2026-09-07-youtube-desktop-player.md`.

## 1Password installation

- Installed desktop 8.12.12 as the user Flathub app, official signed Alpine CLI
  2.39.0-r1 (`op`), and Mozilla-signed Firefox extension 8.12.32.33.
- Desktop native Wayland welcome/sign-in rendering and HTTPS connection passed;
  desktop launcher validated. CLI version/help and credential-free network
  update check passed. Firefox isolated-profile check reports active, enabled,
  and signed; the existing personal browser needs a restart to activate it.
- Six scoped Flatpak/CLI HTTPS and resolver rules were applied after 14 unit
  tests and 13 isolated firewall runtime checks passed; live watcher verified.
- Exact signed APK snapshot `ae4f34e18c202f0b71c0` covers 1007 packages. Firefox
  XPI is archived in Fossil and its export/hash verified. Flatpak commits and
  vendor tarball/executable hashes are recorded.
- Flatpak cannot integrate desktop unlock with Firefox/CLI or provide the SSH
  agent/system authentication. Account sign-in, vault access, reboot and a full
  offline Flatpak restore remain untested. Recovery and evidence:
  `packages/1password/README.md`.

## Reviewed firewall trial and staged radio safeguards (September 7)

- Installed verified OpenSnitch 1.8.0-r1. Added explicit reproducible application
  bootstrap rules, a detached rollback watchdog, and quiet GUI session startup.
  The correct private GUI socket is listening with default Deny.
- The live trial initially denied new IPv4/IPv6 input and unapproved output;
  a fresh authenticated Codex request passed. Later broad interactive rules
  allowed every root program and every application on TCP port 443. A repeated
  denial check failed, so the trial was rolled back; these rules were preserved.
  Application firewall is stopped and not enabled at boot, pending rule review.
- Firewall tests: 28 unit cases and the retained 13-group namespace proof.
  GUI tests: 8 plus the existing session concurrency check. Full trial and
  rollback evidence: security/firewall/activation-verification.json.
- Radio supervisor now enforces Bluetooth blocking during trusted Wi-Fi, safely
  handles invalid session state and respects concurrent authorized commands.
  Staged udev policy removes rfkill's seat ACL grant. All 23 isolated tests pass.
  Radio/udev/WPA/boot settings were not deployed; exact home/hotspot names and
  physical radio/boot verification remain pending.
- Package snapshot c0a227c1d5c4ea962d29 archives 984 installed APK identities and
  signatures. This snapshot was not subjected to another full root restore.
- Patched SwayFX binary still matches its verified hash; the current full
  SwayFX configuration validates with the isolated Intel backend. Stock Sway
  remains active. Bottom captions and effects start at the next normal login.

## Additive gallery gestures and editable prompts

- Kept left next, right gallery, middle pause/resume and scroll previous/next.
  Super/Command+left generates; either Shift+left opens the prompt editor.
  Shift wins when both are held. The native widget ignores non-keyboard Meta
  state, and original gestures work after modifier release.
- The gallery's 18 paintings had hidden all controls below a 16-row viewport.
  A 28-row picker preserves order and fits 1440×900 with 76px vertical clearance.
  Shared guidance now reflects strong Christian faith, admiration for historical
  medieval Crusades and a love of history. Eight original scenes remain and
  three historical scenes are appended. New theme design uses this guidance too.
- Added a GTK prompt editor with shared style and scene title/description fields,
  Save/Cancel, private exact-byte backups and external-change detection. Its
  runtime dependency and helper link are installed. Existing paintings remain.
- Native editor Save/Cancel, scene switching, backup bytes/modes and unchanged
  existing settings pass in private Sway. Screenshot and evidence are in
  `verification/gallery-prompts.{png,json}`.
- All 251 shared and isolated-checkout tests pass. Sixteen real native gesture checks pass
  inside isolated Sway, including both modifier keys, combined modifiers,
  non-keyboard Meta noise and original gestures. No test requested generation.
- Signed oldbook-waybar-art 1.0.0-r1 builds twice identically with networking
  disabled. The exact APK archive export, installed binary and live loaded
  library match. Waybar required a process restart to load the new library.
  Snapshot 7f91e56a66dca04fb8bb records 1007 installed APK identities; only the
  artwork package changed from the previous snapshot. No full restore rerun.
- Physical pointer/keyboard observation and reboot remain unverified. Evidence
  and recovery: `verification/gallery-controls.{png,json}`,
  `packages/waybar-art/verification.json`, and
  `docs/superpowers/specs/2026-09-07-gallery-additive-controls.md`.

## Persistent lease components and resolver compatibility (September 7)

- Staged a validated lease parser, persistent foreground DHCP manager and
  bounded authenticated hook. Real private acquisition/renewal keeps one client
  PID; NAK, silence, expiry, no offers and injected failure clean up owned
  processes. The manager checks expiry independently of delayed BusyBox events.
- WPA scan completion now requires the requested numeric scan ID and preserves
  events received before command replies. No live scan was requested.
- Staged native address/route/DNS application records generation ownership,
  retains partial state for cleanup and preserves unrelated state. Private
  tests verify home → hotspot → home IPv6 restoration and off-prefix gateways.
- All 131 radio tests pass. Seven native lease cases and six resolver locking
  groups pass with matching source hashes, unchanged normalized host state and
  no remaining namespace processes. Full owner/firewall integration is pending.
- Reproduced stock openresolv's two PID-namespace locking failures and packaged
  an explicit compatibility bridge. Two offline builds produced identical
  signed APKs. Source, patches, build inputs, logs and APKs are in Fossil UV.
  Installed main openresolv 3.17.4-r1 matches the tested script; live addresses,
  routes, DNS, radio state, resolver configuration and DHCP identities remained
  unchanged. The documentation APK and stock r0 rollback APK are archived.
- Snapshot 929661069218e44178e3 archives all 1,080 installed APK identities,
  verified against the live world, repositories and public keys. This checkpoint
  does not claim another complete empty-root restore or bootable disk image.
- Persistent radio-owner service/CLI integration, packet-gate/OpenSnitch renewal,
  resolver takeover, legacy-owner migration and reboot/suspend checks remain.
  Exact trusted home/hotspot identities remain unresolved. Live WPA and DHCP
  retain ownership; do not activate the legacy one-shot controller.
- Evidence and rebuild instructions: `security/radio/LEASE-OWNER.md`,
  `security/radio/{dhcp,network,resolver-bridge-install}-verification.json`,
  `security/radio/RESOLVER-LOCKING.md` and `packages/openresolv/README.md`.

## 2026-09-07: persistent radio owner and combined native verification

- Check-in `8fde0cfd32639b74` stages the persistent owner, root-only bounded
  IPC, compatible CLI routing, cancellation fences and reciprocal process
  guardian. Connect/scan cannot use the historical one-shot DHCP path; status
  remains read-only, and off retains its emergency blocking fallback.
- Ordinary off invalidates delayed requests. The guardian preserves child
  identity when inheriting ignored SIGCHLD. Cleanup retains and drains native
  process handles even when the first operation failed before owning an address;
  an unresolved crash marker prevents replacement connections.
- All 213 radio tests pass. Both current native fixtures pass seven cases each.
  The combined fixture uses the real CLI, owner, DHCP client and lease applier
  with synthetic WPA and virtual radio state. It verifies same-client renewal,
  off and stale requests, exact scan completion, home/hotspot IPv6 restoration,
  NAK and server silence. Host-state comparisons match; no private processes
  survive either fixture.
- Real veth IPv6 duplicate-address detection exposed the old three-second
  application cap: a successful combined apply took 3.312 seconds. The cap is
  now four seconds, with DAD retained, removal still three seconds, and the
  five-second hook deadline and actual lease expiry unchanged. Four new tests
  cover slow, failed, stuck and cancelled DAD.
- Failed fixture runs remain archived with their source hashes. The combined
  fixture now offers 32 seconds to allow BusyBox renewal and native application;
  the separate 16-second manager fixture still proves independent expiry.
  Server silence caused authenticated deconfiguration before expiry in the
  combined run; it sent no new lease or ACK and complete cleanup followed.
- `security/radio/owner-verification.json` records current source hashes and
  Fossil artifact names. `security/radio/OWNER-SERVICE.md` explains reproduction
  and limitations. No radio service was installed or live WLAN owner changed.
- The unchanged `packages/locks/929661069218e44178e3.json` still matches all
  1,080 installed package identities, world, repositories and public keys.
  Portable snapshot target:
  `~/.local/share/oldbook/backups/files-2026-09-07-radio-owner-service.fossil`;
  its adjacent JSON records completion, check-in, SHA256 and archived input count.
- Remaining: combined blocked-hook cancellation and guardian-death tests,
  OpenRC startup, packet-gate/OpenSnitch renewal policy, exact trusted SSIDs,
  profile RA/SLAAC decisions, orphan-state recovery, controlled legacy-owner
  migration and reboot/suspend acceptance. The live WPA/DHCP owners remain.

## Combined radio failure and packet-policy checks — 2026-09-07

- Seven combined fault cases passed in 19.20 seconds using the production
  guardian, owner, CLI, DHCP client and native applier in private namespaces.
  Cancellation during WPA/native waits, client/hook death, competing guardians
  and reciprocal guardian/owner death behaved as required. Blocking preceded
  teardown; all host comparisons matched and no test processes survived.
- Six packet-policy cases passed in 28.17 seconds with the installed BusyBox,
  nftables and OpenSnitch. Actual same-client unicast renewal passed through
  the existing DHCP exception. Controlled IPv4 UDP/TCP DNS rules distinguished
  executable, UID and resolver, including nested PID namespaces. Real IPv6
  DAD/neighbor discovery passed, and daemon death denied fresh DNS.
- The fixture explicitly prevents DNS eBPF module loading with a verified empty
  private module directory. OpenSnitch's DNS listener startup is independent of
  process monitoring; selecting proc alone does not disable it. This correction
  and four failed packet-fixture runs remain in the evidence. The first fault
  harness reporting failure also remains recorded without reconstructed results.
- Sources and reports are committed as `e8fe6ee814` and `6043a19199`.
  `security/radio/fault-verification.json` and
  `security/firewall/radio-policy-verification.json` reference source hashes and
  content-addressed Fossil evidence. Production runtime and live rules were
  unchanged in this pass; the earlier 213-test component suite remains applicable.
- `security/radio/INSTALL-PLAN.md` now describes the persistent owner handoff.
  `ORPHAN-RECOVERY.md` specifies same-boot crash recovery but is unimplemented.
  Owner death currently retains its marker and refuses replacement. OpenRC
  startup, recovery implementation, exact trusted profiles, deliberate live
  policy/owner migration and reboot/suspend acceptance remain unfinished.
- The current 1,080-package lock still exactly matches installed identities,
  world, repository configuration and public keys. Existing Hold to Help,
  Gruvbox theme settings, desktop controls and OpenSnitch choices are preserved.

## Orphan recovery primitives and desktop audit — 2026-09-07

- Added the durable root-private journal and namespace-init writer helpers,
  with 57 focused tests and independent module/cross-module review. Faulted
  file writes retain evidence; writer completion distinguishes PID reuse and
  missing metadata and signals only through a held pidfd. Nine immutable proof
  inputs are archived in Fossil; `security/radio/orphan-primitives-verification.json`
  records their hashes, scope and limitations. Check-in: `ef3ead5d42b6`.
- These helpers are staged and not wired into owner startup or command gates.
  Existing orphan handling still refuses replacement. Link-cookie lifecycle,
  lease/resolver recovery, native crash proofs and OpenRC handoff remain pending.
  No live service, radio, packet policy or installed package changed in this pass.
- Rechecked Hold to Help's 36-file release against source and installed files;
  signed main/doc packages, native bridge and local Gruvbox settings still match.
  OpenSnitch daemon, GUI and independent gate remain active with prompts enabled
  and existing grants preserved. Super remains selected pending trigger preference;
  physical Caps support is available. Public source location and maintainer contact
  are still required before distro submission; no publication was performed.

## Gallery hover instructions

- Fixed an unescaped ampersand in the generation instruction that made GTK
  reject the entire tooltip. All plain control text is now escaped at the
  Pango boundary, alongside title, story, collection and generation status.
- Restored Space Ghost control-room wording, Moltar/Zorak rotation comments,
  every original mouse gesture and both added modifier-click instructions.
  The live symlinked helper refreshes automatically; no package rebuild or
  bar restart is needed.
- All 12 artwork tests pass. The regression parses actual Pango markup in
  rotating/paused × idle/generating states and verifies visible literal text.
  Real private-compositor hover rendering and independent review pass;
  screenshot/evidence: `verification/waybar-art-tooltip.{png,json}`.
- The broad suite passed 252 of 254 tests. Its two shortcut-status failures
  also reproduce in the unchanged committed checkout (17 of 19 shortcut
  service tests pass). They remain outside this tooltip fix. Physical hover
  on the active display was not injected; native verification uses a private
  virtual pointer and makes no generation requests.

## YouTube account library in the launcher

- Added browser-session selection, public search, paged YouTube History,
  Watch Later and playlist browsing, and authenticated playback. Selected
  the existing Firefox profile by reference only; no credentials versioned.
- Twelve focused tests, real isolated desktop/PiP playback and disposable-home
  deployment pass. Full desktop suite: 260/262 passed; two existing shortcut
  status tests fail with "no shortcut service status for this display".
- Live account-list/search retrieval remains unverified because host DNS
  fails for both YouTube and Google. Browser fallback/sign-in and retry are
  available. No remote watch-history updates or playlist mutations are made.
  Usage and recovery: `desktop/YOUTUBE.md`; evidence:
  `verification/youtube/library.json` and `library-menu.png`.

## Apple trackpad gestures and Ghost Expo

- Enabled native 3/4-finger workspace swipes, up/down Expo, four-finger
  inward pinch for the launcher, and explicit tap/drag/natural-scroll settings.
  Applied 18 runtime settings and persisted the include without restarting Sway.
- Added on-demand searchable workspace/window layout cards; Super+E and the
  launcher also open Expo. No privileged daemon or additional packages.
- Apple bcm5974 reports libinput gesture capability. Three focused tests,
  parser validation, disposable deployment, and isolated rendering, keyboard
  workspace selection, search-to-window, close IPC and GTK down-swipe pass.
- Full suite: 263/265 passed; the same two unchanged shortcut-service status
  tests fail. Physical swipes await user observation; gestures over Waybar's
  exclusive area and application-specific macOS features are not claimed.
  Usage/recovery: `desktop/GESTURES.md`; evidence: `verification/gestures/`.

## Active-theme Expo and Super-hold

- Replaced Expo's fixed purple CSS with semantic colors from the current theme.
  Connected the active Qt Super-hold launcher to that same palette, with a
  one-second refresh. Restarted the live service; standalone Hold to Help's
  native-platform behavior remains unchanged.
- Four theme tests, 108 Hold to Help tests, real headless Expo interaction checks,
  both rendered Gruvbox previews and disposable deployment pass.
- Broad checkout suite: 276/284 pass; two known shortcut status failures and six
  Bazzite helper execution errors from concurrent work remain outside this fix.
  Evidence: `verification/overlay-theme/` and updated `verification/gestures/expo.png`.

## Quiet Conky panels and Foot drop-down — 2026-09-07

- Super+backtick/tilde toggles a persistent Foot terminal at the top of the
  focused output. Live create/hide/show, shell persistence, opaque rendering,
  Sway/Foot parsers and disposable HOME deployment passed.
- Conky now shows date, battery, gallery notes and rotating text at 60–240 second
  intervals. Removed fast system-stat panels and seconds. All four panels run.
- Full desktop suite: 327/329 passed; the two previously recorded shortcut status
  failures remain. Screenshots/runtime evidence: verification/dropdown-conky/.
  Exact 1,090-package snapshot: f4f8e961fd9563d312a9.
- Pending: identity of the requested Linux app, an email data source, physical
  keypress observation and reboot. Details/recovery:
  docs/superpowers/2026-09-07-dropdown-conky.md (from repository root).

## Fuzzel workspace picker replaces Expo cards

- Replaced the non-preview grid with the existing Fuzzel launcher, as requested.
  Search open windows or select workspaces, including empty numbered desktops.
  Existing Super+E and gesture entry points now open/toggle/close this picker.
- Preserved current-theme colors and Fuzzel typography/shape. Eight focused
  picker/palette tests, isolated window/workspace selection, cancellation,
  show/toggle/close behavior and disposable deployment pass. Physical gestures
  remain as previously documented. Evidence: `verification/gestures/`.

## Translucent drop-down below the bar — 2026-09-07

- Foot background now uses 84% opacity, preserving opaque text and the running
  shell. New shells get generous padding and a beam cursor. Placement follows
  the usable workspace top with one show/resize/position IPC transaction.
- Waybar's top panel now uses the overlay layer, including over fullscreen
  workspaces. Its saved one-line layer change remains alongside unrelated pending
  Waybar edits and is excluded from this focused commit.
- Foot/Sway parsers, offset-output geometry, live fullscreen hide/show and shell
  preservation pass. Visual evidence: verification/dropdown-conky/glass.png.
  Padding/cursor changes apply on the next normal shell close and reopen.

## 2026-09-07 — generated-theme launcher styling

- Added a shared Fuzzel palette adapter and routed application, command deck,
  gallery, YouTube/video, AI-session, and Expo menus through it. Active palettes
  are reread on each opening; generated three-color palettes get contrast-safe
  derived roles. Refined border, selection, and row spacing.
- Fuzzel parser, ShellCheck, theme tests, actual headless application rendering,
  Expo interaction checks, and disposable HOME deployment passed. Screenshots:
  `alpine/verification/launcher-themes/`.
- Full suite: 343 tests, three concurrent Superhold migration failures (one
  deployment alias and two legacy shortcut status checks). These remain outside
  this launcher change. Shared oldbook-wallpaper has concurrent panel edits and
  is excluded from the focused launcher commit; its two launcher calls are updated.

## Drop-down corner request — 2026-09-07

- Live compositor is stock Sway 1.12, which cannot round the Foot surface.
  Installed SwayFX 0.6 already has soft 6px global corners configured; its
  configuration validates. Its pinned corner_radius implementation is global,
  not a per-window or bottom-only control. No ineffective drop-down rule added.
- A 12px drop-down-only radius was considered but not applied after checking
  the implementation. Live rounding remains pending a normal SwayFX login;
  selective bottom-only rounding would require additional compositor support.
  The running desktop and shell were not terminated.

## 2026-09-07 — compact gallery image picker

- Image browsing now shows six paintings per page, sorted by generated_utc,
  then legacy created date or file modification time. Older/newer navigation
  and page counts keep the picker to at most nine rows and 48 characters wide.
  Generation and desktop controls moved into Gallery actions, with a back entry.
- Verified 11 gallery tests and nine wallpaper tests; inspected the real compact
  picker in isolated Sway. Screenshot: verification/launcher-themes/gallery-paged.png.
- Changes are live through the existing HOME symlink. Left this edit uncommitted
  because oldbook-wallpaper also contains concurrent desktop-panel changes;
  no unrelated work was included in a commit.


## Fossil GitHub mirror and Bazzite replay checkpoint (2026-09-07)

- Fossil remains authoritative on `alpine-oldbook`. The incremental Git mirror
  is `~/.local/share/fossil/files-git-mirror`; its `github` remote is
  `https://github.com/Spaceghost/.files.git`. Use
  `alpine/bin/publish-git-mirror` to export and publish that branch without force.
  Fossil autopush is off so existing GitHub branches remain under explicit control.
- `2ce53e613ad0` commits the mirror publisher, GitHub-to-Fossil bootstrap,
  scrubbed public-copy support and the exact 1,090-APK snapshot. Six publication
  tests and five bootstrap tests passed. A real full-history import matched
  all 1,411 exported files and executable modes at Git `252dd09c219a`.
- `823c162fb2dd` checkpoints staged radio source with the preserved non-root
  test log: 270 passes and 95 root-only skips. Native acceptance and activation
  remain pending; see `security/radio/checkpoint-verification.json`.
- `5f3d3a059e61` prepares the Bazzite desktop profile. Seventeen profile tests,
  shell checks and disposable deployment/Sway syntax validation passed on
  Alpine. Fedora image packaging, native Waybar/Superhold builds, systemd/NVIDIA
  behavior and LED permission validation still require the Bazzite host/image.
  A clean checkout of this commit also passes all 17 tests after correcting a
  test assertion that depended on an uncommitted Conky key binding; every
  actually retained Sway helper binding remains checked.
- The private full Fossil backup at
  `~/.local/share/oldbook/backups/2026-09-07-before-github-publication/` passed
  SQLite integrity and SHA-256 verification and includes 1,155 archived inputs.
- The separate scrubbed copy at
  `~/.local/share/oldbook/backups/github-20260907/files-public.fossil` is verified
  and includes 1,206 archived inputs. Its SHA-256 is
  `dc2ea87a802f999af9bc6308daa4995b6683040197ee687aa412c9586f5228ea`.
  This is a prepared local snapshot; it has not been uploaded.
- GitHub publishing is unfinished: native Git authentication is absent, and
  both device login attempts expired. An actual push was rejected for missing
  credentials. Complete `gh auth login --hostname github.com --git-protocol https`
  and `gh auth setup-git`, then rerun the publisher. No successful remote push
  or full-database upload is claimed by this checkpoint.
- Tailscale is absent on this Alpine host. Setup and identity-preserving Fossil
  replication commands are in `docs/GITHUB-FOSSIL.md`.
- The broader desktop suite previously retained two shortcut-status failures;
  it was not certified green during concurrent desktop/package rename work.

## Persistent quiet-panel policy — 2026-09-07

- A later working-tree edit appended the four historical telemetry panels to
  panels.json. Wallpaper relayout read those templates without a content guard.
  Removed them again; preserved Scripture, date, battery, gallery and rotating
  text. Scripture polling is now 120 seconds instead of 30.
- The loader now filters system-stat variables before placement/cache lookup and
  normalizes display/interval-command refreshes to 60–300 seconds. Restoring the
  old CPU/memory/network/storage templates therefore no longer renders them.
  New alpine/AGENTS.md records the user's choice for future contributors.
- All 26 Conky tests pass, including template regression, restored/renamed stats,
  cached rebuild, stale-config cleanup, permitted mail/battery and interval cases.
  Targeted disposable deployment passed; all five live processes reference clean
  generated configs at 60 seconds. Evidence: verification/conky-policy/.
- Email still needs a mailbox source. Arbitrary external command behavior is not
  inspected by the policy; new helpers must honor the documented slow-data rule.
  The broader unrelated desktop suite was not rerun for this focused change.

## 2026-09-07 — Superhold rename, native verification and offline restore

The portable contextual guide is now **Superhold**, installed and running as
`superhold` 0.1.0. Old commands, per-file config fallbacks and native ABI remain
compatible. Both local config names link to the versioned
`alpine/desktop/.config/superhold/config.toml`; Super alone for 0.5 seconds and
existing profiles, scrolling, help and desktop theming are preserved.

Verification: 114 source tests, 18 deployment/current-wrapper tests, two explicit
legacy GTK tests, and four private native Sway/X11/Qt6ct/LXQt checks passed. Two
network-isolated builds produced identical signed APKs. The exact 1,090-package
lock `c89b6eacc0617add1da5` restored offline into a separate root; both command
names and native-library paths loaded there. Evidence and reproducible artifacts
are linked from `alpine/verification/superhold.json`. Only the guide restarted;
public project hosting and maintainer contact remain required before submission.

Staged radio recovery evidence is separately archived in
`alpine/security/radio/orphan-integration-verification.json`: 247 selected tests
and nine isolated cases with 50 ms added to each journal write passed. Earlier
failed runs and limits are retained. This does not activate the staged controller
or establish physical-radio, OpenRC, surviving-writer or reboot acceptance.


## SQLite Coast to Coast notebook — 2026-09-07

- The rotating card now reads a private SQLite database at
  ~/.local/share/oldbook/journal/entries.sqlite3. All eight original Coast to
  Coast lines are preserved, with eight dated assistant-written journal notes
  based on observed desktop work. User feedback keeps the original style dominant:
  three quips for each journal note, one entry every 240 seconds.
- One-time seed/legacy import preserves the old lines without allowing later
  template changes to reset the database. Full text, source, date, enabled status
  and rotation state persist. The live DB stays outside Fossil; reviewed seeds
  are versioned. No automatic private-activity collection or network polling.
- oldbook-journal provides show/list/add/disable/backup. Unit tests verify durable
  rotation, 3:1 weighting, disabled entries, import preservation and readable
  backups; deployed CLI add/list/backup and integrity checks pass. A private live
  backup was made. All 5 journal and 26 Conky tests pass; evidence is under
  verification/desktop-journal/.
- The guard caught a concurrent change of Scripture polling to two seconds.
  Runtime stayed at the one-minute minimum; source was restored to 120 seconds.
  The source-regression failure is retained in the verification directory.

## 2026-09-07 — repair accumulating workspace titles

- Recovered managed workspace base names from stale repeated app suffixes,
  including polluted saved records. Restarted the live naming service and
  confirmed compact names on the actual bar. All 26 workspace tests passed.
- Evidence and recovery: alpine/verification/workspace-titles/.

### 2026-09-07 — scoped Scripture search and immediate selection

Super+/ is Bible-only; Super+Shift+/ uses the question keysym and searches
Torah, Babylonian Talmud, reflections, then Bible. Scope and ordering are covered
by regression tests and persistent alpine/AGENTS.md instructions. Enter now
saves selection metadata and replaces only the owned Scripture Conky process.
The private native Sway/Fuzzel test rendered the selected Torah passage within
three seconds while preserving 60/120-second background intervals. SIGUSR1
alone left cached text stale; that failed attempt is retained in verification.

Added 87,327 English Jewish-text segments, source hashes, edition/license
attribution, a deterministic offline builder, and exact raw inputs in local
Fossil UV storage. A network-disabled rebuild matched byte for byte. Validation:
29 Scripture tests, 26 Conky tests, five journal tests, Sway parser and real
Fuzzel Enter integration passed. Evidence: verification/scripture-selection/.
The live audit preserved the previous selection and other panel PIDs. Original
quip/reflection collections remain. Email still needs a mailbox source; rounded
terminal corners still need the configured SwayFX session at a normal login.

## 2026-09-07 — Agent danger defaults and terminal font

- Local and Alienware Codex launcher commands now match the ocodex alias in shell history: --search --dangerously-bypass-approvals-and-sandbox -s danger-full-access.
- Both Claude launcher commands use --dangerously-skip-permissions with inline settings disabling sandbox.enabled and skipping the danger confirmation.
- Foot regular/bold/italic fonts now default to 9.5 pt in the desktop base and both themes (11 pt minus three 0.5 pt decrements). Live symlinks already point to these files; new terminals/sessions use the defaults.
- Verified: all three Foot configs pass foot --check-config; four agent commands preserve argv through local/remote command construction and parse with installed local CLI --help.
- Existing agent suite: 23/25 pass. Two SSH preflight tests patch the runpy result instead of function globals; both pass with the intended reachability stub applied to function globals in an isolated verification run. Test files unchanged.
- Pending: visual confirmation of a fresh terminal and end-to-end local/Alienware agent sessions; no remote session was started.
- Recovery: restore prior command arrays and size=11 in these four config files; existing sessions retain their launch settings.

## 2026-09-07 — Workspace edge captions and terminal transparency

- Added oldbook-decoration with persistent bottom/right modes, vertical em-dash separators, configured terminal font size, and compact borderless themed chrome.
- Middle Waybar island fits its content, leaves side gaps, yields to workspace controls, and hides on empty workspaces. Foot theme profiles use alpha=0.78 and alpha-mode=all.
- Passed decoration/terminal unit tests, ShellCheck, Foot and compositor configuration validation, and isolated rendering of both caption positions, fullscreen, long/short/empty middle bars. See alpine/verification/workspace-chrome and docs/superpowers/decisions/2026-09-07-workspace-edge-chrome.md.
- Live session has the workspace helper installed. Bottom remains the default; right-click toggles positions. Existing terminals received a palette refresh; new terminals get the full alpha-mode behavior.
- Remaining limitation: runtime Ctrl+- font zoom is local to an existing Foot window; the workspace caption tracks the saved Foot font setting. Physical multi-monitor hotplug was not exercised.
- Shared Waybar and native Sway theme files also contained another active task's edits; their live changes are preserved in the checkout and were not swept into the workspace-caption commit.

## 2026-09-07 — Notification host correction

- Popups and compact history use layer-shell top surfaces, so they appear over ordinary windows while overlay-layer stay-on-top chrome remains above them. History still opens only on request and reserves no exclusive zone.
- Removed SwayFX blur, shadows, and corner clipping from the entire notification/history hosting surfaces in all profiles. GTK still styles each actual card. The empty full-height host is transparent again.
- An isolated top-layer test preserved terminal focus and geometry and kept an overlay-layer 32px bar above the complete popup. A separate live overlay-layer diagnostic established that disabling host effects fixes the transparent host without changing any window rectangle; only its layer selection was superseded.
- Evidence: alpine/verification/notifications/result.json and top-layer-popup.png; alpine/verification/notification-overlay/result.json retains the host-effects diagnostic. Recovery: revert notification config/effect blocks and reload swaync plus SwayFX.


## 2026-09-07 — Theme-aware desktop decoration settings and native tools

- Added a desktop decoration editor showing placement, opacity and corner controls
  beside the editable JSON. Both panels validate before saving; stale edits are
  rejected when another process changes the file. Deployed symlinks and legacy
  placement migration are preserved. Open with oldbook-decoration-settings,
  oldbook-decoration settings, or Shift + right-click on the caption.
- Bottom is selected and the right edge remains available. The user changed live
  opacity to 0.67 in the editor; that preference is preserved. Captions follow
  the active theme with a translucent gradient and no outline. Fullscreen tiled
  captions use square corners, while floating/ordinary captions retain rounding.
- SwayFX layer clipping no longer overrides dynamic caption corners. Notifications
  use TOP below overlay chrome, with no transition or reserved window space;
  transparent host surfaces retain the separate blur/shadow correction. Lock
  ring and all indicator states now derive from the active validated palette.
- The center window-title capsule is replaced with previous/play-pause/next
  music controls. A two-player native check confirms actions target the player
  being displayed. Window titles remain in the bottom/right decoration.
- Built, verified and locally archived a complete native Codex 0.153.4-r0 APK for
  Cascadia testing, without npm or Node. Its CLI, app server, both code-mode
  helpers, resources and responses proxy are checked after clean extraction;
  Alpine zsh occupies both private shell slots. Existing /usr/local/bin tools
  and /opt installation remain available. Recipe and exact artifact hashes are
  under alpine/packages/cascadia/testing/codex/; local commit 570c4bc299b6.
- Installed/archived oldbook-waybar-art 1.0.0-r3 with contextual GTK help for
  workspaces, CPU and mode, preserving all original artwork actions. The complete
  1,099-package snapshot is locks/0b39a04f417c70933a4e.json and exactly matches
  installed APK identities. No remote publication was requested or performed.
- Validation: 9 decoration and 5 lock tests; nine native settings save/invalid
  JSON/external-conflict/reload checks; actual fullscreen-square/floating-rounded screenshots;
  both caption theme previews; compositor/Foot parsers; ShellCheck; isolated
  deployment of the settings files. Live Sway reload returned success and only
  the decoration helper was restarted. Native tooltip and artwork action tests
  passed on the installed r3 library. Left-click now opens the gallery and
  right-click advances artwork; Super/Shift/middle/scroll actions are retained.
  The live bar maps the current r3 library, with updated hover instructions.
- The final broad desktop run passed all 512 tests in 66.437 seconds. An earlier
  run exposed six failures/errors while separate gallery work was in progress;
  those sources have since been corrected by their owner. The legacy shortcut
  fixtures explicitly exercise the legacy implementation and all 19 related
  tests pass. A status-stream lifecycle fix passed 20 focused tests and removed
  nine orphan readers without touching the active reader. Fullscreen and layering
  evidence uses private synthetic sessions; the live screen was not locked,
  and physical multi-monitor hotplug was not exercised.
- Recovery: choose bottom/right in the editor or restore decoration.json; the
  scoped live deployment backup is 1788826717244561542. To restore native
  per-window captions, follow the workspace-edge decision document. Package
  manifests keep the prior inputs and exact signed artifacts locally.

## 2026-09-07 — Prompt-only gallery themes and generation retries

- Create theme from prompt is directly visible; names are generated automatically. Existing theme names have a separate searchable picker, and four paintings per page leave all navigation/actions visible.
- Theme design and painting each allow three retries after the first attempt, with 2/4/8-second waits, one lock, per-attempt logs and saved error history. Image retries reuse the designed theme; checkpoint/activation failures do not repaint.
- All 511 desktop/deployment tests and ShellCheck for oldbook-session pass. Real isolated Fuzzel screenshots are in alpine/verification/gallery-prompts; details and recovery are in docs/superpowers/decisions/2026-09-07-gallery-prompt-retries.md.
- A final live check found a diagnostic Waybar using probe.jsonc/probe.css in place of the normal bar. Stopped that exact process and attempted regular config/style recovery under the session lock, but another Claude session replaced it again with probe2.css. At the user's request, identified the Claude probe worker by its open session scratchpad descriptor and terminated it gracefully. Verified its exit and one regular purple Waybar visible; no further tests were run. The initial exit cause remains unproven. A separate reproduced session startup failure when the Waybar config directory is absent is fixed by creating that directory first.
- Unfinished check: no fresh provider generation was requested for verification; retry recovery used injected failures. Private evidence is in ~/.local/state/oldbook/verification/theme-prompt-retries/.

### Speaker routing investigation — 2026-09-07

- MacBookPro11,5 CS4208 detected on PCH; ALSA Headphone Jack reads 1, causing ACP to mark Speakers unavailable. Speaker and Bass Speaker switches are enabled, headphone playback muted, Auto-Mute disabled.
- Saved the analog sink as the preferred output and directly linked Pithos FL/FR to its speaker playback ports. Live output changed from SUSPENDED with unlinked music to RUNNING with both channels active at 50%. This is a temporary routing workaround, not a detection fix.
- Pending: user confirmation whether a plug is physically present and whether sound is audible; automatic routing, restart persistence, and jack insertion/removal remain unverified. No driver or profile override applied.
- Local evidence and original route state: `~/.local/state/oldbook/audio-repair/`. Undo temporary links with `pw-link -d Pithos:output_FL alsa_output.pci-0000_00_1b.0.analog-stereo:playback_FL` and the matching FR command; `wpctl clear-default 0` removes the newly saved sink preference.

### Persistent speaker workaround — 2026-09-07

- User confirmed empty headphone jack and audible speaker playback. Installed card-specific ACP paths that ignore the false headphone presence signal; headphones remain manually selectable.
- Verified custom profile parsing, speaker/headphone selection, persistence across WirePlumber restart, default-speaker metadata and automatic routing of a fresh three-second playback stream. See `docs/superpowers/decisions/2026-09-07-oldbook-speaker-jack.md`.
- Pending: audible confirmation after this override, full reboot and physical headphone playback. No kernel/package changes.

## 2026-09-07 — Contextual bottom workspace strip

- Built the approved rounded theme-gradient strip with app icon, readable title, subdued window state, hover hints, and float/tile, fullscreen, window-picker and menu controls. Empty workspaces offer launchers. Saved opacity, radius and placement remain intact.
- Right-click now opens window/workspace/layout/scratchpad controls; Shift+right-click retains appearance settings. Window actions capture the displayed container ID. Optional terminal/tmux and PID-matched MPRIS actions are discovered when the menu opens.
- Installed by restarting only oldbook-decoration. Observed its rendered strip and startup log; corrected a missing desktop-file icon fallback encountered at startup. Screenshot: alpine/verification/decoration-context/bottom-strip.png. Decision/recovery: docs/superpowers/decisions/2026-09-07-contextual-workspace-strip.md.
- Per the user's explicit instruction, no tests or live interaction probes were run. Menu actions, tmux/media behavior and multiple outputs remain unverified. Startup emits existing GTK/GI deprecation notices. Private logs and screenshots: ~/.local/state/oldbook/decoration-context/.

### Last.fm dependency — 2026-09-07

- Installed Alpine `py3-pylast` 5.5.0-r1 and verified import of pylast and the Pithos Last.fm plugin using its GTK 3/gettext setup.
- Added the package to the desktop world list; signature-verified and archived all 18 new APKs in local Fossil unversioned storage, with hashes in `alpine/packages/locks/pylast-5.5.0-r1.json`. This supplemental manifest is not a full restore lock.
- Pending: restart Pithos, enable Last.fm in Preferences / Plugins, authorize the account and verify a real scrobble. Account credentials were not accessed.

## 2026-09-07 — Super closes an open Superhold guide

- The running GTK Superhold installation comes from projects/superhold-guide, not the alternate Qt project. Added a counter for fresh presses of either physical Super key and dismiss an open/loading guide when that counter changes. Repeat events are ignored; dismiss cancels the current hold so it cannot immediately reopen.
- Updated the two corresponding installed modules in ~/.local/share/superhold/versions/0.2.0.dev0-70e5051/lib/python3.14/site-packages/superhold and restarted only that daemon. Previous installed files are saved under ~/.local/state/oldbook/superhold-super-dismiss/*.before; restore those two files and restart Superhold to recover.
- Reviewed the exact source diff and installed startup log. Per the user's stop-testing instruction, no tests or simulated key presses were run. Physical key behavior remains unverified.


### Bottom caption / Conky clearance (2026-09-07)

- Corrected the observed 42-pixel Conky displacement caused by Waybar's reserved
  top area. Refit six panels with 60-pixel bottom/right clearance and invalidate
  cached placement when reservations change.
- Scripture search now uses physical-output coordinates with a 60-pixel bottom
  margin. Caption retains purple glass with a subtle accent outline.
- Live geometry and desktop screenshot: verification/bottom-bar-spacing/.
  All six rendered Conky surfaces match planned positions; desktop surfaces
  clear the caption by at least 12 pixels. Conky and decoration regression tests
  exercised; recovery and compositor limitation recorded in
  docs/superpowers/2026-09-07-bottom-bar-spacing.md (repository root).
- Not checked: other compositor implementations or display scales.

### Pithos background startup and music-bar gestures — 2026-09-07

- Installed `oldbook-pithos`, session autostart and hidden-window rules. Left-click on the title toggles playback after 350 ms, double-click opens without toggling, and right-click anywhere on the music modules shows/hides Pithos. Arrow left-clicks retain previous/next. Live bar reloaded; actual Pithos window tested and left hidden.
- Ten helper tests, session concurrency test, ShellCheck and Sway parser pass. Native isolated GTK/Sway/Waybar pointer test passes; evidence in `alpine/verification/pithos-controls/`.
- Full suite: 547 tests, 546 passed, one unrelated Conky error (`test_wallpaper_rebuild_and_cached_layout_cannot_restore_telemetry`, `KeyError: origin_y`). No Conky files changed. Full login cycle and physical XWayland behavior remain untested.
- Recovery/design: `docs/superpowers/decisions/2026-09-07-pithos-bar-controls.md`.

### tmux titles in the bottom decoration — 2026-09-07

- Enabled tmux terminal-title forwarding from `pane_title` in the Alpine desktop and both theme profiles; applied live without restarting sessions. The two tmux Codex windows now publish full working-state/context titles, and the decoration receives them through existing Sway title updates.
- Validated all three configurations and changing pane titles in disposable tmux servers; confirmed live Sway and decoration context titles. Local JSON/screenshot evidence: `~/.local/state/oldbook/tmux-title-*`. Full logout/login remains untested.
- Decision and recovery: `docs/superpowers/decisions/2026-09-07-tmux-decoration-titles.md`.

### tmux agents in the count and switcher — 2026-09-07

- Fixed custom terminal app-ID detection by consulting the existing owned-process snapshot, allowing `oldbook-agent` windows into the existing tmux resolver. Restarted only the workspace service; live bar now reports all four open Codex windows, including both previously omitted tmux windows.
- Fifteen identity and 26 workspace tests pass, including custom-ID tmux discovery and integrated count/switch regression. Live evidence: `~/.local/state/oldbook/tmux-agent-bar-verification.json`. Design/recovery: `docs/superpowers/decisions/2026-09-07-tmux-agent-discovery.md`.

## 2026-09-07 — Animated floating decoration attachment

- The focused floating window now carries its bottom/right decoration. Actual fullscreen on its visible workspace forces the workspace bottom bar; exiting restores the saved preference. Sway's synthetic workspace fullscreen marker no longer mislabels normal windows or reverses the fullscreen action.
- Display-frame animation uses a short critically damped glide and soft mode fades, with persistent 16 ms geometry reads while attached. No outline border; saved theme, opacity 67% and radius 7 preserved.
- Passed 40 focused unit tests and 25 private native checks, including held-drag intermediate frames, exact small-window geometry, unreserved tiled space, fullscreen corner pixels and focus/workspace/destroy cleanup. Evidence: alpine/verification/decoration-attachment/. Deployed only decoration files and restarted its helper; confirmed one live caption.
- Remaining: physical multi-output and mixed-refresh rendering were not exercised. Existing GTK/GI deprecation notices remain. Decision and recovery: docs/superpowers/decisions/2026-09-07-floating-decoration-attachment.md.

## Super+Shift artwork click — 2026-09-07

- Installed oldbook-waybar-art r4: Super+Shift+left-click creates a random named
  gallery theme and displays its first painting. Both sides and mixed modifier
  pairs work. Ordinary clicks, Shift editing and Super painting are preserved.
- All 555 repository tests and 23 installed-library headless interactions pass;
  production tooltips render in rotating, paused and generating states. Two
  offline builds are byte-identical; signature, Fossil APK readback, installed
  payload and live Waybar mappings verified. No generation was invoked by tests.
- Derived the restoration lock from its predecessor with only the r4 APK/world
  identity changed. Pending: reconcile pre-existing host pylast/dependency
  additions into a full host snapshot and perform a full isolated restore.
  Details/recovery: `../docs/superpowers/decisions/2026-09-07-bar-new-theme-gesture.md`.

## 2026-09-07 — Workspace number and name emphasis

- Active workspace number/name are bold and bright; inactive numbers stay bold with regular names. Process suffixes remain regular and subdued across focus and rename updates in both themes.
- Installed signed oldbook-waybar-art 1.0.0-r5 and restarted only Waybar. Passed two identical offline builds, signature/archive checks, 38 GTK checks, six native Waybar states and four tooltips. Synthetic proof: alpine/verification/workspace-emphasis/.
- Restored exact package-lock coverage for all 1117 installed identities, including 18 existing Pylast dependencies missing from the previous lock. Decision/recovery: docs/superpowers/decisions/2026-09-07-workspace-label-emphasis.md. No requested checks remain pending.


## Codex quick launch — 2026-09-07

- Super+left on the Agents (✦) bar module and Super+Ctrl+N invoke
  `oldbook-agents quick`: GPT-6 Astra, ultra reasoning, live search, and
  `--dangerously-bypass-approvals-and-sandbox` in a fresh tmux session.
  The terminal opens on the workspace captured at invocation, starts in `~`,
  and is exempt from first-instance workspace placement. Ordinary left/right
  bar clicks and Super+N retain their existing functions.
- Existing home symlinks apply the changes. Sway reload returned an IPC timeout,
  but the new keyboard binding was subsequently exercised successfully;
  the workspace service was restarted and the active Waybar reloaded.
- Validation: 27 agent tests and 31 workspace tests passed; Sway validation
  passed. Live Codex displayed `gpt-6-astra ultra` and `YOLO mode`. A real
  uinput Super key plus the bar handler created a new session on the captured
  workspace (5 → 5). Evidence: `/tmp/oldbook-quick-launch-evidence.json` and
  `/tmp/oldbook-quick-key-evidence.json`.
- The broad desktop suite was interrupted after several minutes in unrelated
  profile/deployment tests; it did not complete. Focused launcher/workspace
  validation above passed. Partial output is in `/tmp/oldbook-quick-tests.log`.
  No security-service runtime changes or tests are part of this launcher change.
- Changes remain uncommitted because Sway, Waybar and progress documentation
  have overlapping concurrent edits; those unrelated edits were preserved.
- Recovery: remove the Super+Ctrl+N binding and restore the agent module's
  `on-click` to `oldbook-workspaces ai-next`, then reload Sway and Waybar.
  Existing tmux sessions survive terminal closure; reattach with Super+N.

## Personal tmux controls — 2026-09-07

- Restored Ctrl+A, native Vim/split/resize/copy controls, 1-based new windows and
  panes, mouse/clipboard and 10,000-line new-pane history through a shared theme
  include. Reloaded the live server; all three remaining sessions report Ctrl+A.
- Validated 25 shipped/rendered configurations in disposable tmux servers and
  passed 21 deployment/complete-theme tests. Live pane processes and status
  styling survived reload. Evidence: `~/.local/state/oldbook/tmux-preferences/`.
- Not exercised: physical keyboard interaction and a logout/login cycle.
  Design/recovery: `docs/superpowers/decisions/2026-09-07-tmux-personal-controls.md`.

## 2026-09-07 — Theme-following investigation paused at user request

- Superhold is still unresolved: its running GTK installation lacks the newer
  `DesktopTheme` module present in the checkout and loads its palette only when
  constructing a window. No runtime changes or tests were made in this checkpoint.
- Resume from `../docs/superpowers/plans/2026-09-07-theme-following-handoff.md` for
  installed/source paths, verification and recovery steps, and the other known
  application refresh gaps. User requested a quick wrap-up until capacity improves.

## 2026-09-07 — Complete theme profiles and music ratings

- Every existing theme has a validated desktop design; future generation requires
  font, geometry, spacing, opacity, bar/widget placement and launcher width.
  Missing profiles render from shared controls. Switching deploys the full
  application overlay and matching art; new-theme activation uses the switcher.
- Music area middle-click shelves the current Pithos song as tired; Super+middle
  bans it. Native GTK actions work without raising the player. All three music
  sections retain their playback and window controls. The live bar was reloaded.
- Validation: 49 theme/artwork tests, 3 complete-profile/recovery tests, 42 Conky
  tests and 13 Pithos tests passed. Foot, Fuzzel and Ghostty parsed 11 profiles.
  Two native private desktop previews and private Pithos gesture evidence are
  in verification/complete-themes/. Vespersteel Archive subsequently arrived
  with the required design fields and became active through the new pipeline.
- Limits: previews cover two themes, not every application in every theme.
  Physical modifier snapshots have unit coverage; native pointer/D-Bus tests
  used fixture modifiers and a fake player. No actual songs were rated by tests.
- Recovery: restore the source checkpoint with Fossil, run oldbook-theme sync,
  then oldbook-theme use <id> --no-reload to rebuild HOME. Deployment backups
  retain the previous configuration. Rendered profiles are local derived files.
  Unrelated pending desktop, security and publication edits are preserved.

## 2026-09-07 — Stable Conky and adaptive Scripture search

- Removed automatic window/fullscreen Conky reflow and stopped the live watcher.
  Cards keep clearance positions; Scripture search alone follows free/occupied
  bottom space using direct Sway IPC and updates with the active theme.
- Added upper-right Scripture and lower-right Coast to Coast preferences plus
  native click-to-advance on Scripture, Witness, journal and Gallery cards.
- Placement CPU fell from a measured median 1.286s to 0.0505s (96% lower),
  preserving exact results. Background intervals remain 60–300 seconds.
- Passed 43 Conky tests, 10 geometry tests, two native GTK theme tests,
  ShellCheck, compositor validation, eight private geometry scenarios and
  native text-click/redraw/input checks. All six live cards and four click
  hooks verified; scoped deployment backup: 1788832594244521506.
- Full 594-test run had two timeout errors; both passed separately. The
  disabled-card test no longer loads the whole library for unrelated setup.
  Full-suite rerun, physical multi-output checks and real-artwork Gallery click
  verification remain unperformed. Evidence: verification/desktop-space/ and
  verification/conky-clicks/. Decision/recovery: repository docs/superpowers/
  decisions/2026-09-07-adaptive-desktop-space.md.

## 2026-09-07 — Local Superhold theme update installed

- Packaged and activated `0.2.0.dev1-2c5a0afe5578` from `projects/superhold-guide`.
  The guide, settings and release overlay now use the local theme-following code;
  existing physical Super dismissal fixes and personal settings were preserved.
- 134 unit tests, two installed Super-key checks, three desktop validators,
  source/install hash comparison and same-process dark/light graphical checks pass.
  Rollback and reactivation were exercised; `~/.local/bin/superhold-rollback`
  restores the preserved dev0 installation.
- Artifacts/hashes: `packages/superhold-guide/manifest.json`. Evidence/recovery:
  `../docs/superpowers/decisions/2026-09-07-superhold-dev1-install.md`.
  Broader application theme gaps remain in the earlier handoff.

## 2026-09-07 — Decoration animation frame budget

- Included IPC processing in a 120 Hz geometry budget and removed redundant GTK
  resize calls during movement. Restarted only the decoration daemon; one live
  caption retains bottom placement, 67% opacity and radius 7.
- Passed 41 decoration unit tests and all 25 native attachment/fullscreen checks.
  The 120 Hz virtual output measured 63.47 animation callbacks and 62.84 draws
  per second. Physical scanout is not measured; the live panel is nominal 60 Hz
  and the headless backend adds rendering time to its refresh timer.
- Stopped nine confirmed orphan Conky test clients consuming roughly four CPU
  cores. Identity-safe cleanup is now in the concurrent Conky check-in. Evidence,
  screenshots, precise timing limits and recovery: verification/decoration-framerate/
  and ../docs/superpowers/decisions/2026-09-07-decoration-frame-budget.md.

## 2026-09-07 — Ghostty terminal shortcut and theme typography

- Super+Enter now launches Ghostty. The selected theme's primary Foot font and
  point size also drive Ghostty during theme sync and selection, including generated themes.
  Active Vespersteel uses JetBrainsMono Nerd Font at 9.5pt in both terminals.
- All 12 profile pairs and the base Ghostty config validate; eleven theme tests pass.
  Ghostty received its supported live reload and stayed running. Sway and SwayFX
  config validation pass; the live Mod4+Return binding was applied directly.
- Evidence: `verification/ghostty-theme-fonts.json`. Existing profile padding
  changes from concurrent theme work remain preserved.


## Ghostty drop-down and fresh gallery generation — 2026-09-07

- Super+backtick/tilde now opens a dedicated Ghostty scratchpad with the existing
  size, bar clearance, 84% opacity and persistent shell. The old Foot shell is
  preserved. Native live hide/show retained the same PID/container (warm show
  about 0.10s); isolated cold launch, typing, hide/show, offset output, exit/reopen
  and duplicate-window prevention passed. Sway/Ghostty parsers, 18 deployment
  tests and disposable HOME deployment passed. Evidence: verification/ghostty-dropdown/.
- Super+click now excludes painted subjects and insertion/medium mixes across
  themes, inventing a fresh subject and mix when the catalog is exhausted.
  New-theme design rejects repeated scene/art-direction proposals. History
  merges archived artwork and failed image attempts without a 2,000-record cutoff.
  All 89 focused artwork tests passed; read-only live selection recovered 74
  records and excluded 24 old catalog scenes. Evidence: verification/fresh-scenes.json.
- Outstanding: physical terminal shortcut presses and reboot were not observed;
  no external text/image generation was requested to test novelty. Prompt checks
  detect exact/lightly rewritten reuse, while actual visual novelty remains a
  live generation check. Recovery and decisions: docs/superpowers/decisions/
  2026-09-07-ghostty-dropdown.md and 2026-09-07-fresh-gallery-scenes.md.

## 2026-09-07 agent window switching installed

Alt+Tab now opens the themed agent window picker across workspaces; Shift reverses, final Alt release accepts, Escape cancels. Live include/module/launcher deployed and Sway mode confirmed. Eleven switcher tests and 53 focused tests pass; native private Sway keyboard, lifecycle and dark/light rendering checks pass. Screenshots, hashes and recovery are in `alpine/verification/agent-switcher/` and `docs/superpowers/decisions/2026-09-07-agent-window-switcher.md`. Super+Enter preference is preserved in `sway/local.d/terminal.conf`. Physical keyboard confirmation in the live session remains user-observable; broader application theme gaps remain in the earlier handoff.


## Centered Super+plus/minus window resizing — 2026-09-07

- Super+plus/equals grows and Super+minus shrinks both dimensions by 40 logical
  pixels around the current center; keypad keys work too. Tiled windows become
  floating with their original center retained; fullscreen exits before resizing.
- Native resize-set handles independent size limits; the helper coalesces key
  repeat. Managed HOME deployment and all six live bindings are installed.
- Fourteen isolated Sway runtime checks pass, plus parser/compilation and
  disposable HOME deployment. Evidence: verification/centered-resize/.
- Outstanding: physical Shift+= mapping and reboot persistence unobserved.
  Recovery/decision: docs/superpowers/decisions/2026-09-07-centered-window-resize.md.

## STRATA workspace-zero service verification — 2026-09-07

The workspace-zero supervisor passed 22 unit tests and seven isolated native
behavior groups, including pinning, relaunch, singleton launch and compositor
crash cleanup. Live activation observed one review window on zero, a held
daemon lock and HTTP 200 from the local Fossil endpoint. The browser restarted
under the final supervisor using its existing profile. Native bar r6 passed
45 GTK checks, two identical signed offline builds, installation and live
module mapping. Exact sources, screenshots and runtime evidence are retained
in `alpine/verification/strata-service/` and `workspace-strata-zero/`.

The user requested workspace 10 on the 0 key; that mapping is now committed
and active. The dedicated `verification/workspace-ten/` evidence records 61
focused tests, seven isolated native groups, and live migration preserving the
workspace and review-window IDs. Numeric workspace 10 exists and workspace 0
is absent. Earlier zero evidence remains historical. No real logout/login cycle
was performed.


## MacBook keyboard backlight — 2026-09-07

- Enabled at 64/255 (25%). Actual LED writes, saved-state restoration including
  off, concurrent adjustments, and live Sway illumination-down/up dispatch
  passed. Evidence: `verification/keyboard-backlight/`.
- Physical F5/F6 presses, operation during an actual locked session, and
  restoration after a new graphical login remain unverified. The existing
  `hid_apple` Fn policy remains unchanged.

### 2026-09-07: immediate decoration tile/float transitions

- Removed the mode-change crossfade that left the old caption visible while the
  replacement faded in. Tile/float and fullscreen attachment changes now map a
  fully visible replacement immediately; ordinary drag/resize springs remain.
- Isolated native traces reduced stable attachment from 231 to 22 ms for plain
  floating and 305 to 91 ms for centered resize, with no caption overlap. These
  measurements do not cover physical panel scanout.
- All 41 decoration unit tests, Python compilation, and 28 native attachment
  checks passed. Restarted only the live helper and verified its source hash,
  one caption per active output, and unchanged saved appearance settings.
- Evidence: `alpine/verification/decoration-transition/`. Decision and recovery:
  `docs/superpowers/decisions/2026-09-07-immediate-decoration-mode-changes.md`.

## Workspace names ready before first focus — 2026-09-07

Named workspace switch/move commands now include their full titlecase labels
at creation. `4: Signal` is present in the first Sway init/focus event, with
no dependency on the application naming daemon. The overview, show-desktop
return and automatic placement use the same names; existing custom names
and workspace identities remain intact. Exact legacy uppercase defaults
migrate through a batched rename because Sway otherwise ignores case-only
changes. The IPC client retries a full Unix listen backlog within three seconds.

Validation: 99 focused Python tests, 17 private native Sway checks, the Sway
parser and 126 native GTK checks pass. The signed r8 bar APK came from two
identical offline builds, is archived and installed, and matches the running
Waybar mapping. The immutable 1119-package lock is
`alpine/packages/locks/368a9c51ce0830f4e791.json`. The live workspace strip was
visually checked; focus and workspace IDs were preserved during migration.
Evidence and recovery: `alpine/verification/workspace-ready/`,
`alpine/verification/workspace-titlecase/`, and
`docs/superpowers/decisions/2026-09-07-workspace-names-at-creation.md`.
No required checks remain. Physical key-to-screen timing was not measured;
ordered compositor events establish readiness at creation.


## Separate console and system monitor shortcuts — 2026-09-07

- Super+backtick toggles the existing console; Super+tilde toggles a separate
  persistent btop window. Both preserve their processes while hidden.
- Eight native groups exercised the actual US XKB grave/Shift+grave mapping,
  real Ghostty/btop launch, input and independent hide/show. Full SwayFX parsing
  and 22 shortcut-source tests passed. Targeted live bindings are installed;
  the new monitor was shown/hidden while preserving both existing consoles.
- Physical human keypresses and a new login remain unobserved. Evidence and
  screenshots: `verification/console-monitor/`.

## Clipboard integration and history — 2026-09-07

- Added private text/image history (Super+Shift+V), single-instance session watchers,
  clipboard persistence, themed recall/delete/clear controls, and an application-menu entry.
- Connected terminal mouse selections, tmux copy actions, and screenshots to the regular
  clipboard. Neovim and GTK Wayland/XWayland transfers were exercised with synthetic data.
- Evidence, screenshot, regression tests and runtime results: `alpine/verification/clipboard/`.
  Usage and recovery: `alpine/desktop/CLIPBOARD.md`. Live deployment journal:
  `~/.local/state/oldbook/backups/1788838395962593053`.
- Both new signed APKs are archived with hashes/identities in
  `alpine/packages/clipboard/manifest.json`. A whole-host package snapshot is unfinished:
  unrelated local `oldbook-waybar-art-1.0.0-r8.apk` and other artifacts were missing from
  the snapshot cache. Existing current-lock was retained. See `package-snapshot.log`.
- The optional full unittest discovery was interrupted during unrelated, slow Bazzite
  package-export tests. Clipboard, session, theme-switch and complete-theme suites ran
  separately. Existing standalone Foot windows need reopening for mouse auto-copy;
  their explicit Copy shortcut and live tmux controls work immediately.

### 2026-09-07: skip system-monitor decoration

- Added `com.oldbook.monitor` to the console drop-down caption exclusions.
  Geometry, title and actions retain the previous ordinary window during monitor
  focus; normal Ghostty and similarly named applications remain eligible.
- Existing regression cases reproduced three monitor failures before the change;
  all 47 decoration unit tests and Python compilation pass afterward.
- Restarted only the live decoration helper and verified one caption per output,
  imported source hashes and byte-identical saved appearance settings.
- Native monitor evidence and activation: `alpine/verification/decoration-monitor/`.
  Recovery: remove only the monitor ID from `IGNORED_CAPTION_APPS` and restart the
  decoration helper. Physical keypress input is not part of this caption check.


## Center and raise shortcuts — 2026-09-07

- Super+C and Super+Shift+C center the active window in usable workspace space
  and bring it forward. Ordinary floats retain size; tiled views become floating
  with a small margin, and fullscreen views restore before centering.
- Nine isolated native checks, full SwayFX parsing and 22 shortcut-source tests
  passed. Scoped deployment and targeted bindings are active; activation
  preserved all window geometry and focus. Reload moved to Super+Ctrl+Shift+C.
- Physical keypresses and a new login remain unobserved. Evidence and recovery:
  `verification/center-window/`.


## Scripture reflections and local study library — 2026-09-07

- Restored the daily reflection and practice on the live Scripture card from
  all 33 preserved entries. Right-click the search bar opens reflections/study;
  left-click and Super+/ remain Bible-only, with all collections on Super+Shift+/.
- SQLite at `~/.local/share/oldbook/scripture/study.sqlite3` materializes the
  original catalog plus immutable Fossil-tracked `study/entries/*.json` records.
  Sources, source hashes, cited identifiers, local model digest, endpoint, and
  prompt hash accompany generated entries. The generator stages only its exact
  record and reports that a commit is pending. It rejects cloud models/public
  endpoints and uses exact bundled KJV chapter context; no new study prose has
  been generated in this task.
- 72 combined Scripture tests pass, including concurrent history integration;
  18 deployment tests and all 43 Conky tests pass across the original run and
  successful seven-test click-suite rerun. The first Torah load exceeded its
  20-second subprocess timeout under parallel testing; isolated and full click
  reruns passed. No timeout or production limit was weakened.
- Disposable Fossil clone/push/pull/merge/rebuild retained independent additions
  and all 33 legacy reflections. Native Fuzzel Enter and panel replacement were
  exercised in private Sway. Evidence: `verification/scripture-study/`.
- Live deployment journals: `1788838970027102079` (store/reader/bar) and
  `1788839620926671175` (generator/CLI). Prior selection is backed up at
  `~/.local/state/oldbook/scripture/selection-before-study-1788838996144792109.json`.
  Restore that selection and roll back the exact deployment journals for
  recovery; preserve canonical study records independently of runtime SQLite.
- Concurrent Scripture history work began during integration. Tests now isolate
  XDG data; only injected synthetic test-history rows were removed after private
  SQLite backups. The live daily reflection was then restored.
- Unfinished: real local-model generation and quality review. Localhost and the
  configured Alienware Ollama port refused connections; Alienware Tailscale SSH
  was denied by tailnet policy. The user has been asked for a reachable local
  endpoint. No cloud fallback or model download was used. Physical right-click
  remains unobserved; the actual callback/subprocess dispatch was verified.


## Pointer dwell raising — 2026-09-07

- Installed the signed, archived SwayFX 0.6-r2 package and deployed the dedicated
  hover-raise include. Pointer entry keeps immediate focus; native raising waits
  for one second over the same floating window and cancels stale targets.
- All 11 isolated native checks passed against the packaged executable; observed
  raising was at 1.029 seconds. Empty-space leave, newer focus, workspace and
  geometry changes, held buttons and destruction are covered. Evidence:
  `verification/hover-raise/`.
- Exact installed snapshot `fec17adaeaa5972078b8` contains 1121 verified archived
  APKs and preserves the preexisting clipboard additions. Recorded installed
  architectures, versions, identities, world, repositories and public keys
  match. The restoration-oriented checker reports 233 noarch/index architecture
  differences on this existing host; direct recorded-host verification passes.
- Installed binary hash is `47737f93b5a6123eefc910e7acfbc575de0193e14e72e468ec77393d3bcc35b9`;
  running PID 3175 still uses the old `ec6973644284dc52ece0bbd3e6fba4725be28f6212d7f5f62e687edd12a508f1`.
  The old binary validates the complete live config; the quiet runtime request
  produces no config nag. No compositor restart occurred. The new dwell behavior
  awaits the next graphical login. Physical pointer use then, session-lock
  interaction and multiple seats remain unobserved. Recovery retains the old r1
  APK and scoped deployment backup `1788839554794457799`.

- Core study storage/generation committed as `74177c2598ca`. The live reader,
  search bar and reader tests now integrate with the durable Scripture history
  module. Keep both history modules with the reader when restoring application
  code, and preserve the personal history database independently.
- Final native card evidence checks decoded pixels in a tight Scripture crop:
  20,264 changed pixels and 8,949 visible text pixels. The full disposable
  transfer and native rerun passed; screenshots contain only test-desktop
  content. Additional study CLI deployment journal: `1788839620926671175`.

## 2026-09-07 — bar responsiveness and prompted gallery themes

Live r9 gallery widget installed and archived; Super+Shift+right-click accepts
a theme description, with generated naming and required complete desktop design.
Tracker/dimmer recover transient IPC failures; stale agent data is explicit,
title noise no longer floods fullscreen queries, reloads stay in one session.
Native agent/media/mouse checks and focused Python tests passed. Evidence and
recovery: `alpine/verification/waybar-reactivity/README.md`. Physical user clicks
and a new login remain unobserved; live window preservation comparison was
inconclusive while the desktop changed concurrently.

## Predictable Tab switching, window carousel and expose recovery — 2026-09-07

- Super+Tab and Alt+Tab now share every normal window across workspaces in real
  recent-focus order. Hold to cycle a frozen list, add Shift to reverse, release
  to select, or Escape to cancel. Quick taps alternate the last two windows.
  Plain Tab/Ctrl+Tab remain with applications; agent navigation stays on Super+i.
- Four-finger down restores exposed windows, or opens the persistent themed
  carousel when none are hidden. Its angled cards use exact per-window previews
  without visiting hidden workspaces, soft shadows and frame-clock animation.
  Leaving expose cancels stale animation/state while preserving the destination.
- Super+Shift+Space exits fullscreen, floats, sizes to 90% of usable space and
  centers with at least 24px margins. Super+0 remains numeric workspace 10, last.
- All 112 focused unit tests and 54 native check groups pass across selection,
  controller, geometry, shortcut help, resize and expose lifecycle. The carousel
  final sample records a 16.4385ms median active frame interval; this is private
  compositor evidence, not a measured physical-panel frame-rate guarantee.
  Sway parsing, ShellCheck and disposable-HOME deployment pass.
- New helper links and single-owner carousel/showdesktop daemons are active. One
  validated Sway reload loaded the new window-switcher mode. Window IDs survived;
  one window moved during reload and again afterward, so its newer position was
  preserved. The live workspace sequence remains 1,2,3,4,10.
- Evidence, synthetic screenshots, source hashes and recovery:
  `verification/window-navigation/`, `verification/carousel/`,
  `verification/near-full-resize/`, `verification/showdesktop-recovery/`.
  Physical keyboard/touchpad input and a fresh login remain manual checks.

## Hourly Scripture history — 2026-09-07

- Scripture rotates once per hour and preserves every observed selection as a
  complete snapshot in private `~/.local/share/oldbook/scripture/history.sqlite3`.
  Manual choices display immediately and reset the hour; concurrent checks share
  an atomic deadline and do not invent missed entries after sleep.
- The History button opens full passages, study text, sources and provenance.
  Older/newer navigation preserves draft notes for their original entry. Added
  notes, research and generated material append without replacing earlier data.
  The rebuildable study catalog stays separate from personal reading history.
- The existing bar checks deadlines each minute; the Scripture Conky cache uses
  3600 seconds. Busy refreshes retry and a missing Scripture card revives from its
  existing layout while other cards and the disabled preference are preserved.
- All 80 Scripture tests, 44 Conky tests and seven native GTK reader checks pass.
  Final scoped activation preserved the database and all other Conky card PIDs.
  The current entry was rendered, and both live SQLite integrity checks passed.
  Evidence and recovery: `verification/scripture-history/README.md`.
- Private backup: `~/.local/state/oldbook/backups/scripture-hourly-activation-20260908T041657Z`.
  Earlier failed observations and concurrent rebuilds are retained. No physical
  one-hour wait was performed; hourly boundaries use controlled-clock checks.
  Restore application code independently of history; never commit the live DB.

## 2026-09-07 — Cascadia personal desktop package

Source and private release inputs are retained in Cascadia PR #24; native
`edge/personal` is registered locally. Signed oldbook-desktop r1 builds match;
784 archived dependencies verify and install in a disposable root; config HOME
preview and packaged Codex/SwayFX/Waybar checks pass. Exact recovery lock and
source boundary: `docs/superpowers/decisions/2026-09-07-personal-desktop-package.md`.
Public Pages and production signing remain unconfigured (Cascadia issue #22).
Fresh boot/hardware and maintainer-script activation are not verified by this
payload test. The live desktop was not replaced by installing the meta-package.


## Waybar active/inactive workspace recovery — 2026-09-07

- Confirmed the bar lost its workspace event connection while its command
  connection and clock remained live. Workspace labels and active highlighting
  became stale. A scoped restart restored them, but the disconnect recurred
  within two minutes; that restart was not a complete fix.
- Exact previous Waybar/OpenRC APKs are archived and exported for rollback.
  Repair plan: `docs/superpowers/plans/2026-09-07-waybar-ipc-recovery.md`.
  Baseline: `alpine/verification/waybar-ipc-recovery/baseline.json`.
- In progress: adapted upstream reconnection package, native forced-disconnect
  regression, signed build/archival, live activation and package-lock update.


## Pinned feature preservation contracts — 2026-09-07

- Added `FEATURES.md` with 30 stable contracts covering current desktop behavior,
  durable content and package/deployment recovery. Intentional replacements are
  explicit: music center, workspace 10 on Super+0, borderless bottom/right caption,
  complete themes with the original ghost brand, and high-quality still previews.
- Contributor instructions now require affected-feature review. Explicit new user
  choices update a pin; actual unresolved conflicts require a user decision while
  independent work continues. Existing durable preferences are preserved.
- `bin/check-features` maps changed paths (including new hidden Fossil files) to
  overlapping contracts and existing tests. It supports explicit feature IDs,
  JSON impact reports, deduplicated test execution and failure propagation;
  unmapped files/manual-only checks remain visible. The index includes separate
  project sources and requires parity with all 30 documented IDs.
- Nine focused impact/runner tests pass. Evidence and exact source hashes are in
  `verification/feature-contracts/`. This proves the workflow, not every underlying
  feature: physical 60fps/input/hotplug, fresh boot, application-specific refresh
  and other native limits remain explicit in the contracts.

## 2026-09-07 — Scripture header History

- Replaced the separate search-bar History button with a native clickable text
  link on the Scripture header, using its current font and active accent. Shared
  rendering covers existing theme profiles; passage clicks retain advancement.
- Native Wayland checks passed at scales 1 and 2: header pixels match purple/gold
  accents, History opens the reader without changing selection or card PID, and
  body clicks still advance. Source review found no material issues.
- Mapped feature checks completed: 164 of 171 passed. Five existing click tests
  exceeded catalog-loading/advance deadlines on the loaded host; isolated catalog
  selection succeeded in 26.67 seconds against the usual 20-second test deadline.
  The shortcuts status test also timed out at 3 seconds. The unchanged global
  fullscreen desktop-space test returned bottom 16 instead of 60. These checks
  remain unresolved; full-suite success is not claimed.
- Evidence and recovery: `verification/scripture-header/README.md`. Personal
  history backups remain outside the repository. Feature-contract/index updates
  coexist with pre-existing untracked work and are retained in the checkout.


## 2026-09-07 — Theme switch recovery and application refresh

- Fixed the blocker behind five saved-but-unapplied generated themes: foreign
  Scripture backup manifests no longer masquerade as interrupted deployments.
  Real interrupted/damaged journals still block replacement; backups are intact.
- The picker visibly reports errors and permits reapplying the current theme.
  Wallpaper pairing cannot prevent application refresh, and failures return a
  nonzero result. Sway now waits up to 20 seconds for the actual IPC result;
  the live compositor needed 8.913 seconds, exceeding swaymsg's three seconds.
- Added session-preserving btop/Neovim refresh and live history-reader palette
  updates. Native reader tests preserve drafts, navigation, scroll and database
  bytes. Process signals and Foot palette writes exclude other HOME/Sway sessions.
- The Bellows Intercept and its exact saved painting are active. Final live use
  returned zero; Sway, bar, terminals, notification service, panels, tmux and btop
  refreshed. No new generation/provider request was made.
- Validation: 280 feature-contract tests, eight Sway protocol tests, 19 final
  affected tests and 18 reader/history tests passed; real private bar/theme
  screenshots, deployment recovery and Sway parsing are recorded. Full discovery
  ran 829 tests with six assertion failures and three timeouts outside this
  repair. Badge checks passed after concurrent work finished; Bazzite deployment
  timeout/missing resize helper and fullscreen-space disagreement remain open.
- Remaining theme limits: cached user CSS in third-party GTK applications,
  unmanaged Firefox styling, and future drift in existing generated profiles.
  Qt6ct's native three-second refresh was verified; it needs no added helper.
- Evidence, exact runtime limits and recovery:
  `verification/theme-repair/` and
  `../docs/superpowers/decisions/2026-09-07-theme-switch-repair.md`.
  Restore a previous theme with `oldbook-theme use <id>`; never use deployment
  rollback on a Scripture database snapshot. Concurrent pending work is preserved.
- Concurrent Fossil writers initially blocked the scoped commit. After their
  locks cleared, source, screenshots and evidence were committed locally as
  `dc39bb08a597`. Live activation is complete; no other session was interrupted.


## Still previews, overview handoff, theme recovery and ghost branding — 2026-09-07

- Carousel previews retain the full compositor-supplied capture, use trilinear
  sampling and stay frozen until reopening. Completed captures release duplicate
  RGB payloads; cached card nodes preserve image quality. Existing warm socket
  handoff and elapsed-time animation work from the parallel session is retained.
- Mission Control/F3 and Launchpad/F4 keycaps control overview/launcher while
  Fn+F3/F4 remain application keys. Escape/mode exit no longer launches a delayed
  cancel that can close the next overview. Early modifier release is evaluated
  only after actual keyboard entry, Wayland synchronization and queued focus
  delivery, replacing a 50ms guess.
- The current carousel checks pass 34 tests. The late-cancel fix passes 8 native
  checks, Apple behavior passed 8 real GUI checks plus 26 units, and pre-cache
  quality/navigation passed 18 native groups. Later cached-source runs proved 7
  quality/still-image groups but exposed the handoff races. The final focus
  barrier has unit/source proof; three final native attempts stopped before any
  gesture under load 49 on 8 CPUs. Final held/quick input and physical 60fps remain
  unverified, explicitly recorded in `verification/carousel-quality/`.
- Existing-theme gallery generation now applies its exact theme before selecting
  its saved painting. Unthemed and nonactivating requests preserve the desktop
  palette; failed activation preserves the saved image. All 48 focused checks
  pass, including both current modified-click tooltip descriptions.
- Concurrently authored theme repair distinguishes Scripture database snapshots
  from deployment journals and waits for actual Sway reload acknowledgement.
  Private switching changed 25 profile links without touching copied backup data;
  14 focused IPC/session/refresh checks passed. A real reload needed 8.200 seconds,
  explaining swaymsg's false failure after 3 seconds. The final installed helper
  acknowledged success after 8.160 seconds.
- Restored the original 21px white/purple/pink ghost, including hover/glow, while
  preserving centered width and all neighboring styling. Existing profile badges
  are repaired and future rendering protects the brand selectors. Six tests and
  two real private Waybar renders pass; no APK rebuild is required.
- Activated carousel PID 21698 and the Apple bindings. Its cold start exceeded the
  first 10-second observer but became ready; verification resumed without another
  restart. Checked reload removed no window IDs and retains workspaces 1, 2, 3, 4, 10.
  Bellows theme, exact painting, all 24 actual theme links and original ghost colors
  match. The dimmer's generated waybar-state.css is intentionally runtime data.
  The Bellows PNG/metadata/descriptor were checkpointed separately as 03bd636b8582.
- Recovery, source hashes, synthetic screenshots and honest failed attempts live
  in `verification/carousel-quality/`, `verification/apple-overview/`,
  `verification/ghost-branding/` and `verification/theme-switch-repair/`.


## 2026-09-08 — rounded output corners (installed; next login)

SwayFX 0.6-r3 is installed with a final compositor output mask, software cursor
and render locks, and a final explicit-sync fence. The HOME launcher supplies a
20 logical pixel radius. The running compositor was preserved and is still on
its earlier executable: a new login is required for activation. The isolated
packaged renderer passes full-screen, overlay, cursor, redraw, scale, rotation,
resize, reload and session-lock checks; existing hover and 23 titlebar checks
also pass. Config validation passes for both compositors. One deployment timeout
under load passed unchanged on retry. All other 1,120 host package identities
were preserved. Exact artifacts and the new host/desktop locks are archived.

Pending: physical-screen visual confirmation, DRM/direct-scanout and hardware
cursor behavior, GPU-reset recovery and physical frame rate after the next
login. No live compositor restart or fresh-machine boot is claimed. Evidence:
`alpine/verification/screen-corners/`.


## 2026-09-07 — animation responsiveness and Alienware inference preference

- Gruvbox is a confirmed keeper. The remaining 18 themes are unreviewed, with
  the first three native previews and decision record under
  `verification/theme-review/` and `docs/superpowers/decisions/2026-09-07-theme-review.md`.
  No uncertain theme has been removed or silently selected.
- Warm gesture commands now use the owning daemon's Unix socket. The four-finger
  down handoff avoids launching a second interpreter when the carousel is ready.
  Cold-owner recovery remains. The root-owned one-shot priority helper gives
  ordinary compositor threads nice -10 and approved UI threads nice -5, preserving
  batch/realtime policy and ordinary priority for forked child applications.
  The helper and exact HOME links are installed; source/install drift was checked.
- Caption handoffs reuse GTK controls and recreate only the native surface.
  Geometry dispatch runs before redraw; stationary polling is halved and pauses
  during carousel mode. All 52 focused unit tests and 37 native checks passed,
  and the verified caption source is running live. Hover checks completed in
  87–98 ms against the unchanged 250 ms requirement after local Ollama stopped.
- The 253-test animation feature batch passed 252 tests. The existing moving
  watcher cadence assertion measured 17.31 ms against its unchanged 16.67 ms
  threshold under concurrent load. The focused 52-test run passed earlier;
  preserve both results. Full logs and exact activation hashes are under
  `verification/animation-responsiveness/` and `verification/animation-fluidity/`.
- The local Ollama server and model worker were stopped at the user's request.
  `~/.config/oldbook/ollama.json` now disables local startup and records Alienware
  inference preference. A real launcher invocation refuses before runtime work;
  all 16 targeted policy/lifecycle tests pass. The 130-test Scripture impact run
  retained two Conky click failures (20-second selection timeout and asynchronous
  advancement assertion). No Alienware endpoint was guessed, no cloud service
  was used, and remote inference connectivity remains unconfigured.
- Carousel physical 60fps and final inline Bible search activation are still
  being verified in this pass; later evidence below must resolve these entries.

## Whole-keyboard breathing — 2026-09-07

- Clarified the user's breathing request as keyboard illumination. The actual
  MacBookPro11,5 exposes one Apple SMC brightness channel, 0–255, with no per-key
  or multicolor interface. Existing input-group permissions suffice.
- Added a six-second cosine breath, Shift+F6 toggle, Shift+F5 steady, and a
  Keyboard glow control-deck menu. F5/F6 adjust the saved peak while breathing;
  zero/off stops it. Preserve level and mode across login and theme changes;
  reload does not restart it, and animation samples never replace saved state.
- Serialize commands separately from exclusive worker ownership. Verified rapid
  stop/start, stale socket detection through a connected peer, and bounded login
  ownership handoff; another active session produces an explicit error.
- Added KEYBOARD-GLOW to FEATURES.md and the impact/check index. Recorded 18
  keyboard tests, 22 shortcut-source tests, 4 Apple-key tests, 9 feature-index
  checks and three menu scenarios; Python compilation and Sway validation pass.
- Activated the reviewed helper and both runtime Shift bindings. Actual sysfs
  readback completed a 31–255 cycle, preserved the saved 255 and its modification
  time, returned to steady 255 and resumed breathing. Repeated restore reused
  one worker (PID 4259). Left breathing enabled as requested. Evidence and exact
  source hashes: alpine/verification/keyboard-breathing/.
- Still unverified: optical refresh timing, physical engraved-key presses, a
  real logout/login and suspend/resume. The 60Hz request target is not a physical
  frame-rate claim; applesmc may coalesce updates. Recovery: Shift+F5 or
  oldbook-keyboard-backlight steady, preserving the latest chosen brightness.

## Scripture right-click returns to the earlier passage — 2026-09-08

- Right-clicking the desktop Scripture card now returns to the passage shown
  before the current one. Left-click still advances, the header History link
  still opens the reader, and the other cards ignore right-clicks.
- Returns follow the reader's own path rather than raw entry order: each return
  is appended to the durable history as a `manual-previous` entry that holds
  for an hour, and every entry's predecessor is derived from entry order and
  reasons alone. A return after Next goes back to where Next started, and
  returning past a repeated passage does not loop. No schema change and no row
  edited or removed; `oldbook-scripture previous` exposes the same action.
- Validation: 9 Conky click tests and 20 history tests pass, including Lua
  dispatch checks and an end-to-end right-click through the real click helper.
  The mapped 15-file batch passed 13 files; the two failures are unrelated and
  pre-existing in the live checkout (the desktop-space hidden-fullscreen
  assertion, and the Scripture bar theme tests, which need the currently
  missing `alpine/themes/spaceghost.json`). Native headless Sway evidence in
  `verification/conky-clicks/` records a real Wayland right-click returning
  John 3:17 to John 3:16 in 1.32 s with only the Scripture card restarted
  (`returned.png`, `native.json`, `README.md`).
- Activated live by replacing only the Scripture card through
  `oldbook-scripture refresh scripture` (PID 31094 → 1555); the layout and the
  other cards were untouched. The running desktop still uses the `oldbook`
  checkout; the same change is committed at the renamed branch tip.
- Not verified: a physical right-click on the live seat (only the private
  headless seat was driven) and a physical hour of rotation after a return.
