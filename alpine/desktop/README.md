# Spaceghost desktop overlay

This is the deployable HOME overlay for the Oldbook Alpine desktop. It is designed for the MacBookPro11,5 internal `eDP-1` display at 2880×1800 and scale 2: deep violet surfaces, magenta highlights, and spectral-white text. It contains no wallpaper, credential, network profile, or machine secret.

`~/.local/share/oldbook/wallpaper.png` is an activation contract. The deployment unit places the approved `alpine/assets/spaceghost.png` at that path. Sway and swaylock use it when present; the lock screen falls back to solid violet if it is temporarily absent.

## Runtime dependencies

The package snapshot must include `sway`, `swayidle`, `swaylock`, `waybar`, `fuzzel`, `swaync`, `foot`, `zsh`, `starship`, `eza`, `zoxide`, `neovim`, `btop`, `cava`, `grim`, `slurp`, `swappy`, `jq`, `libnotify`, `playerctl`, `pavucontrol`, `pipewire`, `pipewire-pulse`, `wireplumber`, `wlsunset`, `polkit-gnome`, `qt6ct`, `adw-gtk3`, and `papirus-icon-theme`. JetBrains Mono and a Nerd Font symbols font provide the intended metrics and icons.

`oldbook-session` deliberately owns session services once per current UID. On every Sway reload it checks the existing Waybar, SwayNC, Swayidle, PipeWire, WirePlumber, Pulse, and polkit-agent processes before starting anything. This avoids reliance on the release-dependent `/usr/libexec/pipewire-launcher` behavior and prevents duplicate panels, idle daemons, color processes, or authentication agents.

Start a new session through `oldbook-sway`, which wraps Sway in `dbus-run-session` when no session bus is already present. For a pre-existing Sway process that lacks `DBUS_SESSION_BUS_ADDRESS`, `oldbook-session` uses the user runtime bus when available or starts a user-local bus and passes it to the desktop services it launches. It never uses the systemd-specific `dbus-update-activation-environment --systemd` path because this is an OpenRC setup.

## Activation

Run the repository deployment tool after its package and wallpaper stages:

```sh
~/.files/alpine/bin/deploy-home --target "$HOME"
```

Start a new session with `oldbook-sway`; reload a deployed session with `Mod+Shift+C`. Verify the panel, launcher, notification center, sound, and lock screen in the active session before treating the configuration as accepted. For local machine overrides, place a separate file in `~/.config/sway/local.d/`; this is useful for external displays and intentionally not part of the reproducible overlay.

The configured display mode is the native internal panel. Do not copy it to an external display until its supported modes have been inspected with `swaymsg -t get_outputs`.

## Everyday controls

| Control | Action |
| --- | --- |
| `Super+Enter`, `Super+D` | Foot terminal, Spaceghost application menu |
| `Super+Escape` | Lock with the installed `swaylockd` PAM-compatible binary |
| `Print`, `Shift+Print`, `Ctrl+Print` | Full display, selected region, focused-window screenshot |
| Volume and microphone keys | PipeWire `wpctl`, with a PulseAudio-compatible fallback |
| Brightness keys | Kernel backlight steps, with a clear notification if the seat lacks write permission |
| Click the panel audio icon | Open pavucontrol |
| Click the notification glyph | Toggle the Spaceghost notification center |
| Command/Super + left click the artwork icon | Generate a new Space Ghost image and switch to it |
| `Caps Lock` | Escape (including with Shift); the original Escape key still works |

The artwork icon keeps its original controls and tooltip: left click next,
right click gallery, middle click pause, and scroll previous/next. Its small
`oldbook-waybar-art` package supplies native modifier handling; see the
[build and verification guide](../packages/waybar-art/README.md).

The Caps Lock indicator stays on while SwayNC holds notifications and turns off
when they are cleared. This includes notifications retained in the center after
their popups disappear, including during Do Not Disturb. Opening the center alone
does not clear them. `oldbook-notification-led` follows SwayNC's notification count,
discovers Caps Lock LEDs when keyboards are connected, and recovers their state if
the compositor resets it. Reloading Sway reuses one helper; exiting the session
turns the light off.

The helper uses Python's standard library and the installed `swaync-client`.
`brightnessctl` supplies the udev rule granting group `input` write access to LED
brightness, and the desktop user must belong to that group (Jack already does).
It never changes key state to control the light. Diagnostics go to
`~/.local/state/oldbook/notification-led.log`.

To undo this feature, remove `xkb_options caps:escape` and the notification helper
launch from `oldbook-session`, terminate the helper with the PID in
`$XDG_RUNTIME_DIR/oldbook-notification-led.lock`, and reload Sway. A reboot or
keyboard reconnect restores the kernel's default Caps Lock LED trigger.

Screenshots are stored in `~/Pictures/Screenshots` and offered to Swappy for annotation. The helper quotes output paths and accepts only its three fixed capture modes. The Waybar network widget reads only `/sys/class/net` and the current route. It never starts a wireless scan and does not imply radio privacy or connectivity merely because an interface exists.

The overlay does not infer a geographic location. It leaves `wlsunset` disabled by default. Add an explicit, local `wlsunset` command in `~/.config/sway/local.d/` only after choosing the correct location or an intentional fixed schedule.

The tmux overlay retains the existing `C-a` workflow only when `~/.files/.tmux.conf` does not name TPM or another tmux-plugin path. It does not install or fetch a plugin manager. The shell, Neovim, btop, and cava configs likewise use only installed programs and built-in features.
