# Neovim as shell and multiplexer

`nvim` with no arguments opens a `:terminal` running zsh and quits when that
shell exits. `.zshrc` `exec`s it from any interactive terminal that is not
already inside Neovim or tmux, so zsh remains `$SHELL` while Neovim is what you
see. `SPACEGHOST_PLAIN_SHELL=1 zsh` gives one plain shell. On a bash login
shell, add the same block to `~/.bashrc` (see "Install").

## Sessions: one per machine, attach from anywhere

* `nvim-session` keeps one headless Neovim per machine on the shared socket.
  With user systemd it is the `spaceghost-nvim` user service (lingering,
  `Restart=always`, so `exit`/`:qa` just gives you a fresh session); without
  it (Alpine/bak) the login hook starts it with `setsid` on first attach.
* Every interactive terminal runs `nvim-attach`, which joins that session as
  a UI (`nvim --remote-ui`). Two terminals show the same tabs and shells.
* **Detach**: `:detach`, or close the terminal. Shells and jobs keep running.
  **Reattach**: open a terminal. `SPACEGHOST_PLAIN_SHELL=1 bash` skips it.
* **Remote**: `nvim-attach HOST` (alias `a HOST`). With mosh on both ends it
  runs `mosh HOST -- nvim-attach`, so the UI lives on HOST and the link
  survives sleep, roaming and IP changes. `nvim-attach --ssh HOST` instead
  forwards HOST's socket over ssh and runs the UI locally (local clipboard
  and fonts; no UDP needed). mosh cannot forward sockets, hence the split.
* `nvim-session status|stop|sock` on any machine. `spaceghost-install`
  sets a machine up end to end (see Install).

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
curl -fsSL https://raw.githubusercontent.com/Spaceghost/.files/base/.bin/spaceghost-install | sh
# or, with the repo already present:  ~/.files/.bin/spaceghost-install [--native]
```

The installer is idempotent: it clones or updates the repo (into
`~/.spaceghost` when `~/.files` already holds another repository, as on
fedora), links `~/.bin`, `~/.config/nvim`, the zsh files and any terminal
configs whose emulator is installed, hooks `~/.bashrc`/`~/.profile` through
`.bash_spaceghost`, installs Neovim and zsh when missing (apk with sudo on
Alpine; the stable tarball into `~/.local/nvim` elsewhere), installs mosh
where a package manager allows, enables the session service and starts it.
`--native` also installs the Nelua/zig toolchain and builds the helpers.

Machines so far: alienware (Bazzite, brew nvim 0.12.5, nelua backend),
fedora (Sway Atomic, tarball nvim 0.12.5, bash, Lua backend), bak (Alpine,
apk nvim 0.12.2 + zsh, no user systemd, Lua backend).

Terminal themes for foot, kitty and Alacritty live beside the Ghostty one in
`.config/`; see `docs/terminals.md`.

Vim (`.vimrc`) keeps the older `term ++curwin` shell mode as a fallback.
