# Validation

The standalone extraction carries 62 input, Sway/tmux parsing, and lifecycle
regression tests. Four portability tests cover independent XDG configuration,
relative-path fallback, logind lock suppression and the version command.
All 66 tests passed locally on Alpine with Python 3.14. The same tests and
wheel/sdist builds passed in Python 3.10 and 3.14 Alpine containers in
[GitHub CI](https://github.com/Spaceghost/.files/actions/runs/34122749336).

The original source feature was validated on an isolated Sway compositor for
hold/release/chord behavior, nonfocusable overlay mapping, mouse scrolling,
multiple outputs, included Sway files, process lifecycle and session locking.
Those checks establish the source baseline; they do not establish that a full
LXQt session has been tested. The release snapshot does not change the live
Oldbook installation.

Standalone checks performed during preparation are recorded in
`validation.json`. Before release, complete these manual checks on a clean
LXQt with Sway session:

- Fresh login/autostart, single running process, logout and compositor exit.
- Both Super keys, quick taps, chords before and after the hold threshold.
- Keyboard hotplug and inaccessible input devices; no change to permissions.
- QTerminal and PCManFM-Qt identity, profile coverage and menu-launch focus.
- Pointer scrolling and touchpad scrolling without keyboard focus transfer.
- Two monitors, mixed scale, fullscreen app and loading on the focused output.
- Screen locker, virtual terminal switch and fresh press after returning.

LXQt on X11 or another compositor is outside this backend's release scope.
