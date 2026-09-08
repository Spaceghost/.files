# Spaceghost desktop overlay

This is the deployable HOME overlay for the Oldbook Alpine desktop. It is designed for the MacBookPro11,5 internal `eDP-1` display at 2880×1800 and scale 2: Gruvbox Dark charcoal surfaces, cream text, and warm amber highlights with Space Ghost artwork. It contains no wallpaper, credential, network profile, or machine secret.

`~/.local/share/oldbook/wallpaper.png` is an activation contract. The deployment unit places the approved `alpine/assets/spaceghost.png` at that path. Sway uses it initially; the gallery updates the shared painting. The lock helper prefers `current-wallpaper.png`, then this fallback image, then the active theme's solid background. Its ring, text and authentication states follow the same palette.

All workspaces now share the same painting and gallery timer. Foot uses 78%
opacity with 4-pixel padding; Sway keeps a small 4-pixel outer gap. Ghostty is
also installed with matching colors and opacity: launch `ghostty` or select it
in the command deck. To play a muted, looping video behind transparent windows,
run `oldbook-video-background ~/Videos/example.webm`, or choose **Video background**
in the command deck. `oldbook-video-background stop` reveals the shared painting.
The video picker accepts local files and explicit HTTPS URLs. No video starts
automatically. See the [video guide](../packages/mpvpaper/README.md) and
[Ghostty notes](../packages/ghostty/README.md).

Waybar's middle section holds music controls between the left and right desktop
controls. Window titles live in the decoration at the bottom edge. When a floating
window is focused, its decoration attaches to that window and follows moves and
resizes without reserving workspace space. Any fullscreen window on that visible
workspace returns the decoration to the workspace bottom; leaving fullscreen
restores the saved edge and attachment. Global fullscreen applies to all outputs.
Open `oldbook-decoration-settings` to edit placement, opacity and corners beside
the underlying `~/.config/oldbook/decoration.json`. The right edge remains an
option; right-click the caption for placement controls or Shift + right-click to open the
editor. Left-click chooses a window and middle-click toggles floating. The
borderless caption follows the active theme, with square corners for fullscreen
tiled windows and the selected rounding otherwise.

## Runtime dependencies

The package snapshot must include `sway`, `swayidle`, `swaylock`, `waybar`, `fuzzel`, `swaync`, `foot`, `zsh`, `starship`, `eza`, `zoxide`, `neovim`, `btop`, `cava`, `grim`, `slurp`, `swappy`, `jq`, `libnotify`, `playerctl`, `pavucontrol`, `pipewire`, `pipewire-pulse`, `wireplumber`, `wlsunset`, `polkit-gnome`, `qt6ct`, `adw-gtk3`, and `papirus-icon-theme`. JetBrains Mono and a Nerd Font symbols font provide the intended metrics and icons.

The contextual guide uses the locally packaged `superhold` and its Qt 6,
layer-shell-qt and keyboard-input dependencies. Its [portable guide](../../projects/superhold/README.md)
documents desktop support and exact build requirements.

`oldbook-session` deliberately owns session services once per current UID. On every Sway reload it checks the existing Waybar, SwayNC, Swayidle, PipeWire, WirePlumber, Pulse, and polkit-agent processes before starting anything. This avoids reliance on the release-dependent `/usr/libexec/pipewire-launcher` behavior and prevents duplicate panels, idle daemons, color processes, or authentication agents.

Start a new session through `oldbook-sway`, which wraps Sway in `dbus-run-session` when no session bus is already present. For a pre-existing Sway process that lacks `DBUS_SESSION_BUS_ADDRESS`, `oldbook-session` uses the user runtime bus when available or starts a user-local bus and passes it to the desktop services it launches. It never uses the systemd-specific `dbus-update-activation-environment --systemd` path because this is an OpenRC setup.

## Activation

Run the repository deployment tool after its package and wallpaper stages:

```sh
~/.files/alpine/bin/deploy-home --target "$HOME"
```

Start a new session with `oldbook-sway`; reload a deployed session with `Super+Ctrl+Shift+C`. Verify the panel, launcher, notification popups and history card, sound, and lock screen in the active session before treating the configuration as accepted. For local machine overrides, place a separate file in `~/.config/sway/local.d/`; this is useful for external displays and intentionally not part of the reproducible overlay.

The configured display mode is the native internal panel. Do not copy it to an external display until its supported modes have been inspected with `swaymsg -t get_outputs`.

## Everyday controls

| Control | Action |
| --- | --- |
| `Super+Enter`, `Super+D` | Ghostty terminal, Spaceghost application menu |
| Super + backtick (\`) | Toggle the persistent drop-down console |
| `Super+~` (`Super+Shift+grave`) | Toggle a separate persistent btop system monitor in Foot |
| `Super+C`, `Super+Shift+C` | Center the active window and bring it forward |
| `Super+Ctrl+Shift+C` | Reload Sway configuration |
| `Super+Tab` or `Alt+Tab` | Browse all windows in recent-use order; add Shift to reverse, release Super/Alt to select, or Escape to cancel. |
| `Super+Shift+Space` | Float the window, size it to 90% of usable space, and center it with breathing room. |
| Four-finger swipe up / down | Clear the desktop / restore its windows. Down opens the all-workspace carousel when nothing is hidden. |
| `Super+0` | Workspace **10: Strata**, after workspaces 1–9. |
| Hold `Super` alone for half a second | Show contextual shortcuts; release or press another key to dismiss. Scroll the guide without taking keyboard focus. |
| `Super+Escape` | Lock with the installed `swaylockd` PAM-compatible binary |
| `Print`, `Shift+Print`, `Ctrl+Print` | Full display, selected region, focused-window screenshot |
| Volume and microphone keys | PipeWire `wpctl`, with a PulseAudio-compatible fallback |
| Brightness keys | Kernel backlight steps, with a clear notification if the seat lacks write permission |
| Keyboard illumination keys (`F5` / `F6` on the MacBook) | Dim / brighten the keyboard by 10%, including fully off; also available while locked |
| Click the panel audio icon | Open pavucontrol |
| Click the notification glyph | Toggle the compact notification history card |
| Command/Super + left click the artwork icon | Generate a new Space Ghost image and switch to it |
| Shift + left click the artwork icon | Edit shared artwork guidance and scene prompts |
| `Caps Lock` | Escape (including with Shift); the original Escape key still works |

The shortcut guide starts through `sway/local.d/shortcuts.conf` and stays hidden
while the session is locked or inactive. It combines Sway bindings with relevant
application profiles; profiles are useful baselines, not exhaustive shortcut lists.
`oldbook-shortcuts status` reports its state. The default trigger remains Super,
so Caps Lock retains its Escape behavior and notification indicator.

Window switching is shared by both Tab shortcuts. Hold the modifier to browse
a frozen list; repeated quick taps alternate between your two most recent
windows. Ordinary Tab and Ctrl+Tab stay with the application. Agent navigation
remains on Super+i and Super+Shift+i. The gesture-opened carousel stays open:
use arrows, Tab/Shift+Tab, the wheel or a card click; Enter selects and Escape
returns to the window you started from. Its angled previews are captured from
each exact window, including other workspaces, without moving focus. Images
stay in process memory and are discarded when the carousel closes.

Leaving an exposed desktop ends that expose session and restores the captured
output where necessary, preserving the workspace you chose. The warm
`oldbook-carousel daemon` and `oldbook-showdesktop daemon` start with Sway and
use per-session locks. For local recovery, Escape leaves the carousel mode;
`oldbook-carousel cancel` and `oldbook-showdesktop restore` dismiss either view.

The MacBook keyboard light uses the kernel's `applesmc` LED device
`smc::kbd_backlight`; the existing `brightnessctl` udev rule and `input` group
allow control without root. `oldbook-keyboard-backlight` accepts `up`, `down`,
`toggle` and `restore`. It saves the chosen brightness (including off) under
`~/.local/state/oldbook/keyboard-backlight` and restores it at Sway login; first
use preserves an existing level or enables 25% brightness. Sway reloads do not
reset it. With this MacBook's unchanged `hid_apple` setting `fnmode=3` (auto),
`F5`/`F6` adjust the light and `Fn+F5`/`Fn+F6` remain application function keys.

The artwork icon opens the gallery with left click, advances with right click,
pauses with middle click, and scrolls previous/next. Its small
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

Every tmux theme loads `~/.config/tmux/oldbook.conf` for the personal controls
carried over from the historical config: `Ctrl+A` prefix (twice to send a literal
`Ctrl+A`), `v`/`|`/Enter for side-by-side splits, `s` for top/bottom splits,
`h/j/k/l` for pane selection, `H/J/K/L` or `</+/-/>` for resizing, `Ctrl+h/l`
for previous/next window, and Tab for the last pane. Windows and panes start at
1; prefix+0 selects window 10. Copy mode uses vi keys with `v` to select and `y`
to copy. Mouse, clipboard, focus events and 10,000 lines of scrollback are
enabled. These controls survive theme switches; each theme supplies its colors
and status line. Deploy the shared file with
`alpine/bin/deploy-home --only .config/tmux/oldbook.conf`, then reload with
`tmux source-file ~/.tmux.conf`. The scrollback limit applies to newly created
panes; existing panes retain their current limit.
The overlay does not source the historical plugin bootstrap or install a plugin
manager. The shell, Neovim, btop, and cava configs likewise use only installed
programs and built-in features.
