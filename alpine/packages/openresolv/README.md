# openresolv with a host PID lock bridge

This local `openresolv-3.17.4-r1` package adds an opt-in lock compatibility
interface for commands contained in PID namespaces. Ordinary callers retain
upstream's directory/PID lock. The BSD-2-Clause source and Alpine's existing
init-detection patch are preserved; this is a local build, not an Alpine release.

## Rebuild from Fossil

`manifest.json` names the SHA-256-addressed Fossil unversioned artifacts for the
official source, exact build inputs, public signing key, logs and both APKs.
These artifacts are local; no remote publication was performed.

```sh
fossil uv export sha256/901d83a15520b80e117aeca8cb6f5b70ceb205ba050a638d45cebcf304df729b/openresolv-3.17.4.tar.xz /tmp/openresolv-3.17.4.tar.xz
alpine/packages/openresolv/build-offline \
  --source /tmp/openresolv-3.17.4.tar.xz --work /tmp/openresolv-build-one
alpine/packages/openresolv/build-offline \
  --source /tmp/openresolv-3.17.4.tar.xz --work /tmp/openresolv-build-two
```

Build directories must be new. Install the recorded build tools first:
`abuild`, `make`, `patch`, `xz`, `python3`, and util-linux `unshare`. The wrapper
uses existing `doas` authority only to create an empty network namespace, then
runs `abuild -d` as the ordinary user; it installs no dependencies. Configure
abuild with a local signing key (`abuild-keygen -a` on a new builder). Keep its
private key outside Fossil. Only the public key is archived here.

`SOURCE_DATE_EPOCH=1766616122` fixes package timestamps. Two builds with the
recorded tool versions and signing key produced identical signed APKs. Another
signing key changes signature bytes; compare extracted payloads separately.
Verify an exported APK against this directory's public key with
`apk --keys-dir "$PWD/alpine/packages/openresolv" verify /path/to/package.apk`.

## Compatibility interface

`resolvconf --host-pid-lock-version` prints `1` without creating state. A trusted
runner may pass both `OPENRESOLV_HOST_PID` and `OPENRESOLV_HOST_PROC_FD`: its
captured PID in the containing namespace and an inherited directory descriptor
for that namespace's original proc mount. The resolver validates decimal values,
the proc filesystem, and its own PID before any mutating path. Invalid requested
contexts fail. Read-only subscriber children may inherit their parent's context.

The native lock records the containing-namespace PID; liveness checks use that
same proc view. This prevents a contained writer from stealing a live host lock
or waiting indefinitely on a stale namespace-local PID 1. The interface provides
lock compatibility, not authorization; it does not eliminate upstream PID reuse
limitations. The staged privacy controller constructs this context internally.

## Verification and deployment boundary

`verification.json` records six private package tests, two identical offline
builds, six native concurrency groups, ten invalid-context checks and seven
native lease-application cases. The archived stock package reproduced both
original lock failures. Every native fixture reported unchanged host state and
no remaining namespace processes. The packaged resolver exactly matches the
script used by those proofs.

The main APK is installed; the documentation APK is archived. Installation
preserved live DNS, network, radio and DHCP state, as recorded in
[`resolver-bridge-install-verification.json`](../../security/radio/resolver-bridge-install-verification.json).
The APK has no install hooks, service startup or `/etc/resolv.conf` payload.
WPA/DHCP migration, subscriber policy and DNS-provider activation remain staged.
Both new APKs are cached in `~/.local/share/oldbook/apks`; the prior `3.17.4-r0`
artifact remains available for a controlled package rollback.

Upstream source:
[openresolv 3.17.4](https://github.com/NetworkConfiguration/openresolv/releases/tag/v3.17.4).
Alpine baseline:
[APKBUILD](https://raw.githubusercontent.com/alpinelinux/aports/master/main/openresolv/APKBUILD)
and [init-detection patch](https://raw.githubusercontent.com/alpinelinux/aports/master/main/openresolv/detect_init-remove-irrelevant.patch).
