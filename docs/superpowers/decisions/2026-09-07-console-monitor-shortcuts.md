# Separate console and system monitor shortcuts

Super+backtick keeps the persistent Ghostty console. Super+tilde (Super+Shift+
backtick on the MacBook's US layout) toggles a separate Foot window running
the installed, themed btop system monitor. Each window retains its process when
hidden, has its own application identity and launch lock, and uses the existing
drop-down geometry on the focused output.

Use the existing `oldbook-dropdown` helper with an optional `monitor` profile.
Keep no-argument callers and the console's application identity unchanged so
the running shell remains usable. The legacy Foot scratchpad rule is retained.
The shortcut guide describes the two actions separately.

The host has btop rather than its Python predecessor bpytop. No package change
is needed. Reversal: restore the previous helper and `dropdown.conf`, then
reload Sway. An existing monitor can be closed without affecting the console.

The console keeps Ghostty; the monitor uses Foot so repeated launches after
quitting btop use the preferred lightweight terminal. The monitor inherits the
existing Foot theme and font.

Initial verification is under `alpine/verification/console-monitor/`; the Foot
follow-up, including quit/reopen, is under `alpine/verification/console-monitor-foot/`.
