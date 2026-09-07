# Drop-down terminal and quiet desktop panels

Super+grave (the physical backtick/tilde key) and Super+asciitilde toggle a
persistent Foot scratchpad. The terminal occupies 90% of the focused output's
width and half its height, beginning 44 logical pixels below its top edge.
Hiding preserves the shell; exiting the shell lets the next invocation create
another. A per-session lock serializes startup. Its opaque background keeps
underlying windows from interfering with reading.

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
