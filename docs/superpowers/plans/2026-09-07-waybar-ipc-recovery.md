# Waybar workspace connection recovery

> **For agentic workers:** Execute the package and native regression tasks in
> parallel, then review and activate the tested package. Follow the repository's
> Superpowers debugging and verification workflow.

**Goal:** Keep active/inactive workspace labels updating after Sway disconnects
Waybar's event subscription.

**Architecture:** Backport upstream Waybar's event reconnection to the installed
0.15.0 package. Preserve the existing modules, CFFI artwork widget, theme and
workspace typography. Test a forced event disconnect against a private native
desktop before installing the signed APK.

**Tech stack:** Alpine APK/abuild, Waybar C++, Sway IPC, Python native verification.

**Observed failure:** The live workspace event socket had no peer while its
command socket and GTK clock remained live. A scoped restart restored the
highlight and current labels, but the event socket disconnected again within
two minutes. Restarting is therefore insufficient. Upstream commit
`b0b46ec039199d99c36a0d6637e13e292d66fbdc` addresses this failure.

## Constraints

- Work on Fossil `alpine-oldbook`; preserve unrelated pending changes.
- Keep APK repositories on HTTPS with testing tagged.
- Archive exact signed APKs, source inputs and hashes; never expose signing keys.
- Keep tests on a private compositor and bus. Restart only the live session's
  Waybar after verification; retain its environment and session lock.

## Package and regression

- [x] Create `alpine/tests/verify_waybar_ipc_recovery.py`: interpose a private
  Sway IPC proxy, close only the workspace subscription, and assert that the
  real rendered workspace focus and names catch up after resubscription.
- [x] Run against `/usr/bin/waybar` and retain the failing result, bounded CPU
  observation and synthetic screenshot.
- [x] Add `alpine/packages/waybar/` with the Alpine 0.15.0 recipe, pinned sources,
  upstream reconnect backport, any required prerequisites, and build guidance.
- [ ] Build a signed APK in an isolated build directory. Test the extracted
  binary with the same native regression; verify fullscreen/hover and the CFFI
  workspace attributes still work. Review the patch's teardown and retry paths.

## Activation and reproducibility

- [ ] Archive the signed APK and source inputs in Fossil's content-addressed
  artifact storage; export and check their hashes. Preserve the previous APK.
- [ ] Simulate and install only the reviewed local package, then restart only
  the current Waybar process and confirm live active/inactive states remain
  current beyond the previous recurrence window.
- [ ] Update the exact installed package lock and record verification and
  recovery instructions under `alpine/verification/waybar-ipc-recovery/`.
- [ ] Record unfinished checks in `alpine/PROGRESS.md`, review exact paths and
  commit only this repair with Fossil. Do not publish remotely.
