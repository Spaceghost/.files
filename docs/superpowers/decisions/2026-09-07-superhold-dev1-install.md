# Install the local theme-following Superhold

Superhold `0.2.0.dev1-2c5a0afe5578` is installed and running from the local wheel.
The active launcher is `~/.local/bin/superhold`; menu entries and Sway startup
already use it. The system `/usr/bin/superhold` is a separate older Qt package.

The package source is `projects/superhold-guide`, which includes the physical
Super-key dismissal fixes missing from the standalone `~/src/superhold` tree.
All installed Python module hashes match the captured source. No application
source was changed during this packaging task.

## Package and recovery

Wheel and sdist hashes, exact source file hashes and local installation paths
are in `alpine/packages/superhold-guide/manifest.json`. Both archives are retained
locally under `~/.local/share/superhold/packages/0.2.0.dev1-2c5a0afe5578` and in Fossil's
unversioned content-addressed archive. No package or repository was published.

Run `~/.local/bin/superhold-rollback` from the active Sway session to restore the
preserved patched dev0 prefix and its launchers. To reactivate this dev1 build,
run:

```
python3 /home/jack/.local/share/superhold/backups/0.2.0.dev1-2c5a0afe5578/switch.py activate
```

The switcher verifies preserved hashes and process identity, terminates only
Superhold, atomically swaps its launchers, and checks graphical/keyboard readiness.
Rollback and reactivation were both exercised successfully. The earlier rollback
command is restored when returning to dev0. Personal settings are preserved.

## Validation

- 134 unit tests on the exact source snapshot; two additional installed-package
  checks exercise both Super keys against open/loading guides and held-key
  suppression. Three desktop entries validate; both launchers pass ShellCheck.
- The same guide, settings and release-overlay processes changed from dark to
  light after replacing a disposable GTK CSS symlink. Screenshot color checks
  pass. The private headless guide fixture neutralized its missing-seat focus
  timeout; these checks prove theme updates, not physical input/focus behavior.
- Live daemon PID at completion was 23237, with 2
  readable keyboards and an active graphical session. Source hashes, version,
  explicit process path and rollback/reapply readiness were checked.

Screenshots: [dark](../../../alpine/verification/superhold-guide-dev1/guide-dark.png)
and [light](../../../alpine/verification/superhold-guide-dev1/guide-light.png).
Full local evidence: `/home/jack/.local/state/oldbook/verification/superhold-dev1-install`.

Existing fullscreen/LXQt release limitations remain as documented by the project.
The broader theme gaps in the earlier theme-following handoff remain separate
work; this installation resolves the stale installed Superhold version.
