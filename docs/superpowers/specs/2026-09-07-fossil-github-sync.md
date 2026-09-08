# Fossil, GitHub, and host replay

The authoritative contributor checkout remains `~/.files`, on Fossil branch
`alpine-oldbook`. Publish that branch to `Spaceghost/.files` without replacing
the existing GitHub branches. The Git translation lives outside the checkout
at `~/.local/share/fossil/files-git-mirror`; Fossil owns its `.mirror_state`.

Use an explicit publisher which incrementally exports and pushes one branch,
without force. Keep Fossil's broad autopush disabled. Failed publication can be
retried even when there are no new Fossil check-ins. Authenticate Git through
the local credential helper; never put tokens in remote URLs or source files.

The user subsequently authorized continuous publication. A user cron job
runs the explicit publisher every minute, sharing its mirror lock with manual
runs. Push only committed `alpine-oldbook` changes; suppress inherited tag
following. Record a successful publication only after verifying GitHub's branch
ID, so failed pushes retry without a new commit. Skip network requests for an
unchanged verified commit. Bound command execution and diagnostic logs, retain
an inspectable status file, preserve unrelated cron jobs, and provide removal.
Cron does not create commits or publish full Fossil database backups.

Other hosts may bootstrap a new Fossil repository from GitHub through Git
fast-export/import. This is a source recovery path, not native Fossil cloning:
project/check-in identities change, and Git excludes unversioned artifacts.
Preserve full repository identity and archived APK/source inputs in a separate
consistent database backup. A publicly distributed copy must be scrubbed;
private backups contain Fossil account credentials and must remain private.

Bazzite reuses an explicit desktop allowlist with Fedora/session overrides,
backup and rollback. Alpine packages, security activation, media-service
ownership and machine-specific display settings are not portable. Applying
user configuration remains explicit; upgrading an image must not overwrite
HOME. Native Bazzite execution cannot be validated on this Alpine host.

Tailscale is presently absent on Alpine. Document installation/authentication
and native Fossil replication over a tailnet; this request does not authorize
silently choosing a tailnet or changing the active firewall.

Validation uses disposable Git/Fossil repositories, export retry/non-fast-forward
checks, source-import file/mode comparison, scrubbed-copy integrity checks,
and profile deployment/rollback. Record publication and runtime limits honestly.
