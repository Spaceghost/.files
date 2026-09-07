# Contextual shortcut overlay

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

Add or override app profiles in `~/.config/oldbook/shortcuts.json`:

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

`oldbook-shortcuts dump` prints the current contextual list as JSON.
`oldbook-shortcuts preview --seconds 5` shows a temporary layout preview.
`oldbook-shortcuts status` prints the current session's service record.
These commands also accept `--socket PATH` for an explicit Sway session.

The separate `~/.config/sway/local.d/shortcuts.conf` startup snippet launches
`oldbook-shortcuts daemon`. A per-compositor lock prevents duplicates across
reloads. Status files under `$XDG_RUNTIME_DIR/oldbook-shortcuts/` contain service
metadata; key events and typed content are never written to them.

Abrupt compositor shutdown can terminate GTK before the final status write.
The process still exits and releases its resources; status records are checked
against process identity, and each new compositor session gets a separate record.

Input devices are opened read-only with the user's existing access. The service
does not grab input or alter device permissions. It suppresses the overlay
during locking and outside the active graphical session. No additional package
installation is required on the current Oldbook package snapshot.

To disable the feature, comment out the startup command, read the PID from
`oldbook-shortcuts status`, and send that process SIGTERM. Re-enable the command
and run `oldbook-shortcuts daemon` to restore it. Deployment uses the normal
`deploy-home` recovery journal; its recorded backup can be rolled back with
`alpine/bin/deploy-home --target "$HOME" --rollback BACKUP_DIRECTORY`.

Design, validation and outstanding physical checks are recorded in
`docs/superpowers/specs/2026-09-07-contextual-shortcuts.md`,
`alpine/verification/contextual-shortcuts.json` and `alpine/PROGRESS.md`.
