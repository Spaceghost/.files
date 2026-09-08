# STRATA follows workspace nine

STRATA uses workspace 10 so its numeric ordering follows workspaces 1 through
9. The 0 key remains its shortcut: Super+0 opens or focuses the dedicated
review window, and Super+Shift+0 moves the current window to workspace 10.
Workspace 0 is no longer a default overview entry or a reserved STRATA theme.
The overview starts with workspaces 1 through 10, while real additional
workspaces remain visible when present.

The workspace model, launch defaults, Sway assignment, STRATA service and
native workspace strip all identify `10: STRATA`. The service pins the exact
`mbp-intel-strata` app ID to 10, returns it there if moved, and reopens it there
after closure. Background startup and recovery retain the ordinary browser's
focus. Explicit launching remains a serialized focus/reuse operation with
bounded retries when Sway IPC is busy. The private Firefox profile and
loopback Fossil endpoint remain the existing review session's state.

This supersedes the workspace selection in
[the workspace-zero service decision](2026-09-07-strata-workspace-zero-service.md).
Its supervision and session-lifetime behavior still applies.

The existing focused unit tests and native isolated verifier now expect
workspace 10. Evidence, source hashes and the synthetic compositor screenshot
are recorded in [workspace-ten verification](../../../alpine/verification/workspace-ten/README.md).
The native verifier uses private HOME, XDG directories, D-Bus, Sway and HTTP
port, with Foot standing in for the dedicated browser and a private HTTP
fixture standing in for Fossil. It verifies placement, focus and service
lifecycle; live migration evidence is recorded separately in that directory.

Recovery requires restoring the workspace model, launch defaults, overview,
Sway rules and STRATA service together, then restarting the affected desktop
helpers and returning the existing review window to the restored workspace.
Restore the matching archived workspace-strip APK if reverting its labels.
The dedicated browser profile does not need to be recreated.
