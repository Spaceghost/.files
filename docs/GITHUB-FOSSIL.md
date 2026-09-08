# Fossil, GitHub and another host

The Fossil repository is the authoritative history. GitHub is a one-way Git
mirror of its `alpine-oldbook` branch and a convenient source-tree recovery
path. It is not a complete Fossil replica.

## Publish the Git mirror

From `~/.files`, update the local translation without using the network:

```sh
alpine/bin/publish-git-mirror --export-only
```

After authenticating Git for `https://github.com/Spaceghost/.files.git`, publish
the configured branch:

```sh
alpine/bin/publish-git-mirror
```

For GitHub CLI authentication on this host, run:

```sh
GH_BROWSER=true gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
alpine/bin/publish-git-mirror
```

Open the URL and enter the device code printed by `gh`. `GH_BROWSER=true`
keeps the CLI polling while you open the browser yourself. Authentication in
an editor's GitHub connector does not supply credentials to native Git.

The helper defaults to the current checkout, the Git mirror at
`${XDG_DATA_HOME:-$HOME/.local/share}/fossil/files-git-mirror`, and branch
`alpine-oldbook`. It runs Fossil's incremental export with `base` as the Git
main branch, disables Fossil autopush, and pushes only
`refs/heads/alpine-oldbook` without force. It then verifies the remote branch
ID. Use `--checkout`, `--mirror`, `--remote`, or `--branch` only when those
locations intentionally differ.

A Fossil branch may be published under a different name with
`--remote-branch`. This is for the case where the remote branch of the same
name has moved on independently and must not be rewritten: a second machine or
another session's line. The push is never forced, so a diverged branch is
rejected rather than overwritten, and the branch beside it fast-forwards:

```sh
alpine/bin/publish-git-mirror --remote-branch alpine-oldbook-live
```

The receipt records the destination as well as the commit, so the same commit
still publishes the first time it is sent under a new name. On 2026-09-08 the
Fossil branch had two open leaves, this desktop's and another session's
renamed line; GitHub's `alpine-oldbook` carries the latter, and this desktop
publishes to `alpine-oldbook-live`, which the other line folds from.

Keep the mirror's untracked `.mirror_state/` directory intact. Fossil uses it
to map prior exports and append only new history. A failed Git push can be
retried with the same command even when no new Fossil check-in exists.

Changes made on GitHub do not flow back into Fossil. Pull requests and GitHub
web edits therefore do not belong in this workflow. Commit in Fossil, export,
then publish.

## Continuous publication

Enable the current user's minute-by-minute cron job from `~/.files`:

```sh
alpine/bin/install-git-mirror-schedule --print
alpine/bin/install-git-mirror-schedule
```

The installer preserves unrelated jobs and saves the previous crontab under
`~/.local/state/oldbook/git-mirror-schedule/`. On Alpine, ensure cron runs now
and after boot:

```sh
doas rc-update add crond default
doas rc-service crond start
```

On another distribution, enable its cron daemon before using this installer.
Authenticate native Git using the commands above on each publishing host.
Prefer one publishing host for a given GitHub branch; a GitHub-imported Fossil
repository has different artifact IDs and is unsuitable as a second publisher
to the original mirror branch.

Every minute, the job exports committed history and checks the exported
`alpine-oldbook` commit. It pushes when that commit differs from the last
successfully verified publication. An unchanged, already-published commit
does not contact GitHub. Authentication errors and offline periods leave the
commit pending for the next minute, including after a reboot. Uncommitted
working-tree edits are never added or committed by this job.

The job and manual publisher share a lock beside the Git mirror. A busy run
is skipped, and each Git/Fossil command has a three-minute timeout that also
terminates its child helpers. Logs rotate at 1 MiB with one previous copy.
Fossil autopush remains disabled; this job performs the explicit branch push.
It does not upload complete Fossil backups or unversioned artifacts.

Check the schedule and the latest result:

```sh
crontab -l
cat ~/.local/state/oldbook/git-mirror/status.json
tail -n 30 ~/.local/state/oldbook/git-mirror/sync.log
```

`status.json` reports `ok`, `busy`, or `error`, the check time, and the verified
commit when available. The scheduler honors `XDG_STATE_HOME` when set in its
environment; cron normally uses the paths above. The last verified remote,
branch and Git commit are recorded locally in the mirror's
`.git/oldbook-published.json`. Manual `publish-git-mirror` always contacts and
verifies GitHub, even when that receipt matches.

To stop automatic publication while preserving other jobs:

```sh
alpine/bin/install-git-mirror-schedule --remove
```

## Recover from GitHub

On a host that has Git, Fossil and Python 3, run the helper from any temporary
copy of the GitHub branch. The first publication above must succeed before
the `alpine-oldbook` branch and helper are available there. If the helper is
not already available:

```sh
temporary="$(mktemp -d)"
git clone --depth 1 --single-branch --branch alpine-oldbook \
  https://github.com/Spaceghost/.files.git "$temporary/files"
"$temporary/files/alpine/bin/bootstrap-fossil-from-github"
```

Remove that temporary directory after the bootstrap succeeds. From an existing
copy of the helper, the command is simply:

```sh
alpine/bin/bootstrap-fossil-from-github
```

The bootstrap defaults to:

- source: `https://github.com/Spaceghost/.files.git`
- branch: `alpine-oldbook`
- repository: `~/.local/share/fossil/files.fossil`
- checkout: `~/.files`

Both destination paths must be absent. The command clones the Git repository
into a temporary mirror, streams `git fast-export --all` into
`fossil import --git`, verifies the requested branch, and opens it. It removes
the partial repository and checkout if any step fails. For an offline copy or
different destination:

```sh
alpine/bin/bootstrap-fossil-from-github \
  --source /media/backup/files.git \
  --repository "$HOME/.local/share/fossil/recovered.fossil" \
  --checkout "$HOME/recovered-files" \
  --branch alpine-oldbook
```

The destination database is created with mode `0600`, and the checkout opens
with Fossil autosync suppressed.

Git import creates a new Fossil project code and new Fossil check-in IDs.
Exported commit messages retain `FossilOrigin-Name` for historical mapping, but
the recovered repository cannot Fossil-sync with the original by artifact ID.
Author attribution may also differ. Treat this as disaster recovery from the
versioned Git tree, not routine two-way synchronization.

Fossil documents marks files for carefully managed incremental Git imports,
but the installed `fossil git import` convenience command is still marked
`TBD`. This setup does not use repeated Git-to-Fossil import. Re-run the
bootstrap only for another new recovery destination.

## Preserve the complete Fossil repository

Git has nowhere to store Fossil wiki, tickets, technotes, forum data, private
artifacts, or unversioned files. This repository's unversioned area contains
the exact APKs, source archives and verification evidence used for restoration,
so a GitHub mirror alone cannot reproduce the full archive.

Create a consistent private database backup, including unversioned content:

```sh
alpine/bin/backup-repository --output /secure/backup/files.fossil
```

The private copy contains Fossil account credentials and must not be published.
To prepare a separate credential- and private-metadata-scrubbed copy for review:

```sh
alpine/bin/backup-repository \
  --output /secure/staging/files-public.fossil \
  --public
```

The helper writes a SHA-256 metadata file beside the database. `--public`
scrubs only the new copy, vacuums it, and checks that Fossil password fields are
empty. Review stored versioned and unversioned content before choosing any
publication destination. No full database backup is currently published by
this procedure.

For identity-preserving replication to another machine, expose the native
Fossil repository through a trusted SSH or Fossil HTTP endpoint and clone it:

```sh
fossil clone -u --private \
  ssh://USER@TAILSCALE-HOST//absolute/path/to/files.fossil \
  "$HOME/.local/share/fossil/files.fossil"
mkdir "$HOME/.files"
cd "$HOME/.files"
fossil open "$HOME/.local/share/fossil/files.fossil" alpine-oldbook
```

Omit `--private` when private branches should stay on the source host. The
`-u` option is required for unversioned content. Later exchanges must use
`fossil sync -u` rather than `push -u` or `pull -u`; an HTTP Fossil account
also needs the unversioned-write (`y`) capability. Use tailnet ACLs to restrict
the endpoint to the intended machines.

## Tailscale status and setup

Tailscale is not installed or configured on the Alpine host as of
2026-09-07. Alpine edge/community provides the client and a separate OpenRC
service package:

```sh
doas apk add tailscale tailscale-openrc
doas rc-update add tailscale default
doas rc-service tailscale start
doas tailscale up
```

The final command prints a browser URL for the user to authenticate the host to
their tailnet. Do not store authentication keys in this repository.

Bazzite includes a native setup recipe, so package layering is unnecessary:

```sh
ujust tailscale enable
sudo tailscale up
```

Authenticate both hosts into the same tailnet before using the native Fossil
clone command above.

References: [Fossil's GitHub mirror guide](https://www.fossil-scm.org/home/doc/trunk/www/mirrortogithub.md),
[Git import/export](https://fossil-scm.org/home/doc/revamp-home-page/www/inout.wiki),
[unversioned content](https://fossil-scm.org/home/doc/trunk/www/unvers.wiki),
[Tailscale for Linux](https://tailscale.com/docs/install/linux), and
[Bazzite's Tailscale recipe](https://github.com/ublue-os/bazzite/blob/main/system_files/desktop/shared/usr/share/ublue-os/just/80-bazzite.just).
