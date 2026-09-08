# Discover agents behind custom terminal IDs

The agent launcher gives Foot windows the Wayland app ID `oldbook-agent`.
ApplicationResolver recognized terminals only by Wayland/X11 application IDs,
so these windows skipped its existing tmux-client and pane discovery and were
classified as ordinary applications. The count and switcher share that resolver.

Include the window PID's command name from the existing UID-filtered process
snapshot when recognizing a terminal. Both the batch tmux-query gate and per-view
resolution use this same decision. No new process scan, title-based agent guess,
or per-window tmux subprocess is added. Existing visible/dominant-pane semantics
and stale/missing-PID behavior remain in place.

Validation: the new custom-ID direct-agent and tmux-agent regressions failed
before the fix and pass after it. Fifteen identity tests and 26 workspace tests
pass, including an integrated count/switch test that resolves a custom-ID tmux
agent and selects its Sway container. Live preview and the restarted workspace
daemon include both previously omitted agent containers, 86 and 156. The live
bar reports four Codex windows and lists all four workspaces. Local evidence:
`~/.local/state/oldbook/tmux-agent-bar-verification.json`.

Recovery: restore the preceding app_identity.py and restart only
`oldbook-workspaces daemon`. Agent processes and tmux sessions need no restart.
This change covers tmux clients attached to desktop terminal windows; it does not
change the existing exclusion of detached sessions or hidden scratchpad windows
from this window switcher.

The selector and bar tooltip label resolved tmux agents as `Codex (tmux)`
(or `Claude (tmux)`). This suffix is applied only to the session display name
when the resolver supplies a tmux pane; workspace names, agent kinds, counting
and Sway container targets stay unchanged. All 41 identity/workspace checks
pass after the label change.
