# Workspace names ready on entry

Direct switch and move commands now create complete labels, including
`4: Signal`, before Sway emits the first creation or focus event. The shared
names use titlecase. Existing custom names still win when switching by number.

The native fixture runs a private Sway compositor with no naming daemon. It
executes the production binding commands and records ordered workspace events
through a subscribed IPC barrier. Synthetic Foot windows provide targets for
move and assignment checks; the screenshots contain no real user windows.

- `native-red/`: the original bindings emit bare `4` at creation and first
  focus; nine assertions fail while custom-name reuse already passes.
- `native/`: all 16 creation, picker, show-desktop return, move, assignment
  and custom-name checks pass with the new labels.
- `native-case-red/`: the added migration check demonstrates Sway's successful
  no-op for a capitalization-only rename (16/17 checks pass).
- `native-case-green/`: all 17 pass after batching the temporary and final
  rename. The populated workspace keeps its ID, fixture window and exact
  Unicode application suffix; no extra workspace remains.

- `native-final/`: all 17 checks pass on the final source after the bounded
  IPC connection retry. The saturated backlog has its own socket regression.

A real private Unix-socket regression reproduces EAGAIN and verifies recovery
when the backlog drains. The final naming daemon is running with a fresh
workspace snapshot; see `naming-service-activation.json`.

The model's earlier failing/passing tests and exact hashes are retained here.
All 99 focused tests pass. Their logs cover workspace naming/placement, the overview, show-desktop
return and STRATA. The Sway configuration parser passes; its log retains the
existing graphics PCI diagnostic.

`activation.json` records the live titlecase bases and preserved workspace
IDs/focus. `workspace-labels-live.png` shows the inspected, cropped live bar.
`binding-activation.json` records all 21 accepted live switch/move
and assignment commands. Its observed labels precede the final case migration.
The activation recovery note records the initial Unicode quoting error and
service restart. Subsequent migration used the production quoting and rename
implementation. The updated native bar package and live module mapping are
recorded in [workspace-titlecase](../workspace-titlecase/README.md).

To repeat the native checks without touching the live desktop:

```sh
python3 alpine/tests/verify_workspace_creation.py \
    --output /tmp/workspace-names-new-run
```

This validates Sway's first emitted label and preservation of existing
workspaces. It does not measure physical key-to-screen latency or physical
display frames. No logout/login cycle was required for activation.
