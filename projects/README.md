# Which shortcut guide is which

Three directories here contain a program called Superhold, and only one of them
is the program that runs on this machine. They are separate codebases with
different module names, different toolkits and different configuration files,
so a change made in the wrong one is silently invisible. Read this before
editing any of them.

| Directory | What it is | Does it run here? |
| --- | --- | --- |
| [`superhold-guide/`](superhold-guide/) | GTK 3, `0.2.0.dev1`, modules named `shortcut_*.py` under `src/superhold/`. Settings in `~/.config/superhold/config.json`. | **Yes.** This is the one. |
| [`superhold/`](superhold/) | Qt 6, `0.1.0`, modules named `sources.py`, `qt_overlay.py`, `service.py`. Settings in `~/.config/superhold/config.toml`. | No. Reachable through the `oldbook-shortcuts` wrapper only. |
| [`hold-to-help/`](hold-to-help/) | The pre-rename name, kept so the old command and import path still resolve. | No. |

There is also `~/src/superhold`, outside this repository and outside Fossil: an
older standalone checkout missing the Super-key dismissal fixes. Nothing reads
it. It is not a place to make changes.

## How the running guide is started and installed

Sway starts it from `desktop/.config/sway/local.d/shortcuts.conf`:

```
exec_always --no-startup-id ~/.local/bin/superhold daemon
```

`~/.local/bin/superhold` is not a symlink into this checkout. It is a two-line
wrapper pointing at an installed virtualenv under
`~/.local/share/superhold/versions/<version>-<source hash>/`, whose
`site-packages/superhold/` holds a **copy** of `superhold-guide/src/superhold/`.
Editing this checkout therefore changes nothing that the keyboard reaches until
that copy is updated and the daemon is restarted. This is deliberate: the
installed prefix is hash-verified so it can be rolled back, and
`../alpine/packages/superhold-guide/manifest.json` records what was packaged.

To make a source change take effect:

1. Copy the changed modules into the installed prefix, preserving the previous
   files somewhere under `~/.local/state/oldbook/` so the change is reversible.
2. Restart only the daemon, with the Sway session's own environment.
3. Re-record the changed files' digests in
   `~/.local/share/superhold/backups/<version>/manifest.json`, because
   `switch.py` refuses to roll back or reactivate when a preserved file's hash
   no longer matches. Skipping this step leaves `~/.local/bin/superhold-rollback`
   broken.

`~/.local/bin/superhold-rollback` returns to the preserved previous prefix; the
matching `switch.py activate` restores this one.

## Keeping the three in step

The default section order — the focused application, then tmux, then its
terminal, then the desktop, then system-wide controls — is shared by all three
implementations and by the legacy overlay in
`../alpine/desktop/.local/lib/oldbook/shortcut_sources.py`. So is the rule that
the guide's own window is never treated as the context to describe. Only the
running guide and the portable Qt project carry the settings that reorder,
hide, rename and add sections; the legacy overlay takes the defaults and offers
no configuration.
