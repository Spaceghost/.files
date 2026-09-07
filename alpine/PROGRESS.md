# Oldbook verification

Verified on Alpine edge x86_64, MacBookPro11,5, 2026-09-07.

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
  The notification helper is deployed and running; the LED follows retained
  SwayNC notifications. Five helper tests, Sway validation, ShellCheck and
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
- Existing Codex processes must restart to load callbacks. Approval alerts and
  next-prompt badge cleanup require reviewing/trusting the hooks via `/hooks`;
  that interactive trust remains pending. ChatGPT browser response completion
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
  extra instances remain free. Workspaces 1–6 have independent artwork state.
- Compact bar/window spacing, title decorations and live Foot transparency
  applied. Six distinct wallpapers and concurrent-launch reuse verified.
- Sway/Foot parsers, disposable deployment and focused tests passed. The full
  197-test run had one session-startup timeout; isolated rerun passed. Reboot
  persistence remains unverified. Details and recovery: 
  `docs/superpowers/specs/2026-09-07-strata-workspaces.md`.

## Square bar and terminal playlist player

- Removed all Waybar CSS corner radii and the SwayFX Waybar layer radius.
  Stock Sway and SwayFX parsers passed; live cropped screenshot is
  `verification/square-bar/bar.png`.
- Foot-only playlist playback is not implemented. Foot has no native video
  background option; the existing mpvpaper helper targets the whole desktop.
  A terminal-scoped renderer/compositor design is required. Pending: oldbook
  and watchlist playlist URLs, whether Delete affects YouTube or a local queue,
  and approval of the end-of-video Delete/Rewatch/Keep & Next design.
