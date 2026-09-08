# Workspace application names and AI sessions

Workspace labels retain their numeric prefix and include the application with
the largest displayed content area: `1: GHOST · ✦ Codex`, for example. Numbers
1–5 retain the existing GHOST, ORBIT, LAB, SIGNAL and LOUNGE themes. A manual
workspace name becomes the base for subsequent labels. Existing names containing
quotes, backslashes, dollar signs or control characters are left untouched because
Sway cannot address them losslessly with this command serializer. The panel shows existing
workspaces; numeric navigation and move shortcuts continue using Sway's
`workspace number` commands.

The service compares tiled and floating content rectangles clipped to their
workspace. Fullscreen content takes precedence. Only the active tab/stack branch
participates; focus breaks equal-area ties but a small focused window cannot
replace a larger application. Inactive workspaces are still named. Scratchpad
windows are excluded. Updates arrive within about one second, including terminal
foreground changes that do not change the Sway window title.

Application IDs supply normal labels. Terminal identity uses owned process
metadata and tmux's current client/window plus the largest displayed pane. Hidden
tmux windows and detached sessions cannot supply a terminal's label. Browser
ChatGPT tabs are recognized only when the browser exposes ChatGPT in its title;
an arbitrary conversation title alone is insufficient. Native Codex and ChatGPT
identities receive a star. Raw conversation or terminal titles are never used as
workspace labels.

The star button counts recognized AI windows. Left click or `Super+i` moves to
the next one. Right click or `Super+Shift+i` opens a session chooser with Codex
terminal and ChatGPT browser launchers. The service never launches an AI process
unless the user selects a launcher.

Supported Codex completion and approval callbacks add content-free desktop
notifications through SwayNC and the existing Caps Lock notification light. The
matching workspace receives `✓` for a recent completion or `!` for an approval
request, and the star badge changes color. These are recent event indicators,
with a five-minute expiry and next-prompt cleanup; they are not inferred current
agent state. See [Codex notification setup](2026-09-07-codex-notifications.md)
for hook trust, startup requirements and exact recovery commands. ChatGPT browser
response completion is not exposed by this integration.

## Lifecycle and recovery

`mbp-intel-session` starts `mbp-intel-workspaces daemon` with its startup lock
closed in the child. A per-runtime flock prevents duplicate services. Private
runtime state contains workspace/app labels and routing IDs, not conversation
content. Stale or malformed panel state falls back to an idle star.

On SIGTERM the service restores original workspace names only when they still
match its last applied names, preserving any external rename. To stop it, read
`$XDG_RUNTIME_DIR/mbp-intel/workspaces/service.lock` and send SIGTERM to that PID.
Remove its `mbp-intel-session` startup block to keep it disabled after reload;
`mbp-intel-workspaces daemon` starts it again. Configuration and helper files are
versioned in Fossil and HOME deployment has a durable rollback journal.

## Verification plan

Run geometry, identity, notification and malformed-state unit tests; validate
Sway configuration and the changed session shell script; deploy into disposable
HOME. Exercise real renaming, resizing, tabs, fullscreen, numeric navigation,
manual names and graceful cleanup in a separate headless Sway session. Finally
verify live names, one service instance, panel rendering and content-free test
notification routing without changing the user's window focus or clearing
existing notifications. Record outcomes in `alpine/verification/` and PROGRESS.

## Sources

- [Waybar 0.15 Sway workspace format](https://github.com/Alexays/Waybar/blob/0.15.0/man/waybar-sway-workspaces.5.scd)
- [Sway IPC protocol](https://github.com/swaywm/sway/blob/master/sway/sway-ipc.7.scd)

Persistent placeholder names are removed because Waybar matches them by exact
name, which would otherwise duplicate renamed numeric workspaces. The panel uses
`{value}` with markup disabled so its native workspace click behavior follows
the actual Sway name. Derived labels exclude command and markup control syntax.
