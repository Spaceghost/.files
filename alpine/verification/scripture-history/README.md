# Hourly Scripture and personal reading history

Scripture keeps complete selected passages, study content, sources, licenses and
provenance in `~/.local/share/oldbook/scripture/history.sqlite3` (or under
`XDG_DATA_HOME`). This is personal append-only data, separate from the disposable
`study.sqlite3` catalog cache. Do not rebuild it, publish it, or commit it.

Every selection has a one-hour deadline. Manual selections display immediately
and reset that deadline. Automatic rotation advances to the next passage in its
collection or the next full study entry; waking after a long absence records one
observed change rather than fabricating missed hours. Identical consecutive
selections and repeated identical additions are deduplicated. Concurrent refresh
processes share the SQLite transaction that checks and advances the deadline.

Conky's Scripture command interval is 3600 seconds. The existing Scripture bar
checks the saved deadline once per minute, so restarting a Conky cache during a
theme/layout change cannot postpone rotation indefinitely. A rendered entry ID
acknowledges actual card output; a busy or failed refresh retries next minute.
A missing Scripture process is revived from its existing config under the same
layout lock, while the disabled flag and other card processes are preserved.
Other cards retain the 60–300-second policy. No new daemon is required.

The Scripture bar's **History** button opens the scrollable reader. Older, Newer
and Latest navigate full entries without changing the desktop selection.
Sources and model/method/date provenance are ordinary reading text; exact stored
metadata is available in the collapsed **Full entry data** panel or JSON export.
Additional notes, research or generated material are appended to the viewed
entry, and unsaved drafts remain associated with that entry during navigation.
**Show this passage on desktop** reselects its preserved snapshot for one hour.
Super+/ remains Bible-only; Super+Shift+/ remains the expanded collection picker.

```sh
oldbook-scripture history
oldbook-scripture history-list --limit 100
oldbook-scripture history-show 12
oldbook-scripture history-show 12 --json > entry-12.json
oldbook-scripture history-add --entry 12 --input note.txt
oldbook-scripture history-add --entry 12 --kind research --input research.txt --metadata sources.json
oldbook-scripture history-add-study STUDY_ID --entry 12
oldbook-scripture history-backup /path/to/new-history-backup.sqlite3
```

`history-add-study` attaches a complete existing curated or locally generated
study record, including its source excerpts and model provenance. It does not
call a model or fetch sources. JSON metadata supplied with `history-add` can keep
additional sources, license, provenance and other entry-specific data unchanged.
The SQLite backup command refuses to overwrite an existing destination.

Verification uses disposable directories and synthetic entries; it does not
call a model or the network. `unit-tests.log` records 80 Scripture tests;
`conky-tests.log` records all 44 required Conky tests. `native-final/` contains
seven real GTK control checks and visually inspected full-height reader and
attribution screenshots. Reproduce native checks with fresh output paths:

```sh
env OLDBOOK_SCRIPTURE_HISTORY_VERIFY_OUTPUT=/tmp/scripture-reader-proof \
  python3 alpine/verification/scripture-history/run-private-gtk.py \
  --binary alpine/tests/verify_scripture_history.py --output /tmp/scripture-gtk-proof
```

`activation.json` records the exact live source hashes and replacement process
identities. `activate.py` backs up private state and both SQLite databases using
SQLite's online backup, verifies integrity, and restarts only the Scripture card
and bar using the old bar's selected desktop environment. The linked command was
already observed by Conky before explicit activation, so the first backup is
accurately recorded as post-initialization rather than a pristine pre-migration
snapshot. No personal SQLite file is included here. A physical one-hour wait was
not performed; deadline behavior is verified using controlled clocks.

To recover application code, restore the reviewed helper/library/config source
revision and restart those same Scripture components. Keep `history.sqlite3` in
place: application rollback must not discard newly recorded history or notes.
If repairing a damaged database is necessary, retain the damaged file and use
the newest consistent private SQLite backup. Restore only needed state/config
files from the backup; do not restore stale process IDs or lock files.
