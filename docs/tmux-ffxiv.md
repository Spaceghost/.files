# Spaceghost tmux in FFXIV

The persistent work lives in session `0` on **bak**. Alienware's local game
and Fedora's streamed game attach to grouped views of those same windows:

| Surface | Session on bak | Connection |
| --- | --- | --- |
| Desktop | `0` | Existing terminal, or `spaceghost-tmux` |
| Local FFXIV on Alienware | `ffxiv-alienware-0` | Local Ghostty agent → SSH → bak |
| FFXIV on Fedora | `ffxiv-fedora-0` | Container Ghostty agent → Fedora SSH relay → bak over Tailscale |
| Moonlight | Same Fedora game view | Moonlight streams Fedora; no second tmux server |

Grouped sessions share actual windows, panes, processes, and tmux paste buffers.
Each session chooses its current window independently. Within the *same* shared
window, the active pane and pane geometry are still shared; these are not
independent terminal emulators. Disconnecting a terminal or stream leaves the
tmux work running on bak. No tmux server is nested inside another.

## Controls and focus

- **Ctrl-backtick** opens/closes Ghostty's terminal in FFXIV.
- **Ctrl-a Ctrl-Space** opens the tmux command deck.
- **Ctrl-a F** opens the FFXIV focus/session guide.
- **Ctrl-a F, d** switches that tmux client to the desktop session.
- **Ctrl-a w** switches among sessions and windows.
- **Ctrl-a Ctrl-a** sends a literal Ctrl-a to the application.
- **Ctrl-a d** detaches the terminal client; its work continues on bak.
- **Ctrl-Shift-c/v** remain Ghostty's copy/paste shortcuts.

For Moonlight PC, **Ctrl-Alt-Shift-z** toggles keyboard/mouse capture,
**Ctrl-Alt-Shift-d** minimizes the stream, and **Ctrl-Alt-Shift-q** disconnects
without terminating the game. These are Moonlight shortcuts, not tmux bindings.
See the [Moonlight input documentation](https://github.com/moonlight-stream/moonlight-docs/wiki/Setup-Guide#keyboardmousegamepad-input-options).

Focus the Ghostty terminal before typing tmux commands. When it is hidden,
keyboard input belongs to the game. A host-side tmux test cannot establish that
an actual Moonlight stream, controller, clipboard, or game focus works correctly;
those require checking the running game. tmux paste buffers are shared, but
Moonlight client and remote desktop clipboards are separate systems.

## Installation pieces

Install `.bin/spaceghost-tmux` as `~/.local/bin/spaceghost-tmux` on bak. The
helper accepts `--view desktop`, `--view alienware`, or `--view fedora`.
`--prepare` creates/configures the view without attaching or changing focus.
The canonical session defaults to `0`; `--session NAME` selects another.
Existing sessions with a colliding game-view name but a different group are
rejected without changing them. An absent canonical session starts a new shell;
this does not automatically restore old agent processes.

Put `integrations/ffxiv/spaceghost_tmux.lua` in the Ghostty plugin configuration's
`lua/` directory on each game machine. Wrap the existing final return in the
user's `lua/init.lua`:

```lua
return require('spaceghost_tmux').apply(settings.apply(config), {
  'ssh', '-tt', '-o', 'BatchMode=yes',
  '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
  'bak', '/home/jack/.local/bin/spaceghost-tmux', '--view', 'alienware',
}, 'Alienware')
```

That example assumes Alienware's existing SSH access to bak. Fedora's container
uses its dedicated SSH relay command instead: it has no direct tailnet route.
Keep machine-specific SSH configuration and all private keys outside this repo.
Dedicated relay keys permit terminal attachment and disable forwarding; entering
tmux grants access to its existing shell panes, so these are trusted user keys,
not a sandbox for untrusted clients. Host keys are pinned from the already
authenticated machines; do not disable host-key checks.

The module appends one profile, makes it the default for new terminals, and
preserves existing profiles, agent credentials, appearance, and key handling.
Use `/term reload` in the game after updating Lua; existing terminals continue
running their original commands. Open a new terminal to use the new profile.
In-game views have a compact, one-row FFXIV bar. Ctrl-a B restores the second
status row when useful. The game connection uses `attach-session -E` so its
environment does not replace the desktop session's SSH/display variables.

## Verify and recover

Open the Spaceghost profile in each game and confirm that the expected existing
window content appears. Switch windows in the game and confirm the desktop's
selected window stays unchanged. Create a harmless window, detach, reconnect,
and confirm the same pane process persists. Test Ctrl-a Ctrl-Space, copy mode,
Ctrl-backtick, and Moonlight's capture/release shortcuts in a real stream.

Before deployment, back up each machine's `lua/init.lua`. To undo the plugin
change, restore that file and run `/term reload`. The added module is inert when
not required. Restore the previous tmux config separately if desired. Do not
kill grouped sessions/windows to roll back: their windows contain shared work.
