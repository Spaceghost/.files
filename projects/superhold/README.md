# Superhold

Hold Super alone for half a second to see a contextual shortcut guide. Release
it or press another key to dismiss it. Scroll with the pointer wheel while the
focused application keeps keyboard focus.

Superhold is a standalone Linux desktop utility extracted from Oldbook. Version
0.1.0 is a local release candidate, ready for packaging and review; it is not an
official LXQt component.

## Naming and migration

Superhold is the project, package and primary command name. The earlier local
Hold to Help candidate was not publicly released. Installed commands are
`superhold` and the compatibility command `hold-to-help`. From the source tree,
or with the module directory on `PYTHONPATH`, `python -m superhold` is primary
and `python -m hold_to_help` remains compatible. CMake installs Python modules
under `share/superhold`, outside the ordinary Python import path; its command
launchers locate that directory automatically.

Configuration now lives in `$XDG_CONFIG_HOME/superhold` (normally
`~/.config/superhold`). Each default file independently falls back to the same
filename in `hold-to-help` only when the new file is absent. Invalid new files
are errors, and explicit `--config` / profile paths keep their existing behavior.
No configuration files are moved or rewritten automatically.

The runtime lock/status directory deliberately remains
`$XDG_RUNTIME_DIR/hold-to-help`: old and renamed clients share the same display
lock, so installing the rename cannot create a duplicate overlay beside an
already-running daemon. Existing daemons need no immediate restart. The old
source-checkout path contains small regular compatibility wrappers; release
archives contain only regular manifest-listed files.

Native builds install `libsuperhold-layer-shell.so` under `lib/superhold`.
`SUPERHOLD_LAYER_SHELL_LIBRARY` is the primary explicit override. The previous
`HOLD_TO_HELP_LAYER_SHELL_LIBRARY` is also accepted, and the new library exports
thin deprecated `hth_layer_shell_*` forwarders alongside `superhold_layer_shell_*`.
The Alpine package preserves the old library path with a compatibility link;
portable CMake installs use only the new path, so users must update an old
explicit override or retain the old library. The loader can still use that old
library's ABI. Qt inherits the desktop palette, fonts and style; Super held
alone for 0.5 seconds remains the default trigger.

## Desktop support

| Session | Context and input | Requirements |
| --- | --- | --- |
| Sway / SwayFX | Sway bindings and includes, active mode, focused app, terminal/tmux; physical hold | Sway IPC, Wayland, layer-shell-qt, readable evdev keyboard |
| X11 / Openbox / LXQt | EWMH focused app, configured Openbox/LXQt shortcuts, terminal/tmux; physical hold | python-Xlib, XInput2, xkbcomp, EWMH window manager |

Application profiles are labeled baselines or user additions, not an exhaustive
shortcut API. Other Wayland compositors need a backend and a supported global
input mechanism. Installing LXQt's theme plugin alone does not add LXQt shortcut
configuration to a Sway session.

## Install from source

Requirements: Python 3.11+, PyQt6, python-Xlib (X11), Qt 6.10+ development files,
layer-shell-qt 6.6+ development files (Wayland), CMake 3.20+, and a C++17 compiler.
Use packages provided by your distribution. On Alpine:

```sh
doas apk add python3 py3-qt6 py3-xlib xkbcomp dbus qt6-qtwayland layer-shell-qt
doas apk add build-base cmake qt6-qtbase-dev layer-shell-qt-dev
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local
cmake --build build
ctest --test-dir build --output-on-failure
doas cmake --install build
```

Use `-DBUILD_WAYLAND=OFF` for an X11-only installation. A signed, reproducible
Alpine recipe and offline builder live in `alpine/packages/superhold` in the
parent repository. No npm or downloaded Python wheels are needed.

## Use and configure

```sh
superhold daemon
superhold dump
superhold preview --seconds 5
superhold status
```

Copy `examples/config.toml` to `~/.config/superhold/config.toml` to select
`trigger = "capslock"` or change `hold_seconds` (0.15–3 seconds). The trigger is
physical: selecting Caps Lock does not disable its normal toggle or change
your Caps-to-Escape mapping. The default remains Super. Override session
detection with `--backend sway` or `--backend x11`.

Copy `examples/profiles.json` to `~/.config/superhold/profiles.json` and replace
the example with your application's identity and shortcuts. XDG_CONFIG_HOME is
respected. `--profiles PATH` keeps an existing profile collection usable.

Add `exec_always --no-startup-id superhold daemon` to Sway, or copy the supplied
desktop entry to `~/.config/autostart/` for X11/LXQt. Do one per session; duplicate
instances are rejected. The package does not enable autostart automatically.
`--help` lists diagnostic options without requiring a running display.

## Theme integration

The guide uses QPalette, QStyle and Qt's application fonts. It does not set
`QT_QPA_PLATFORMTHEME`, choose Fusion, or embed Gruvbox colors. LXQt can supply
its normal Qt platform theme; other desktops can use their own plugin or qt6ct.
Oldbook's existing qt6ct palette supplies local Gruvbox Dark.

Palette and font events update the visible guide. A desktop plugin that only
loads settings at startup requires restarting the guide after a theme change.
There is no universal cross-desktop theme-change protocol. Generic keyboard
icons follow the active icon theme.

## Development and release

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
python3 tools/make-release.py --output /tmp/superhold-0.1.0.tar.gz
```

Native checks use private displays and synthetic context:

```sh
python3 tools/verify-x11.py --theme qt6ct --output /tmp/superhold-x11-qt6ct
python3 tools/verify-x11.py --theme lxqt --output /tmp/superhold-x11-lxqt
python3 tools/verify-x11-daemon.py --output /tmp/superhold-x11-daemon
python3 tools/verify-wayland.py --library build/native/libsuperhold-layer-shell.so --output /tmp/superhold-wayland
```

The X11 check needs Xvfb and Openbox; Wayland requirements are listed by the
verification tool's `--help`. Neither test takes over your active display.

The release helper archives only the reviewed paths in `SOURCE_MANIFEST`, with
sorted entries, fixed ownership and timestamps. Keep build outputs, caches and
credentials out of that manifest. Release artifacts
must pass the tests, native focus/input checks, and two isolated APK builds.
Keep the recipe's pinned source digest synchronized with the final archive.
See CONTRIBUTING.md for review expectations. Before public submission, choose
the public project location and maintainer contact and publish the reviewed
source archive; no registry or upstream reservation is implied by this name.

## Privacy and licensing

The guide runs as the desktop user, does not grab keys, log typed text, or send
telemetry. Sway's existing device read permissions are required; the package
does not grant broad input-group or root access. Shortcut context inspects local
window metadata, configuration, process identity, and live tmux key tables.

Superhold is GPL-3.0-or-later; see LICENSE. Qt, PyQt6, layer-shell-qt and
python-Xlib remain separately distributed dependencies under their respective
licenses. The original contextual guide was developed for Spaceghost's Oldbook
configuration; this project preserves that lineage without claiming LXQt
endorsement.
