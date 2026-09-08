# Base consolidation — 2026-09-08

Evidence for folding the live `oldbook`-named fork of `alpine-oldbook` into
the `mbp-intel` renamed line and merging the result onto `base`.

- `identity-rules-replay.log`: the rules in `alpine/tools/identity_rewrite.py`
  replayed over the rename check-in 468f8ebd2a. All 1002 renamed paths match;
  of 408 rewritten files, the four listed differences are the identity row the
  rename added to FEATURES.md, the PROGRESS entry it appended, and the two
  slips the fold corrects (`Wants=oldbook-desktop-settings.service` in the
  Bazzite session target, and an error message in the Python identifier form).
- `fossil-merge.log`: Fossil's own merge of bf2495e221 into 8905755d8d before
  contents were recomputed (19 textual conflicts, all superseded by the fold).
- `fold-report.json`: what `alpine/tools/fold_live_fork.py` recomputed: 67
  three-way merges, 434 additions with 5 moved to renamed paths, 91 binaries
  from the live side, two hand-resolved conflicts (FEATURES.md, PROGRESS.md)
  and the two slips.
- `unit-tests.log`: the full suite on the merged tree, 947 tests. Three of the
  four failures are recorded as pre-existing on both lines (the desktop-space
  hidden-fullscreen reservation, the Bazzite deployed-helper palette path, and
  the ghost-branding check that expects the never-committed waxen-meridian
  descriptor). The fourth was a stale Bazzite exclusion assertion superseded by
  the live line's whole-tree replay, in which Waybar's notifications module
  still runs the panel-status helper; the assertion was corrected.
- `bazzite-rerun.log`: the Bazzite profile tests after that correction, 17
  tests with only the pre-existing failure.

Syntax over the merged tree: 372 Python, 14 shell, 185 JSON and 6 Lua files
parse and `sway --validate` passes. Outside recorded evidence, the only
`oldbook` tokens left are the branch name, the superseded package row and the
rename's own narrative. Nothing here was run against the live desktop.
