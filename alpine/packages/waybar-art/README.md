# Artwork button for Waybar

This small native musl CFFI widget adds **Command/Super + left click: generate and
switch**. Existing controls remain: left click next, right click gallery, middle
click pause, scroll up previous and scroll down next. It displays the complete
tooltip, icon and state classes from `oldbook-wallpaper status` without rewriting
the help text. Other panel modules are unchanged.

Waybar 0.15 has no custom-module modifier mapping. Its documented CFFI ABI lets
this widget handle only its own pointer events. Unfocused layer-shell panels
receive no GTK keyboard modifiers, so the callback also checks the current
Left/Right Meta state with Linux `EVIOCGKEY`. The desktop user needs read access
to `/dev/input/event*`, supplied here by the existing `input` group membership.
It never reads the input event stream, stores key history, changes focus or adds
global Sway bindings. This implements the MacBook's physical Command keys.

## Build and install

Source and the upstream ABI header are versioned in this checkout. The recipe
needs `build-base pkgconf gtk+3.0-dev json-glib-dev`; development headers are not
runtime dependencies. Restore the package lock before rebuilding exact inputs.

```sh
alpine/packages/waybar-art/build-offline --work /tmp/waybar-art-build
doas apk add /tmp/waybar-art-build/apks/oldbook/x86_64/oldbook-waybar-art-1.0.0-r0.apk
```

The helper creates a fresh work directory and builds with networking disabled,
using the build user's private abuild key outside the checkout. The library is
installed at `/usr/lib/waybar/oldbook-art.so`; configuration remains symlinked to
`alpine/desktop/.config/waybar/config.jsonc`. Source edits require rebuilding the
package and restarting Waybar. `verification.json` records two-build hashes.

## Verify

```sh
alpine/packages/waybar-art/verify-headless --module /usr/lib/waybar/oldbook-art.so --output /tmp/waybar-art-test
```

The test requires `sway waybar build-base pkgconf wayland-dev grim` and `doas` for a temporary
uinput keyboard. It disables that exact synthetic device in existing Sway
sessions before creation, injects real Command state and pointer events into a
contained panel, and dispatches every action to a stub. It never generates an
image. Screenshots and nine interaction checks are retained in the output.

![Preserved controls and added Command-click help](interaction-preview.png)

Upstream: [CFFI ABI documentation](https://github.com/Alexays/Waybar/blob/0.15.0/man/waybar-cffi.5.scd),
[standard event mapping](https://github.com/Alexays/Waybar/blob/0.15.0/src/AModule.cpp).
