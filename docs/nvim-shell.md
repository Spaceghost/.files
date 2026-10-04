# Neovim as shell and multiplexer

`nvim` with no arguments opens a `:terminal` running zsh and quits when that
shell exits. `.zshrc` `exec`s it from any interactive terminal that is not
already inside Neovim or tmux, so zsh remains `$SHELL` while Neovim is what you
see. `SPACEGHOST_PLAIN_SHELL=1 zsh` gives one plain shell.

## One instance

* The first instance listens on `$XDG_RUNTIME_DIR/nvim-spaceghost.sock`
  (`$SPACEGHOST_NVIM_SOCK` overrides).
* `$EDITOR`/`$VISUAL` are `~/.bin/nvim-remote`. Inside a Neovim terminal it
  targets `$NVIM`; from a tmux pane or another terminal it targets the shared
  socket; with no live instance it runs `nvim`.
* `nvim-remote` blocks until the buffer is closed (`:q`, `:bd`), so
  `git commit`, `crontab -e`, and `kubectl edit` behave normally. `+N` jumps to
  a line.

## Keys (prefix `Ctrl-\`)

| key | action | key | action |
| --- | --- | --- | --- |
| `c` | new tab shell | `h j k l` | focus window |
| `s` / `v` | split shell below / right | `n` / `p` | next / previous tab |
| `z` / `=` | zoom / balance | `Ctrl-n` | leave terminal mode |

`:Shell [tabnew|vnew|new]` opens a shell from the command line.

Vim (`.vimrc`) keeps the older `term ++curwin` shell mode as a fallback.
