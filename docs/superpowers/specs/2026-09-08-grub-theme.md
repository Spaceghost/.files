# Ghost Planet GRUB menu — 2026-09-08

## What

The boot menu is now Gruvbox, three seconds long, and carries the Ghost. Round
one had already recoloured every text-mode screen through kernel parameters; the
GRUB menu itself was the last screen still in stock white-on-black at a one
second timeout.

- `alpine/system/grub/theme/` holds the versioned theme: `theme.txt`, a
  `background.png`, nine selection tiles and two PF2 fonts.
- `alpine/bin/build-grub-theme` regenerates all of it from the palette and
  `alpine/assets/spaceghost.png`. `--check` re-renders into a temporary
  directory and reports whether the committed theme is still current.
- `alpine/system/grub/grub_theme.py` is the pure logic: a PF2 font writer and
  parser, the theme.txt renderer and validator, the `/etc/default/grub` key
  rewriter and a check that a generated `grub.cfg` really shows the themed menu.
- `alpine/bin/install-boot-console` gained `--skip-theme` and `--remove-theme`
  and now installs the theme and sets five GRUB keys.
- `alpine/system/grub/render-preview` draws the menu from the committed theme
  as evidence, since `grub-emu` is not packaged.

## Why a font compiler

GRUB draws menus with its own bitmap font format, PF2. `grub-mkfont` is not in
Alpine's grub package here, and the stock `unicode.pf2` is sixteen pixels tall,
which on a 2880x1800 panel is about two millimetres of text. A themed menu in an
illegible font is worse than no theme.

PF2 is a simple container: named sections for the metadata, a character index of
absolute file offsets, and glyphs stored as five big-endian metrics followed by a
one-bit-per-pixel bitmap packed as a continuous stream with no per-row padding.
The generator renders each code point with Pango at the requested pixel size,
thresholds the alpha at half, and hands the rows to `build_pf2`. Two sizes are
shipped, 32 pixels for the title and entries and 20 for the subtitle, help line
and countdown, covering printable ASCII, Latin-1, the punctuation GRUB's own
strings use, light box drawing and the Material Design ghost at U+F02A0 that the
desktop already brands itself with.

The failure mode is safe: if a font will not load, GRUB falls back to its
built-in one and the menu still works.

## Why the background is small and blurred

GRUB decodes the PNG on the CPU before the menu appears, so a sharp panel-sized
image would cost real time at every boot. The background is 1280x800 and heavily
blurred, stretched to the panel by `desktop-image-scale-method`. Blurred content
upscales invisibly, and the file stays around 230 KB.

The painting is graded rather than pasted: its blurred luminance is stretched
across its own range, warmed towards amber, held back in the middle of the screen
where the menu text sits, and lifted by a soft amber lamp behind the wordmark.
The gallery leans nocturnal, so a plain darkening turned the first attempt to mud.

## GRUB keys

`GRUB_TIMEOUT=3` and `GRUB_TIMEOUT_STYLE=menu` show the menu for three seconds.
`GRUB_THEME` points at the installed `theme.txt`. `GRUB_GFXMODE=auto` takes the
panel's own mode and `GRUB_GFXPAYLOAD_LINUX=keep` hands it to the kernel, so the
framebuffer console keeps the graphics mode and round one's palette and Terminus
font apply from the first kernel message.

`rewrite_grub_keys` replaces a key in place when it is present and appends the
rest under one managed comment, so the file keeps its order and a second run
changes nothing. It refuses a duplicated key and refuses shell metacharacters.

## Entry titles

The menu titles are unchanged. Renaming them means changing `GRUB_DISTRIBUTOR`,
which also changes the `gnulinux-*` identifiers that `set default` selects, and
the installer's own guarantee is that the stock entry's title, kernel, initramfs
and parameters are identical before and after. Ghost Planet branding lives in
the wordmark and the subtitle instead.

## Ordering

`00_header` only emits the theme when the file already exists on disk, so the
installer copies the theme before it runs `grub-mkconfig`. Alpine's `00_header`
globs `"$themedir"/*.pf2` and `"$themedir"/f/*.pf2` for `loadfont`, which is why
the fonts sit beside `theme.txt` rather than in a `fonts/` subdirectory.

## Verification

38 unit tests in `alpine/tests/test_grub_theme.py`: the bitmap packer, a PF2
round trip through the writer and parser, sorted index offsets, rejected
malformed glyphs, theme rendering and validation against shipped fonts and
images, the GRUB key rewriter's idempotence and refusals, the menu-config check,
and the committed theme's own consistency.

On the machine: a dry run, a real install, an idempotent second run,
`grub-script-check` on the generated config, and the structural proof that the
stock entry still boots the same kernel, initramfs, root and crypt parameters
and stays first and default. Evidence and the rendered preview are in
`alpine/verification/grub-theme/`.

The first real install failed and rolled itself back, which is worth recording:
the menu check anchored `set timeout=3` at the start of a line, and
`grub-mkconfig` indents it by two spaces inside its `feature_timeout_style` test.
The safety net behaved exactly as designed, no file was left changed, and the
patterns now tolerate leading whitespace with a test for the real indented form.

**Unverified:** the menu itself. `grub-emu` is not packaged, no reboot was
performed, and the preview is a simulation drawn from the theme rather than by
GRUB. The first boot after this change is the real check.

## Rollback

```sh
doas alpine/bin/install-boot-console --remove-theme   # plain GRUB menu, theme removed
doas alpine/bin/install-boot-console --rollback /var/backups/alpine-rice/boot-console-<stamp>
```

`--remove-theme` empties `GRUB_THEME`, which is what `00_header` tests for, and
deletes the installed theme files. It leaves the three-second timeout alone,
since that is a separate preference. The palette, font and banner initramfs from
round one are untouched by both paths.
