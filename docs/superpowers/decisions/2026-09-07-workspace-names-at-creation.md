# Workspace names are ready at creation

Switching to an absent workspace previously asked Sway to create a bare number,
then waited for the application naming daemon to rename it. That exposed a
visible `4` → `4: SIGNAL` transition.

The direct switch and move bindings now use Sway's numbered named target,
for example `workspace number "4: Signal"`. The number reuses an existing
workspace, including a custom name; the complete label names a new workspace
before its first creation or focus event. No helper process is needed in the
keyboard switching path. The overview, show-desktop return, first application
placement and STRATA moves use the same names when creating a destination.

The shared names are Ghost, Orbit, Lab, Signal, Lounge and Strata. Existing
custom names and process suffixes retain their behavior. The name model migrates
exact old uppercase defaults and saved numeric originals to titlecase, so a
graceful daemon restart retains the full base name. Sway treats names without
case and otherwise ignores a capitalization-only rename; the helper performs
the temporary and final rename in one IPC command while retaining the same
workspace and windows. The native bar recognizes
both titlecase and legacy defaults, preserving bold active names and the
existing inactive number/name distinction.

Workspace numbering remains as configured: STRATA is on ten, reached by the
zero key. No names are invented for the ordinary workspaces six through nine.

Verification is recorded in
[workspace-ready](../../../alpine/verification/workspace-ready/README.md).
The native regression captures Sway creation/focus events with no naming
daemon running; it also verifies reuse of an existing custom-named workspace.
The original configuration emits bare `4` events; the updated configuration
emits `4: Signal` from the first event. Screenshots contain only synthetic
windows in a private compositor.

Recovery: restore these bindings and naming helpers together, restart the
workspace naming service, and restore the previous Waybar helper APK if its
name recognition must also be reverted. The user profile, theme, wallpaper
and window placement are not reset.
