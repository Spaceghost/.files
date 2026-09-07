# Video backgrounds

`mpvpaper` 1.8-r0 comes from Alpine edge/community. Its exact APK and the
new `mpv-libs` dependency are stored as SHA-256-addressed Fossil unversioned
artifacts listed in `manifest.json`. Both artifacts passed `apk verify`, and
their APK identities match the installed packages.

The desktop helper accepts a local file or an explicit HTTPS URL:

```text
oldbook-video-background ~/Videos/background.webm
oldbook-video-background https://media.example/background.mp4
oldbook-video-background picker
oldbook-video-background stop
```

Playback is muted and loops. Hardware decoding uses mpv's `auto-safe` mode,
which falls back when the compositor or codec cannot provide a safe hardware
path. The helper places its layer surface on `bottom`, above the existing
static background and below application windows. It does not stop or
reconfigure the static wallpaper process. `stop` terminates only the exact
process group recorded in the user's private runtime directory, so other mpv
processes are unaffected.

The system monitor and video intentionally share Sway's `bottom` layer so both
remain behind normal windows. The helper waits for mpv's `vo-configured` and
`time-pos` properties over a private runtime IPC socket before it reloads the
Waybar process for the current Sway socket and Wayland display. This maps the
monitor above the newly rendered video without changing keyboard focus or
restarting an unrelated Waybar session.

The picker lists up to 500 local videos below `~/Videos` and `~/Downloads`.
Typing an HTTPS URL into the picker is also explicit selection. HTTP URLs,
URLs containing credentials, and missing local files are rejected.

To export and verify an archived APK, use the artifact and checksum from the
manifest:

```text
fossil uv export sha256/<sha256>/<filename>.apk /tmp/<filename>.apk
apk verify /tmp/<filename>.apk
sha256sum /tmp/<filename>.apk
```

The full package closure remains controlled by `alpine/packages/current-lock`.
The current 955-package snapshot includes both video packages and Ghostty.
