# MBP Intel profile for Bazzite Sway

This profile replays the portable desktop pieces from `alpine/desktop` onto a
Bazzite HOME. It uses an explicit allowlist, Bazzite systemd user services and
the existing `alpine/bin/deploy-home` journal. Alpine APKs, OpenRC services,
radio/privacy services, firewall controls and native musl binaries are not
included.

Run these commands from a Git or Fossil checkout of the `alpine-oldbook`
branch. Preview and check do not change desktop files:

```sh
bazzite/bin/mbp-intel-bazzite-profile preview
bazzite/bin/mbp-intel-bazzite-profile check
bazzite/bin/mbp-intel-bazzite-profile apply
```

`apply` prints the exact backup directory. Restore it with:

```sh
bazzite/bin/mbp-intel-bazzite-profile rollback \
    "$HOME/.local/state/mbp-intel/backups/<printed-id>"
```

Re-run preview after pulling the mirror branch, inspect the changes, then run
apply. Managed links depend on the checkout remaining at its current path.
Gallery generation also uses the checkout as its source of prompts, themes and
artwork. A Git-only clone can preview, apply and roll back the desktop, but
generated-art checkpoints and the Super+6 Strata browser are unavailable. Use
the repository's documented Fossil bootstrap so the checkout has its local
`~/.local/share/fossil/files.fossil` database and those features work. `check`
reports the missing database on Git-only hosts.

## Runtime prerequisites

The Bazzite image must provide Sway with `sway-systemd`, Waybar with CFFI
support, SwayNC, swayidle, Foot, Fuzzel, Ghostty, Conky, btop, Thunar,
NetworkManager, PipeWire/WirePlumber, brightnessctl, grim, slurp, jq, wl-clipboard,
libnotify, playerctl, pavucontrol, Python 3, PyGObject GTK 3, python-dbus,
GtkLayerShell introspection, PyQt 6, mpv, yt-dlp, Fossil and Firefox. Provider CLIs and their
notification hooks remain per-user installs. The image must disable LXQt's
notification daemon so SwayNC alone owns `org.freedesktop.Notifications`.

The image must also package Fedora/glibc Superhold, including its `superhold`
command and `libsuperhold-layer-shell.so` bridge under `/usr/lib64/superhold`
or `/usr/lib/superhold`. The replay wrapper uses that installed build; it never
loads the Alpine native package.

The Bazzite transform runs the image's stock `swaylock` in the foreground. Its
documented `-R/--ready-fd` interface and every configured indicator, color,
image and scaling option match the guarded Alpine invocation. Validate both
manual locking and swayidle on the real host before treating the replay profile
as usable.

Bazzite's systemd session owns D-Bus, PipeWire, WirePlumber and policy-kit. The
profile never starts duplicate media/session daemons. The checked-in user units
start the MBP Intel panel, notification center, idle lock, workspace labels,
shortcut overlay, attention indicator and wallpaper rotation with the Sway
session. The fixed MacBook `eDP-1` mode is removed; put machine-specific output
configuration in `~/.config/sway/local.d/` after applying.

The Caps Lock attention LED still needs a Fedora udev/SELinux rule granting the
desktop user write access to the relevant LED brightness nodes. Until the image
adds and validates that rule, the helper reports the permission failure and
leaves the key mapping itself unchanged.

## Native artwork button

The Alpine `/usr/lib/waybar/mbp-intel-art.so` is a musl build and is deliberately
excluded. Do not run `dnf5 install` on the immutable host. Add the development
packages and compilation below to the custom image build, or run the commands
inside a matching Fedora toolbox/distrobox whose HOME is shared with the host.
The resulting library belongs at the per-user path materialized into Waybar:

```sh
dnf5 install gcc pkgconf-pkg-config gtk3-devel json-glib-devel
install -d -m 755 "$HOME/.local/lib/mbp_intel"
cc -shared -fPIC -O2 -Wall -Wextra -Werror \
  -Wl,-z,relro,-z,now \
  -I alpine/packages/waybar-art \
  -o "$HOME/.local/lib/mbp_intel/mbp-intel-art.so" \
  alpine/packages/waybar-art/art.c \
  $(pkg-config --cflags --libs gtk+-3.0 json-glib-1.0)
```

When building in a toolbox, confirm its Fedora release and architecture match
the host. Run `mbp-intel-bazzite-profile check` afterward and exercise the module
with the installed host Waybar before restarting the live bar. The native
module preserves left/right/middle/scroll gallery actions plus Super-click
generation and Shift-click prompt editing. The source header targets Waybar's
CFFI ABI version 2, so the image build must compile and exercise the module
against its exact Waybar release before declaring the profile supported.

The profile tests run on Alpine with disposable HOMEs and prove allowlisting,
preview, journaled apply/rollback, hardware-neutral Sway output, source-checkout
anchoring, and transformed Waybar behavior. A real Bazzite boot, systemd user
session, NVIDIA compositor, Fedora-built CFFI module, LED permissions and full
native GUI interaction remain host validation requirements.

## Minimal image integration

The image repository only needs to install the prerequisites, remove the LXQt
notification autostart, add the reviewed LED permission rule, and test this
profile at a pinned `Spaceghost/.files` `alpine-oldbook` commit. Fetch that
public commit in the workflow with persisted checkout credentials disabled.
Do not copy the whole checkout into the image and do not pass Codex, Claude,
GitHub, SSH, Wi-Fi or registry credentials to the container build. Keep the
profile application explicit through a `ujust mbp-intel-apply` wrapper so image
updates cannot overwrite an existing HOME.
