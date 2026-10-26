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
* **Attach in a pane**: from a shell inside the cockpit, `a HOST` (or
  `Ctrl-\ a`, `:Attach HOST [vnew|new|tabnew]`, deck entry) opens HOST's
  cockpit in a vertical split labelled `@HOST`. The prefix keeps controlling
  the local cockpit; `Ctrl-]` toggles REMOTE KEYS (shown with the host in the
  statusline) so the prefix and navigation shortcuts drive the remote one
  instead. `:detach` inside closes the
  pane.
* `Ctrl-Space` is only seen by terminals that speak the kitty keyboard
  protocol (Ghostty, foot, kitty, Alacritty, WezTerm); older terminals send
  NUL, which Neovim drops, so use `Ctrl-\` there.
* Only the instance started by `nvim-session` (`--listen`) owns the shared
  socket; a plain `nvim` never claims it.
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

## Navigate without a prefix

These keys work while typing in a shell and while editing a file:

| key | action |
| --- | --- |
| `F2` | Find any pane across all tabs, including attached hosts |
| `Alt-Left/Down/Up/Right` | Passed through to the terminal application |
| `Ctrl-PageUp` / `Ctrl-PageDown`, or `Alt-[` / `Alt-]` | Previous / next tab, wrapping at the ends |
| `Alt-1` through `Alt-9` | Jump directly to a tab |
| `Alt-o` | Toggle back to the previous pane, even in another tab |
| `F1` / `F4` | Field guide / command deck |

In the `F2` picker, each row shows the tab number and custom name, pane
number, shell/file/remote type, host or title, directory, and unread output.
`SHARED N` marks multiple panes displaying the same buffer.
The current pane is marked `>` and selected initially. Use `j`/`k`, arrows,
or Tab/Shift-Tab to move; Enter focuses the selection. Type `/bak` to find
an attached host, `/project` for a directory or title, or `/tab 3` for a tab.
Use `n`/`N` for more matches. Escape cancels search; Escape again closes the
picker. `q` also closes it. The list scrolls and has no pane-count limit.
Returning to a shell puts it back in terminal input mode.

Choosing a remote host in the picker enters that host's own tabs and panes
picker and enables REMOTE KEYS. This works through the live attached UI;
it does not need a second SSH connection or a cached list of remote tabs.
The local picker lists local panes and host entries; each host's picker
lists the tabs and panes inside that session.

In an attached host pane, `Ctrl-]` switches between LOCAL and REMOTE KEYS.
In REMOTE KEYS, `F1`/`F2`/`F4`, Alt-tab shortcuts, Alt-1..9,
Alt-o, Ctrl-PageUp/Down, and the prefix all go to that host. The statusline
shows `REMOTE @HOST / ^] local`. Press `Ctrl-]` to return to local controls.
Routing is per host pane and survives a configuration reload. You can still
send a single prefix to a host by pressing the prefix twice in local mode.
Alt-arrows always pass through to terminal applications, including inside
a nested remote session. To focus a pane, use the prefix followed by
`h`/`j`/`k`/`l`.
If your terminal emulator intercepts an Alt or Ctrl-Page key, use the
prefix equivalents below. The statusline shows the current tab and pane
numbers and reminds you of `F2` and `F4`.

## Pane sizing with multiple clients

Neovim uses the minimum attached client width and height as the shared canvas.
Shells fill their panes within that canvas and grow again when the smaller
client resizes or detaches. There is no fixed 80×24 limit. The tab bar and
shared status bar use one row each; the command line appears only when needed
(`cmdheight=0`). Splits divide the remaining area. No automatic maximization
or pane balancing changes your layout.

## Redraw a terminal or remove a duplicate pane

Press `F4`, release it, then press `d` to redraw the focused pane. This
refreshes Neovim and asks the terminal program to redraw at its current
size. It does not send Ctrl-L or other input to the program. The prefix
followed by `d`, or `:TermRedraw`, does the same thing.

Press `F2`, select an unwanted duplicate pane, then press `x`. This removes
the selected view without entering its host, and keeps its shell and other
views running. The picker refuses to remove a pane that has no duplicate.

`F4`, then `x` also closes the focused pane. If another pane shows the same
terminal buffer, only the duplicate view closes. Closing the last view of
a terminal through `F4 x` still stops that terminal, so use `:detach` to
leave a session running. `Ctrl-]` returns host navigation to local control
when the statusline shows `REMOTE @HOST`.

## Keys (prefix `Ctrl-\` or `Ctrl-Space`)

| key | action | key | action |
| --- | --- | --- | --- |
| `Space` | command deck | `?` `F1` | field guide |
| `c` | new tab shell | `s` / `v` | split shell below / right |
| `h j k l` | focus pane | `H J K L` | resize pane |
| `n` / `p` | next / previous tab | `1`-`9` | jump to tab |
| `Tab` | previous pane across tabs | `w` | searchable tabs + panes + hosts picker |
| `z` / `=` | zoom / balance | `x` | close pane |
| `d` | redraw pane and its terminal | | |
| `` ` `` | scratch terminal (toggle) | `g` | git observatory |
| `~` | btop / htop | `e` | edit a file |
| `a` | attach a machine in a split | `Ctrl-]` | toggle all navigation between local and remote |
| `[` | copy mode (`Esc` returns) | `]` | paste `"` register into shell |
| `,` | rename tab | `r` | reload configuration |
| prefix | send the prefix itself | `Ctrl-n` | leave terminal mode (`Ctrl-\ Ctrl-n`) |

`:Shell [tabnew|vnew|new]` opens a shell from the command line.

Navigation regression checks from the repository root (isolated Neovim
instances; the nested check runs a real remote UI inside a terminal):

```sh
nvim --headless -u NONE -l tests/nvim-navigation.lua
nvim --headless -u NONE -l tests/nvim-nested.lua
```

Agentic checks after installing its dependencies (the last sends one small
prompt using the existing Codex login):

```sh
nvim --headless -u NONE -l tests/nvim-agentic-terminal.lua
nvim --headless -u NONE -l tests/nvim-agentic.lua --live
```

## Native Codex application (Agentic)

`Ctrl-\ i` opens Agentic: native Neovim chat, input, file context, tool activity,
permission buttons, and split diff previews, using the existing Codex ChatGPT
login on this machine. `Ctrl-Space i` also works in supported terminals.
The chat follows the Spaceghost violet/mint theme. It is not a terminal wrapper.

1. In a shell, `cd` to the project; in an editor, open a project file.
2. Press `Ctrl-\ i`, type a prompt, and press `Ctrl-s` to send.
3. Follow permission prompts to review edits; `]c` / `[c` navigate preview hunks.

In normal mode, Enter also sends; in insert mode, Enter inserts a newline.
`q` in normal mode hides the chat while the session keeps running.
`Ctrl-\ I` in a file adds it, or adds the visual selection when one is active.
Type `@` in the prompt for workspace file completion; `/` lists agent commands.

`F4 i` opens the Codex menu: toggle (`i`), new session here (`n`), live sessions
(`s`), restore saved sessions (`r`), rotate layout (`l`). Existing sessions keep
their workspace; use New session after changing projects. New sessions start
in the originating file's directory or shell's OSC 7 directory. On a remote
pane, switch to REMOTE KEYS with `Ctrl-]` first to run Codex on that host.

Commands: `:Codex`, `:CodexNew`, `:CodexSessions`, `:CodexRestore`, `:CodexAdd`,
`:CodexDiagnostics`, `:CodexLayout`, `:CodexMenu`.
Within Agentic, `\m` chooses a model, `\o` opens agent options, `\t` chooses
reasoning effort, and Shift-Tab changes agent mode. The initial mode is Workspace
access (workspace writes, with permission requests for additional access).

Install or repair on any configured host:

```sh
~/.bin/spaceghost-agentic-install
# Reload the running cockpit: F4 r
```

Requires git, Node.js 20.19+ (or 22.12+), npm, Neovim 0.11+, and a Codex login
(`codex login`). The installer pins Agentic's commit and installs the maintained
`@agentclientprotocol/codex-acp` adapter from the committed npm lockfile. Its
compatible bundled Codex shares `~/.codex` authentication/configuration and
leaves the standalone Codex CLI intact. No credentials are stored in this repo.
Dependencies live under Neovim's data directory, never install at startup, and
only load when opening the UI. To update, change `agentic/plugin-revision` or
`agentic/package.json`, regenerate the lockfile in that directory, and rerun
the installer on each host.

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
