# Workspace title recovery — 2026-09-07

The live workspace records had incorporated repeated application suffixes into
both original and base names. Waybar displayed those actual Sway names, filling
the bar and crowding out status modules.

The naming model now recovers the managed GHOST/ORBIT/LAB/SIGNAL/LOUNGE/STRATA
prefix before appending the current application. This repairs polluted records
and recovers when generated names outlive their saved state. Other custom base
names retain their existing handling.

Validation: 26 workspace tests passed, including missing-state and polluted-base
regressions. Restarted only the live workspace naming daemon; inspected the
before/after bar captures. Live names became `1: GHOST · oldbook-dropdown`,
`2: ORBIT · ✦ Codex`, and `6: STRATA · Fossil`.

Recovery: restore workspace_model.py from the parent revision and restart
oldbook-workspaces daemon. No Waybar style or ghost changes were needed.
