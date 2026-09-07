# Hold to Help Alpine package

This recipe builds the standalone `projects/hold-to-help` source release against
Alpine's Qt6, PyQt6 and layer-shell-qt. It installs a user-session utility, not a
system daemon. No npm, input-group membership change, or automatic autostart is
part of the package.

`manifest.json` pins the source archive and built package by SHA-256. Export the
source artifact from Fossil using its manifest `artifact` name, then run:

```sh
fossil uv export sha256/5a87cd9744374b4740ffe7dc366d173492e59a66f5f66bd4567d0124a12b90d5/hold-to-help-0.1.0.tar.gz /tmp/hold-to-help-0.1.0.tar.gz
alpine/packages/hold-to-help/build-offline \
  --source /tmp/hold-to-help-0.1.0.tar.gz --work /tmp/hold-help-build-one
alpine/packages/hold-to-help/build-offline \
  --source /tmp/hold-to-help-0.1.0.tar.gz --work /tmp/hold-help-build-two
```

Build directories must not exist. Builds run as the ordinary build user inside
an empty network namespace. `abuild -d` does not install dependencies. Restore
the recorded package closure first if the compiler or development packages are
missing. A local abuild signing key is required; only its public key belongs in
the repository. APK signatures are local release signatures, not Alpine's
official repository endorsement.

The source release is also rebuildable with CMake independently of these
dotfiles. `tools/make-release.py` inside the project normalizes archive ordering,
ownership and timestamps. After changing source, regenerate the archive,
manifest and APKBUILD checksums and repeat both builds. Do not keep a released
version number for different published contents.

Local `oldbook-shortcuts` remains a compatibility command. It uses the workspace
source when launched through this checkout's deployed symlink, and otherwise
uses the installed package. Existing Oldbook application profiles remain
available; the standalone default is `~/.config/hold-to-help/profiles.json`.
Keep the installed native bridge synchronized with source changes through the
recipe. Sway startup continues to use the compatibility command.

For distribution beyond this workstation, choose a public release location and
maintainer contact, publish the reviewed source, and adapt the APKBUILD source
URL. GPL-3.0-or-later license text and contributor documentation are included.
No upstream LXQt submission or public release has been performed.

## Recorded verification

Both final builds produced byte-identical signed main and documentation APKs;
all 108 package tests passed inside each isolated build. Native Sway and X11
checks cover focus, scrolling, physical triggers, remapped Caps, short chords,
lock suppression, and Qt palette/font changes. The installed bridge was tested
again on a private Sway display. See `alpine/verification/hold-to-help.json` and
the adjacent synthetic preview.

Lock `alpine/packages/locks/10265f085b5a34747518.json` preserves all 1,079 installed
package identities and public signing keys. The complete closure restored into
an empty directory with networking disabled; restored CLI and native bridge
loading passed. This verifies packages and files, not a bootable disk image.
