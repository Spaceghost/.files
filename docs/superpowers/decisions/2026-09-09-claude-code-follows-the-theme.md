# Claude Code follows the desktop theme, reactively

Claude Code was pointed at a custom theme whose overrides were empty, so it was
the stock dark theme wearing a local name while every other surface on the
machine carried the palette. It is now a themed surface like the terminals and
the bar: every theme profile carries `.claude/themes/oldbook.json`, rendered
from the same template through the same recolouring path as the rest.

The whole override set is covered — all seventy keys the application defines,
not the handful that are obviously visible — so no colour is left reading from
the base theme and clashing. Claude's own marks keep the warm role, the accent
drives the rate-limit meter, and the diff grounds are the theme's background
carrying the change's colour rather than fixed pastels, so they stay legible
under a light palette as well as a dark one. `base` follows the palette's own
light-or-dark reading, because the application decides its dimming and contrast
from that one word.

It is genuinely reactive. Claude Code exports a watcher over its themes
directory and reloads a running session when the file under it changes, so
repointing the deployed symlink at another profile restyles open sessions with
nothing to signal and no restart. `oldbook-theme` therefore adds no reload
step, only a report — in the same voice as the Qt and Firefox notes it already
prints — saying whether the file is deployed and whether the user's settings
actually select it.

Two things are deliberately not automated. The theme's file name never varies:
`custom:oldbook` in `~/.claude/settings.json` resolves against it, so a
per-theme name would break the reference on every switch. And the switch does
not write that settings line itself; a theme command silently editing an
application's own settings file is not a trade the user offered, so it reports
the missing line instead.

The template lives at `alpine/desktop/.claude/themes/oldbook.json` in the
Gruvbox baseline shades, which is what lets `render_profile` recolour it for
every theme, generated ones included, and what lets `ensure_profile` complete
older profiles that predate it. Reversal: remove `CLAUDE_THEME` from the
renderer's path set and the `base` rewrite, delete the template and the three
profile copies, and set `theme` back to a built-in name. Checks:
`alpine/tests/test_complete_themes.py`.
