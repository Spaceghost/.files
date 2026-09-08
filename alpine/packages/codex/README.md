# Standalone Codex on Alpine

The CLI and app-server **package** archives retain their complete layout:
`bin/`, `codex-package.json`, `codex-path/rg`, and `codex-resources/`.
The code-mode host ships in both packages. The responses proxy is a separate
archive. `release.json` pins version 0.153.4, target, download URLs and GitHub
release SHA-256 digests. Every archive is also stored in Fossil under its
content-addressed `artifact` name. No npm is used.

Install or restore after exporting each archive from Fossil into a cache:

```sh
alpine/bin/install-codex --download-only --cache /path/to/cache
doas alpine/bin/install-codex --cache /path/to/cache
```

When all three cache files exist, installation performs no downloads. It
checks every checksum before extracting and preserves the complete upstream
archives. Executables live under `/opt/codex/0.153.4`; launchers in
`/usr/local/bin` point into those packages. Existing launchers are backed up
under `/var/backups/alpine-rice/codex-*`. It does not edit `~/.codex`.

The upstream musl package's private zsh requests the GNU loader
`/lib64/ld-linux-x86-64.so.2`. On Alpine the installer retains that original as
`zsh.upstream-gnu` and uses the APK-managed `/bin/zsh` in its executable slot.
`alpine-adaptations.json` records this change. The exact zsh APK is included in
the package snapshot. CLI, app-server, proxy, bundled bwrap/rg and native zsh
launch checks are required; experimental shell-fork behavior is not claimed
verified by these checks.
