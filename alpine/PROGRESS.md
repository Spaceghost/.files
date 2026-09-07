# Oldbook progress

Plan: `docs/superpowers/plans/2026-09-07-oldbook.md`.

- Execution recovered by installing Codex 0.153.4's separate musl code host.
- Baseline world/repositories saved outside repository before package changes.
- GitHub history imported: 89 Fossil check-ins; `alpine-oldbook` branch created.
- Repository AGENTS.md preserved. HTTPS APK repositories enabled and refreshed.
- Desktop and build dependencies installing; networking remains unchanged.
- OpenSnitch absent in configured package indexes: source build required.
- Radio startup clarification pending; no claim of RF silence or security yet.

Ruling: Use Fossil equivalents for Git workflow steps because user explicitly
requested Fossil. Cost: Git-specific automation from Superpowers is inapplicable.
Ruling: Carry forward the user's authorization and settled purple/rebuild design
instead of reopening design approval. Cost: reversible styling may need revision.

| Unit | Own consistency | Shared interface |
| --- | --- | --- |
| Desktop | HOME overlay, 2x display; stock Sway parser first | deploy-home installs overlay and wallpaper path |
| Rebuild | archive full installed closure, retain exact artifacts | package manifest contains all desktop/security dependencies |
| Security | preserve live connection while staging, test before activation | UI helper names coordinated with desktop; root-owned policy |
| Review | require runtime and restore evidence | no full-release tag before all units verified |
