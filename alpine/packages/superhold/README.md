# Superhold Alpine package

Build the standalone `projects/superhold` release against Alpine's Qt6,
PyQt6 and layer-shell-qt. Superhold is a desktop utility with native Qt theming;
local Gruvbox Dark comes from the desktop configuration. No npm is required.

## Rebuild

`manifest.json` pins the source archive and signed APKs by SHA-256. Export its
source artifact from Fossil, then build twice in new directories:

```sh
alpine/packages/superhold/build-offline \
  --source /tmp/superhold-0.1.0.tar.gz --work /tmp/superhold-build-one
alpine/packages/superhold/build-offline \
  --source /tmp/superhold-0.1.0.tar.gz --work /tmp/superhold-build-two
```

The builder checks the source digest, runs as the ordinary build user inside
an empty network namespace, and uses `abuild -d` without installing dependencies.
Restore the recorded APK closure first when development packages are missing.
A local abuild signing key is required; keep only its public key in Fossil.
Local signatures do not imply Alpine repository endorsement.

The source release also builds directly with CMake. Its release helper fixes
archive ordering, ownership and timestamps. Source changes require fresh archive
checksums, both APK builds and appropriate verification. Do not reuse a publicly
released version for different contents.

## Compatibility and integration

`superhold` is the primary command. `hold-to-help` and `mbp-intel-shortcuts` remain
compatibility commands. The new configuration directory is
`~/.config/superhold`; existing `~/.config/hold-to-help` files remain fallbacks.
The shared legacy runtime lock prevents a new and old daemon running together.
Existing controls, application profiles, physical triggers and Qt theming stay
available. Startup retains the MBP Intel compatibility command.

For an existing checksum-pinned Hold to Help installation, use the verified APKs
to replace just those two pins; inspect APK's `--simulate` output first:

```sh
doas apk --no-network add 'hold-to-help=0.1.0-r0' 'hold-to-help-doc=0.1.0-r0' \
  /path/to/superhold-0.1.0-r0.apk /path/to/superhold-doc-0.1.0-r0.apk
doas apk --no-network del hold-to-help hold-to-help-doc
```

The second command removes the compatibility constraints from world; the newly
pinned Superhold packages retain the compatibility commands and dependencies.
Both native library paths export the current and deprecated bridge symbols.

The package provides/replaces the former main and documentation package names.
The old recipe directory contains a compatibility build wrapper. Historical verification
for the earlier name remains in `alpine/verification/hold-to-help.json`; it does
not substitute for verification of this renamed release.

## Release status

This is a local release candidate. Public source hosting and maintainer contact
are still required before distribution submission. Superhold is GPL-3.0-or-later;
LXQt inclusion requires upstream review. No public release has been performed.
Current build, installation and reproducibility evidence will be recorded in
`alpine/verification/superhold.json` and the package manifest.
