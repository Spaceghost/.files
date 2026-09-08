# Ghostty drop-down terminal

Super+backtick/tilde now toggles one persistent Ghostty window. It keeps the
existing 94% output width, 52% output height and placement below the reserved
workspace top edge. The installed Ghostty 1.3.2-dev supports native Wayland,
a separate GTK application ID and command-line appearance overrides.

The launcher uses `com.mbp-intel.dropdown` and disables GTK single-instance
forwarding, inheriting the active Ghostty theme and shell. Drop-down overrides
provide 84% background opacity (including colored cells), balanced 20x16
padding, a bar cursor and no decorations or resize overlay. Ctrl+Shift+N is
unbound in this instance to avoid creating a second window with the same ID.
Sway handles focus and placement. Native Ghostty quick-terminal/global shortcut
support is unnecessary for this existing Sway scratchpad workflow.

GTK/font/renderer startup exceeded the old five-second Foot deadline in both
isolated and live checks, so startup allows fifteen seconds. Warm show reuses
the shell and took about 0.10 seconds live. Startup also handles the window
already being hidden by the Sway rule: Sway rejects changing floating state
on a hidden scratchpad container.

The launcher and Sway include are already linked into HOME. The exact new
window rule was applied to the running session; no full desktop reload was
needed. The previous Foot process was preserved in the scratchpad. To recover
that shell, run:

```sh
swaymsg '[app_id="^mbp-intel-dropdown$"] scratchpad show'
```

For rollback, restore the earlier Fossil versions of
`alpine/desktop/.local/bin/mbp-intel-dropdown` and
`alpine/desktop/.config/sway/local.d/dropdown.conf`, then reload Sway. Close the
Ghostty shell normally when finished; rolling back the launcher does not stop it.

Verification artifacts are in `alpine/verification/ghostty-dropdown/`. The live
crop shows the active theme and empty shell. Live checks confirm native Wayland,
focused show, hidden state, and unchanged process/container across hide/show.
The isolated compositor check also exercises cold launch, typing, offset-output
placement and reopening after shell exit. The final Ghostty overrides and Sway
configuration parse successfully, and all 18 deployment/recovery tests plus a
selected-file disposable HOME deploy pass.
Physical keyboard presses and reboot persistence were not observed.

References: [Ghostty configuration](https://ghostty.org/docs/config/reference)
and [GTK application IDs](https://docs.gtk.org/gio/type_func.Application.id_is_valid.html).
Installed `+show-config --default --docs` was used for version-matched options;
`+validate-config` takes a config file, not arbitrary launch overrides.
