# Space Ghost Control Deck

The floating panel is designed for the Oldbook's 1440×900 logical display. Edit
`config.jsonc` or `style.css` here; deployment links them into `~/.config/waybar/`.
CSS reloads automatically. After JSON edits, restart Waybar from the session
or send `pkill -USR2 -u "$(id -u)" -x waybar` (Waybar 0.15 may print a harmless
Glib dispatcher warning during in-process reload).

| Control | Actions |
| --- | --- |
| Ghost badge | Left: command deck. Right: application launcher. |
| Artwork | Left: next image. Right: gallery picker. Middle: pause/resume rotation. Scroll: previous/next. Hover: artwork provenance, rotation state, and all controls. Command/Super+left: generate a new image and switch to it. |
| Workspaces | Click a named workspace; scroll to cycle. GHOST, ORBIT, LAB, SIGNAL, and LOUNGE are visual labels for 1–5, without forced application assignments. Workspaces 6–10 appear when used. |
| Focused window | Click to choose any open window. Window title is shortened on the panel. |
| Media | Appears with an MPRIS player. Left: play/pause. Right: next track. Middle: previous. |
| CPU | Hover to reveal memory, temperature, and root storage; click to open btop. |
| Network | Live receive rate; hover shows transmit rate, IP addresses, and signal. Hover also reveals radio and firewall state. Left: network controls. Right: connection report. |
| Sound | Scroll for volume, left for mixer, right for mute. Hover reveals microphone; click its icon to toggle microphone mute. |
| Battery | Hover reveals brightness and keep-awake controls. Scroll brightness to adjust. Left: lock/suspend/logout menu. |
| Notifications | Left: notification center. Right: Do Not Disturb. |
| Clock | Los Angeles time. Click to show date/seconds; scroll to browse the calendar. |

`oldbook-panel-status` reads local kernel counters and addresses. Neither the
panel nor its tooltips initiate wireless scans. Radio status reports rfkill;
firewall status reports the daemon process, without asserting that a ruleset
has been audited or that hardware is physically silent. Radio-off uses the
separately installed privacy controller. Session logout requires confirmation;
suspend runs the lock helper successfully first.

`oldbook-control` uses fixed argument lists, never shell evaluation of menu text.
Window switching passes only numeric Sway container IDs. External titles,
interface names, and addresses are escaped before being used as markup.

Configuration references: [Waybar 0.15 groups](https://github.com/Alexays/Waybar/blob/0.15.0/man/waybar.5.scd.in),
[workspaces](https://github.com/Alexays/Waybar/blob/0.15.0/man/waybar-sway-workspaces.5.scd),
[MPRIS](https://github.com/Alexays/Waybar/blob/0.15.0/man/waybar-mpris.5.scd).
