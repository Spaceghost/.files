# Repository Guidelines

## Project Structure & Module Organization

The contributor checkout is `~/.files`, a Fossil repository seeded from
`Spaceghost/.files` on GitHub. Its database is
`~/.local/share/fossil/files.fossil`; work on the `alpine-oldbook` branch.
Preserve the existing `~/.files/AGENTS.md` and follow its repository instructions.
Historical dotfiles remain at the checkout root. Alpine-specific configuration
belongs in `alpine/desktop/`, security services in `alpine/security/`, package
recipes and locks in `alpine/packages/`, and artwork in `alpine/assets/`.
Implementation plans and design decisions live in `docs/superpowers/`.

## Build, Test, and Development Commands

Run commands from `~/.files`:

- `fossil status` and `fossil diff`: review pending changes.
- `python3 -m unittest discover -s alpine/tests -v`: exercise deployment recovery.
- `alpine/bin/deploy-home --target /tmp/mbp-intel-preview`: deploy into a disposable HOME.
- `alpine/bin/package-archive --help`: inspect package snapshot and restore commands.
- `sway --validate --config alpine/desktop/.config/sway/config`: validate desktop syntax.

## Coding Style & Naming Conventions

Use portable POSIX shell with quoted variables; the default shell is Alpine
`ash`, so avoid Bash-only syntax. Use four spaces in Python and descriptive
hyphenated executable names. Run ShellCheck on changed shell scripts. Keep
configuration files focused on one application and share the purple palette.

## Testing Guidelines

Use Python `unittest` for deployment and recovery behavior. Name tests
`test_*.py`. Validate configuration with its application's parser. Test firewall
and radio changes in isolation before affecting the active connection. Preserve
runtime evidence; syntax validation alone does not prove security or a rebuild.

## Commit & Review Guidelines

Existing history uses concise imperative subjects, often prefixed with a scope,
for example `tmux: ...`, `docs: ...`, or `fix ...`. Commit with Fossil after
reviewing the exact paths. Describe behavior, validation, and recovery steps;
include screenshots for visual changes. Remote publishing requires authorization.

## Configuration & Reproducibility

Keep APK repositories on HTTPS and testing explicitly tagged. Archive exact APK
artifacts and hashes. Never commit passwords, Wi-Fi PSKs, private signing keys,
or Codex authentication files. Record unfinished checks in `alpine/PROGRESS.md`.
