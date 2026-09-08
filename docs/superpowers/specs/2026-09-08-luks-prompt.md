# LUKS prompt in Gruvbox

Date: 2026-09-08. Scope: the encrypted-root passphrase prompt at boot on the
Oldbook, which is the first thing the screen shows after GRUB.

## Why the palette already covers the prompt

Alpine's initramfs init (`/usr/share/mkinitfs/initramfs-init`, mkinitfs
3.14.0) builds `cryptopts` from `cryptroot`/`cryptdm`, then, inside
`if [ -n "$KOPT_root" ]`, calls `ebegin "Mounting root"` and
`nlplug-findfs $cryptopts ... "$KOPT_root"`. nlplug-findfs runs cryptsetup,
which prompts on the kernel console. The console palette (`vt.default_*`),
default attribute (`vt.color`) and font (`fbcon=font:TER16x32`) are kernel
parameters applied before `/init` runs, so the prompt is already cream on
charcoal in Terminus 16x32 from the boot-console change; the initramfs needs no
change for that. With `quiet`, deferred fbcon takeover means the prompt is the
first console output, so it is also the first frame the palette is seen on.

## Banner initramfs

For the masthead itself the init has to print it. mkinitfs sources
`/etc/mkinitfs/mkinitfs.conf` after its `init=` default, so `init=` could be
overridden there; that was rejected because the apk trigger that rebuilds
`/boot/initramfs-lts` on every kernel upgrade would then silently put the
patched init on the default boot path. Instead:

- `alpine/system/mkinitfs/initramfs-init` is the installed stock init plus one
  guarded block before `ebegin "Mounting root"`: when `cryptroot` is set, two
  `printf` lines print "GHOST PLANET  Oldbook - Alpine Linux" and "Encrypted
  root. Enter the passphrase to continue." using sixteen-colour SGR escapes and
  ASCII only. `initramfs-init.stock` (GPL-2.0-only, from mkinitfs 3.14.0-r0),
  `stock.json` (hashes and package) and `ghost-banner.patch` (the seven-line
  diff) are versioned beside it. `install-boot-console --render-init`
  regenerates all four from the installed init; `boot_console.patch_init`
  refuses to apply twice or to a script without exactly one root-mount step.
- `install-boot-console` refuses to build unless `patch_init(installed stock)`
  equals the versioned file, so a mkinitfs upgrade blocks the build until the
  patch is re-rendered and reviewed. It builds with
  `mkinitfs -i <versioned init> -o /boot/initramfs-lts-ghost.oldbook-new <kernel>`
  (same features as the stock file, from the untouched mkinitfs.conf), then
  proves the archive: the `init` member equals the versioned file byte for
  byte, the archive holds `usr/lib/modules/<kernel>/`, and its file list is
  compared with `/boot/initramfs-lts`. Only then is it moved to
  `/boot/initramfs-lts-ghost`. A later run reuses the archive while its init
  still matches; `--rebuild-ghost` forces a rebuild, `--remove-ghost` withdraws
  the entry and the file.
- The GRUB entry is derived from the stock entry of the freshly generated
  grub.cfg (same kernel, command line, device search and hints), with the title
  suffix " (Ghost Planet initramfs)", the id suffix "-ghost" and
  `initrd /initramfs-lts-ghost`, written as a managed block in
  `/etc/grub.d/40_custom`. grub.cfg is regenerated again and validated: the
  stock entry stays first with `set default="0"`, boots `/initramfs-lts`, and
  the ghost entry must mirror its kernel and command line exactly.

## Host state (2026-09-08)

- Built `/boot/initramfs-lts-ghost` for 6.18.49-0-lts: 615 files, 21473178
  bytes, sha256 `03b4134285a76a8b845ace33f4a495032068abf07c62133f005256ea28838c1a`
  (first build; the withdraw/re-add check below produced a fresh archive with
  new timestamps and therefore a different hash but the same init member).
  Against the stock archive's 614 files it lacks nothing and adds two apk keys
  that were installed after the stock initramfs was built
  (`etc/apk/keys/jack-6a9e83bd.rsa.pub`, `etc/apk/keys/support@1password.com-61ddfc31.rsa.pub`),
  which the `base` feature's `/etc/apk/keys/*` glob now includes.
- `/etc/grub.d/40_custom` carries the managed block; `/boot/grub/grub.cfg`
  lists the stock entry first (default 0), the UEFI firmware entry, then the
  ghost entry. Backup: `/var/backups/alpine-rice/boot-console-1788860819556982985`
  (40_custom, grub.cfg, and the created initramfs recorded for removal).
- `/boot/initramfs-lts`, `/etc/mkinitfs/mkinitfs.conf` and the stock entry are
  untouched.

## Test-booting and adopting it

The menu is shown for one second (`timeout_style=menu`); press an arrow key
during that second to stop the countdown, select "Alpine Linux edge, with
Linux lts (Ghost Planet initramfs)" and press Enter. `doas grub-reboot
'Alpine Linux edge, with Linux lts (Ghost Planet initramfs)'` should select it
for the next boot only through grubenv on the FAT boot partition; that path
was not exercised. To make it the default later, set
`GRUB_DEFAULT='gnulinux-lts-advanced-4b064483-69c1-4e36-8a36-83695fc84506-ghost'`
in `/etc/default/grub` and regenerate grub.cfg; the installer's validation
currently expects `set default="0"` and would need that expectation relaxed
first. After a kernel upgrade rerun `doas alpine/bin/install-boot-console` so
the ghost archive is rebuilt for the new modules; until then the ghost entry
may fail to boot while the stock entry is unaffected.

## Rollback

```sh
doas alpine/bin/install-boot-console --remove-ghost
# or restore the recorded files:
doas alpine/bin/install-boot-console --rollback /var/backups/alpine-rice/boot-console-1788860819556982985
```

## Validation

- Unit tests: banner inserted once before the root mount, refusal to patch
  twice, `sh -n` and a stub execution of the patched block; entry derivation;
  custom-fragment replacement/removal; structural validation with and without
  the ghost entry; listing comparison.
- `sh -n` on the full patched init; ShellCheck findings identical to the stock
  init apart from line numbers; `--render-init` reproduces the versioned files
  byte for byte; real build and install; `grub-script-check` on the live file;
  the init member extracted from the archive matches the versioned file;
  idempotent re-run reused the archive; `--remove-ghost` withdrew the entry and
  file and a further run rebuilt both.

## Unverified

No reboot: neither the coloured prompt nor the banner entry has been booted.
The banner entry is opt-in from the GRUB menu and is not the default.
