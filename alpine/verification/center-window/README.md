# Center and raise verification — 2026-09-07

The [native result](evidence.json) records nine passing checks with the
production helper, binding fragment, verifier and pointer fixture hashes.
Super+C and Super+Shift+C both center and raise the focused window.
Reload moves to Super+Ctrl+Shift+C in the main Sway configuration.

The [before screenshot](before.png) shows the purple target focused below an
overlapping control. A virtual pointer gives it focus without raising it.
The [centered screenshot](centered-raised.png) shows the same 600×400 window
centered and above the unchanged control. Native Sway IPC also verifies its
position, focus and final position in the floating stack. Both shortcuts pass.

The remaining checks verify that a single tiled window becomes floating at
90% of usable workspace size ([screenshot](tiled-to-floating.png)), fullscreen
exits while restoring the previous useful floating size, oversized windows
fit the usable area, and centering works on an output at a nonzero position
([screenshot](offset-output.png)). Repetition preserves geometry and the
existing window process; an empty workspace produces no new window.

The fixture reserves 40 pixels at the top of a 1440×900 private output. The
center of its usable area is (720, 470), rather than the full output center.
The production helper uses Sway's `move position center` after size changes,
so the compositor uses its constrained pending size and workspace area in one
transaction. Explicit criteria `focus` raises an already-focused floating
window in the installed SwayFX source.

Run from the repository root with a new output directory:

```sh
python3 alpine/tests/verify_center_window.py --output /tmp/oldbook-center-new
```

Required tools are Python 3, SwayFX, Foot, wtype, grim, a C compiler,
wayland-scanner, pkg-config and Wayland client development headers. The
verifier builds the existing virtual-pointer fixture in a temporary directory.
Keyboard input uses wtype with explicit Mod4 and Shift modifiers. HOME and
all XDG directories are private; the session bus address points to a
nonexistent private socket. Only that compositor and its fixture processes
receive commands. No live session settings or windows changed during these
checks.

[Runtime logs](runtime.log) retain native warnings and shutdown messages.
[Prior fixture evidence](prior-fixtures/) preserves early attempts that found
the cursor-command limitation and initial Foot mapping races. The final
fixture creates its initial windows as floating and waits for their requested
geometry before testing behavior. Tiled conversion is exercised after mapping.
Those earlier runs are diagnostic records; the passing result above records
the final source hashes.

[Activation](activation.json) records successful targeted IPC replacement of
the three shortcuts, unchanged focus and geometry for existing windows, and
one current source definition per shortcut. Only the new helper and binding
fragment were installed through [scoped deployment](deployment.json), whose
[durable journal](deployment-journal.json) records both links. No actual user
window was centered and the desktop configuration was not reloaded.

The [full SwayFX configuration validation](config-validation.json) passed with
no parser errors or overwritten bindings. The [shortcut-source result](shortcut-tests.json)
and [test log](shortcut-tests.log) record all 22 existing tests passing after
the new helper label was added. The Python helper introduces no changed shell
script requiring ShellCheck.
