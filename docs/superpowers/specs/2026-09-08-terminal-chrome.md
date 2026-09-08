# Terminal chrome: splash, shaders and Neovim — 2026-09-08

Three small terminal eyecandy items from the approved rice list, implemented
in the shared HOME overlay with identical live copies under the Gruvbox Dark
profile where a file exists in both places.

## fastfetch splash

`~/.local/bin/oldbook-splash` runs fastfetch with a logo this terminal can
draw. The installed fastfetch is compiled with ImageMagick and chafa support
but neither library is in the package closure, so it cannot decode images
itself. The helper therefore prepares the logo:

- **Ghostty** (`TERM_PROGRAM=ghostty`, or a kitty-protocol terminal found by
  walking `/proc` parents): a kitty graphics command using the *file* medium
  (`t=f`), so only the PNG path crosses the pty and Ghostty reads and scales
  the painting itself. Responses are suppressed (`q=2`) and the cursor is left
  in place (`C=1`).
- **Foot** (found by process name, because the desktop's `foot.ini` sets
  `TERM=xterm-256color`): a 7-bit sixel stream encoded by the packaged
  libsixel through ctypes (median-cut palette, error diffusion, about 1.3 s
  at the 2× cell size on first use), cached per painting hash, logo size and
  terminal cell size under `~/.cache/oldbook/splash/`. A numpy/GdkPixbuf
  encoder (216-colour cube, ordered dithering) is the fallback when the
  library is missing; it is correct but several times slower.
- **Anything else** (SSH, unknown terminals): the text ghost in
  `~/.config/fastfetch/ghost.txt`, coloured through `logo.color`.

Both image paths are handed to fastfetch as `--logo-type raw` with the logo
size in cells, so its layout stays correct. `OLDBOOK_SPLASH_LOGO` overrides
detection (`kitty`, `sixel`, `text`, `none`).

The logo is `~/.local/share/oldbook/wallpaper.png`, the deployment's approved
Space Ghost painting. `~/.config/fastfetch/config.jsonc` holds the layout:
Gruvbox key/title/separator colours, Nerd Font keys, system rows, and command
rows for the Fossil branch, the current painting title (read from the gallery
state file with jq), the hour's Scripture reference (read from the durable
selection file, never through `oldbook-scripture panel`, which acknowledges
Conky renders), and the MPRIS track on air. Header colours use `{#keys}` and
`{#separator}` placeholders so generated themes recolour them.

`.zshrc` runs the splash once per terminal: interactive shell, a TTY on
stdout, not inside tmux, and `OLDBOOK_SPLASH` unset; the variable is exported
so nested shells stay quiet.

## Ghostty shaders

`~/.config/ghostty/shaders/warm-bloom.glsl` lifts bright amber and cream
pixels with an eight-tap ring and adds a fraction of that warm glow.
`~/.config/ghostty/shaders/cursor-smear.glsl` draws a parallelogram from the
previous cursor cell to the current one, tinted with `iCurrentCursorColor`,
whose tail retreats toward the cursor over 150 ms. It skips unfocused panes
and the first frame. Both are enabled through `custom-shader` in the shared
Ghostty config; the profile copy is derived from it by `oldbook-theme sync`
and carries the same lines. `custom-shader-animation = true` animates only
the focused surface.

GLSL reserved words (`half`, `sample`) and `inout` parameters were avoided
after Ghostty's glslang pass rejected the first drafts.

## Neovim chrome

`init.lua` (both copies) adds `laststatus = 3`, a statusline with a coloured
mode block, file name and modified dot, the Fossil or git branch (read from
the checkout on disk and refreshed asynchronously at most every thirty
seconds), diagnostics counts, filetype, encoding and a position block; a
winbar with the file name; and `fillchars` for thin split separators and a
blank end-of-buffer. Highlight groups derive from the Gruvbox palette and are
reapplied on `ColorScheme`. No plugin manager, no plugins.

## Verification

- `alpine/tests/test_terminal_chrome.py`: copy parity, the `.zshrc` guard,
  JSONC validity and theme placeholders, helper argument selection for text,
  none, kitty and sixel logos with a recorded fake fastfetch, sixel encoder
  output, shader configuration parity and reserved-word checks, derived
  profile survival, and a headless Neovim statusline evaluation.
- Private headless SwayFX sessions (`WLR_BACKENDS=headless`, private D-Bus and
  runtime directory) rendered the splash in Ghostty (kitty file medium) and
  Foot (sixel), Neovim with two splits in Foot, and Ghostty with both shaders
  loaded; the smear was captured with a slowed test copy of the shader.
  Screenshots: `alpine/verification/terminal-chrome/`.
- Live checks once the display woke: short-lived pre-floated Ghostty and Foot
  windows on the real 2× panel showed the splash with the painting in place
  in both terminals, and Ghostty logged both shaders loaded on the real GPU.
  Those captures include blurred desktop content behind the transparent
  terminals and were not kept. Two lessons came out of them: libsixel's 8-bit
  DCS is ignored by Foot in UTF-8 mode (7-bit is used), and a window resized
  after the splash printed (the drop-down console does this) may leave the
  kitty image displaced after Ghostty reflows. The Neovim chrome was only
  seen headlessly.

## Rollback

Remove the splash block from both `.zshrc` copies, delete the `custom-shader`
lines from both Ghostty configs (or run `oldbook-theme sync` after removing
them from the shared copy), and drop the chrome section from both `init.lua`
copies. The cached logos under `~/.cache/oldbook/splash/` can be deleted at
any time.
