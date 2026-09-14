# Incus client package supplement

Catbed has Alpine `incus-client 7.0.1-r1` and unrestricted TLS access to bak.
The installation added 39 packages while preserving all 1,143 existing package
identities. Alpine's client package depends on LXC and dnsmasq; their services
remain disabled, as does rsyncd, and the Incus server package is absent.

[manifest.json](manifest.json) identifies the immutable
[100-package supplement](../locks/c0155382d40b84878872.json). It contains the
client's complete 58-package installed runtime closure, every installation
addition, and those additions' dependencies. All 22,105,388 signed APK bytes
are retained by SHA256 in local Fossil UV, with package identities,
architectures and public verification keys in the lock. Preserve a full Fossil
database backup; a Git export does not carry the APKs. TLS private keys remain
outside the repository.

## Verify and recover in an isolated root

From a restored Fossil checkout on Alpine x86_64 with Python, Fossil and APK:

```sh
cd "$HOME/.files"
incus_lock=alpine/packages/locks/c0155382d40b84878872.json
incus_cache="$HOME/.cache/incus-client-restore"
alpine/bin/package-archive verify --lock "$incus_lock" --cache "$incus_cache"
doas alpine/bin/package-archive restore --lock "$incus_lock" --cache "$incus_cache" --root /var/tmp/incus-client-restore
alpine/bin/package-archive verify-root --lock "$incus_lock" --cache "$incus_cache" --root /var/tmp/incus-client-restore
```

The restore root must be new or empty. This restores the supplement's package
payload only; the root is not a complete bootable workstation.

For an existing Alpine host, first verify/export the same supplement and preview
its offline package transaction:

```sh
doas apk --repositories-file /dev/null --no-network add --simulate "$incus_cache"/*.apk
```

Review the listed version changes before applying the same command without
`--simulate`. Explicit APK paths add the selected packages to APK world while
retaining existing world entries. This differs from the original client-only
world entry. The supplement's own `world` contains only `incus-client`, so
`package-archive install-host` is unsuitable: it would replace the complete
host world with that small file.

## Evidence and existing archive limits

[Package verification](../../verification/incus-bak/package-verification.json)
records all 39 additions and the validation: 100 APKs exported from Fossil into
an initially empty cache, matching SHA256, trusted signatures and installed APK
identities; a successful offline solve selecting exactly 100 packages in an
isolated empty database; and 30 passing archive feature tests. Full payload
unpacking, maintainer scripts and booting the isolated root were not tested.

The full workstation `current-lock` remains unchanged. It already lagged the
installed machine by 22 added packages and four changed identities before this
setup. A full snapshot also found a large pre-existing UV archive gap, failed
once on a transient Fossil database lock, and was stopped during its retry to
keep this work scoped to Incus. Partial UV additions were retained. This
supplement proves recovery inputs for the client; it does not certify recovery
of the entire workstation.
