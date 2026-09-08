# MBP Intel verification

Verified on Alpine edge x86_64, MacBookPro11,5, 2026-09-07.

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
  through the preserved `mbp-intel-shortcuts` command. The original GTK source
  remains for rollback. Workspace Python edits take effect on service restart.
- Super remains the half-second hold trigger; physical Caps is configurable
  without changing Caps-to-Escape. Existing shortcut sections, custom profiles,
  pointer scrolling, release/chord cancellation and focus behavior are retained.
- Qt supplies palette, fonts and style. Local qt6ct and native LXQt settings
  both select Gruvbox Dark, Inter and MBP Intel icons; LXQt palette/font changes
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
- Added `mbp-intel-video-background` and its command-deck picker. Playback loops
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
  A terminal-scoped renderer/compositor design is required. Pending: mbp-intel
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
  using journal `~/.local/state/mbp-intel/backups/1788782412724579771`; duplicate
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
- Signed mbp-intel-waybar-art 1.0.0-r1 builds twice identically with networking
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
  `~/.local/share/mbp-intel/backups/files-2026-09-07-radio-owner-service.fossil`;
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
  this launcher change. Shared mbp-intel-wallpaper has concurrent panel edits and
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
  because mbp-intel-wallpaper also contains concurrent desktop-panel changes;
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
  `~/.local/share/mbp-intel/backups/2026-09-07-before-github-publication/` passed
  SQLite integrity and SHA-256 verification and includes 1,155 archived inputs.
- The separate scrubbed copy at
  `~/.local/share/mbp-intel/backups/github-20260907/files-public.fossil` is verified
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
- Recovery: restore the source checkpoint with Fossil, run mbp-intel-theme sync,
  then mbp-intel-theme use <id> --no-reload to rebuild HOME. Deployment backups
  retain the previous configuration. Rendered profiles are local derived files.
  Unrelated pending desktop, security and publication edits are preserved.

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


## Center and raise shortcuts — 2026-09-07

- Super+C and Super+Shift+C center the active window in usable workspace space
  and bring it forward. Ordinary floats retain size; tiled views become floating
  with a small margin, and fullscreen views restore before centering.
- Nine isolated native checks, full SwayFX parsing and 22 shortcut-source tests
  passed. Scoped deployment and targeted bindings are active; activation
  preserved all window geometry and focus. Reload moved to Super+Ctrl+Shift+C.
- Physical keypresses and a new login remain unobserved. Evidence and recovery:
  `verification/center-window/`.


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
  complete snapshot in private `~/.local/share/mbp-intel/scripture/history.sqlite3`.
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
- Private backup: `~/.local/state/mbp-intel/backups/scripture-hourly-activation-20260908T041657Z`.
  Earlier failed observations and concurrent rebuilds are retained. No physical
  one-hour wait was performed; hourly boundaries use controlled-clock checks.
  Restore application code independently of history; never commit the live DB.


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


## 2026-09-08 — desktop identity renamed to mbp-intel (source only)

The `oldbook` identity became `mbp-intel` across the versioned source: 408 files
rewritten and 903 paths renamed. This covers the 48 HOME helpers, the shared
Python package (`.local/lib/mbp_intel`, imported as `mbp_intel` because a hyphen
is not a legal identifier), the config, share and state directory names, the
`MBP-Intel-Gruvbox` icon theme, the `MBP_INTEL_` environment variables, the
`mbp_intel_workspace_*` Waybar colors, the `com.mbp-intel.*` drop-down
application IDs, the `inet mbp-intel` firewall table, the `mbp-intel-waybar-art`
package recipe, the Bazzite systemd units and the surrounding prose.

Verified on a clean checkout of the branch tip: 856 unit tests with the same
three pre-existing failures as the tip before the rename
(`test_ghost_branding` error, `test_bazzite_profile` deployed-helper assertion,
`test_desktop_space` hidden-fullscreen assertion). The rename introduced one
regression, a Lua pattern in `test_conky_clicks` where the new name's hyphens
were read as quantifiers; it was fixed and all 45 Conky checks now pass. Python
and POSIX shell syntax, JSON parsing, every relative documentation link, the
feature-check index and `sway --validate` all pass.

Recorded evidence keeps the old name on purpose: `verification/`, `archive/`,
`packages/locks/`, `packages/world`, `packages/current-lock` and the installed
OpenSnitch rule copies describe artifacts that exist on disk under that name.
The Fossil branch stays `alpine-oldbook` so the GitHub mirror and the other
sessions committing to it are not orphaned.

Pending, and deliberately not performed here: the running machine is untouched.
The live HOME still carries `oldbook` symlinks and
`~/.local/{state,share,config,lib}/oldbook` personal data, the icon-theme
setting still reads `Oldbook-Gruvbox`, and the root `sway` wrapper, wayland
session entry, `/etc/oldbook`, `/var/lib/oldbook`, the `inet oldbook` table, the
installed `oldbook-waybar-art` and `oldbook-radio-runtime` packages and the
`oldbook` hostname are unchanged. Activation needs a data move, a HOME redeploy,
stale-symlink removal, `install-desktop-system`, a package rebuild and a
firewall reactivation. That would restart the compositor under live agent
sessions, so it is left for an authorized migration. No native, visual or
physical verification is claimed for this check-in.

## Scripture right-click returns to the earlier passage — 2026-09-08

- Right-clicking the desktop Scripture card now returns to the passage shown
  before the current one. Left-click still advances, the header History link
  still opens the reader, and the other cards ignore right-clicks.
- Returns follow the reader's own path rather than raw entry order: each return
  is appended to the durable history as a `manual-previous` entry that holds
  for an hour, and every entry's predecessor is derived from entry order and
  reasons alone. A return after Next goes back to where Next started, and
  returning past a repeated passage does not loop. No schema change and no row
  edited or removed; `mbp-intel-scripture previous` exposes the same action.
- Validation: 9 Conky click tests and 20 history tests pass, including Lua
  dispatch checks and an end-to-end right-click through the real click helper.
  The mapped 15-file batch passed 13 files; the two failures are unrelated and
  pre-existing in the live checkout (the desktop-space hidden-fullscreen
  assertion, and the Scripture bar theme tests, which need the currently
  missing `alpine/themes/spaceghost.json`). Native headless Sway evidence in
  `verification/conky-clicks/` records a real Wayland right-click returning
  John 3:17 to John 3:16 in 1.32 s with only the Scripture card restarted
  (`returned.png`, `native.json`, `README.md`).
- Activated live from the running `oldbook`-named checkout by replacing only
  the Scripture card through `oldbook-scripture refresh scripture`
  (PID 31094 → 1555); the layout and the other cards were untouched. This
  check-in carries the identical change under the renamed helpers.
- Not verified: a physical right-click on the live seat (only the private
  headless seat was driven) and a physical hour of rotation after a return.
