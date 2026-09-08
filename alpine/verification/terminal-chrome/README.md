# Terminal chrome evidence

Headless renders from private SwayFX sessions (`WLR_BACKENDS=headless`,
private runtime directory and D-Bus, 1440×900 at scale 1) produced by
`headless-terminal.py`, a copy of the harness used on 2026-09-08. The live
display was powered off and locked at the time, so nothing here is a capture
of the physical panel; the same files render there at scale 2 with the real
cell size reported by the terminal.

| File | What it shows |
| --- | --- |
| `splash-ghostty-kitty.png` | `oldbook-splash` in Ghostty with the live config: the painting through the kitty *file* medium, Gruvbox keys, Fossil branch, painting title and Scripture rows; both shaders loaded. |
| `splash-foot-sixel.png` | The same splash in Foot through the cached numpy sixel encoder (216-colour cube, ordered dithering). |
| `ghostty-cursor-smear-slowed.png` | `cursor-smear.glsl` with `DURATION` raised to 8 s for the capture, two seconds after the cursor jumped from the bottom-left to row 3, column 44: the tail has retreated toward the cursor. The shipped shader fades in 150 ms. |
| `neovim-chrome-foot.png` | Neovim with two vertical splits: winbar file names, thin `▏` separator, and the statusline with mode, file, Fossil branch, filetype and position blocks. |

Reproduce, for example:

```sh
python3 alpine/verification/terminal-chrome/headless-terminal.py \
    --output /tmp/splash --client foot --foot-config ~/.config/foot/foot.ini \
    --command '~/.local/bin/oldbook-splash; sleep 30' --wait 6
```

Ghostty logs `loaded custom shader` for each file; a shader that fails glslang
is skipped with a `spirv error` line, which is how the reserved words `half`
and `sample` were caught before shipping.
