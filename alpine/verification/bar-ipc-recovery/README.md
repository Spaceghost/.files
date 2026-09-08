# Bar helper recovery

Both workspace naming/AI status and fullscreen bar styling had stopped after
Sway IPC timeouts. The workspace snapshot had `updated_at=0`, leaving no live
agent/window state until another session startup. The helpers now retain their
single-instance ownership and reconnect on a fresh stream after transient
connection, snapshot or event-frame failures. They wait before retrying and exit
when the compositor socket disappears or refuses connections.

Three subprocess tests use real private Unix sockets with deliberately truncated
IPC frames: workspace subscription recovery, workspace snapshot recovery while
preserving a custom name, and fullscreen-style snapshot recovery. All three pass,
along with all 38 workspace tests. The style fixture suppresses only host Waybar
signals; no real desktop state is read or changed by the fault tests.

Live helper PIDs 10225/10227 were started after these edits by session startup;
root verified fresh snapshots for four workspaces and three AI windows. Waybar
PID 26778 stayed running. The initial ACPI wait sample was transient; subsequent
samples showed busy event processing. Separate read-only observations confirmed
clock and workspace updates and a stream of animated terminal-title events.

Recovery: restore the two helper scripts and restart only their processes.
Private pre-recovery workspace data is retained under
`~/.local/state/oldbook/bar-ipc-recovery/`; personal state is not committed here.
