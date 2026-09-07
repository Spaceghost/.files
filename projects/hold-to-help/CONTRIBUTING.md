# Contributing

Use Python 3.11 or newer, four spaces, explicit imports, and standard-library
unittest. Native code uses C++17 and the distribution's Qt6 and layer-shell-qt.
Keep the input state machine, context discovery, service lifetime and rendering
separate. Do not grab keys, force desktop colors, or collect network telemetry.

Run `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v`
from this directory, then build and run CTest as described in README.md.
Input and session changes also require native Sway and X11 checks: keyboard
focus must remain with the original application, stale work must stay hidden
after release, and a locked or inactive session must suppress the guide.

Profiles must name their source and coverage honestly; do not present a
maintained baseline as a complete application API. Test parsing using temporary
configuration files, including missing, malformed, and hostile display text.
Qt tests must exercise palette changes and plaintext labels.

This source currently lives at `projects/hold-to-help` in the Spaceghost dotfiles
Fossil checkout. Use concise scoped commit subjects, such as `hold-to-help: fix
release cancellation`. Reviews should describe the trigger, resulting behavior,
tests, supported desktop/version, and screenshots for visual changes. Preserve
existing shortcut sources and interactions unless a change explicitly requires
their removal. Contributions use GPL-3.0-or-later.
