# Persistent desktop preferences

The 0 key selects workspace 10. Keep STRATA on numeric workspace 10, displayed
after workspaces 1–9; do not introduce a separate workspace 0 for it.

Every desktop theme must be complete. The user explicitly rejects palette-only
themes; do not introduce that category or treat recoloring a few overlays as a
finished theme. Generated themes have the same requirement as built-in themes.
Theme switching must apply the theme across the desktop and applications;
silently retaining the previous theme's application styling is incomplete.

Conky is a slow information display, not a system monitor. Preserve the user's
explicit choice across theme changes, wallpaper pairing, template updates and
rebuilds: no CPU/load/frequency, memory/swap/process, storage I/O, network or
thermal telemetry. Waybar owns those stats. Battery charge/status is allowed.
Keep date, Scripture, gallery notes and rotating text; email is welcome when a
mailbox source is configured. Periodic refreshes must be 60–300 seconds.

Do not restore historical reactor, memory, storage or transmission panels.
Keep the runtime guard in `desktop/.local/lib/oldbook/conky_policy.py` and its
integration in `conky_layout.load_panels`. Run
`python3 -m unittest discover -s alpine/tests -p 'test_conky*.py' -v` from the
repository root for changes touching these templates, layout or refresh logic.
Explicit new user preferences may change this policy; incidental artwork or
layout work must not.

Rotating desktop text lives in the user's SQLite journal at
`~/.local/share/oldbook/journal/entries.sqlite3`, accessed through `oldbook-journal`.
Do not restore JSON/random-line rotation. Preserve the original Coast to Coast
voice: three quips for each journal note.
Preserve all eight original lines and the four-minute interval,
one-time legacy import, full stored entries and backup support. Dated journal
notes must describe observed events; do not invent personal experiences or
collect private activity automatically. The live database is personal data and
must not be committed; only the reviewed seed collection is versioned.

Scripture shortcuts: Super+/ searches only Bible verses. Super+Shift+/ searches
all collections, with Bible results after Torah, Talmud and reflections. Do not
add non-Bible results or collection-switch commands to the Bible-only picker.
Enter must save the choice and refresh only the Scripture card immediately;
keep background refresh intervals at 60–300 seconds. Preserve the offline
English Torah (JPS 1917) and Babylonian Talmud (William Davidson) collection,
source manifests and attribution alongside the Bible and curated reflections.

Keep Conky placement stable through window, focus and fullscreen changes; the
user prefers no automatic reflow to abrupt motion or continuous CPU work.
Use fixed caption clearance when laying out cards, favor useful lower-right
space, and preserve native click-to-advance on the reading cards. Scripture
search may adapt to free/occupied edges and must follow the active theme.
