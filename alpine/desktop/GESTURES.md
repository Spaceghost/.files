# Apple trackpad and Ghost Expo

Gestures are handled directly by Sway/libinput. No privileged gesture daemon,
input grab, compositor replacement, or extra package is required.

| Gesture | Action |
| --- | --- |
| Three or four fingers left | Next existing workspace |
| Three or four fingers right | Previous existing workspace |
| Three or four fingers up | Open Expo |
| Three or four fingers down | Close Expo |
| Four-finger pinch inward | Application launcher |
| Four-finger spread outward | Close Expo |
| Two-finger scroll | Natural scrolling in the application |
| Two-finger pinch | Application zoom, where supported |
| One / two / three-finger tap | Left / right / middle click |
| Tap, then drag | Drag without holding the physical click |

**Super+E** toggles Expo. It is also available as **Ghost Expo** in the launcher
and **Expo · all workspaces** in the command deck.

Expo displays desktop 1–10 plus any additional numbered workspaces, with window
layout cards that refresh while open. Click a window to focus it, or click a
workspace heading to enter it. Search filters names, applications and titles;
Enter activates the first match. With search empty, 1–9 and 0 select desktops
1–10. Escape, Close, or a downward swipe dismisses the overview. Empty desktops
are selectable; scratchpad windows are excluded. There is no background process
when the overview is closed.

The miniature cards show window geometry and titles, not live content thumbnails.
Sway does not expose hidden workspace screenshots through ordinary screen capture;
this overview never flips through workspaces to photograph them. Choosing Expo
also leaves application zoom gestures alone.

Sway does not handle compositor gesture bindings when the pointer is over a bar's
exclusive region. Start swipes over an application or desktop. Expo handles its
own downward and horizontal swipes while it owns the pointer. Browser-specific
back/forward, zoom, and other gestures depend on that application's support;
these bindings do not emulate every macOS gesture or Force Touch feature.

Configuration: `~/.config/sway/gestures.conf`. The existing Sway configuration
includes it, so it survives login/reload. Runtime verification identified Apple's
`1452:628:bcm5974` touchpad and confirmed libinput's gesture capability. See
`alpine/verification/gestures/` for parser, isolated overview and live input evidence.

To reverse workspace directions, exchange `workspace next` and `workspace prev`
in that file. To disable desktop gestures, remove the include and reload Sway.
For immediate removal without a reload, `swaymsg unbindgesture swipe:3:left`
(and the corresponding finger/direction combinations) removes each binding.
