---
name: commit-by-concern
description: Review the working tree before committing and split it into one commit per concern, setting aside unrelated side-tweaks so they get their own commits. Use before every fossil or git commit, and especially at the end of a long session where incidental fixes piled up alongside the main change.
---

# Commit by concern

A commit should be reviewable on its own terms: a reader sees the subject line,
and every file in that commit is explainable by it. Long sessions break this by
accident. You fix the thing you were asked to fix, and on the way you also
straighten a typo, delete a stray debug print, rename a confusing local, tighten
a test that was bothering you. Swept into one commit under the primary message,
those side-tweaks are invisible: they are not mentioned, nobody reviews them,
and when one of them turns out to be wrong the bisect lands on a commit whose
message describes something else entirely.

The fix is not to stop making small improvements. It is to give each one its own
commit. Run this before every commit, not only when you suspect a mess.

## 1. Read the whole diff before writing any message

Enumerate every changed path and read what actually changed in it. Do not write
the commit message first and then collect files that seem to match — that is how
unrelated changes get swept in, because a file you touched for a second reason
still looks like it belongs.

    fossil status                      # or: git status --short
    fossil diff <path>                 # or: git diff -- <path>

Read the diff of every path you intend to commit. A path you cannot explain is a
path you must not commit yet.

## 2. Sort every changed path into three buckets

**Primary** — the change the task was actually about. This is what the commit
message will describe.

**Incidental (mine)** — real changes you made this session that a reviewer would
not expect to find under the primary subject. Typo and comment fixes, a stray
debug statement removed, an unrelated helper improved, a dependency bumped
because it was in your way, formatting you could not resist. These are worth
keeping. They are not worth hiding.

**Not mine** — edits made by another session, another agent, or the user, sitting
in the same checkout. Never commit these. On this machine several Claude sessions
routinely edit `~/.files` at once, so an unfamiliar modified file is the normal
case, not an anomaly.

Deciding "not mine" is a memory question, not a diff question: did *you* write
this, in this session? If you cannot say yes, leave it alone. An uncommitted file
costs nothing and stays recoverable; a file wrongly swept into your commit lands
in someone else's history and is tedious to unpick.

## 3. Commit each bucket separately, in an order where each stands alone

Give every group an explicit path list so nothing rides along:

    fossil commit -M <message-file> <path> <path> ...
    git commit -- <path> <path> ...           # after: git add -- <paths>

Order them so each commit makes sense at the moment it lands. If the primary
change depends on an incidental refactor, commit the refactor first, so the
primary commit is coherent on its own rather than referring backwards to
something that has not happened yet. Otherwise incidental commits can follow the
primary one; order matters less than independence.

Each incidental commit gets a message describing *itself* — not "also fixed a
typo", but a subject naming what it fixed and a line on why it was worth doing.
A one-line commit with a real message reviews in seconds. The same line buried
in a fifty-line diff reviews never.

## 4. When one file holds two concerns

This is the case worth slowing down for. A single file containing both the
primary change and an unrelated tweak cannot be split by path.

**Prefer not to create it.** When you notice yourself making an unrelated edit
inside a file you are already changing, that is the moment to decide whether it
belongs in this session at all.

**In git**, split it at the hunk level: `git add -p <path>` to stage only the
primary hunks, commit, then stage and commit the rest.

**In fossil**, which has no hunk staging, use a patch file in the scratchpad
rather than editing the file twice in place:

1. Save the current file: `cp <path> $SCRATCH/full`
2. Write the primary-only version to `<path>`
3. Commit that path
4. Restore: `cp $SCRATCH/full <path>`
5. Commit again for the incidental change

**Do not do this to a live-consumed file.** Anything under
`alpine/desktop/.config/` or `alpine/desktop/.local/bin/` is symlinked into HOME
and read by the running desktop. Step 2 briefly changes the user's live system,
and a concurrent session may read or write the file inside that window. For those
files, commit once and name both concerns in the message — an honest combined
commit beats a split that disturbs a desktop somebody is sitting at.

## 5. Verify, then say what you did

After committing, `fossil status` should show your paths gone and everyone
else's still present. Confirm both halves of that: that what you meant to commit
landed, and that you did not sweep up work that was not yours.

Then tell the user what went into each commit. If you made a judgement call —
combining two concerns in a live file, or leaving a change uncommitted because
you could not attribute it — say so plainly rather than letting it pass silently.

## Repository conventions here

`~/.files` is a Fossil repository. Its commit messages use a scoped imperative
subject (`sway:`, `notify:`, `decoration:`, `docs:`) followed by prose that
explains why the change was made, not merely what changed.

Fossil's comment linter rejects the angle brackets in a `Co-Authored-By` email
address, so commits carrying attribution need `--no-verify-comment`. Write the
message to a scratchpad file and pass it with `-M` rather than fighting quoting
on the command line:

    fossil commit --no-verify-comment -M $SCRATCH/msg.txt <path> ...

Adding binary assets needs `fossil add --dotfiles` and, for content Fossil reads
as binary, `--no-warnings`; the repository's `binary-glob` setting already covers
the common extensions.

## Checklist

- [ ] Read the diff of every changed path
- [ ] Sorted each into primary / incidental / not mine
- [ ] Nothing in "not mine" is in any commit
- [ ] Each commit has an explicit path list
- [ ] Each commit's subject explains every file in it
- [ ] Ordered so each commit stands alone
- [ ] Verified with `fossil status` afterwards
- [ ] Told the user what landed in which commit
