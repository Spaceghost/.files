# Spaceghost Gruvbox Dark

The warm charcoal, cream and gold desktop saved from Sharkdeck on 2026-10-28:
compact ghost launcher and Waybar, borderless Sway chrome, Foot and Ghostty,
Fuzzel, GTK 3/4, Swaylock and Swaynag colors. The manual runtime estimate,
`PLUG!` warning, power menu entry and timer shortcut are disabled.

Apply from your `.files` checkout (Python 3 standard library only):

```sh
python3 ~/.files/themes/spaceghost-gruvbox/apply.py
```

This copies appearance configuration and the bundled GTK theme, backs up every
replaced file, and includes the Sway theme in your existing config. Each run
prints its backup location and exact undo command. Close/reopen applications,
reload Sway (`swaymsg reload`) and restart your Waybar to display changes.
Existing Sway keybindings, output geometry and local hardware overrides remain.
The bar is 28 pixels tall and intentionally compact for the original 480px panel.
If your Sway bar invokes swaybar rather than Waybar, configure its
`swaybar_command ~/.local/bin/spaceghost-waybar` to use this bar.

For another Linux Wayland machine, install Sway, Waybar (with MPRIS support),
Foot, Fuzzel, Python 3, iw, iproute2 and DejaVu fonts using its package manager, then:

```sh
git clone --depth 1 https://github.com/Spaceghost/.files.git ~/.files
python3 ~/.files/themes/spaceghost-gruvbox/apply.py --desktop
```

`--desktop` also installs a portable Sway session with the saved shortcuts and
Waybar launcher. It backs up any existing Sway config. Start Sway using your
normal login/session method. There are no forced SPI outputs, touch mappings,
software rendering settings, boot edits or autologin changes in this profile.
Ghostty, Swaylock and Swaynag are optional; this does not install applications.
Bar controls for YouTube and Sharkdeck button mapping require the separate
`yt` and `sharkdeck-keys` tools from the original device. Other optional controls
use `htop`, `alsamixer`, `playerctl` and `grim` when installed.

Preview file installation without changing your desktop:

```sh
python3 ~/.files/themes/spaceghost-gruvbox/apply.py --home /tmp/gruvbox-preview --desktop
```

To undo, use the command printed by the apply script:

```sh
python3 ~/.files/themes/spaceghost-gruvbox/apply.py --restore /path/to/backup
```

The zip vendors the installed `jmattheis/gruvbox-dark-gtk` theme from commit
`04221c1317bed7a765a09f5bb00a97765ce4a711`, including its license. Apply works
offline. Terminal and panel configuration are captured directly from the device;
no credentials, runtime timer state, music accounts or machine identities are included.
Boot-console theming remains specific to Sharkdeck and is not applied here.

## Wi-Fi indicator and WalnutPi stability

The bar shows signal bars and a percentage derived from RSSI (−100 to −50 dBm
mapped to 0–100%), colored aqua/gold/red. Tooltips show SSID, dBm, link rate and
addresses. It falls back to `/proc/net/wireless` when UWE5622 omits nl80211 signal
statistics; the original Waybar network module incorrectly displayed 0% here.
Association is not a guarantee of Internet connectivity. Ethernet can coexist;
this module explicitly displays Wi-Fi status.

On WalnutPi only, apply the optional system configuration separately:

```sh
doas python3 ~/.files/themes/spaceghost-gruvbox/board/apply-wifi.py
```

This backs up the local WPA configuration, enables its local control socket,
adds higher-priority profiles for non-DFS 5 GHz while retaining original profiles
as fallback, and installs an if-up hook to disable Wi-Fi power saving. Credentials
stay in `/etc/wpa_supplicant/`; the script prints an undo command. Applying it
briefly reconnects Wi-Fi. Requires Alpine ifupdown, wpa_supplicant and iw.

Observed on this board: 2.4 GHz had driver TX timeouts and 67% gateway packet loss
in a 15-packet sample; after reconnecting on 5 GHz a 20-packet sample had zero loss
and 5.1 ms average RTT. This is short-run verification, not a long-term guarantee.
The CPU already runs up to its supported 1.416 GHz and measured about 63°C; no
unsupported clock, voltage, transmit-power or thermal-limit changes are included.

The detected AXP313a PMIC has no battery charger and `/sys/class/power_supply`
is empty. The external battery charger must be identified before any charge-rate
change is possible. No battery charge-current setting was changed.

## Switch Wi-Fi from the launcher

Press **Super+D**, type **wifi**, and open **Wi-Fi Networks**. Choose a saved
network (✓), a nearby network (+), or refresh the scan. The current connection
is marked ●. New WPA/WPA2 personal networks use a masked password prompt;
open networks ask before connecting. Failed joins restore the previous profile.
Enterprise, WEP, OWE and WPA3-only networks require advanced system setup.

The picker uses Fuzzel and `wpa_cli` with existing control-socket access, or
existing passwordless `doas`/`sudo` access. It adds no privilege rules. On Alpine
it asks the existing udhcpc process to release/renew its lease after a switch.
Successful selections are saved in the local WPA configuration and preferred at
next boot. Other enabled profiles remain available as fallback. Passwords are
converted to WPA keys in memory and passed through stdin, never command-line
arguments; credentials remain in the system WPA configuration, outside `.files`.
Keep `~/.local/bin` in your session PATH so the launcher can find the command.

Run the picker checks with:

```sh
python3 -m unittest discover -s ~/.files/themes/spaceghost-gruvbox/tests -v
```
