# Workspace zero typography — 2026-09-07

The empty `0: STRATA` workspace uses the same emphasis as other named
workspaces: active number and name are bold and bright; inactive number is
bold and name is regular. Process suffixes keep their existing subdued style.

The updated native GTK fixture first failed against the previous helper:
the active STRATA name had weight 400 where weight 700 was required. After
changing the recognized empty workspace from `6: STRATA` to `0: STRATA`, all
45 checks passed. The fixture then passed again when linked directly against
the library extracted from the signed r6 APK. Fatal GTK warnings were enabled;
each run used private Xvfb, D-Bus, HOME and XDG directories.

The recipe was frozen before two network-isolated builds. Their signed APKs
are byte-identical, both pass `apk verify`, and the local Fossil unversioned
archive reads back exactly the original artifact.

- APK: `oldbook-waybar-art-1.0.0-r6.apk`
- APK SHA-256: `c3337cc121e97d30a47f38fd27eb3e8e8015e128edd73c1cc20b85f29fa70273`
- Library SHA-256: `2c2a92972276144526d3950075379b24852fba3638e337eb6cc12cd5a5f7da73`
- APK identity: `Q1CDjR05pVBYn01wo4gkJg+bo25U8=`

The logs and JSON here retain the failing and passing GTK results, source
hashes and both build logs. `art.c` is unchanged, preserving gallery gestures.
Existing r4/r5 gallery, hover and real-Waybar checks are identified as historical
evidence in the package verification record.

The signed r6 package is installed; its library hash matches the extracted
artifact. All other installed package identities remain unchanged. The new
immutable lock, `alpine/packages/locks/c66a59a07dc3f7c8d5cb.json`, matches all
1,119 host package names, versions, installed architectures and APK identities.
It retains the previously installed rclone and shell-completion packages; their
exact APKs were fetched after local/archive cache misses, verified and archived.
Their installed `arch` and native `artifact_arch` remain separate. The existing
lock is preserved.

Live Waybar PID 25862 maps the installed r6 library. A read-only check matched
the mapped inode/device to the installed file and confirmed its SHA-256 against
the signed package. `desktop-activation.json` records this without workspace
names or window titles; package verification has no pending checks.

To run the GTK fixture again from the repository root:

```sh
cc -std=c11 -Wall -Wextra -Werror \
    alpine/packages/waybar-art/tests/workspace-emphasis.c \
    alpine/packages/waybar-art/help.c \
    -o /tmp/workspace-strata-gtk $(pkg-config --cflags --libs gtk+-3.0)
python3 alpine/verification/workspace-strata-zero/run-private-gtk.py \
    --binary /tmp/workspace-strata-gtk --output /tmp/workspace-strata-gtk-new
```
