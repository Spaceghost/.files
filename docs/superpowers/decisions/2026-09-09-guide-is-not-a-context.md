# The shortcut guide is not somewhere you are

Superhold described whatever window Sway reported as focused, and its own
window is a window. The persistent guide is focusable so its rows can be
clicked, so a second after it opened — the controller re-snapshots every second
while visible — the guide replaced the shortcuts being read with its own, and
redrew to do it. Clicking into it did the same. The caption strip did the
matching thing from the other side: it attached itself to the guide, naming the
guide instead of the window the guide was describing, and taking the caption
off that window for as long as the guide was up.

Both are now excluded. The provider remembers the window it was opened over and
looks that window up again in the current tree on each refresh, so its identity
stays current while the guide holds focus. The hold is released the moment
focus lands on anything that is not the guide, and a remembered window that has
since closed is dropped rather than described. Because the refreshed snapshot
is then identical to the displayed one, the controller's existing equality
check means nothing redraws at all, which is what makes it smooth rather than
merely correct.

The caption side reuses the existing mechanism: `superhold` and
`org.superhold.Settings` join `IGNORED_CAPTION_APPS` alongside the drop-downs
and the firewall prompt. Identity is matched across app_id, class and instance
and casefolded, so the settings window is caught however it presents itself,
while `superhold-notes` and similar names still get a caption.

The retention rule is shared by all three shortcut-guide implementations. The
running GTK guide re-resolves the remembered window by container id; the
portable Qt project and the legacy overlay retain the window record itself,
which is enough for their paths and avoids a tree lookup the X11 backend cannot
do.

Reversal: drop `OWN_WINDOW_IDS` and the retention helper from the three
providers and remove the two names from `IGNORED_CAPTION_APPS`. Checks:
`projects/superhold-guide/tests/test_shortcut_sources.py` and
`alpine/tests/test_decoration_placement.py`.

## Which tree runs, and why that mattered here

The first version of the section-order work went into `projects/superhold`,
which is not what runs on this machine. `projects/README.md` now states plainly
which of the three Superhold directories the keyboard reaches, that
`~/.local/bin/superhold` is an installed hash-verified copy rather than a
symlink into the checkout, and what has to happen for a source edit to take
effect. `projects/hold-to-help/README.md` previously sent readers to the wrong
tree for new development and no longer does.

Installing by hand into that prefix also broke `~/.local/bin/superhold-rollback`:
`switch.py` verifies the digest of every preserved file and refuses to run when
one has changed. The digests have been re-recorded, the rollback check is clean
again, and `alpine/packages/superhold-guide/manifest.json` now carries a
`local_patch` block naming the changed files and where the previous installed
modules are kept, so the packaging record no longer implies the install matches
the packaged source.
