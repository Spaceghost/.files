# Workspace-edge chrome

The workspace has one caption per output, showing the selected workspace's
focused window. Normal windows use zero-width pixel borders. The caption starts
at the bottom; `mbp-intel-decoration right`, `bottom`, or `toggle` changes its edge
and saves the choice in `~/.config/mbp-intel/decoration.json`. The legacy state
position is migrated and synchronized. The window menu includes placement; Shift +
right-click opens `mbp-intel-decoration-settings`, which shows the controls and
editable JSON together. Opacity and radius changes apply on the next poll.
The right edge spells the title vertically, replacing `|` with an em dash and
keeping combining accents together. Long vertical titles are shortened to the
available height; hovering shows the full title. Left-click opens the window
picker, and middle-click toggles that window's floating state. Right-click opens
window actions. See [the contextual strip decision](2026-09-07-contextual-workspace-strip.md)
for the newer quick controls and application actions, including their untested status.

Font family and point size follow Foot's configured font (currently JetBrains
Mono Nerd Font, 9.5 pt). The active palette supplies the borderless gradient.
The strip has compact padding and four rounded corners. Fullscreen tiled chrome
is square. The strip uses the overlay layer so it remains visible in fullscreen.
Floating and ordinary windows retain the theme's rounding. The helper does not
capture keyboard focus, and a lock prevents duplicate instances on reload.

The center title island was removed at the user's request. That space now holds
music controls; the workspace caption carries the focused window title.

Foot profiles use alpha 0.78 with alpha-mode=all so application-painted cells
remain transparent as well. Existing terminals were repainted using the owned-PTY
palette helper; newly opened Foot windows get alpha-mode=all. Foot itself makes
fullscreen terminal backgrounds opaque. Agent launch commands retain the danger
switches configured earlier.

Validation: decoration unit tests, terminal palette tests, ShellCheck for the
session script, Foot parsers for all three profiles, and Sway/SwayFX validation.
`python3 alpine/tests/verify_workspace_chrome.py --output /tmp/chrome-proof`
creates an isolated SwayFX desktop and records bottom/right/fullscreen, short and
long title bars, and empty-workspace screenshots. The saved evidence is under
`alpine/verification/workspace-chrome/`; screenshots use synthetic content.

Recovery: choose `mbp-intel-decoration bottom` to restore placement. To remove the
workspace strip, stop its daemon and remove its mbp-intel-session startup entry.
The prior SwayFX native-caption defaults were `default_border normal 0` and
`default_floating_border normal 0`, with `titlebar_position bottom`. Restore those
only if native per-window captions are wanted again. Prior Foot theme alpha was
0.94 for Spaceghost and 0.98 for Gruvbox, without alpha-mode=all.

References: [Waybar packing options](https://github.com/Alexays/Waybar/blob/master/man/waybar.5.scd.in)
and [Foot transparency settings](https://codeberg.org/dnkl/foot/src/branch/master/doc/foot.ini.5.scd).
