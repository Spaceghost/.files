# Contextual workspace strip

The approved design retains the bottom strip and its saved opacity and corner
radius, with a soft vertical theme gradient, a small application icon, centered
title, subdued window-state label, and compact float/tile, fullscreen, window
picker, and menu buttons. Fullscreen tiled strips remain square. Hover highlights
and tooltips explain the controls. The right-edge option remains available.

Click the title or window-picker button to choose a window. Middle-click the
title to float/tile that window. Right-click a control or title, click the app
icon, or use the ellipsis for window actions. Shift+right-click opens the existing
appearance editor. Moving the strip is now an explicit menu action instead of
the default right-click gesture.

The window menu offers tiling layouts, workspace moves, scratchpad placement and
recovery, title copying, window switching, and close. Floating windows add center
and pin/unpin actions. Empty workspaces offer installed Terminal, Files, Browser,
and Applications launchers. Commands use fixed argument vectors; titles and
workspace labels are never shell commands. Window operations capture a numeric
container ID so changing focus while a menu is open does not retarget the action.

Application actions are discovered asynchronously only when requested:

- Terminals can open their launch directory, or a resolved tmux pane directory,
  in a new terminal or Files. Custom terminal app IDs are recognized through the
  owned process executable.
- Identified tmux panes offer horizontal/vertical splits, zoom, and scrollback.
  Actions target that pane explicitly and check its process identity before use.
- MPRIS controls appear only for a player whose D-Bus owner PID matches the
  window process, with available previous/play/pause/next actions. Other players
  are not selected as a fallback.

Implementation lives in `mbp-intel-decoration` and `decoration_actions.py`.
Discovery and command execution run off the GTK thread. Each output has a
separately scoped stylesheet; steady state does not redraw the strip every poll.
Existing deployment symlinks load these files directly from the checkout.

The user explicitly requested that testing stop. No unit tests, integration
tests, synthetic desktop sessions, or automated interactions were run for this
change. The source was reviewed, the decoration daemon was restarted to install
it, and its startup log and rendered strip were observed. A missing desktop-file
icon fallback exposed during startup was corrected. Existing GTK/GI deprecation
notices remain. Menu behavior, tmux/media actions, and multiple outputs remain
unverified at the user's request.

The private activation log and screenshots are under
`~/.local/state/mbp-intel/decoration-context/`. The [included screenshot](../../../alpine/verification/decoration-context/bottom-strip.png)
records the empty-workspace launchers; no window actions were exercised.

Recovery: restore the decoration helper and appearance-editor tooltip from the
parent of this check-in, then restart only `mbp-intel-decoration daemon`. The new
actions module can remain unused or be removed. Saved placement, opacity, and
radius were not changed. Waybar and the other desktop services were not restarted.
