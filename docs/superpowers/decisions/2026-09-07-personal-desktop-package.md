# Space Ghost desktop package in Cascadia

Cascadia source checkout: `/home/jack/src/cascadia`, branch
`personal/oldbook-desktop`, initially committed as `5a99cd6`. It is based on the
active Alpine overlay work, not Cascadia's older master bootstrap.

The signed `spaceghost-desktop-2026.09.07-r0.apk` selects the desktop runtime and owns
the system launcher/display-manager entry. This checkout keeps the home overlay,
helper programs, themes and configuration. The package does not contain
credentials, clipboard/reading/journal history or personal radio policy.

The tagged local repository is registered alongside the existing edge sources:
`@personal /var/lib/cascadia/repositories/apk/edge/personal`.
No desktop meta-package was installed over the working host. Recovery removes
that one repository entry; previous repository files are backed up beside
`/etc/apk/repositories`. The r0 repository directory is retained for comparison.

Cascadia's `docs/SPACEGHOST-DESKTOP.md` describes private-release download and restoration.
The full .files Fossil database retains all 784 artifacts named by the desktop
lock `alpine/packages/locks/562f5ede7edcea8723de.json`. Both signed desktop builds
have SHA-256 `8ce4a691f61566e994706aa7f15f52abb59b2ee46b4195b5512d21fc9a4f6a44`.
The separate current host lock retains all installed packages and now reflects
the r9 gallery APK's native world constraint and the personal repository entry.

Verification: all 784 archived APKs verified; signed native index resolves and
installs the desktop into a disposable root; installed identities match its
lock. Codex, SwayFX and Waybar version checks succeed there. Home deployment
passes in a disposable HOME. Maintainer scripts were disabled in the root test;
fresh boot/hardware behavior is not claimed. Evidence lives in Cascadia under
`docs/assets/oldbook/`. Public Pages/signing setup remains the existing Cascadia
issue #22; local and private-release recovery do not require public hosting.

The current package and command are named `spaceghost-desktop`, per the owner.
The repository index and private-release recovery use this name; old package
artifacts remain historical recovery inputs. Component/helper names in .files
remain intact. Rename verification preserves identical dependency metadata,
checks the actual APK launcher and confirms native apk selection.
