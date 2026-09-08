# MBP Intel radio runtime APK

`mbp-intel-radio-runtime` installs only the fixed privileged CLI, fourteen Python
runtime modules and two DHCP helpers. APK owns their root-owned files and modes;
there are no install scripts, policies, doas grants, OpenRC services, sleep hooks,
runlevel links or command invocations. Installing the runtime does not transfer
WPA, DHCP or DNS ownership and does not activate the radio policy.
The local recipe explicitly uses abuild's `!fhs` exception to preserve the
reviewed `/usr/local` paths; it is not an Alpine distribution submission.

## Source and build

After the runtime is reviewed and frozen, create its deterministic source archive:

```sh
alpine/security/radio/make-runtime-release \
  --output /tmp/mbp-intel-radio-runtime-0.1.0.tar.gz
```

`RUNTIME_SOURCE_MANIFEST` contains the exact reviewed regular-file allowlist.
The release refuses links, special files and unexpected runtime modules; private
configuration, caches and native fixture output are excluded. Source metadata,
file modes, ordering and gzip timestamps are fixed. Update the source SHA-256 in
`manifest.json` and SHA-512 in `APKBUILD` only after review. Pending pins prevent
the builder from running. Do not change a released version's contents.

```sh
alpine/packages/privacyctl-runtime/build-offline \
  --source /tmp/mbp-intel-radio-runtime-0.1.0.tar.gz --work /tmp/radio-build-one
alpine/packages/privacyctl-runtime/build-offline \
  --source /tmp/mbp-intel-radio-runtime-0.1.0.tar.gz --work /tmp/radio-build-two
```

The builder follows the Superhold package workflow: run `abuild -d` as the build
user inside an empty network namespace, without installing dependencies. Restore
the recorded package closure first. The installed patched `openresolv=3.17.4-r1`
is required for the native resolver lock contract. Keep the signing private key
outside Fossil; the adjacent public key verifies local APK signatures.

The APK check runs only lease parsing, private UNIX-socket protocol tests and
temporary-file release tests. The source also includes the separately reviewed
root-only profile tests. These checks do not replace native radio recovery proof.

## Installation boundary and recovery

Before adding the verified APK, simulate the local transaction and inspect the
exact seventeen files for existing ownership or unmanaged collisions. Do not use
APK overwrite or force flags. Preserve any preexisting reviewed runtime package
artifact for APK rollback. Removal or downgrade changes files only; it is not a
radio rollback and must not be used on an active owner without the separately
reviewed blocked handoff.

Follow [the radio migration plan](../../security/radio/NETWORK-MIGRATION.md) before
installing policy or service integration. No trusted SSID is supplied by this APK.
Package installation is not authorization to connect or start the supervisor.

## License status

No separate radio license has been assigned. `LicenseRef-Unknown` records that
fact for this local package; it grants no additional rights. The Superhold GPL
license does not establish a license for this runtime. Public redistribution has
not been performed.
