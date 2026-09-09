# Drop-downs follow the workspace instead of waiting to be recalled

A shown console or system monitor is sticky, so Sway carries it to whichever
workspace is switched to on that output. Hiding clears sticky first, so a
window in the scratchpad follows nothing and holds no workspace open by being
the only window on it. Both drop-downs therefore work from every workspace
without being pinned to any, which is what the shortcut was already meant to
mean and now needs no second keypress.

Sticky is Sway's own mechanism and costs nothing at rest, so no watcher process
listens for workspace events. `oldbook-dropdown` enables it in the same
transaction that shows the window and disables it in the same transaction that
hides it; a scratchpad container belongs to no workspace and cannot be moved by
the sticky pass regardless, so the explicit disable is belt and braces against
a stale flag rather than a correctness requirement.

The existing one-press recall for a window parked on another workspace by hand
is unchanged; the follow behavior means it is rarely reached. Reversal: drop
`sticky enable`/`sticky disable` from the two `swaymsg` transactions in
`alpine/desktop/.local/bin/oldbook-dropdown`. No binding, workspace assignment
or compositor reload is involved.

Verification is under `alpine/verification/dropdown-follows-workspace/`, from
the extended `alpine/tests/verify_ghostty_dropdown.py` running a private
headless compositor. Nothing was sent to the live session.
