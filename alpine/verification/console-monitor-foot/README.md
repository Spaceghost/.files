# Foot system-monitor drop-down

Super+tilde now launches btop in Foot. Super+backtick continues to use the
existing Ghostty console. The shared application identity, geometry and
independent hide/show behavior remain; quitting btop closes its Foot terminal,
and the next toggle starts it again.

Ten native groups passed in private HOME/XDG/SwayFX using the actual US XKB
map, real Foot and btop, and an independent Ghostty console. The q/quit/reopen
check retained the console, observed the old Foot/btop processes exit, and
opened exactly one replacement monitor. The recorded timings include input
and IPC waits and are not a comparative startup benchmark. Screenshots here
show only the synthetic test desktop. No private test processes remained.

The live helper is an existing managed symlink, so no package or binding
change is needed. There was no older Ghostty monitor left to replace.
Recovery: restore oldbook-dropdown from the parent revision; existing shells
remain untouched. A running monitor can be closed and reopened to switch host.
