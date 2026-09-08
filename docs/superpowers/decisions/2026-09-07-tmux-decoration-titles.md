# Forward tmux pane titles to the workspace decoration

The tmux-hosted Codex windows had the static Sway title `Codex`, while their
active tmux panes already contained Codex's full working-state and context title.
The live tmux server had `set-titles off`. The decoration correctly used Sway's
window title; the missing update was between tmux and its terminal client.

Enable `set-titles` and use `#{pane_title}` as `set-titles-string` in the Alpine
desktop tmux configuration and both Spaceghost/Gruvbox theme profiles. Apply the
two options to the live server without restarting sessions or changing focus.
This follows the active pane and lets Sway's normal title events update the
existing decoration. No extra process polling or title parser is introduced.

Validation: all three configurations loaded in disposable tmux servers under
private HOMEs. Expanded title strings followed two successive test pane titles.
Both live oldbook-agent terminal titles changed from `Codex` to the full Codex
title; `output_contexts` returned that same full title for the focused output.
Runtime JSON and a bottom-edge screenshot are saved locally at
`~/.local/state/oldbook/tmux-title-{verification,live}.json` and
`~/.local/state/oldbook/tmux-title-bar.png`. A full logout/login was not performed.

Recovery: remove the two settings from the three configurations and run
`tmux set-option -g set-titles off` to stop forwarding terminal titles. Active
sessions and their contents do not need to be restarted.

Reference: https://github.com/tmux/tmux/wiki/Advanced-Use
