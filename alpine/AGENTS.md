# Persistent desktop preferences

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
