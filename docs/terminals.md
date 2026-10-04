# Terminals

Every terminal does the same job here: draw Neovim. The shell hook in `.zshrc`
(or `~/.bashrc`) starts Neovim, Neovim owns tabs, splits, titles and `$EDITOR`.
Each config therefore keeps the emulator's own chrome and keybindings minimal
and ships the Spaceghost palette so TUIs inside the shell match the HUD.

| terminal | config | notes |
| --- | --- | --- |
| Ghostty | `.config/ghostty/config` + `themes/spaceghost` | shell integration `detect`, title from Neovim, `Ctrl-Shift-T` still opens a Ghostty tab |
| foot | `.config/foot/foot.ini` | scrollback disabled (Neovim has it), beam cursor |
| kitty | `.config/kitty/kitty.conf` | Nerd symbols mapped onto Fira Code |
| Alacritty | `.config/alacritty/alacritty.toml` | no decorations |

Palette (shared with `.tmux.conf` and `colors/spaceghost.lua`):

```
background 0b0d16   surface 161a2b   foreground e8edf7   muted 8992ad
violet b4a1ff   mint 79efc2   amber f3c969   alert ff7597   blue 7fb7ff   cyan 7fe3f0
```

Fonts: Fira Code with Symbols Nerd Font Mono as fallback (both present on the
Bazzite workstation under `/usr/share/fonts`).
