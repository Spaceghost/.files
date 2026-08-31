# Reproducible Sway desktop

A shared, rollback-friendly Fedora Sway configuration with a Catppuccin-inspired visual layer, optional nwg-shell components, Nushell, and a separately built SwayFX session.

## Layout

- Upstream Sway remains the Fedora Atomic base and safe fallback.
- SwayFX 0.5.3 is built into `~/.local/opt/swayfx-0.5.3`; it does not replace `/usr/bin/sway`.
- `~/.config/swayfx/config` includes the normal Sway configuration, then adds blur, shadows, rounded corners, and layer-shell effects.
- Waybar is the default panel. Press `Mod+Shift+B` to toggle between Waybar and nwg-panel.
- Rofi is `Mod+D`; nwg-drawer is `Mod+Shift+D`; notifications are `Mod+N`; the power menu is `Mod+Shift+E`.
- Nushell is installed and configured, but Bash remains the login shell.
- `packages/fedora-atomic.lock` records the exact known-good base commit, RPM versions, and SwayFX/scenefx source pins.

## Rebuild

```bash
~/dotfiles/install.sh
~/dotfiles/install-host.sh
~/dotfiles/build-swayfx.sh
```

Reboot after the host install, then choose either **Sway** or **SwayFX** in SDDM. Applying the layered desktop packages only at boot is intentional: live replacement is less predictable while the desktop stack is running.

## Rollback

`install.sh` moves replaced files into timestamped directories beneath `~/.local/state/sway-desktop-backups/`. Restore the desired files from the newest directory, or remove a managed symlink and copy its backup into place.

To remove only the layered host packages, review `packages/fedora-atomic.txt`, then run `sudo rpm-ostree uninstall PACKAGE...`. Remove `/usr/local/bin/swayfx-session` and `/usr/local/share/wayland-sessions/swayfx.desktop` to remove the SDDM entry.
