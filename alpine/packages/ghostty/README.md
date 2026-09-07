# Ghostty

Installed from Alpine's explicitly tagged `edge/testing` repository as
`ghostty@testing`, package `1.3.1_git20260810-r1`. The binary reports
`1.3.2-dev+0000000`. `simdutf` and the automatic Zsh completion subpackage were
the only added dependencies; no existing packages were upgraded.

Launch `ghostty` or choose **Ghostty terminal** in the desktop command deck.
The deployable configuration uses the same Gruvbox colors, JetBrains Mono font,
78% opacity and small padding as Foot. It prefers Sway's window decorations.
Foot remains the configured Super+Enter terminal.

The exact signed APKs are preserved in Fossil's unversioned artifact store.
`manifest.json` records each source URL, installed APK identity and SHA-256.
All three passed `apk verify` and comparison with the installed package database.
Export an artifact using its manifest path:

```sh
fossil uv export sha256/<sha256>/<filename>.apk /tmp/<filename>.apk
apk verify /tmp/<filename>.apk
sha256sum /tmp/<filename>.apk
```

`ghostty +validate-config` validates the deployed configuration. Native rendering
evidence is saved in `alpine/verification/ghostty*`. Snapshot
`0e1e8733a3ab9504808a` extends the prior 952-package lock with these three verified
artifacts. All 955 installed identities match and every artifact is present;
the prior packages were unchanged. This was an incremental archive check, not
a fresh installation or rebuild of the full closure.

To remove Ghostty, run `doas apk del ghostty` and remove `ghostty@testing` from
the repository package world. The configuration can remain for later reinstall.

References: [Alpine package](https://pkgs.alpinelinux.org/package/edge/testing/x86_64/ghostty)
and [Ghostty configuration](https://ghostty.org/docs/config/reference). The installed
binary's `+show-config --default --docs` supplied the version-matched option list.
