# Contextual shortcuts on a Super hold

The user approved this behavior on 2026-09-07: holding either Super key alone
for 500 ms opens a scrollable shortcut overlay. The focused application's
shortcuts come first, Sway second, and relevant tmux, terminal and system
controls follow. Releasing Super or pressing another key dismisses the overlay
immediately, without taking keyboard focus from the application. A chord
cancels that hold until Super is released; it must never produce a delayed flash.

## Design

A per-session Python service reads Linux input events without grabbing devices,
recording keystrokes, or changing permissions. Existing input-group access is
sufficient on this machine. It tracks pressed keys across keyboards, tolerates
hotplug and resynchronizes after dropped events. It suppresses display outside
the active graphical session and during locking. GTK3 and GtkLayerShell provide
a scrollable overlay on the focused output with no keyboard interactivity.
Existing installed libraries suffice; no package change is planned.

Sway IPC supplies the focused view, current binding mode and loaded main
configuration. Included files must also be traversed, with variables, globs,
relative paths and bounded recursion. Sway does not retain their contents in its
IPC response, so these files are read from disk and the coverage label makes
that distinction explicit. Reload Sway after editing includes to align the list
with the compositor. Bindings must respect modes, unbinds and overrides.
Known commands receive readable labels; unknown commands are displayed
literally and never executed. Inactive-mode bindings are not represented as active.

Application profiles supply documented baseline shortcuts, labeled as partial.
Terminal context uses foreground process names and, when applicable, the active
tmux pane, never the largest pane. Live tmux queries supply the effective prefix
and bindings. Unknown apps explicitly show unavailable app coverage and retain
the Sway layer. Extra profiles can be supplied locally. No universal or complete
in-app discovery is claimed; editor modes and website-specific keys require
future app integration. Sources never inspect command arguments, buffer contents,
passwords or terminal scrollback.

The service starts from a new `sway/local.d/shortcuts.conf` snippet, uses a
per-Sway-socket lifetime lock, and exits on compositor shutdown. Reloading Sway
does not duplicate the daemon. `--dump` inspects contextual data and `--preview`
opens a short-lived overlay for layout checks without input monitoring.
The new files deploy through the existing recoverable HOME deployer.

## Verification and recovery

Unit tests cover hold thresholds, release, chords before/after the threshold,
repeat events, multiple keyboards, disconnect and dropped-event recovery;
shortcut-provider tests cover focus, modes, variables, overrides and unknown apps.
An isolated Sway session checks overlay visibility, focus preservation, scrolling,
fullscreen, service uniqueness and shutdown. Preserve a screenshot and machine
readable runtime evidence. Run the complete Alpine unittest suite, Sway validation
and disposable HOME deployment before enabling the service in the live session.

Stop the daemon with its recorded PID and remove/disable the local startup
snippet to disable the feature. The deployment journal restores prior files.
Record any unverified physical-key or reboot checks in `alpine/PROGRESS.md`.
