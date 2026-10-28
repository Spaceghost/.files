# Space Ghost on Guix

This directory describes the MacBookPro11,5 as a Guix System host and carries
the portable desktop through Guix Home.  It records the observed disk UUIDs,
LUKS2/LVM layout, EFI mount, Intel microcode, Radeon firmware, BCM43602 firmware,
PipeWire session, Bluetooth, greetd autologin, Sway session and the complete
Oldbook HOME overlay.  A narrow `/usr/bin` compatibility set preserves the
absolute Python, Sway, Foot, btop, Neovim and doas identities used by the
existing recovery and live-refresh checks while their packages remain in the
Guix store.

The configuration is deliberately not applied from Alpine.  Installing Guix
System replaces the operating system and boot configuration; test it from Guix
installation media and preserve the Alpine recovery image first.

## Evaluate and install

Use the pinned channels, then evaluate without building:

```sh
guix time-machine -C guix/channels.scm -- system build guix/config.scm --dry-run
guix time-machine -C guix/channels.scm -- home build guix/home.scm --dry-run
```

On installation media, copy the checkout to `/home/jack/.files`, mount the EFI
system partition at `/mnt/boot`, open LUKS as `root`, activate `vg0`, mount
`vg0/lv_root` at `/mnt`, and run the normal `guix system init` workflow against
`guix/config.scm`.  After first boot, set Jack's local password and activate the
home generation:

```sh
passwd jack
guix time-machine -C ~/.files/guix/channels.scm -- \
  home reconfigure ~/.files/guix/home.scm
```

## Exact compatibility boundary

The declarative base is complete, but five locally patched Alpine components do
not yet have Guix package recipes: the SceneFX-patched SwayFX compositor, the
screen-corner/output-mask patch, swaylock-effects supervisor, native Waybar art
module, and Superhold.  `config.scm` therefore boots stock Sway as the documented
recovery path.  It does not claim the patched compositor effects, 60-fps motion,
power-key lock guard, or native Waybar module are reproduced until those recipes
are built remotely and added to the pinned channel.  Ghostty, Firefox, Tailscale,
OpenSnitch and Codex are likewise channel-dependent/nonfree leaf packages and
are not silently replaced.

The Oldbook nftables policy is not enabled yet: its fail-closed outbound queue
requires the matching OpenSnitch build and enabling it without that daemon would
remove networking.  Radio ownership, Incoming Transmissions, catbed guard and
boot-theme publication remain migration work for Shepherd services.  These gaps
are explicit so a successful evaluation cannot be mistaken for full behavioral
verification.

Theme descriptors, rendered profiles, artwork and provenance are published in
the separate `Spaceghost/oldbook-themes` repository.  The current theme engine
still uses `~/.files/alpine/themes` as its writable source of truth; do not delete
that tree until the engine accepts a separate state/repository root.
