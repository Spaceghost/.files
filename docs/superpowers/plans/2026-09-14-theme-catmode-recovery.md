# Theme and catmode recovery

Goal: retain unfinished theme and cat-hearth work, package theme effects, and
keep input parked across the Linux boot, desktop, lock, and shutdown stages.

The user has approved recovery, implementation, merge, and publishing.

1. Restore missing Starship module tables; preserve the later plain Waybar
   design. Retain the Space Ghost profile/icons, signed-XPI installer, panel
   patch and its honest build evidence. Run focused regression tests.
2. Make theme-effects.json an overlay-owned declaration. Default ripple on;
   skip loading/warming a disabled effect. Bundle descriptor and profile with
   hashes, include owned icons/assets, reject unsafe archive paths and links.
3. Keep catbed alive after lock readiness. Start it before session services.
   Add an OpenRC input guard after root/devices are available, with an exact
   deliberate release chord and verified handoff to the user guard. Inhibit
   internal input during shutdown so killing userspace does not release it.
   Keep firmware cooling automatic in the boot guard.
4. Validate isolated behavior, record remaining physical boot/lock/shutdown
   checks in PROGRESS.md, commit exact paths, merge the branch leaves, and
   publish without rewriting remote history.

Recovery: oldbook-watch stop; rc-service oldbook-catmode stop from SSH or an
external keyboard. Firmware and encrypted-root entry precede this service.
