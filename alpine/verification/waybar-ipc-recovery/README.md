# Waybar active/inactive workspace recovery

The bar lost its Sway workspace event connection. The command connection stayed
open and the GTK clock advanced, but workspace names and the focused CSS class
stopped updating. The CFFI workspace text styling module remained loaded and the
theme still provided both emphasis colors.

A scoped restart restored the current names and active highlight. The event
connection dropped again within two minutes, so restarting alone was not a
complete repair. `baseline.json` records both observations and the exact previous
Waybar and OpenRC APK artifacts. Detailed live socket observations and narrow bar
screenshots are retained privately in the directory named by that record.

Upstream Waybar added event reconnection after 0.15.0 in
[commit b0b46ec](https://github.com/Alexays/Waybar/commit/b0b46ec039199d99c36a0d6637e13e292d66fbdc).
That diagnosis matches the disconnected socket. The precise reason Sway closed
this session's connection was not established; earlier title-event traffic makes
buffer pressure plausible, but does not prove it.

The local repair belongs in `alpine/packages/waybar/`. Native verification uses a
private compositor and a proxy that interrupts only the bar's event feed;
production workspace names and application contents are not test fixtures.

## Archived build inputs

`source-archive.json` records the pinned upstream source tarball and its verified
Fossil readback. `build-input-archive.json` records all 362 APK inputs from the
isolated build root: 335 were already archived, and 27 additional APKs were
signature-checked, archived, exported and hash-checked. Each artifact uses a
SHA-256 namespace and can be restored with `fossil uv export`.

## Recovery

`baseline.json` identifies both previous signed `0.15.0-r3` APKs. Export those
artifacts under their original filenames, then install them together with
`doas apk add --no-network --allow-downgrades PATH/waybar-0.15.0-r3.apk
PATH/waybar-openrc-0.15.0-r3.apk`. Restart only the live session's Waybar using its
existing environment and lock. This reverts the package; it also restores the
old event-disconnect limitation.
