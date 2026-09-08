# Persistent desktop preferences

## Feature preservation contract

Read [FEATURES.md](FEATURES.md) before changing the desktop, gallery, theme
renderer, package closure or deployment. Its feature IDs pin the user's current
behavior choices; historical PROGRESS entries and older screenshots do not
override them. Run `alpine/bin/check-features <changed-path> ...` from the checkout
to identify overlapping contracts and their existing checks. Use `--run` to run
those checks, then perform the relevant native/visual verification described in
the contract. Unmapped files need review; passing unit checks alone does not
prove the live desktop or physical frame rate.

Preserve every affected contract unless the current user request explicitly
changes it. A new explicit choice authorizes updating that pin and recording
which earlier choice it supersedes. Otherwise, when two requirements actually
conflict, explain the concrete conflict and ask the user while continuing
independent work. Do not silently drop behavior, reset personal settings, use a
theme profile as permission to replace shared controls, or overwrite another
session's edits. Update the contract and check index alongside intentional
behavior changes; record validation gaps honestly in PROGRESS. Before a scoped
Fossil commit, review source/install drift and the exact paths being committed.

## Existing durable preferences

Run AI inference on the Alienware's GPUs, not on this MacBook Pro. Do not start
or restart a local Ollama server or model runner on the MacBook. Desktop
responsiveness takes priority; an unavailable Alienware endpoint is not
permission to fall back to the MacBook's CPU.

The 0 key selects workspace 10. Keep STRATA on numeric workspace 10, displayed
after workspaces 1–9; do not introduce a separate workspace 0 for it.
Only Strata–Fossil is anchored there. Summon the console and system monitor on
the current workspace; neither dropdown is pinned to a workspace.

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
mailbox source is configured. Periodic refreshes must be 60–300 seconds, except
Scripture: select and display a new passage once per hour (3600 seconds).

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

Scripture search is editable directly in the existing desktop bar; do not open
a separate picker window. Click or Super+/ focuses the entry, and selection,
Escape or focus loss releases the keyboard. This replaces the earlier button
that launched Fuzzel.

Scripture shortcuts: Super+/ searches only Bible verses. Super+Shift+/ searches
all collections, with Bible results after Torah, Talmud and reflections. Do not
add non-Bible results or collection-switch commands to the Bible-only picker.
Enter must save the choice and refresh only the Scripture card immediately;
hold a manual choice for one hour before automatic rotation resumes. Scripture
history is durable personal SQLite data, separate from the rebuildable study
cache: preserve full passages, study material, sources, provenance and linked
additional notes. Never rebuild or commit the history database. Keep all other
background card intervals at 60–300 seconds. Preserve the offline
English Torah (JPS 1917) and Babylonian Talmud (William Davidson) collection,
source manifests and attribution alongside the Bible and curated reflections.

Keep the earlier Scripture reflections and practice text available. Scripture
study notes, inspirations, and observations use the SQLite reading library
rebuilt from Fossil-tracked canonical records; never add application tables to
the Fossil repository database. Generate new study prose only with AI on the Alienware's GPUs,
ground it in attributed high-quality sources, and preserve source excerpts,
hashes, and model provenance. Do not silently use a cloud model or include the
separate personal desktop journal in this published study collection.

Keep Conky placement stable through window, focus and fullscreen changes; the
user prefers no automatic reflow to abrupt motion or continuous CPU work.
Use fixed caption clearance when laying out cards, favor useful lower-right
space, and preserve native click-to-advance on the reading cards. Scripture
search may adapt to free/occupied edges and must follow the active theme.

Scripture cards must read continuously: passage and source citation, reflection,
then practice. Do not insert a separate speaker/“who said” or duplicate title
section. Preserve author/source metadata in the reading library and history.
