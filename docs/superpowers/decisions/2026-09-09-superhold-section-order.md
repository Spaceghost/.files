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

Superhold is the running implementation. The legacy overlay under
`alpine/desktop/.local/lib/oldbook/` — reachable only with
`OLDBOOK_SHORTCUTS_LEGACY=1` — takes the same default order and gains no
settings, which keeps one arrangement across both paths without duplicating a
second configuration format.

Reversal: remove the `[sections]` table handling and `Sections` from
`superhold/config.py` and restore the ordered `sections.append` calls in both
implementations. Checks: `projects/superhold/tests/test_config.py`,
`projects/superhold/tests/test_sources.py` and
`alpine/tests/test_shortcut_sources.py`.
