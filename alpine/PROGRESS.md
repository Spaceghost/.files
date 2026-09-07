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
