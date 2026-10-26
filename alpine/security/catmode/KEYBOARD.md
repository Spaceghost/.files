# Keyboard breathing outside the desktop

`keyboard-breathe.c` is a small native Apple SMC light worker. It needs no
Python, GTK, compositor, sound server, or network. The OpenRC service starts
in sysinit, waits for the LED driver, disables competing kernel LED triggers,
and produces a six-second breath at a modest 45 percent peak.

When the desktop keyboard worker owns its runtime lock, the native worker
yields. Once the desktop has taken over, it continues yielding for that Sway
session even if the user chooses steady light. It resumes after session exit.
This does not change desktop lock-screen overlays or the user's other light
modes. The light is whole-keyboard, not per-key RGB.

Build with the system C compiler:

```sh
cc -std=c11 -Wall -Wextra -Werror -Os -static \
  alpine/security/catmode/keyboard-breathe.c -lm -o /tmp/oldbook-keyboard-breathe
```

Install the binary as `/usr/local/sbin/oldbook-keyboard-breathe` and the service
as `/etc/init.d/oldbook-keyboard-breathe`, both root-owned mode 0755. Enable it
with `rc-update add oldbook-keyboard-breathe sysinit`. The service currently
targets this machine's UID 1000.

For recovery, `rc-service oldbook-keyboard-breathe stop` releases the fallback
and restores its entry brightness when it still owns the light. The desktop
worker is not stopped or signalled by this service.

This reaches early OpenRC userspace after the real root filesystem is available.
It does not yet run in firmware or the encrypted-root initramfs. The static
binary can be included in a future initramfs integration, but that integration
and a physical boot/shutdown check are still required before claiming coverage
of those stages.
