# Desktop caption clearance

Keep the existing bottom caption and purple glass styling. Add a quiet accent
outline; preserve the saved opacity and fullscreen corner policy.

Runtime evidence showed Conky's power rectangle at y=822, height=82, intersecting
the caption at y=867. Its planned y=780 was displaced by Waybar's 42-pixel
exclusive zone. Convert planned screen coordinates to Conky's usable-area margins
using the live top surface extent. Reserve 60 logical pixels at the bottom and
right, and include layout reservations in wallpaper cache identities.

Scripture search uses absolute layer-shell positioning with a 60-pixel bottom
margin, matching the planner. All six panels were refitted and inspected on the
live desktop. Evidence: `alpine/verification/bottom-bar-spacing/`.

Recovery: restore the affected source files, restart the caption and Scripture
search processes, then run `~/.local/bin/mbp-intel-conky layout`. Existing wallpaper
and panel content remain intact. Unrelated pending repository edits were preserved.

Limit: origin compensation uses SwayFX's layer_shell_surfaces extension and the
configured top namespace. A compositor without this extension falls back to zero;
that environment and different display scales were not runtime-tested.

The clearance check applies to the desktop workspace strip. Captions attached
to floating application windows move with those windows and can cover background
panels just as the application itself does.
