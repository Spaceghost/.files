# Drop-downs come along when the workspace changes

The console and the system monitor were already summonable from any workspace,
but only by pressing the shortcut again: a window left visible stayed on the
workspace that summoned it, and it kept that workspace alive by being the only
window on it. Switching away and back meant pressing the key twice.

Both windows are now sticky while shown. Sway moves a sticky floating container
to the newly focused workspace on the same output, so a visible console or
monitor arrives with no keypress, keeping its position under the bar. Hiding
clears sticky before moving the window to the scratchpad, so a hidden window
follows nothing, and a container in the scratchpad belongs to no workspace and
cannot be dragged out of it. The one-press recall for a window parked on
another workspace by hand is unchanged.

`alpine/tests/verify_ghostty_dropdown.py` was extended and run in a private
headless compositor with separate HOME/XDG paths and a non-activating D-Bus
session. `headless.json` records eight console checks and eight workspace
checks, all passing. Monitor container 6 kept Foot PID 6876 and btop PID 6880
while following switches to workspaces 2 and 10, being hidden, staying put
through a switch to workspace 7 while hidden, and being reshown. The console
followed each switch alongside it and was recalled independently. Placement on
an offset output, keyboard input, quit/reopen and the unbound new-window
shortcut still pass.

Run: `python3 alpine/tests/verify_ghostty_dropdown.py --output-dir /tmp/oldbook-dropdown-check`.

Screenshots are from the private fixture. The test called the production helper
directly against its own compositor; no command was sent to the live session and
no live console or monitor process was touched. The installed helper is a
symlink into this checkout, so the next shortcut press reads the new code
without a compositor reload.
