# Neovim as shell and multiplexer

`nvim` with no arguments opens a `:terminal` running zsh and quits when that
shell exits. `.zshrc` `exec`s it from any interactive terminal that is not
already inside Neovim or tmux, so zsh remains `$SHELL` while Neovim is what you
see. `SPACEGHOST_PLAIN_SHELL=1 zsh` gives one plain shell. On a bash login
shell, add the same block to `~/.bashrc` (see "Install").

## One instance

* The first instance listens on `$XDG_RUNTIME_DIR/nvim-spaceghost.sock`
  (`$SPACEGHOST_NVIM_SOCK` overrides). The HUD shows `SRV` when this is it.
* `$EDITOR`/`$VISUAL` are `~/.bin/nvim-remote`. Inside a Neovim terminal it
  targets `$NVIM`; from a tmux pane or another terminal it targets the shared
  socket; with no live instance it runs `nvim`.
* `nvim-remote` blocks until the buffer is closed (`:q`, `:bd`), so
  `git commit`, `crontab -e`, and `kubectl edit` behave normally. `+N` jumps to
  a line. The buffer opens as a split above the shell that asked for it.

## Cockpit

* **Tabline** = tmux window list: `N / name  NOW` for the current tab, `LIVE`
  for a running shell, `NEW` when a hidden shell printed output, `EXIT` for a
  dead one, `EDIT` for a file tab. Tabs are named from the shell's OSC 0 title
  (the running command, else the cwd); `Ctrl-\ ,` renames.
* **Statusline** (global): mode, shell title or file, cwd (fish-style
  shortened), git branch, LOAD / MEM / BAT telemetry, pane index, `SRV`.
* **Shell integration**: `.zshrc` emits OSC 7 (cwd) and OSC 0 (title) so new
  splits open in the focused shell's directory and the HUD tracks it.
* **Colorscheme** `spaceghost` matches `.tmux.conf` and the terminal themes;
  terminal palette colors are set so TUIs inside the shell match too.

## Keys (prefix `Ctrl-\`)

| key | action | key | action |
| --- | --- | --- | --- |
| `Space` | command deck | `?` `F1` | field guide |
| `c` | new tab shell | `s` / `v` | split shell below / right |
| `h j k l` | focus pane | `H J K L` | resize pane |
| `n` / `p` | next / previous tab | `1`-`9` | jump to tab |
| `Tab` | last pane | `w` | tabs + panes picker |
| `z` / `=` | zoom / balance | `x` | close pane |
| `` ` `` | scratch terminal (toggle) | `g` | git observatory |
| `~` | btop / htop | `e` | edit a file |
| `[` | copy mode (`Esc` returns) | `]` | paste `"` register into shell |
| `,` | rename tab | `r` | reload configuration |
| `Ctrl-\` | send a literal Ctrl-\ | `Ctrl-n` | leave terminal mode |

`:Shell [tabnew|vnew|new]` opens a shell from the command line.

## Native helpers (Nelua + zig cc)

`.config/nvim/native/spaceghost.nelua` implements the telemetry sampler,
OSC 7 decoding and path shortening. `~/.bin/spaceghost-native toolchain`
installs the latest zig master tarball and builds nelua-lang with `zig cc`
under `~/.local/spaceghost`; `~/.bin/spaceghost-native` compiles the module to
`~/.local/share/nvim/spaceghost/libspaceghost.so`. `lua/spaceghost/native.lua`
loads it over LuaJIT FFI and falls back to pure Lua when it is missing, so the
config works unchanged on hosts without the toolchain. The field guide shows
which backend is active.

## Install

```sh
gh repo clone Spaceghost/.files ~/.files
ln -sfn ~/.files/.zshrc ~/.zshrc; ln -sfn ~/.files/.zshenv ~/.zshenv; ln -sfn ~/.files/.bin ~/.bin
ln -sfn ~/.files/.config/nvim ~/.config/nvim
ln -sfn ~/.files/.config/ghostty/config ~/.config/ghostty/config
ln -sfn ~/.files/.config/ghostty/themes ~/.config/ghostty/themes
~/.bin/spaceghost-native toolchain && ~/.bin/spaceghost-native   # optional
```

Terminal themes for foot, kitty and Alacritty live beside the Ghostty one in
`.config/`; see `docs/terminals.md`.

Vim (`.vimrc`) keeps the older `term ++curwin` shell mode as a fallback.
