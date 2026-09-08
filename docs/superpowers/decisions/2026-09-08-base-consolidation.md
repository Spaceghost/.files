# Consolidate alpine-oldbook onto the default branch and publish it

The user asked for everything to be committed on the master branch and pushed
to the GitHub mirror. Two facts shape how that is done.

The repository has no branch called `master`. GitHub's default branch (its
`HEAD`) is `base`, which Fossil imported as the `base` branch and labelled
`trunk`; `alpine-oldbook` was created from that branch's leaf. "Master" is
therefore read as `base`, on both sides. Renaming it later is a GitHub branch
rename, not a history change.

`alpine-oldbook` had two open leaves: the `mbp-intel` identity rename and the
live checkout's deliberate fork, which keeps the running desktop's `oldbook`
names until the authorized migration. "Everything" includes both, so the live
fork is folded into the renamed line rather than left dangling. The fold does
not use Fossil's textual merge for the files the live side touched. Instead
the identity rules of the rename were reconstructed in
`alpine/tools/identity_rewrite.py` and replayed over every file the rename
check-in rewrote or moved: all 1002 renamed paths and 404 of 408 rewritten
files match byte for byte. The four remaining differences are the identity row
the rename added to FEATURES.md, the PROGRESS entry it appended, and two slips
in the rename itself, corrected here: the Bazzite session target still wanted
`oldbook-desktop-settings.service` although that unit was renamed, and one
error message took the Python identifier form of a helper name. With those
rules, each live-touched file is a three-way merge whose pivot and live sides
are rewritten first, so only genuine changes remain; evidence paths are copied
verbatim, binaries take the live version, and live additions under old names
are moved. `alpine/tools/fold_live_fork.py` performs this and is the procedure
for folding later commits from the live checkout until the migration lands.

GitHub's `base` had moved beyond Fossil's leaf by one commit made directly with
Git (32b7cd88, a cloud-init host profile and a one-line `.bin/👻` change). That
commit is imported into Fossil's `base` first, so Fossil stays authoritative and
its `base` remains a superset of GitHub's before the merge.

Fossil's Git export assigns different commit IDs from GitHub's originals, so an
exported `base` can never fast-forward the real GitHub branch, and the existing
policy is not to replace GitHub branches. The default branch is therefore
published with one Git merge commit whose first parent is GitHub's current
`base` head and whose second parent is the exported Fossil `base` merge, with
the exported tree as its content. That is a fast-forward for GitHub, rewrites
nothing, and records the Fossil lineage. `docs/GITHUB-FOSSIL.md` documents the
repeatable steps; the minute-by-minute job still publishes only
`alpine-oldbook`.

Consequences kept deliberately: the live `~/.files` checkout stays on its
`oldbook`-named fork and is no longer a leaf, so commits from it need
`fossil commit --allow-fork <paths>` (or a private checkout of the tip) and a
fold afterwards. The running machine is unchanged; the migration described in
`2026-09-08-mbp-intel-rename.md` is still pending and still needs the user's
authorization. Backup copies named `*-original*` that the live line committed
are carried over untouched rather than judged here.
