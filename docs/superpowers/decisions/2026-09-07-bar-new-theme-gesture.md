# Super+Shift+click creates a gallery theme

Super/Command+Shift+left-click on the Waybar artwork button invokes
`oldbook-wallpaper new-theme`. Both left and right modifier keys work, including
mixed sides. The combined gesture takes precedence over Shift's prompt editor.
Super alone still paints in the active theme; Shift alone still edits prompts.
The other mouse buttons and scrolling retain their existing behavior.

The new command reuses the gallery's random-theme pipeline with `--new-theme=`
and `--activate`: create a named art direction and palette, generate its first
painting, save it, and switch to that painting when ready. This is the existing
gallery theme behavior; it does not generate application configuration profiles
or change `alpine/themes/current`.

The signed `oldbook-waybar-art-1.0.0-r4.apk` built twice byte-identically without
networking. Signature verification, Fossil unversioned readback and installed
payload hashing passed. The physical session's Waybar was restarted under its
existing service lock and its mappings checked against the installed library.
All 555 repository tests passed. Isolated interaction checks cover 23 actions,
and production tooltip screenshots cover rotating, paused and generating states.
No real generation was requested during verification.

The restoration lock was derived from `0b39a04f417c70933a4e`, replacing only the
Waybar APK and its world identity. This preserves the existing restoration target
with the new gesture; it is not a new snapshot of the full host. The host's
pre-existing pylast/dependency additions remain outside that closure. Full host
closure reconciliation and an isolated full restore were not performed here.

Recovery: restore the archived r3 APK recorded in the previous lock, install it
with `doas apk --no-network add --allow-downgrade /path/to/oldbook-waybar-art-1.0.0-r3.apk`,
and restart the session's Waybar. That restores Shift precedence. The new helper
command and tooltip can be reverted separately without affecting saved artwork.
