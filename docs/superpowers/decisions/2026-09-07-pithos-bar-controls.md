# Pithos background startup and music-bar gestures

Pithos starts automatically through `mbp-intel-session` and Sway sends newly mapped
Pithos windows to its scratchpad. The program stays alive for playback and
scrobbling. Session reloads check the Gtk.Application D-Bus owner and do not raise
or hide an existing instance. Both Alpine's lowercase `pithos` Wayland app ID and
`io.github.Pithos` are recognized, with an XWayland class rule as a fallback.

The center track title uses `mbp-intel-pithos click` for single/double-click
arbitration. A single left click toggles Pithos playback after 350 ms. A second
press during that interval cancels the pending toggle and shows/focuses the
window. This avoids Waybar MPRIS's ignored GDK double-click event and the unwanted
pause that would occur if single-click ran immediately. State is serialized with
flock under a private per-Sway-session runtime directory. Right-click toggles the
window, bringing it to the current workspace if necessary. The previous/next
arrow buttons retain their left-click track navigation actions; their right-click
also toggles Pithos.

Showing a window hidden through Pithos's tray reactivates its existing GTK
instance and then brings its mapped window out of the scratchpad. Hiding never
quits the process or changes playback. No credentials or account settings are
modified.

The three MPRIS modules select player `io`: Playerctl reports Pithos's short name
as `io` and its full instance as `io.github.Pithos`, while Waybar 0.15.0 matches
only the short name. Explicit control commands target the full Pithos instance.
This bar is now intended for Pithos. Another MPRIS application sharing the short
name `io` could compete for its display; none was present during validation.

## Validation and evidence

- Ten isolated helper tests cover click arbitration, hidden/visible windows,
  cross-workspace visibility, existing-instance reload, cold startup and tray
  reactivation. The first seven were observed failing before implementation.
- Session concurrency test passes. ShellCheck passes for the changed POSIX
  startup script; Sway's parser accepts the configuration.
- The private Waybar/Sway verifier uses a fake MPRIS service and real GTK window
  with a private D-Bus, HOME and Wayland display. Physical pointer events confirm
  previous, one play/pause, next, right show/hide and double open without any
  extra playback operation. Startup and repeated start leave the window hidden.
- `alpine/verification/pithos-controls/` contains private-session screenshots and
  event evidence. No personal player content appears in these artifacts.
- Live helper show/toggle commands changed the user's actual Pithos window from
  visible to hidden. The bar was reloaded and the window left hidden.
- Full desktop suite: 547 tests, 546 passed; unrelated Conky policy test errors
  with `KeyError: origin_y` in `mbp-intel-conky.build`. No Conky files were changed.
- Full logout/login and physical XWayland behavior remain untested.

## Recovery

Restore the preceding Sway, Waybar and `mbp-intel-session` configurations, remove
`~/.local/bin/mbp-intel-pithos`, and reload Sway and Waybar. Bring a retained window
back with `[app_id="pithos"] scratchpad show` through swaymsg, or launch Pithos
again if its tray hid it. Existing Pithos account and Last.fm settings are intact.

## Source references

- Installed `/usr/share/pithos/pithos/application.py` and notification icon plugin
- https://github.com/Alexays/Waybar/blob/0.15.0/src/modules/mpris/mpris.cpp
- https://github.com/Alexays/Waybar/blob/0.15.0/src/AModule.cpp
