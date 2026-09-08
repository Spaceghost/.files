# Validation

## Desktop themes — 0.2.0.dev1

The theme update passes **134 automated tests** on Alpine/Python 3.14, including
nine new cases for live stylesheet changes, symlink targets, atomic replacement,
invalid/missing-file recovery, bounded reads, and provider/timer cleanup.

An isolated graphical comparison reproduced the old purple panel despite GTK
exporting Gruvbox colors. The updated persistent guide used the shared Gruvbox
palette and then changed to a light palette in the same visible window. Search,
results, selected text, shortcut buttons, and the scrollbar followed the new
colors. The release overlay and preview also followed symlink-target changes and
recovered after malformed CSS. These checks did not change the installed theme
or send keyboard shortcuts to the host desktop.

Screenshots: [Gruvbox](theme-gruvbox.png) and [live light palette](theme-light.png).

## Interactive application — 0.2.0.dev0

The `0.2.0.dev0` standalone application passes **125 automated tests** locally
on Alpine with Python 3.14. Coverage includes input synchronization and dropped
events, hold cancellation, configuration recovery, Sway/tmux source parsing,
search alternatives, native target verification, Enter event ordering, queued
activation, initial session checks, and per-compositor process ownership.

Private headless SwayFX 0.6 (Sway 1.12.0) sessions verified:

- The persistent guide takes focus, survives Super release, and dismisses on a
  real pointer click outside it.
- Search followed immediately by Enter sends Ctrl+Shift+S to the original GTK
  application without leaking Enter. Uppercase alternatives and multistep
  native sequences work; a real button click delivers exactly once.
- Twelve native Sway cases cover Super/Ctrl/Shift, named and numeric uppercase
  symbols, release bindings, and punctuation. A following unmodified binding
  verifies that modifiers are released after each case.
- Menu-style `show` survives initial asynchronous session checking, reuses the
  daemon PID, and remains searchable under release-mode settings. Idle settings
  reload, readable delivery errors, repeated show, SIGTERM and stopped status
  also pass.
- Settings Save, Cancel, Reset and malformed-file preservation pass in GTK.
- Fixed-size GTK windows float automatically, restore the target on hiding,
  and map on the current output after a monitor change.

The integration controller used a synthetic input monitor. Real key delivery
and pointer clicks went only to disposable compositor sockets; no physical
keyboard was exercised or host input injected. No installed configuration,
startup entry, or original MBP Intel service was changed.

Runtime evidence is in [interactive checks](runtime-interactive-validation.json),
[native Sway checks](runtime-native-validation.json), and
[focus/settings checks](runtime-focus-validation.json). Screenshots show the
[guide](guide.png), [search](search.png), and [settings](settings.png).
The wheel and source archive build with `python3 -m build --no-isolation`, and
all three desktop files pass `desktop-file-validate`. An isolated installation
with system GI bindings passed three repeat native-interaction checks; the
runtime record also retains an initial fixture focus-loss failure.

The earlier 66-test extraction passed Python 3.10/3.14 in
[GitHub CI](https://github.com/Spaceghost/.files/actions/runs/34122749336).
That result applies to `0.1.0.dev0`; the current work has not been pushed to
its intended dedicated repository. Its earlier record is retained in
[validation-0.1.json](validation-0.1.json).

## Before release

Persistent search cannot yet appear above a fullscreen application. Sway hides
the ordinary floating guide; it dismisses after one second without changing
the application's fullscreen state. Leave fullscreen before using persistent
search. The nonfocusable reference/release overlay has different compositor
behavior and does not provide keyboard search.

Complete a full LXQt with Sway session test: fresh login and optional autostart,
QTerminal and PCManFM-Qt profiles, menu focus, both physical Super keys, hotplug,
input permissions, lock/VT switching, logout, mixed monitor scaling, and
compositor exit. Select a license and make the dedicated GitHub repository
available before distribution. LXQt on X11 or other compositors remains
outside this backend's support.
