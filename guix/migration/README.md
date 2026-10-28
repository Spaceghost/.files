# Reversible Alpine-to-Guix bridge

The live desktop remains owned by Alpine while Guix is introduced as a foreign
package manager.  This is intentional: the current SwayFX, output-mask,
swaylock-effects, native Waybar art and Superhold behavior must not be replaced
by stock Guix packages merely because a profile evaluates.

`patched-binaries.sha256` pins the executables currently driving the desktop,
and `apk-packages.txt` pins their installed Alpine package revisions.  Run
`guix/bin/audit-current` before and after each migration step.  It also verifies
the immutable APK closure, the published theme checkout and the most recent
private pre-migration backup.

The first Guix profile is isolated at
`~/.guix-extra-profiles/oldbook-migration/oldbook-migration`; it is not added to
the session `PATH`.  Preview it before installing:

```sh
guix package --dry-run \
  --profile="$HOME/.guix-extra-profiles/oldbook-migration/oldbook-migration" \
  --manifest="$HOME/.files/guix/migration/profile.scm"
```

`guix/bin/apply-stage-one` reapplies this exact bootstrap idempotently.  It
installs Alpine's Guix package, enables its OpenRC daemon and realizes only the
isolated manifest.  It deliberately does not run `guix pull`, reconfigure Guix
Home, or change a graphical command.  The pre-Guix package closure is
`321d9e0702cf3368824f.json`; the post-bootstrap closure is
`a39763a9ea503b106be7.json`.  Both are immutable, hash-addressed locks whose APK
artifacts are stored in the Fossil repository.

Do not activate `home.scm` over the live home yet.  It contains stock graphical
packages and is the eventual whole-home target, not the compatibility bridge.
Patched Guix recipes must be built on `alienware` or `bak`, substituted onto
this laptop, and pass the same behavior checks before the corresponding Alpine
package is retired.

The whole Guix System configuration is likewise a target, not an in-place
installer.  The current LVM volume group has no free extents, so it must first
be tested on external storage or after an explicitly planned offline resize.
