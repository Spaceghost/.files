# OpenSnitch on Alpine edge

This local package builds OpenSnitch **1.8.0** without npm, pip dependency
downloads, systemd, or a live network during compilation. The recipe builds the
daemon, Qt6 GUI, and OpenRC services. Compilation uses Alpine's musl toolchain.

## Provenance and preserved inputs

- Upstream: <https://github.com/evilsocket/opensnitch/tree/v1.8.0>
- Signed tag object: `d757f06116094d1d460e843c546ae1d31999bf18`.
- Source commit: `b404c4c6316760fa7bc415509d3f8d747f7dc9cc`.
- Source date epoch: `1765715806`.
- Generator versions from the upstream release workflow: protobuf Go `1.34.1`,
  gRPC Go generator `1.3.0`.
- `SHA256SUMS` fixes the upstream archive and offline inputs archive. The latter
  contains vendored daemon modules and both generator source trees with their
  own vendored dependencies. Their licenses and module checksums remain present.

The APK closure snapshot preserves the Go, C, Python and protobuf toolchains.
Rebuilding the same package payload is distinct from reproducing the signature:
the private signing key stays outside Fossil. Retain the public key with the
signed APK artifacts; back up the private key separately if future package
signing with the same identity is needed.

## Build

Restore the two source archives from Fossil's unversioned artifacts, then run:

```sh
alpine/packages/opensnitch/build /path/to/restored/sources /path/to/output
```

The builder checks source SHA256s and stages the reviewed recipe and configuration
in a temporary directory. It uses `GOPROXY=off`, `GOTOOLCHAIN=local`, vendored Go
modules and `python3 -m build --no-isolation`. Output is under
`OUTPUT/oldbook/x86_64/`. An abuild signing key is required (`abuild-keygen -a -n`).
Do not run the upstream installation Makefiles.

`prepare-inputs OUTPUT` is the separate online maintainer operation. It downloads
the pinned source and checksum-verified Go modules, regenerates the source input
archive, and prints hashes for comparison. It requires the preserved Go version,
GNU tar, gzip, wget and protoc. Ordinary rebuilds do not run it.

## Local changes

`external-output-queue.patch` adds an opt-in environment switch:
`OPENSNITCH_EXTERNAL_OUTPUT_QUEUE=1`. The daemon then manages only its DNS
interception rule; `oldbook-firewall` owns the permanent output queue. Both
native queue creation and the native rule-count monitor account for that mode.
The monitor also rejects stale native output interception rules so they cannot
mask a missing DNS interception rule. Without the switch, upstream behavior
remains intact.

`wheel-layout.patch` excludes upstream test modules from installation and places
desktop files/icons under `/usr/share`, rather than inside Python site-packages.
Python protocol files are regenerated against the installed APK protobuf tools.
English interface text is available; translation source files remain in the
upstream archive but compiled translation catalogs are not installed.

See `../../security/firewall/README.md` for behavior, activation and recovery.
