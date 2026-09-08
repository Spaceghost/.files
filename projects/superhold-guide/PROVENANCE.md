# Superhold shortcut guide — vendored source

This is the shortcut guide that is actually installed and running: the GTK
layer-shell overlay with the search box, click-to-run actions, the settings
window and `dismiss_mode = focus_loss`, which is what keeps the guide on
screen after Super is released.

It is **not** the same program as `projects/superhold`. That one is a
portable Qt rewrite, version 0.1.0, with its own `qt_overlay`, `hold`,
`service` and `x11` modules and no search. The two share a name and nothing
else; this repository now carries both rather than pretending one supersedes
the other.

Mirrored from `/home/jack/src/superhold`, a local git checkout with no
remote, at version 0.2.0.dev1
(git HEAD 70e5051).

The local palette support in `src/superhold/theme.py`, and its use in
`shortcut_overlay.py` and `shortcut_window.py`, was uncommitted in that
checkout when this mirror was taken. Vendoring it here is the point: the
installed wheel is built from these files, so without them a reinstall of
superhold silently restores the hardcoded purple overlay.
