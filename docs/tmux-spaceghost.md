# Spaceghost / mission control

The root `.tmux.conf` is a self-contained Spaceghost setup: void black,
spectral violet, ion mint, and amber notifications. It uses tmux's native
status lines, menus, popups, and key tables. No icon font, theme plugin,
background daemon, or network request is needed for the theme.

The root configuration is separate from the Alpine desktop theme overlays;
installing it does not rewrite those profiles.

## Read the instrument panel

The solid mint **NOW** tab is your current window. Other tabs show their
state separately from unread activity:

| Indicator | Meaning |
| --- | --- |
| READY, mint | Codex's title reports `Ready` or `Waiting` |
| BUSY, violet | Codex's title reports `Working` or `Thinking` |
| LIVE, muted | No explicit agent state and no silence alert yet |
| QUIET, muted | tmux observed no window output for 30 seconds |
| NEW, amber | Unread output since you last visited that window |
| EXIT, rose | The active pane has exited and remains visible |
| !, rose | A window bell was reported |

READY and NEW can appear together. QUIET does not mean a process has stopped;
a build may work silently. Agent state describes the window's active pane,
while activity and silence apply to the window. Spinner-only or unrecognized
titles fall back to LIVE/QUIET instead of guessing whether an agent is done.

Structured Codex titles show the task without repeating the user and state
metadata. A window you rename with `Ctrl-a ,` keeps your chosen name. The
complete active pane title is still forwarded to the terminal and desktop.

The second row shows the command, directory, Git branch (or detached commit),
pane position, and system load where width permits. Long paths retain their
useful ending. Chrome and titles shorten on narrow terminals, leaving more
room for the native clickable, scrolling window list. Git status scans happen
only when you open the Git popup; the status bar reads only the branch/HEAD.

## Controls

Start every shortcut below with **Ctrl-a**. **Ctrl-a Ctrl-Space** opens the
command deck; ordinary **Ctrl-a Space** cycles layouts.

| Key after Ctrl-a | Action |
| --- | --- |
| Ctrl-Space | Command deck |
| F1 | Flight manual |
| Ctrl-e | Geometry / persistent resize mode |
| h j k l | Select pane |
| H J K L | Resize pane by five cells |
| v, \|, Enter | Split right, in the current directory |
| s, - | Split below, in the current directory |
| c | New window in the current directory |
| Ctrl-h / Ctrl-l | Previous / next window |
| Tab / a | Last pane / last window |
| w | Session/window tree |
| z | Zoom/unzoom pane |
| N | Toggle pane labels for this window |
| Backtick | Scratch terminal; exit or Ctrl-d closes it |
| g | Git observatory: tracked changes and recent commits; Enter closes |
| [ then v / y | Enter copy mode, select / copy |
| b / ] | Buffer browser / paste |
| B | Toggle one/two status rows for this session |
| S / Ctrl-r | Save / restore with tmux-resurrect |
| r / R | Reload `~/.tmux.conf` |
| Ctrl-a | Send a literal Ctrl-a to the application |

In geometry mode, `h j k l` and arrows resize by three cells; capitals resize
by ten. `=` balances panes and Space cycles layouts. `q`, Escape, Enter, or
Ctrl-c exits. Other keys leave the mode without typing into your application.
The status bar shows **RESIZE** while the mode is active.

Existing TPM, logging, sidebar, yank, and manual resurrect integrations remain.
Automatic saves, automatic restore, and boot restore remain disabled. Prefix
Ctrl-s stays unbound. The legacy `?`, `~`, and `A` shortcuts still depend on
your existing man, htop, and `/usr/local/bin/autossh` setup.

## Install or update

Target tmux 3.3 or newer; verified with 3.7c. Git is needed for Git information.
Linux load comes from `/proc/loadavg`; BSD/macOS use `sysctl vm.loadavg`.
Modern terminal entries get RGB support, and tmux-256color is selected when
`tput` can resolve its terminfo; otherwise the config uses screen-256color.

Back up your current `~/.tmux.conf`, copy this repository's root `.tmux.conf`
there, and run:

```sh
tmux source-file ~/.tmux.conf
```

Existing panes continue running. Default-terminal and the larger history limit
take effect in newly created panes. Clipboard delivery depends on the terminal
supporting tmux's clipboard integration.

The theme works without TPM. To use the listed plugins, install TPM in its
standard `~/.tmux/plugins/tpm` location, then use Ctrl-a Shift-i. Config and
binding overrides deliberately run after TPM so plugins cannot replace them.

## Recovery

Restore your saved config and source it. Options and bindings absent from that
file may remain in an already-running server; a fresh server loads only the
restored config. Do not kill a server containing work to reset its appearance.

For a temporary plain bar while keeping sessions alive:

```sh
tmux set-option -g status on
tmux set-option -g status-style 'bg=black,fg=white'
tmux set-option -g status-left '[#S] '
tmux set-option -g status-right '%H:%M'
```

`B` and `N` create session/window-specific choices. To inherit the global
defaults again, use `tmux set-option -u status` and
`tmux set-option -wu pane-border-status` in the affected session/window.
