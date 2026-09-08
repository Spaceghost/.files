# Clean caption handoffs between floating windows

Hover focus reused a caption's movement spring for the next window, producing
a short slide and size adjustment. Updating the position immediately still
showed the previous GTK buffer width for one frame at the new position.

Each newly focused floating window now receives a fresh caption surface with
its controls and complete attachment geometry prepared before the first map.
The previous surface is disposed immediately; handoffs have no entry fade.
Dragging the same window retains its existing surface and movement spring.
Animation callbacks start after mapping, when GTK has a frame clock.

All 41 decoration unit tests and 28 native attachment checks passed, including
nine pointer handoffs, six rapid alternations, complete sampled rectangles,
single-caption ownership and animated held dragging. Source hashes, screenshots,
failure evidence and live activation details are in
[decoration-hover](../../../alpine/verification/decoration-hover/README.md).
Only the live decoration daemon was restarted; saved appearance stayed intact.

Recovery: restore only `alpine/desktop/.local/bin/oldbook-decoration` from this
check-in's parent, then restart `oldbook-decoration daemon`. No compositor, bar
or saved-preference reset is needed.
