# Oldbook desktop package in Cascadia

Cascadia source checkout: `/home/jack/src/cascadia`, branch
`personal/oldbook-desktop`, initially committed as `5a99cd6`. It is based on the
active Alpine overlay work, not Cascadia's older master bootstrap.

The signed `oldbook-desktop-2026.09.07-r1.apk` selects the desktop runtime and owns
the system launcher/display-manager entry. This checkout keeps the home overlay,
helper programs, themes and configuration. The package does not contain
credentials, clipboard/reading/journal history or personal radio policy.

The tagged local repository is registered alongside the existing edge sources:
`@personal /var/lib/cascadia/repositories/apk/edge/personal`.
No desktop meta-package was installed over the working host. Recovery removes
that one repository entry; previous repository files are backed up beside
`/etc/apk/repositories`. The r0 repository directory is retained for comparison.

Cascadia's `docs/OLDBOOK.md` describes private-release download and restoration.
The full .files Fossil database retains all 784 artifacts named by the desktop
lock `alpine/packages/locks/02beacad9920bd7ed02e.json`. Both signed desktop builds
have SHA-256 `2db7794622a160dcc2da32931b41fe4afa8d4ac22035099f1b6c5d92f168db0c`.
The separate current host lock retains all installed packages and now reflects
the r9 gallery APK's native world constraint and the personal repository entry.

Verification: all 784 archived APKs verified; signed native index resolves and
installs the desktop into a disposable root; installed identities match its
lock. Codex, SwayFX and Waybar version checks succeed there. Home deployment
passes in a disposable HOME. Maintainer scripts were disabled in the root test;
fresh boot/hardware behavior is not claimed. Evidence lives in Cascadia under
`docs/assets/oldbook/`. Public Pages/signing setup remains the existing Cascadia
issue #22; local and private-release recovery do not require public hosting.
