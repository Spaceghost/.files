# Automatic `.files` sync and live reload

`spaceghost-sync` checks `origin/base` every two minutes. It fast-forwards
incoming commits, pushes commits made on this host, and rebases clean local
commits if another host published first. Alienware and Fedora use a user
systemd timer; Bak uses cron. Installation enables the schedule and immediately
runs the worker; no terminal, confirmation, or login is required afterward.

Committed changes reload existing applications automatically:

- **Neovim:** every reachable Spaceghost instance in the user's runtime directory
  or standard temporary socket directory. SSH and cron recover the runtime
  directory before choosing a socket. Editors with other configurations are
  ignored; buffers, shells, and running jobs stay open.
- **tmux:** running user servers load the checkout's `.tmux.conf`, including
  changes to its helpers. Sessions and panes stay open.
- **Ghostty on Linux:** a running GTK instance receives its D-Bus `reload-config`
  action. The worker never launches a new terminal. Settings that Ghostty cannot
  change at runtime take effect in newly opened terminals.
- **User systemd:** changed units receive `daemon-reload`. Services are not
  restarted automatically.

Each application records its own successfully applied revision. Failed reloads
retry next cycle without blocking other applications. Missing previous Git
objects trigger a reload. Local committed configuration still reloads when the
network is unavailable. Shell startup files apply to new shells; the worker
never injects commands into an existing prompt or interrupts a running command.

For GitHub HTTPS requests, the worker resolves a fresh IPv4 address through the
system resolver and supplies it to Git's libcurl. This handles hosts where the
system resolver works but libcurl's resolver fails, while retaining HTTPS
hostname and certificate verification. No addresses are pinned permanently.

The public repository is the shared source of truth. The worker never stages,
commits, stashes, or discards working-tree edits. Commit a change on any host;
the worker publishes it and the other hosts receive it within a few minutes.
New files must be added to Git before committing. If incoming changes overlap
unfinished edits, or committed changes conflict during a rebase, sync stops
and leaves the local work intact.

Run `~/.bin/spaceghost-sync install` once on each host to enable the schedule.
Repeating installation is safe. Check a host with `~/.bin/spaceghost-sync status`;
its log is `~/.local/state/spaceghost-sync/sync.log`. Run
`~/.bin/spaceghost-sync run` to retry immediately. `~/.bin/spaceghost-reload`
applies pending application reloads without a network request.
