# Adaptive desktop space and clickable reading cards

The desktop can use an unoccupied bottom edge. A fullscreen window, a tiled
window reaching the bottom strip, or fixed edge chrome requires the existing
clearance placements. Floating windows and their attached captions must not
cause the desktop to rearrange. Scripture search follows the available space.
Conky keeps clearance positions because the user prefers stable cards to
expensive or abrupt automatic reflow.

`desktop_space.py` calculates logical output space from Sway's visible workspace
and SwayFX layer extents. Normal margins are 16 pixels; occupied edges reserve
at least 60 pixels or the actual fixed bar depth plus 16. Only actual containers
identify fullscreen: Sway's synthetic workspace flag is ignored. Hidden local
fullscreen does not affect a visible workspace; global fullscreen does.

Conky has no automatic window-state watcher. It uses at least 60 pixels of
bottom/right clearance when laying out a theme or painting, and keeps its
positions and processes through window/focus/fullscreen changes. Cache keys
include those insets and a layout version. Scripture search reads Sway over a
direct socket once per second, avoiding repeated `swaymsg` subprocesses, and
uses absolute layer positioning on the chosen output. Waybar's top reservation
remains compensated in Conky's rendered margins; bottom-positioned Waybars do
not contribute a top offset.

The placement search precomputes image costs per card size with NumPy, retaining
scan order, collision checks and exact tie decisions. A six-card benchmark cut
median placement CPU from 1.286 seconds to 0.0505 seconds (96%); image decoding
and process restart time are excluded. The wallpaper case and 100 varied grids
produced identical placement dictionaries.

Corner preferences give Scripture the upper right and Coast to Coast the lower
right, while preserving artwork detail scoring and collision avoidance. Native
Conky mouse hooks advance Scripture, Witness and Coast to Coast with targeted
refresh; Gallery uses the existing next-painting action. Explicit clicks leave
background refresh at 60–300 seconds and preserve the SQLite journal's three
quips per note. No personal journal data is versioned.

The Scripture bar now retains one GTK style provider and refreshes it when the
shared palette changes. This fixes a startup-only palette that survived theme
switches and ensures Gruvbox uses its actual gold accent.

Recovery: restore these source files using the scoped deployment backup,
restart Scripture search, and run `mbp-intel-conky layout`.
Saved verses, journal entries, decoration preferences and artwork are retained.

Validation: 43 Conky tests, 10 geometry tests, two real-GTK theme-switch tests,
ShellCheck and compositor syntax checks passed. Eight private SwayFX scenarios
kept Conky positions and processes fixed while Scripture search moved between
16- and 60-pixel margins. Native clicks changed rendered text and only the
clicked process; tiled and floating applications kept their input. Evidence
and screenshots live in `alpine/verification/desktop-space/` and
`alpine/verification/conky-clicks/`.

The full 594-test run encountered two timeouts under concurrent work. Both
affected checks passed separately; the disabled-card test now seeds its saved
reading directly instead of loading the entire library as unrelated setup.
The complete suite was not repeated. Gallery's click uses the existing next
action; changing actual artwork through that click and multiple physical
outputs were not tested. The live bar's five-second sample consumed 0.02 CPU
seconds (0.4% of one core); the private sample measured 0.2%.
