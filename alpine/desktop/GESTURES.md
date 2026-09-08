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

Expo now opens Fuzzel, the same launcher used elsewhere on this desktop.
It lists open windows with their workspace and app names, followed by desktops
1–10 and any additional numbered workspaces. Type to filter, select with the
arrow keys or mouse, and press Enter to switch. Escape cancels. Selecting an
empty workspace enters it; scratchpad windows stay out of the list.

The picker inherits Fuzzel's fonts, sizing, and shape, with colors from the
active theme at launch. It closes after selection and has no background service.
Repeated upward swipes reuse the open picker; Super+E toggles it.

Sway does not handle compositor gesture bindings when the pointer is over a bar's
exclusive region. Start swipes over an application or desktop. Escape is always
available to dismiss the picker. Browser-specific back/forward, zoom, and other
gestures depend on that application's support; these bindings do not emulate
every macOS gesture or Force Touch feature.

Configuration: `~/.config/sway/gestures.conf`. The existing Sway configuration
includes it, so it survives login/reload. Runtime verification identified Apple's
`1452:628:bcm5974` touchpad and confirmed libinput's gesture capability. See
`alpine/verification/gestures/` for parser, isolated overview and live input evidence.

To reverse workspace directions, exchange `workspace next` and `workspace prev`
in that file. To disable desktop gestures, remove the include and reload Sway.
For immediate removal without a reload, `swaymsg unbindgesture swipe:3:left`
(and the corresponding finger/direction combinations) removes each binding.
