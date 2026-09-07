# LXQt integration

Superhold targets **LXQt on Wayland with Sway**. Select Sway in LXQt Session
Settings under Wayland Settings. LXQt can use several compositors; the current
Sway IPC, input, and layer-shell backend does not support LXQt on X11, KWin,
labwc, or other compositors. A complete LXQt session remains unverified.

The application uses GTK 3 with native desktop windows for its guide and
settings. It requires no LXQt library and does not modify LXQt preferences.
Release-mode hold gestures use a nonfocusable layer instead of a normal window.

## Application menu and panel

Installing the Python package installs two menu entries:

- **Superhold Shortcut Guide** runs `superhold show`.
- **Superhold Settings** runs `superhold settings`.

Both can be added to a panel launcher. For a source checkout, copy the two
desktop files from `share/applications/` into `~/.local/share/applications/`
and set their `Exec` entries to the full source-launcher path. Set `TryExec`
where present to that same executable.

The guide can be opened with the mouse. It asks an existing daemon to open, or
runs until the one-shot window closes. Search and scroll, then click a native
shortcut; the guide hides, restores the original target, and sends the key
sequence after held keys have been released. Keyboard access and `wtype` are
required for activation. The settings window opens independently of Sway and
edits its own XDG configuration file only when **Save** is selected.

The persistent guide closes on focus loss. Menu activation can affect which
application is focused when the context is captured; launcher-to-application
focus behavior must be checked in the full LXQt session. Unsupported shortcuts
remain visible with disabled controls and an explanation.

## Optional autostart

In **LXQt Session Settings → Autostart**, add `superhold daemon`. Alternatively,
copy `integrations/lxqt/superhold.desktop` into `$XDG_CONFIG_HOME/autostart/`,
normally `~/.config/autostart/`. Adjust `Exec` and `TryExec` for a virtual
environment or source checkout.

The package installs that sample only under
`share/superhold/integrations/lxqt`; installation does not enable keyboard
monitoring automatically. LXQt Session Settings can enable or disable the
autostart entry. Choose either LXQt autostart or Sway's startup entry; a
per-compositor lock also prevents duplicate services.

By default, holding Super alone for 500 ms opens the persistent guide. Settings
can change the delay or select a layer that closes when Super is released. A
menu-launched guide stays persistent in either configuration. Valid settings
changes are picked up by the idle daemon without restarting the session.

## Remaining release checks

The persistent normal window currently maps behind fullscreen applications.
Explicitly focusing it through Sway disables the application's fullscreen
state, so Superhold does not use that workaround. Resolving fullscreen behavior
is a release blocker; see `runtime-focus-validation.json` for isolated evidence.

Full LXQt testing must cover QTerminal, PCManFM-Qt, menu and panel launch focus,
screen locking, logout, keyboard access, native activation, mixed monitor
scaling, and a fresh login. Static app profiles remain partial. AT-SPI action
discovery and direct accessible activation are future work, separate from the
current native keyboard delivery.

References: [LXQt session launch](https://lxqt-project.org/wiki/Launching-LXQt-sessions.html),
[XDG autostart support](https://lxqt-project.org/wiki/Miscellaneous.html), and
[LXQt module entries](https://lxqt-project.org/blog/2022/09/20/about-modules-in-lxqt/).
