# Contextual shortcut overlay

The guide is now the standalone **Hold to Help** project in
`projects/hold-to-help/`, with a CMake source release and signed Alpine package.
`mbp-intel-shortcuts` remains the compatibility command; the installed command is
`hold-to-help`. The original GTK implementation remains available for rollback.

Hold either **Super** key by itself for half a second. A scrollable overlay
shows the focused application's shortcuts, the active Sway mode's shortcuts,
and applicable terminal, tmux and system controls. Release Super to dismiss it.
Pressing another key cancels the overlay for that hold, and your usual shortcut
continues to work. Use the mouse wheel or touchpad to scroll the list.

The overlay does not take keyboard focus. Application key combinations are
shown as reference: release Super before using an app shortcut that does not
itself contain Super. Quick taps and normal Super combinations do not open it.

## Coverage

Sway's main configuration and current mode come from the running compositor.
Included files are also traversed, but Sway's IPC does not preserve their loaded
contents: these are read from disk. The coverage label identifies this mixture.
Reload Sway after editing included files so the list and active bindings agree.
The app heading uses the focused window and, for terminals, its foreground
command and active tmux pane. tmux controls come from the running server's
effective key tables.

Application profiles are explicitly labeled partial baselines. They cannot
automatically account for every remapping, plugin, editor state or website.
Unsupported applications show that app-specific coverage is unavailable while
keeping the Sway and relevant surrounding controls. The overlay never executes
the commands it displays.

The Codex CLI profile includes `/keymap, Enter`, which opens Codex's own current
shortcut browser and remapping interface. Its baseline keys are versioned for
the installed Codex CLI 0.153.4.

Add or override app profiles in `~/.config/mbp-intel/shortcuts.json`:

```json
{
  "profiles": {
    "writer": {
      "name": "Writer",
      "aliases": ["org.example.Writer"],
      "coverage": "Partial local profile",
      "rows": [
        {"key": "Ctrl+S", "description": "Save document"},
        {"key": "Ctrl+Shift+S", "description": "Save as"}
      ]
    }
  }
}
```

Aliases identify the application ID or foreground command, rather than a
document title. Invalid profiles are reported in the overlay and do not remove
the built-in shortcuts.

## Operation

`mbp-intel-shortcuts dump` prints the current contextual list as JSON.
`mbp-intel-shortcuts preview --seconds 5` shows a temporary layout preview.
`mbp-intel-shortcuts status` prints the current session's service record.
These commands also accept `--socket PATH` for an explicit Sway session.

The separate `~/.config/sway/local.d/shortcuts.conf` startup snippet launches
`mbp-intel-shortcuts daemon`. A per-compositor lock prevents duplicates across
reloads. Status files under `$XDG_RUNTIME_DIR/hold-to-help/` contain service
metadata; key events and typed content are never written to them.

Abrupt compositor shutdown can terminate Qt before the final status write.
The process still exits and releases its resources; status records are checked
against process identity, and each new compositor session gets a separate record.

Input devices are opened read-only with the user's existing access. The service
does not grab input or alter device permissions. It suppresses the overlay
during locking and outside the active graphical session. No additional package
installation is required after restoring the recorded Hold to Help package snapshot.

## Theme and portable configuration

Qt supplies the palette, fonts and style. The local qt6ct settings and the
optional native LXQt configuration both use Gruvbox Dark, Inter and the MBP Intel
icons. LXQt's named preset is `~/.local/share/lxqt/palettes/Gruvbox-Dark`.
The guide follows application palette/font events; a platform plugin that only
reads settings at startup requires restarting the guide after a theme change.

Edit `~/.config/hold-to-help/config.toml` (deployed from this workspace) to choose
`trigger = "capslock"`, or change `hold_seconds`. The current default remains
Super and Caps-to-Escape is preserved. Physical-trigger selection never remaps
the key. The standalone profile path is `~/.config/hold-to-help/profiles.json`;
the compatibility command keeps the existing MBP Intel profile path usable.

The compatibility launcher imports the workspace project when deployed through
its repository symlink. Restart the shortcut daemon after editing Python files;
rebuild the package after native bridge changes. Set
`MBP_INTEL_SHORTCUTS_LEGACY=1` when launching the compatibility command to use the
preserved GTK implementation during rollback. Stop the current guide first so
two implementations do not observe the same hold.

To disable the feature, comment out the startup command, read the PID from
`mbp-intel-shortcuts status`, and send that process SIGTERM. Re-enable the command
and run `mbp-intel-shortcuts daemon` to restore it. Deployment uses the normal
`deploy-home` recovery journal; its recorded backup can be rolled back with
`alpine/bin/deploy-home --target "$HOME" --rollback BACKUP_DIRECTORY`.

Design, validation and outstanding physical checks are recorded in
`docs/superpowers/specs/2026-09-07-contextual-shortcuts.md`,
`alpine/verification/contextual-shortcuts.json` and `alpine/PROGRESS.md`.
