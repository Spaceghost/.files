# Console and monitor shortcut verification

Eight native check groups passed in a private HOME, XDG directories, SwayFX
compositor and non-activating D-Bus. A virtual keyboard used the actual US XKB
layout and evdev KEY_GRAVE (41), verifying Mod4 produces grave and Mod4+Shift
produces asciitilde. The bindings launched separate real Ghostty windows, with
btop running in the monitor; independent hide/show retained both window IDs and
processes. The private processes were cleaned up after verification.

The initial temporary harness tried typing before the shell was ready; it was
corrected to wait for Ghostty's started-subcommand event. That diagnostic remains
in `/tmp/oldbook-dropdown-key-check/`; no production failure was identified.
The reproducible native driver/harness is retained there as `verify.py` and
`us-key.c`. The images here contain only the isolated test desktop.

Full actual SwayFX configuration validation had no errors or duplicate bindings.
All 22 existing shortcut-source tests passed. `activation.json` records targeted live
binding installation and monitor/console identity checks. Physical human keypresses and a new
login remain unobserved; the actual US keymap was exercised through native input.

Recovery and behavior: `docs/superpowers/decisions/2026-09-07-console-monitor-shortcuts.md`.
