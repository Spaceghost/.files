# Root-installed system files

Everything under `alpine/system/` is versioned source for files that live
outside HOME. Each has an idempotent installer in `alpine/bin/` that compares
exact content before replacing anything and moves the previous file to
`/var/backups/alpine-rice/<component>-<nanoseconds>/`, mirroring its absolute
path, so every change can be reversed from that directory.

| Component | Sources | Installer | Host files |
| --- | --- | --- | --- |
| Desktop entrypoint | `alpine/bin/oldbook-ui-priority`, Qt palettes | `alpine/bin/install-desktop-system` | `/usr/local/bin/sway`, session entry, backlight udev rule, `/usr/share/qt6ct/colors/*` |
| Autologin | `greetd/config.toml` | copied by hand (see the greetd notes in `alpine/desktop/README.md`) | `/etc/greetd/config.toml` |
| Boot console | `boot/console-palette.json` (generated), `boot/issue.template`, `boot/boot_console.py`, `boot/console_palette.py` | `alpine/bin/install-boot-console` | `/etc/default/grub`, `/boot/grub/grub.cfg`, `/etc/issue` |
| Banner initramfs | `mkinitfs/initramfs-init` (+ stock copy and patch) | `alpine/bin/install-boot-console` | `/boot/initramfs-lts-ghost`, `/etc/grub.d/40_custom` |

## Boot console

`console-palette.json` is generated, not authored: `alpine/bin/build-console-palette`
renders it from the theme named in `alpine/themes/current`, taking the sixteen VT
colours from that theme's own Foot palette — the same file Ghostty's palette is
derived from — so the terminals, the console, the LUKS prompt, the rescue gettys
and the GRUB menu cannot drift apart. `oldbook-theme use` runs it on every
switch and says so; `--check` reports whether the committed file is current, and
`install-boot-console` refuses to install a palette the selected theme has moved
on from (`--skip-palette-check` overrides). Applying a new theme to the boot
chain is therefore three commands, only the last of which needs root:

```sh
alpine/bin/build-console-palette      # after oldbook-theme use, if it is not already current
alpine/bin/build-grub-theme           # repaint the menu in the new palette
doas alpine/bin/install-boot-console  # publish both to /etc and /boot
```

`install-boot-console` appends that VT palette (`vt.default_red`,
`vt.default_grn`, `vt.default_blu`), the default attribute `vt.color=0x0F`
(cream on charcoal) and `fbcon=font:TER16x32` (the kernel's built-in Terminus,
sized for the 2880×1800 panel) to `GRUB_CMDLINE_LINUX_DEFAULT`. The managed
tokens are replaced on every run; every other token and line is preserved.
`/etc/issue` is rendered from `boot/issue.template`, whose colour tokens become
sixteen-colour SGR sequences, so the rescue gettys on tty2–tty6 print a small
Ghost Planet masthead in the same palette. The console font service stays
disabled: the kernel option covers the initramfs and the running system alike.

`grub.cfg` is regenerated into a temporary file, checked with
`grub-script-check`, and compared against the live file: the stock entry must
keep the same title, kernel, initramfs, root, cryptroot, cryptdm and modules
parameters plus exactly the managed tokens, the boot device lookup and the
default selection must be unchanged, and any banner entry must mirror the stock
entry. Only then is the file moved into place. On any mismatch the run restores
its own backups and exits non-zero.

```sh
alpine/bin/install-boot-console --dry-run          # preview, no root needed
doas alpine/bin/install-boot-console               # install or re-apply (builds the banner initramfs too)
doas alpine/bin/install-boot-console --skip-ghost  # palette, font and getty banner only
doas alpine/bin/install-boot-console --remove-ghost
doas alpine/bin/install-boot-console --rollback /var/backups/alpine-rice/boot-console-<ns>
alpine/bin/install-boot-console --render-init      # after a mkinitfs upgrade, as the user; review and commit
python3 -m unittest alpine/tests/test_boot_console.py alpine/tests/test_theme_boundary.py -v
```

## Banner initramfs

`alpine/system/mkinitfs/initramfs-init` is the installed mkinitfs init plus one
guarded block that prints a Gruvbox masthead before the encrypted-root
passphrase prompt. The installer builds it into `/boot/initramfs-lts-ghost`
with `mkinitfs -i`, proves the archive carries that exact init and the kernel's
modules, compares its file list with the stock archive, and publishes it as an
additional GRUB entry derived from the stock entry (managed block in
`/etc/grub.d/40_custom`). The stock entry stays first and default;
`/boot/initramfs-lts` is never replaced. Select the entry from the one-second
GRUB menu to test it. Rerun the installer after a kernel upgrade so the ghost
archive matches the new modules. See `docs/superpowers/specs/2026-09-08-luks-prompt.md`.

## Boot menu theme

`alpine/system/grub/theme/` is the Ghost Planet GRUB menu: a graded, blurred
background from the current painting, an accent-coloured selection bar and two
PF2 fonts compiled from JetBrains Mono, because `grub-mkfont` is not packaged and
GRUB's own font is sixteen pixels tall. Its colours are the console palette's
sixteen plus the hard ground, surface and border of the theme that palette names,
so the menu paints the same chrome the desktop does; a palette naming no theme
falls back to the Gruvbox shades. `alpine/bin/build-grub-theme` regenerates it
(`--check` says whether the committed copy is current) and
`alpine/system/grub/grub_theme.py` holds the font writer, the theme renderer and
the GRUB key rewriter. The installer copies the theme to
`/boot/grub/themes/ghost-planet`, sets a three-second menu and hands the
graphics mode to the kernel so the console palette above still applies.
`--skip-theme` leaves it alone, `--remove-theme` withdraws it. See
`docs/superpowers/specs/2026-09-08-grub-theme.md` and the rendered preview in
`alpine/verification/grub-theme/`.

Nothing here reboots, switches VTs or loads a font into a live console. The
visual result is only observable at the next boot.
