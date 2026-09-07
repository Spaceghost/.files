# STRATA and compact workspace defaults

Super+6 opens or focuses one dedicated Firefox profile running the local Fossil
review UI at http://127.0.0.1:8766/timeline?r=alpine-oldbook&y=ci.
The workspace naming service retains 6: STRATA and labels its browser Fossil.
The launcher serializes concurrent calls, reuses its review window, starts one
loopback-only Fossil UI server, and stops that server when the compositor socket
is removed. The private Firefox profile remains outside the repository.

## Default placement

Sway IPC handles placement; no Devilspie process is needed. The first recognized
instance is designated: Codex → 1 GHOST, Pithos → 2 ORBIT, Claude → 3 LAB,
btop → 4 SIGNAL, Firefox → 5 LOUNGE, and Fossil → 6 STRATA. Existing windows
are adopted in place on initial enablement. Designated windows are moved only
once; later manual moves and additional instances are preserved. Closing a
primary window does not pull an already open extra window into its place.
Placement state survives service restart within the same compositor session.

## Artwork and spacing

Superseded by the user's request for one desktop image across all workspaces:
`workspace_rotations` is now empty. Selection, pause and rotation use the shared
global state; existing per-workspace files remain inactive for recovery. The
initial shared painting is the Space Ghost Yosemite landscape. Default app
placement above remains active. The following records the earlier arrangement.

Workspaces 1–6 retain independent artwork, pause flags, and rotation deadlines
under ~/.local/state/oldbook/wallpaper/workspaces/. Workspace events restore
the selected image immediately. Automatic rotation avoids other workspaces'
current selections when enough images exist. Explicit image selection may
intentionally choose the same image. These six rotations use the entire gallery:
the active-theme subset currently has only one image, while the full gallery
has nine. Other workspaces share the prior global image without automatic
rotation. Existing gallery controls act on the focused workspace.

The bar is 32 logical pixels tall, flush to the top, with 4-pixel side margins,
10-pixel base text and smaller lower corner rounding. Sway inner gaps are 3
and outer gaps 1, producing measured 4-pixel edges and 4 pixels below the bar.
Title text is 9pt with 8×1 padding; Foot fallback decorations are 18px.
Foot transparency was applied live with the existing safe terminal-theme helper.
Concurrent finer Foot opacity/padding adjustments were retained.

## Verification and recovery

- Live screenshots and measured workspace geometry: alpine/verification/strata/.
- All six workspace artwork IDs were distinct after live switching.
- Two concurrent STRATA launches left exactly one review window.
- Loopback listener confirmed at 127.0.0.1:8766; branch timeline rendered.
- Sway and Foot parser validation and disposable HOME deployment passed.
- Focused placement, naming, wallpaper, artwork, identity and terminal-theme
  tests passed. A 197-test full-suite run had one unrelated 4-second session
  startup timeout; that test passed separately in 1.94 seconds.
- Reboot persistence has not been exercised. A fresh browser profile's first
  startup may take longer on a heavily loaded machine; failures are logged
  under ~/.local/state/oldbook/strata.log.

To undo placement, remove the placement callback in oldbook-workspaces and
restart that daemon; no manual window moves need reversing. Remove
workspace_rotations from gallery.json and restart oldbook-wallpaper to restore
global rotation. Restore the ordinary Super+6 binding to stop launching STRATA;
close its browser and terminate its --serve helper to stop the local UI.
The settings and scripts can also be restored from the preceding Fossil check-in.
Do not commit or remove the private Firefox profile during configuration rollback.
