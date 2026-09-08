# Agent window switching in Sway

Alt+Tab opens a compact window picker for agent windows across workspaces.
Keep Alt held and tap Tab to advance, add Shift to go backward, release the
last held Alt key to accept, or press Escape to cancel. Window titles and
workspace labels distinguish sessions. Ordinary terminals are excluded;
Codex, ChatGPT, Claude and the Oldbook agent launchers are recognized through
the existing application resolver. Scratchpad windows are excluded.

Candidates follow Sway's focus-tree traversal order, frozen for each gesture.
The selected window receives focus only on acceptance. Its container ID, PID,
application ID and agent identity are checked again, so closing a target while
the popup is open cannot focus a replacement. This is a window switcher, so
multiple agent panes inside one terminal remain one window.

The transient GTK layer surface uses the active Oldbook palette and GTK font.
It refreshes colors while visible, shows ordinary candidate sets together and
scrolls larger sets. A dedicated Sway binding mode lets GTK receive Tab and
Alt-release events in order; Escape also restores the default mode if the
popup exits unexpectedly. The singleton socket and lock are released before
the final focus command. No background switcher daemon is installed.

## Installation and checks

The launcher, Python module and `sway/local.d/agent-switcher.conf` were deployed
with `deploy-home`, first into `/tmp/oldbook-agent-switcher-preview`, then into
the live HOME. The live deployment backup is
`~/.local/state/oldbook/backups/1788835183838710801`.

- 11 switcher unit tests pass; the focused identity/workspace suite totals
  53 passing tests. Python compilation and the complete SwayFX configuration
  parser pass.
- Private Sway with a persistent virtual keyboard and actual terminal clients
  passes forward/reverse cycling, stable focus while browsing, final Alt
  release, Escape, rapid taps before mapping, reopening, singleton handling
  and closed-window handling. Same-process dark-to-light rendering passes.
- Both screenshots show all three fixture agent windows and a clear selection.
  [Active theme](../../../alpine/verification/agent-switcher/popup-active-theme.png)
  and [light theme](../../../alpine/verification/agent-switcher/popup-light.png).
- Live reload dropped its IPC reply, but a subsequent query confirms the
  `agent-switcher` mode was loaded and the active mode is `default`. Both Alt+Tab
  bindings and the Ghostty Super+Enter binding were also applied explicitly,
  each returning success. No keyboard events were injected into the live session.

Structured evidence with source hashes is retained in
`alpine/verification/agent-switcher/`. The native harness and detailed logs
remain in `~/.local/state/oldbook/verification/agent-switcher/`.

## Recovery

To dismiss a stuck popup, run `oldbook-agent-switcher cancel` and
`swaymsg 'mode "default"'`. To remove this deployment, run:

```
alpine/bin/deploy-home --rollback /home/jack/.local/state/oldbook/backups/1788835183838710801
```

Reload Sway afterward. Ghostty's persistent Super+Enter preference is a separate
`sway/local.d/terminal.conf` include; its installation backup is
`~/.local/state/oldbook/backups/1788834887513148285`.
