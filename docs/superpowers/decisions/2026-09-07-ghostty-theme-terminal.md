# Ghostty follows the selected terminal theme

Super+Enter launches Ghostty. `alpine/desktop/.config/sway/local.d/terminal.conf`
sets `$term` and the binding after the shared defaults; ordinary theme profile
changes do not replace this preference.

Ghostty's font family and point size are derived from the selected profile's
primary Foot font, alongside its terminal colors. The base fallback is
JetBrainsMono Nerd Font at 9.5 pt, matching Foot. Both `mbp-intel-theme sync` and
selecting a theme refresh the derived Ghostty config. This keeps later changes
to a profile's terminal font from requiring a separate manual sync.

The active Vespersteel theme and all 12 existing profiles match. An integration
regression selects the same profile twice with different Foot fonts/sizes and
checks the actual Ghostty symlink deployed into a disposable HOME. All 11 theme
switch tests pass. Ghostty validates every profile and the base config; the
running Ghostty process received SIGUSR2 and remained running. Sway and SwayFX
configuration parsers pass; the live Mod4+Return binding was applied explicitly.

Evidence: `alpine/verification/ghostty-theme-fonts.json` and the actual isolated
[Ghostty render](../../../alpine/verification/ghostty-theme-fonts.png).
To restore the previous shortcut, set `$term` to `foot` in `terminal.conf` and
reload Sway. For an intentional terminal font change, edit the selected Foot
profile then reselect that theme; both terminals will follow it.
