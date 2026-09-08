# Cascadia testing Codex APK

This local `testing/codex` aport packages the complete official Codex 0.153.4
x86_64 musl CLI, app-server and responses-proxy archives. It does not use npm,
Node.js or an npm package payload. The executable bundles remain together under
`/usr/lib/codex/0.153.4`, with stable launchers in `/usr/bin`.

Both official bundles contain a private GNU-linked zsh that cannot launch on
Alpine. The APK preserves it as `zsh.upstream-gnu`, depends on Alpine `zsh`, and
puts an absolute `/bin/zsh` symlink in each private-shell slot. The bundled
native `rg` and `bwrap` remain in both resource layouts. Stripping and automatic
ELF dependency tracing are disabled so abuild neither modifies the signed
upstream executables nor mistakes the preserved GNU-only shell for a runtime
dependency.

Restore the three archives named in `manifest.json` from Fossil UV storage into
a source cache, then build inside a network namespace:

```sh
alpine/packages/cascadia/testing/codex/build-offline \
    --source-cache /path/to/cache \
    --work /new/build/directory
```

The builder checks SHA-256 for every cached archive, lets abuild verify the
pinned SHA-512 values, builds with networking disabled, verifies the APK
signature, extracts its payload into a clean staging root and launches the CLI,
app-server, both code-mode helpers, bundled utilities, native zsh links and
proxy there. The package does not read or write `~/.codex` during those checks.
The exact reviewed APK and its SHA-256/SHA-512 digests are recorded in
`manifest.json` and archived in Fossil UV storage at the content-addressed name
listed there.

Install the resulting local file with apk so ownership and future upgrades are
tracked by the package database:

```sh
doas apk add /path/to/codex-0.153.4-r0.apk
```

The current standalone installation has `/usr/local/bin/codex*` links, and
`/usr/local/bin` normally precedes `/usr/bin`. Installing this APK can therefore
leave the older standalone launchers shadowing the package. After installing
the APK and checking `/usr/bin/codex --version`, move or remove only those four
known `/usr/local/bin` symlinks so ordinary `codex` resolves to `/usr/bin/codex`:

```sh
/usr/bin/codex --version
command -v codex
```

Do not remove `/opt/codex/0.153.4` until the packaged installation has been
used successfully and the old links have been retired; it is the rollback copy.
