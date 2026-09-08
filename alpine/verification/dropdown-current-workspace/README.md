# Dropdown follows the current workspace

The monitor had no workspace assignment, but the toggle helper hid any existing visible monitor and returned. When it had been left on another workspace, the first shortcut therefore hid it there instead of bringing it to the current workspace. The native red run reproduced this on workspace 2: the monitor ended in `__i3_scratch` after one toggle.

The helper now hides a dropdown when it is on the focused workspace, and immediately recalls it when it is on another workspace. It keeps the same Foot and btop processes and computes placement from the focused output/workspace. The console uses the same independent toggle behavior. No binding or workspace-assignment changes were needed. Only Strata–Fossil stays anchored on workspace 10, selected with the 0 key.

The extended existing `alpine/tests/verify_ghostty_dropdown.py` passed all eight previous console checks and four workspace checks in a private headless compositor with separate HOME/XDG paths and a non-activating D-Bus session. Monitor container 6, Foot PID 9440 and btop PID 9445 remained the same while being recalled onto workspaces 2 and 10 and hidden/shown on each. Console recall kept its shell and left the monitor hidden. Console keyboard input, offset geometry, quit/reopen and the unbound new-window shortcut still passed. Both private monitor processes exited during fixture cleanup.

Run: `python3 alpine/tests/verify_ghostty_dropdown.py --output-dir /tmp/oldbook-dropdown-check`.

`native-red.log` preserves the reproduced failure; `native-green.json` records the passing checks and process identities. Screenshots are from the private fixture. The test called the production helper directly; the unchanged grave/asciitilde binding had already been verified with physical US-keymap events in the earlier console/monitor verification. No live desktop commands or monitor/console process changes were made for this verification. The installed helper is a symlink to the edited checkout, so subsequent user shortcuts read the corrected code without a compositor reload.
