# Superhold sections read from the most local context outward

The guide put the desktop second, immediately after the focused application,
and left the terminal and tmux below it. That is backwards for how the contexts
actually nest: the focused application runs inside tmux, which runs inside its
terminal, which runs on the desktop, which runs on the machine. The order is
now application, tmux, terminal, desktop, system controls, with profile
diagnostics last, so each section is one step further out than the one above
it and the desktop sits immediately before the system-wide controls.

The order is no longer a property of the code that builds the sections.
`superhold/sources.py` collects sections into a mapping keyed by name and
`Sections.arrange` in `superhold/config.py` decides what is shown and in what
sequence. An optional `[sections]` table in `~/.config/superhold/config.toml`
reorders sections, hides them, renames them, and defines custom sections of
`key`/`description` rows that are ordered, renamed and hidden exactly like the
built-ins. Sections omitted from `order` keep their default place after the
listed ones, so a partial list stays valid when a new section kind appears.

Validation follows the existing profile rules: single tidy display lines, no
control characters, bounded counts, custom coverage that must begin with
`Partial`, and custom names that may not shadow a built-in. An invalid table
fails at load with a named error, the same way an invalid `trigger` already
does, rather than being silently ignored.

Three implementations exist and all three now share the default order.
`projects/superhold-guide` (0.2.0.dev1) is the one that actually runs: Sway
starts `~/.local/bin/superhold daemon`, which resolves to an installed venv
under `~/.local/share/superhold/versions/`. It gets the same feature through a
`sections` object in `~/.config/superhold/config.json`, and because the daemon
already re-reads its settings once a second while idle, an edit takes effect
without a restart. `projects/superhold` (0.1.0) is the portable Qt project
behind the `oldbook-shortcuts` wrapper and reads `config.toml`. The legacy
overlay under `alpine/desktop/.local/lib/oldbook/`, reachable only with
`OLDBOOK_SHORTCUTS_LEGACY=1`, takes the default order and gains no settings,
because inventing a third configuration format for a path behind an escape
hatch would cost more than it returns.

The running guide's `AppConfig` is a frozen dataclass whose fields are all
hashable, so `SectionLayout` stores tuples rather than dicts and converts to
and from plain JSON at the file boundary. That keeps `save_config`'s existing
guarantees — atomic writes, unknown fields preserved, malformed files never
replaced — working unchanged.

The GTK settings window is untouched; sections are edited in the file. An
editor for them is a larger piece of UI and a separate decision.

Reversal: remove `SectionLayout` and the `sections` field from each config
module and restore the ordered `sections.append` calls in all three
implementations. Checks: `projects/superhold-guide/tests/test_config.py` and
`tests/test_shortcut_sources.py`, `projects/superhold/tests/test_config.py` and
`tests/test_sources.py`, and `alpine/tests/test_shortcut_sources.py`.
