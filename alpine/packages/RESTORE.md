# Restore the archived Alpine workstation

Start with an installed, bootable **Alpine edge x86_64** system, a normal user
with `doas` access, and working `python3` and `fossil` commands. Install those
bootstrap tools before going offline. Disk partitioning, encryption, firmware,
bootloader installation, user creation, and network credentials are separate
machine setup tasks; the package archive does not provision a bootable disk.

Bring a complete, consistent backup of `files.fossil` containing both versioned
history and its unversioned APK/source artifacts. A checkout directory or a
GitHub source archive alone does not contain the archived packages. The example
backup is mounted at `/media/backup/files.fossil`. Run these three steps as the
normal user; administrator steps explicitly use `doas`.

1. Copy the Fossil database and open its `alpine-oldbook` branch in an empty
   checkout directory. Use the verified release checkout recorded with your
   backup if several revisions are present.

   ```sh
   mkdir -p "$HOME/.local/share/fossil" "$HOME/.files"
   cp /media/backup/files.fossil "$HOME/.local/share/fossil/files.fossil"
   cd "$HOME/.files"
   fossil open "$HOME/.local/share/fossil/files.fossil" alpine-oldbook
   ```

2. Restore the signed APK binaries selected by `alpine/packages/current-lock`.
   This explicit command installs packages on the running machine.

   ```sh
   doas alpine/bin/package-archive install-host --cache /var/cache/mbp-intel-apks
   ```

3. Restore Codex's complete musl bundles, install the desktop entrypoint, and
   link the normal user's overlay. Enable the painting schedule after setting
   up a local ChatGPT login with `codex login`.

   ```sh
   alpine/bin/source-archive --kind codex --cache "$HOME/.local/share/mbp-intel/sources"
   doas alpine/bin/install-codex --cache "$HOME/.local/share/mbp-intel/sources"
   doas alpine/bin/install-desktop-system
   alpine/bin/deploy-home --target "$HOME"
   codex login
   alpine/bin/install-wallpaper-schedule
   doas rc-update add crond default
   doas rc-service crond start
   doas rc-update add tailscale default
   doas rc-service tailscale start
   ```

   Then `doas tailscale up` once, and approve the machine in the admin console.
   The desktop's remote agents reach the tailnet over Tailscale SSH, so no ssh
   key is needed on this machine and none is kept; the far side must run
   `sudo tailscale up --ssh` and the tailnet policy must permit the hop.

   The offline scripture library is not carried in the checkout beyond the
   bundled King James text. The first desktop login fetches the rest in the
   background through `mbp-intel-scripture-library bootstrap`, which needs
   working HTTPS; `mbp-intel-scripture-library install --all` does it on demand
   and adds the Talmud.

   Start `sway` from a TTY. For a first graphical session on fresh hardware,
   also enable the usual Alpine seat/udev services and required user groups;
   retain the base system's working login/seat setup. The user overlay starts
   its D-Bus, sound, panel and notification services within Sway.

The package install exports APKs from Fossil, verifies every full-file SHA256,
checks signatures using the lock's public keys, and validates native APK
identities before touching the installed package database. APK installation uses
local archive paths with networking disabled and no external repositories.
Afterward it compares locked versions, architectures, and APK identities and
writes the lock's `world` and HTTPS repository configuration.

Unrelated packages already installed on the machine are retained. A simulated
transaction that would remove packages is refused. Extra packages are listed
explicitly, and the command does not claim an exact closure match while they
remain. Their removal is a separate, deliberate administrator action. Existing
configuration uses APK's normal protected-file handling; check any `.apk-new`
files and follow the main Alpine setup instructions for desktop system services,
Codex, and security activation. Machine credentials and Codex authentication
must be configured locally.

## Recovery and verification

Before installing, the command creates a private root-owned directory under
`/var/backups/mbp-intel/install-host-*` with an `etc.tar` archive, the original APK
database, selected lock, and simulated transaction output. The `/etc` backup may
contain machine secrets. Keep it private and outside Fossil.

A failed live installation can leave partial package changes. Preserve its
backup and error output and inspect the affected configuration before retrying.
Restoring only the APK database would misrepresent the binaries on disk; it is
not a package rollback. Use your system backup for whole-system rollback, or
reinstall the appropriate previously archived signed packages together with
reviewed configuration recovery.

For a disposable offline package-closure test, use a new or empty root instead
of `install-host`:

```sh
doas alpine/bin/package-archive restore --cache /var/cache/mbp-intel-apks --root /var/tmp/mbp-intel-restore
alpine/bin/package-archive verify-root --cache /var/cache/mbp-intel-apks --root /var/tmp/mbp-intel-restore
```

The isolated restore publishes its root only after closure validation. Failed
staging directories remain alongside it as evidence, and the requested root
can be retried. This verifies package restoration, not bootability or physical
hardware behavior.

## Binary restoration and source rebuilds

`install-host` restores the archived signed APK binaries. It does not compile
Alpine's entire package collection from source. The lock also retains the
installed toolchain packages needed by the local recipes.

Custom SwayFX and OpenSnitch source inputs are separately content-addressed in
Fossil. Export and verify them without networking:

```sh
alpine/bin/source-archive --cache "$HOME/.local/share/mbp-intel/sources"
```

Then follow [SwayFX's offline build instructions](swayfx/README.md) and
[OpenSnitch's build instructions](opensnitch/README.md). Those documents record
which payload or signed-binary comparisons were actually verified. Building
new packages requires a local signing key; private signing keys are never
included in the Fossil repository. Installing the already archived APKs only
requires the public verification keys recorded in their lock.
