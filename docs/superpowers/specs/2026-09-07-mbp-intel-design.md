# MBP Intel: reproducible Alpine desktop

## Requirements and decisions

The target is Jack's MacBookPro11,5 running Alpine edge, with Sway on a
2880×1800 panel at scale 2. The requested visual direction is deep purple,
electric lilac and magenta. Fossil is authoritative; seed all GitHub
Spaceghost/.files history and retain the original AGENTS.md. The user has
authorized the complete setup and selected its visual direction, Fossil,
reproducibility, and standalone Codex installation without npm.

## Components

1. `alpine/desktop/` is a deployable HOME overlay: Sway, Waybar, launcher,
   notification center, foot, zsh, tmux theme, GTK/Qt preferences and helpers.
   Keep original dotfiles outside the overlay intact. Use HiDPI defaults,
   touchpad gestures/settings, brightness/audio keys, idle locking, screen
   capture, and consistent readable colors. Assets live in `alpine/assets/`.
2. `alpine/bin/` manages deployment, backup, verification and package snapshots.
   Deployment backs up conflicting files, never collects credentials, and is
   repeatable. Snapshot the entire installed package closure, not just world.
   Archive signed APKs and checksums through Fossil unversioned artifacts so
   edge mirror churn cannot silently change a rebuild. Capture toolchain and
   source inputs for custom packages. Reproducible environment restoration is
   required; bit-identical source compilation is a separate verified claim.
3. `alpine/security/` holds OpenRC services and root-owned policy for radio and
   firewall management. OpenSnitch requires a local APK because no package is
   present in configured indexes. Preserve connection during provisioning;
   activate disruptive fail-closed controls only after recovery is ready.
4. `alpine/packages/` tracks world intent, HTTPS repositories, exact installed
   versions, source provenance, custom APK recipes and verification metadata.
   Keep edge/testing tagged. Do not mix stable Alpine repositories into edge.

## Radio model

Boot policy needs the user's pending choice: all radios off until explicitly
enabled, or automatic discovery limited to trusted profiles. A network SSID is
not a proof of location. Automatic scans may transmit before connection; a
software configuration cannot prove physical RF silence from boot firmware.
Keep trusted credentials local and root-readable only. Never claim an SSID
allowlist or MAC randomization makes the hardware undetectable.

## Acceptance evidence

Validate Sway config with its parser, inspect the real desktop through a
screenshot and IPC, test launcher/notifications/audio and lock readiness.
Test deployment in a temporary HOME twice and recover a conflicting file.
Verify all archived APK hashes, exercise restore in an isolated root, compare
the installed closure, and preserve a Fossil backup independent of checkout.
Exercise firewall allow/deny and daemon-failure behavior, verify boot ordering
and rfkill state, and leave RF/reboot checks unproven until actually observed.

## Scope still required

The complete desktop, application firewall, radio policy, offline rebuild,
custom-package source builds, recovery and runtime checks are deliverables.
An attractive screenshot or a green syntax check alone does not complete this
project.
