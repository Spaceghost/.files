# Catmode stages

Install with `doas alpine/bin/install-catbed-guard`. This installs root-owned
helpers, registers the OpenRC boot service, and does not park live input.

- Linux boot: after encrypted root and local filesystems are available, the
  OpenRC service exclusively grabs the Apple internal keyboard/trackpad and
  power/sleep buttons. External keyboards and SSH remain recovery routes.
- Desktop: oldbook-session starts oldbook-watch before audio and other services.
  The boot guard hands over only when the live user guard has proven keyboard
  focus and all physical keys are up. A deliberate boot-stage exit requires
  exactly Super+Shift+Escape held for a second, then released. After reaching
  the desktop, its guard has its own deliberate exit with the same chord.
- Lock: every oldbook-lock call attempts catbed before acquiring the lock.
  Catbed survives readiness and unlock until deliberately released. A failed
  catbed start is reported, but never prevents security locking.
- Shutdown: the power deck enters catbed/lock, then inhibits the internal
  input devices in the kernel before requesting shutdown. The boot service
  also inhibits input when OpenRC enters shutdown. That setting survives the
  final process kill. A failed power-deck request restores device input.

The boot helper requests quiet fans through the existing root-owned thermal
watchdog, using its stricter closed-lid limit (58 C) and a three-second renewal
deadline. Missing sensors, excess heat, helper failure, handoff, shutdown or
caller death restore automatic cooling. The boot guard generates no heat.
The existing oldbook-cat thermal controller remains separately configurable;
its fan holds retain temperature, heartbeat and caller-lifetime cutoffs.

Recovery: use an external keyboard or SSH and run
`doas rc-service oldbook-catmode stop`, then `oldbook-watch stop` in the desktop
session if needed. `doas /usr/local/sbin/oldbook-catmode recover` clears a
shutdown inhibition after an interrupted shutdown. Status is available through
`/usr/local/sbin/oldbook-catmode status` and `oldbook-watch status`.

This is not firmware protection: GRUB and the encrypted-root prompt run before
this service. It cannot prevent a hardware long-press power cut. Initramfs
integration needs a separate release/recovery path for disk unlock. Physical
boot, held-key handoff, hotplug, and interrupted shutdown still need validation.
Keep ventilation clear; software cannot compensate for covered cooling vents.
