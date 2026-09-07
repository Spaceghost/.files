# LXQt integration

Superhold's first LXQt target is **LXQt on Wayland with Sway**. Select Sway
in LXQt Session Settings under Wayland Settings. LXQt can run with several
different compositors; selecting LXQt alone does not establish compatibility.
The Sway IPC and layer-shell backend does not support LXQt on X11 or other
compositors. This snapshot has not yet been exercised in a full LXQt session.

Install the Python package or use its source launcher with an absolute path.
In **LXQt Session Settings → Autostart**, add `superhold daemon`. The sample
`integrations/lxqt/superhold.desktop` can also be copied into
`$XDG_CONFIG_HOME/autostart/` (normally `~/.config/autostart/`). It is installed
only as an example under `share/superhold/integrations/lxqt`, so package
installation does not enable keyboard monitoring automatically.

Make sure `Exec` and `TryExec` can locate your installation. For a virtual
environment or source checkout, set both entries to the full executable path.
The autostart item can be enabled and disabled in LXQt Session Settings. Avoid
adding the startup command to Sway as well unless duplicate startup is intended.

For a mouse-launchable reference, copy
`share/applications/superhold.desktop` to `~/.local/share/applications/`, and
adjust its executable path if needed. It appears as **Superhold Shortcut
Guide** in the application menu and can be added to a panel launcher. It shows
the current Sway focus for 30 seconds without opening keyboard devices, with
a **Close preview** button for immediate dismissal. Menu
focus behavior may affect which app is current; this needs a full LXQt test.
The guide does not invoke actions when a row is clicked.

Release testing must cover QTerminal, PCManFM-Qt, menu launch focus, screen
locking, logout, keyboard access, monitor scaling and a fresh login. App
profiles remain partial; there is no universal Qt shortcut enumeration in
this snapshot. A later accessibility adapter can query AT-SPI action names,
key bindings and enabled states, then provide explicit action activation.

References: [LXQt session launch](https://lxqt-project.org/wiki/Launching-LXQt-sessions.html),
[XDG autostart support](https://lxqt-project.org/wiki/Miscellaneous.html),
and [LXQt module entries](https://lxqt-project.org/blog/2022/09/20/about-modules-in-lxqt/).
