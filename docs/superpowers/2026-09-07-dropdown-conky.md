# Drop-down terminal and quiet desktop panels

Super+grave (the physical backtick/tilde key) and Super+asciitilde toggle a
persistent Foot scratchpad. The terminal occupies 94% of the focused output's
width and 52% of its height, anchored to the workspace's usable top edge below
the bar. Show, resize and placement use one IPC transaction.
Hiding preserves the shell; exiting the shell lets the next invocation create
another. A per-session lock serializes startup. Its warm charcoal background
is 84% opaque, retaining fully opaque text. New shells get 20x16 padding and
a beam cursor. Waybar uses the overlay layer so fullscreen scratchpad windows
cannot cover it. The existing shell received background alpha through Foot's
OSC 11 extension without restarting; its old padding/cursor remain until it
is closed normally and reopened.

The Conky panel templates now contain date, battery charge/status, artwork notes
and rotating Coast to Coast text. CPU, RAM, process lists, storage I/O, network
throughput, temperatures, uptime and seconds are removed. Panels refresh every
60 seconds; artwork text runs every 120 seconds and rotating text every 240.
Wallpaper/theme changes can still trigger an immediate placement rebuild.
No email source was configured: no local Maildir was present and no account
source has been selected. The separately requested Linux app remains unnamed.

Conky 1.24.2 is installed. Snapshot f4f8e961fd9563d312a9 captures all 1,090
installed APK identities and exact signed artifacts in Fossil UV. This is not a
new bootable-image or offline-restore claim.

Validation: Sway and Foot configuration parsers passed, disposable HOME
installation passed, and actual Sway hide/show preserved the terminal container.
Fresh startup and opaque rendering passed. All four Conky processes stayed live
with generated 60-second configs. Screenshots and runtime data are under
alpine/verification/dropdown-conky. The full unittest run passed 327/329; the
two previously documented shortcut-service status failures remain. Physical
keyboard presses and reboot persistence remain unobserved.

Recovery: remove ~/.config/sway/local.d/dropdown.conf and reload Sway to remove
the bindings/rule; close the drop-down shell when no longer needed. Use
oldbook-conky stop to stop panels, or oldbook-conky toggle to disable persistence.
Edit ~/.config/conky/panels.json and run oldbook-conky restart to adjust cards.
The HOME files link to the versioned overlay.

## Glass appearance follow-up

Sway and Foot parser checks pass for the final settings. Live hide/show on a
fullscreen workspace preserves container 259, and its top matches the reserved
workspace boundary. Geometry also passes on an offset output. Waybar restarted
and reports the expected 32-pixel height. Screenshot: glass.png; runtime checks:
glass-runtime.json under alpine/verification/dropdown-conky. No slide animation
or SwayFX-only effect is required by the running stock Sway session.

The shared Waybar config already contains unrelated pending changes; its one-line
layer change is applied and saved there but deliberately left out of this focused
commit. Preserve `"layer": "overlay"` when committing the other Waybar edits.
