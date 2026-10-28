# Automatic `.files` sync

`spaceghost-sync` checks `origin/base` every two minutes. It fast-forwards
incoming commits, pushes commits made on this host, and rebases clean local
commits if another host published first. Neovim reloads when its config changes.
Alienware and Fedora use a user systemd timer; bak uses cron. Run
`~/.bin/spaceghost-sync install` once on each host to enable the schedule.

The public repository is the shared source of truth. The worker never stages,
commits, stashes, or discards working-tree edits. Commit a change on any host;
the worker publishes it and the other hosts receive it within a few minutes.
New files must be added to Git before committing. If incoming changes overlap
unfinished edits, or committed changes conflict during a rebase, sync stops
and leaves the local work intact.

Check a host with `~/.bin/spaceghost-sync status`. The log is at
`~/.local/state/spaceghost-sync/sync.log`. Run `~/.bin/spaceghost-sync run`
to retry immediately. Running `~/.bin/spaceghost-sync install` again is safe.
