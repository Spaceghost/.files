# STRATA on workspace zero

STRATA moves from workspace 6 to workspace 0. The desktop session starts
`oldbook-strata --daemon`; Super+0 opens or focuses its dedicated review window.
Super+6 returns to ordinary workspace switching, and Super+Shift+0 moves the
current window to zero. The overview includes zero even before its window maps
and retains access to workspace 10. Workspace names and the native bar helper
recognize `0: STRATA`, including an empty active workspace’s bold name.

Sway assigns exact app ID `oldbook-strata` to zero and suppresses focus during
background mapping. The service adopts an existing review browser and Fossil
server. It returns review windows moved elsewhere to zero and restarts a closed
or failed browser/server with bounded backoff. Explicit launching remains a
serialized focus/reuse operation. Ordinary Firefox is unaffected and retains
workspace 5 as its first-instance default.

One daemon lock belongs to each compositor session. IPC recovery retains its
supervised children; transient connections and failed launches retry with bounded
delays. A pidfd pins the original Sway peer's lifetime, so a killed compositor's
remaining socket cannot keep its service alive. An initially stale socket also
exits without starting children. Session shutdown releases the daemon and its
owned children. Private Firefox
state remains outside Fossil. The Fossil endpoint remains loopback-only at
`127.0.0.1:8766`; the configurable port is used by isolated verification.

The initial live review window was moved intact from workspace 6 to zero.
Final service activation replaced an intermediate supervisor and restarted its
owned browser using the existing profile. The new supervisor, its Fossil
endpoint and the replacement review window on zero all passed live checks.
These observations apply to the workspace-zero candidate recorded in the
verification evidence; subsequent concurrent workspace-number edits are not
covered by that evidence.

Validation and activation evidence are recorded in
[the service verification](../../../alpine/verification/strata-service/README.md).
The native test uses a private compositor, HOME, runtime and D-Bus, synthetic
Foot browser windows and a private loopback Fossil fixture. It does not touch
the live Firefox profile or the host Fossil listener.

Recovery: stop the STRATA daemon, restore this change’s launcher/session entry,
workspace mappings and Sway rules from its parent, then restart the workspace
naming service. Restore the previous bar APK to recover its old named-workspace
mapping. The existing Firefox profile is retained. A real logout/login cycle
is not part of the isolated runtime verification.
