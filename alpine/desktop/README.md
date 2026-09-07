# Spaceghost desktop overlay

This is the deployable HOME overlay for the Oldbook Alpine desktop. It is designed for the MacBookPro11,5 internal `eDP-1` display at 2880×1800 and scale 2: Gruvbox Dark charcoal surfaces, cream text, and warm amber highlights with Space Ghost artwork. It contains no wallpaper, credential, network profile, or machine secret.

`~/.local/share/oldbook/wallpaper.png` is an activation contract. The deployment unit places the approved `alpine/assets/spaceghost.png` at that path. Sway uses it initially; the gallery updates the shared painting. The lock helper prefers `current-wallpaper.png`, then this fallback image, then solid Gruvbox charcoal (`#282828`).

All workspaces now share the same painting and gallery timer. Foot uses 78%
opacity with 4-pixel padding; Sway keeps a small 4-pixel outer gap. Ghostty is
also installed with matching colors and opacity: launch `ghostty` or select it
in the command deck. To play a muted, looping video behind transparent windows,
run `oldbook-video-background ~/Videos/example.webm`, or choose **Video background**
in the command deck. `oldbook-video-background stop` reveals the shared painting.
The video picker accepts local files and explicit HTTPS URLs. No video starts
automatically. See the [video guide](../packages/mpvpaper/README.md) and
[Ghostty notes](../packages/ghostty/README.md).

Waybar keeps the current-window/media capsule against the right-hand status
group. The far left and right ends are square; the inner corners are rounded.
A second, click-through Waybar surface sits behind windows at the right edge.
Its Unicode bars show per-core CPU use and memory, followed by temperature,
network throughput, root-disk usage and uptime. It reserves no window space.
To remove this monitor, remove the object named `monitor` from the Waybar config
array and reload Waybar with SIGUSR2. The top bar remains the first object.

## Runtime dependencies

The package snapshot must include `sway`, `swayidle`, `swaylock`, `waybar`, `fuzzel`, `swaync`, `foot`, `zsh`, `starship`, `eza`, `zoxide`, `neovim`, `btop`, `cava`, `grim`, `slurp`, `swappy`, `jq`, `libnotify`, `playerctl`, `pavucontrol`, `pipewire`, `pipewire-pulse`, `wireplumber`, `wlsunset`, `polkit-gnome`, `qt6ct`, `adw-gtk3`, and `papirus-icon-theme`. JetBrains Mono and a Nerd Font symbols font provide the intended metrics and icons.

The contextual guide uses the locally packaged `hold-to-help` and its Qt 6,
layer-shell-qt and keyboard-input dependencies. Its [portable guide](../../projects/hold-to-help/README.md)
documents desktop support and exact build requirements.

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
| Hold `Super` alone for half a second | Show contextual shortcuts; release or press another key to dismiss. Scroll the guide without taking keyboard focus. |
| `Super+Escape` | Lock with the installed `swaylockd` PAM-compatible binary |
| `Print`, `Shift+Print`, `Ctrl+Print` | Full display, selected region, focused-window screenshot |
| Volume and microphone keys | PipeWire `wpctl`, with a PulseAudio-compatible fallback |
| Brightness keys | Kernel backlight steps, with a clear notification if the seat lacks write permission |
| Click the panel audio icon | Open pavucontrol |
| Click the notification glyph | Toggle the Spaceghost notification center |
| Command/Super + left click the artwork icon | Generate a new Space Ghost image and switch to it |
| Shift + left click the artwork icon | Edit shared artwork guidance and scene prompts |
| `Caps Lock` | Escape (including with Shift); the original Escape key still works |

The shortcut guide starts through `sway/local.d/shortcuts.conf` and stays hidden
while the session is locked or inactive. It combines Sway bindings with relevant
application profiles; profiles are useful baselines, not exhaustive shortcut lists.
`oldbook-shortcuts status` reports its state. The default trigger remains Super,
so Caps Lock retains its Escape behavior and notification indicator.

The artwork icon keeps its original controls and tooltip: left click next,
right click gallery, middle click pause, and scroll previous/next. Its small
`oldbook-waybar-art` package supplies native modifier handling; see the
[build and verification guide](../packages/waybar-art/README.md).

Caps Lock still sends Escape. Its indicator is off normally and keeps flashing
while an attributable Codex, Claude, or ChatGPT window has not been visited
since its alert. Focusing or closing one target clears only that window; other
pending windows keep the flash active. Ordinary desktop notifications and old
retained messages do not light it.
`oldbook-notification-led` discovers Caps Lock LEDs when keyboards are connected
and recovers their state if the compositor resets it. Reloading Sway reuses one
helper; exiting the session turns the light off.

The notification stream uses `py3-dbus` and `py3-gobject3`, already present in the
locked package snapshot. It watches new desktop notification calls without
intercepting delivery or recording notification contents. Browser alerts need
site attribution; the current SwayNC path provides none, so generic
Firefox/Chromium notices are ignored. The browser and website must actually emit
a desktop notification with a validated origin hint. CLI setup and supported
signals are described in the AI attention notes under `docs/superpowers/specs/`.
`brightnessctl` supplies the udev rule granting group `input` write access to LED
brightness, and the desktop user must belong to that group (Jack already does).
It never changes key state to control the light. Diagnostics go to
`~/.local/state/oldbook/notification-led.log`.

To disable the light integration, remove the notification helper launch from
`oldbook-session` and terminate the PID in
`$XDG_RUNTIME_DIR/oldbook-notification-led.lock`. Leave `caps:escape` configured
to retain the Escape mapping. A reboot or keyboard reconnect restores the
kernel's default LED trigger; the helper detaches it again when it starts.

Screenshots are stored in `~/Pictures/Screenshots` and offered to Swappy for annotation. The helper quotes output paths and accepts only its three fixed capture modes. The Waybar network widget reads only `/sys/class/net` and the current route. It never starts a wireless scan and does not imply radio privacy or connectivity merely because an interface exists.

The overlay does not infer a geographic location. It leaves `wlsunset` disabled by default. Add an explicit, local `wlsunset` command in `~/.config/sway/local.d/` only after choosing the correct location or an intentional fixed schedule.

The tmux overlay retains the existing `C-a` workflow only when `~/.files/.tmux.conf` does not name TPM or another tmux-plugin path. It does not install or fetch a plugin manager. The shell, Neovim, btop, and cava configs likewise use only installed programs and built-in features.
