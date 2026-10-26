# Rebuild the Oldbook workstation

This is the authoritative disaster-recovery procedure for recreating the
machine. Do not begin with the public Git mirror unless the private recovery
release is unavailable: Git contains the readable source tree, but not the
complete Fossil UV store, private state, session history, or uncommitted work.

The verified snapshot described here is:

- private release: `Spaceghost/oldbook-recovery`, tag
  `catbed-2026-10-26-36cea2db`;
- Fossil branch/check-in: `alpine-oldbook` / `36cea2db`;
- public mirror branch: `Spaceghost/.files:alpine-oldbook-live`;
- package lock: `alpine/packages/locks/321d9e0702cf3368824f.json`;
- package closure: 1,186 signature- and identity-verified APKs;
- Fossil UV entries: 1,377.

## What you need

1. A bootable Alpine edge x86_64 installation with working networking.
2. A normal user named `jack` with UID 1000 and `doas` access. Several
   machine-specific services intentionally record that identity.
3. Access to the private GitHub repository `Spaceghost/oldbook-recovery`.
4. Access to `bak:/home/jack/recovery/catbed/2026-10-26/`. That directory holds
   the SSH/age decryption identity and machine-identity archives. Its two
   checksum manifests were verified on `bak` when the snapshot was made.

Install only the bootstrap tools on the fresh Alpine system:

```sh
doas apk add age fossil github-cli python3 zstd
```

Partitioning, disk encryption, firmware, a bootloader, the base user, and an
initial network connection must already work. Do not transplant old Tailscale,
SSH host, or Wi-Fi identities merely to obtain that first connection.

## 1. Recover the decryption identity

From a machine already authorized to reach `bak`, copy and verify the small
identity archives:

```sh
mkdir -m 700 recovery-identity
scp 'bak:/home/jack/recovery/catbed/2026-10-26/user-identity.tar*' recovery-identity/
scp 'bak:/home/jack/recovery/catbed/2026-10-26/root-machine-identity.tar*' recovery-identity/
(cd recovery-identity && sha256sum -c user-identity.tar.sha256)
(cd recovery-identity && sha256sum -c root-machine-identity.tar.sha256)
mkdir -m 700 recovery-identity/user
tar -xf recovery-identity/user-identity.tar -C recovery-identity/user
chmod 600 recovery-identity/user/.ssh/id_ed25519
```

Keep this directory private. The root archive contains host keys, Wi-Fi state,
and a Tailscale node identity. It is evidence for selective restoration, not a
file to extract blindly over a running replacement system. Cloning a live
Tailscale identity can conflict with the original machine.

## 2. Download and verify the private release

Authenticate with GitHub using a fresh login, then download the release:

```sh
gh auth login --hostname github.com --git-protocol https --web
mkdir -p recovery-assets
gh release download catbed-2026-10-26-36cea2db \
  --repo Spaceghost/oldbook-recovery \
  --dir recovery-assets
(cd recovery-assets && sha256sum -c SHA256SUMS)
```

`SHA256SUMS` uses portable basenames. Do not decrypt or extract an asset whose
checksum fails. GitHub's release digests were also checked against these local
hashes when the snapshot was published.

## 3. Reassemble the authoritative Fossil database

The definitive database is encrypted and split because the encrypted stream is
larger than GitHub's per-asset limit:

```sh
cd recovery-assets
cat files-final-36cea2db.fossil.zst.age.part-aa \
    files-final-36cea2db.fossil.zst.age.part-ab \
    > files-final-36cea2db.fossil.zst.age
sha256sum -c files-final-36cea2db.fossil.zst.age.sha256
age --decrypt \
  --identity ../recovery-identity/user/.ssh/id_ed25519 \
  --output files-final-36cea2db.fossil.zst \
  files-final-36cea2db.fossil.zst.age
zstd --decompress files-final-36cea2db.fossil.zst \
  --output files.fossil
sha256sum files.fossil
python3 - <<'PY'
import hashlib, json
from pathlib import Path
meta = json.loads(Path('files-final-36cea2db.fossil.json').read_text())
actual = hashlib.file_digest(Path('files.fossil').open('rb'), 'sha256').hexdigest()
assert actual == meta['sha256'], (actual, meta['sha256'])
print('verified Fossil database', actual)
PY
fossil test-integrity files.fossil
cd ..
```

The JSON metadata must report `sqlite_integrity: ok`, check-in `36cea2db`, and
1,377 unversioned entries. The older `files-private-postcommit.*` database and
`after-171f1b7c-to-ec7362b0.bundle` are retained only as fallback history; do
not combine them with the definitive `files-final-*` database.

## 4. Open the checkout

The destination database and checkout must not already exist:

```sh
install -d -m 700 "$HOME/.local/share/fossil"
install -m 600 recovery-assets/files.fossil \
  "$HOME/.local/share/fossil/files.fossil"
mkdir "$HOME/.files"
cd "$HOME/.files"
fossil open "$HOME/.local/share/fossil/files.fossil" alpine-oldbook
fossil info
```

Confirm that `fossil info` names check-in `36cea2db` or a documented descendant
on `alpine-oldbook` before changing the host.

## 5. Preview, then rebuild the machine

Run the idempotent orchestrator as `jack`, not as root:

```sh
cd "$HOME/.files"
alpine/bin/oldbook-rebuild --plan
alpine/bin/oldbook-rebuild
```

The rebuild exports the exact APKs from Fossil, verifies full-file SHA-256,
Alpine signatures, architectures, and APK identities, installs the locked
closure, installs the desktop entry point, deploys the HOME overlay, configures
greetd/OpenRC services and schedules, and reports login steps that require a
person. It escalates individual system operations with `doas`.

Complete the reported interactive steps:

```sh
codex login
doas tailscale up
```

Approve the replacement machine in the Tailscale admin console. Start `sway`
from a TTY for the first graphical test. Detailed package behavior and rollback
boundaries are in [`alpine/packages/RESTORE.md`](alpine/packages/RESTORE.md).

## 6. Restore private user data deliberately

Do this only after the base rebuild works. Extract each archive into a staging
directory first; inspect it before copying files into HOME:

```sh
mkdir -m 700 "$HOME/recovery-staging"
cd recovery-assets
age --decrypt --identity ../recovery-identity/user/.ssh/id_ed25519 \
  sessions-config.tar.zst.age | zstd --decompress | \
  tar -xf - -C "$HOME/recovery-staging"
```

Split archives must first be concatenated. Reassemble and inspect them like
this:

```sh
cat development-personal.tar.zst.age.part-aa \
    development-personal.tar.zst.age.part-ab \
    > development-personal.tar.zst.age
age --decrypt --identity ../recovery-identity/user/.ssh/id_ed25519 \
  development-personal.tar.zst.age | zstd --decompress | \
  tar -tf - | less
age --decrypt --identity ../recovery-identity/user/.ssh/id_ed25519 \
  development-personal.tar.zst.age | zstd --decompress | \
  tar -xf - -C "$HOME/recovery-staging"
```

Use the same concatenate/decrypt/inspect sequence for
`oldbook-state.tar.zst.age.part-aa` and `part-ab`. The archives contain:

- `sessions-config`: Codex/Claude sessions, user configuration, SSH material,
  and shell/tmux state;
- `sessions-config-final-delta`, `sessions-config-terminal-delta`, and
  `sessions-config-closeout`: changes made after the main session snapshot;
- `development-personal`: project trees, checkouts, documents, downloads, Go
  workspace, and Flatpak user data;
- `oldbook-state`: Oldbook runtime/recovery state, application/browser state,
  Scripture data, and compact Alpine recovery metadata;
- `root-system`: `/etc`, `/boot`, installed APK database, root's HOME, selected
  `/var/lib` state, and root deployment backups.

Apply the session deltas in the order listed after the main session archive.
Extract `root-system` only into a root-owned staging directory and compare it
with the fresh machine. Restore credentials and host identities selectively.

## 7. Recover unfinished work

Committed history ends at `36cea2db`. Another Codex task was still working
during the backup, so its final bytes are preserved separately rather than
misrepresented as a clean commit. Read `live-worktree-final5-status.txt` and
`live-worktree-final5-files.txt`, then inspect the encrypted archive:

```sh
cd recovery-assets
age --decrypt --identity ../recovery-identity/user/.ssh/id_ed25519 \
  live-worktree-final5.tar.zst.age | zstd --decompress | tar -tf -
```

To continue that exact WIP, first verify that the checkout is clean, then
extract into `~/.files` and review the resulting Fossil diff:

```sh
cd "$HOME/.files"
test -z "$(fossil changes)"
cd ../recovery-assets
age --decrypt --identity ../recovery-identity/user/.ssh/id_ed25519 \
  live-worktree-final5.tar.zst.age | zstd --decompress | \
  tar -xf - -C "$HOME/.files"
cd "$HOME/.files"
fossil status
fossil diff
```

Do not commit that WIP until its original task and tests have been reviewed.

## 8. Verify the rebuilt workstation

From `~/.files`:

```sh
alpine/bin/package-archive verify \
  --cache /var/cache/oldbook-apks \
  --lock alpine/packages/locks/321d9e0702cf3368824f.json
python3 -m unittest discover -s alpine/tests -v
alpine/bin/deploy-home --target /tmp/oldbook-preview
sway --validate --config alpine/desktop/.config/sway/config
alpine/bin/oldbook-rebuild --plan
fossil status
```

Also verify a real login, graphics, audio, Wi-Fi, suspend/resume, Tailscale,
firewall policy, and physical input/output hardware. Syntax tests do not prove
those machine-specific paths.

## Public-source fallback

If the private release or decryption identity is unavailable, follow
[`docs/GITHUB-FOSSIL.md`](docs/GITHUB-FOSSIL.md) to bootstrap from
`Spaceghost/.files:alpine-oldbook-live`. That recovers the published source
tree, but it is not a complete replica and cannot restore private sessions,
credentials, captured WIP, or every archived binary artifact.
