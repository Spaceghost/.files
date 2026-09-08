# Hold to Help

## Intent

Extract the contextual shortcut guide into a standalone, publishable desktop
utility. Preserve the existing hold/release, scroll, Sway, tmux, and application
profile behavior. Use the active desktop's Qt palette, font, and style. This
MBP Intel uses Gruvbox Dark through qt6ct; the released application must not force
that theme on LXQt or other desktops.

## Boundaries

- Name: **Hold to Help**, command `hold-to-help`, initial version `0.1.0`.
- License: GPL-3.0-or-later; dependencies retain their own licenses.
- Python 3.11+, PyQt6, Qt6, CMake; no npm or bundled language runtime.
- Sway on Wayland uses layer-shell-qt and the existing readable evdev devices.
- X11 uses EWMH context, XInput2 key edges and XQueryKeymap without grabbing keys or devices.
- LXQt/Openbox shortcuts are parsed where configured; application shortcut
  coverage is explicitly partial. No claim of universal Wayland support or
  upstream LXQt adoption.
- Configurable `super` or `capslock` physical hold trigger, default 0.5 seconds.
  Preserve the current Super trigger and Caps-to-Escape mapping locally until
  the user's intended Caps Lock feature is confirmed.
- Overlay never takes keyboard focus. Release, another key, session lock,
  inactive graphical session, or lost compositor connection hides it.
- Pointer scrolling remains available. Context work runs outside the GUI thread;
  stale results cannot reopen the overlay after release.
- Configuration lives under `$XDG_CONFIG_HOME/hold-to-help/`; a compatibility
  wrapper preserves `mbp-intel-shortcuts` and existing custom profile paths.

## Architecture

`hold.py` owns input state, `sources.py` and `profiles.py` collect labeled shortcut
sections, `service.py` coordinates asynchronous collection and session lifetime,
and `x11.py` supplies X11 context/input. `qt_overlay.py` renders plain text using
QPalette, QStyle and application fonts. A small C ABI library connects PyQt's
QWindow to layer-shell-qt; it links the distribution's Qt, not a bundled copy.
`cli.py` implements daemon, dump, preview, status, and diagnostic flags.

## Distribution and proof

Ship a standalone CMake source archive, desktop entry, manual, configuration
examples, contributor documentation, and Alpine APKBUILD. Build without network
access twice from a pinned archive and compare artifacts. Preserve source, APKs,
dependency closure, checksums, commands, and evidence in Fossil. Test real X11
and nested Sway windows, palette updates, focus preservation, input cancellation,
and scrolling. Install locally without restarting the user's compositor.
Prepare artifacts for publication; uploading or proposing upstream inclusion
is a separate user-authorized step.
