# Source provenance

The standalone package starts from the contextual shortcut feature in
`Spaceghost/.files`, Fossil check-in
`4fcdfda1f5caf45ef834688ab13225c7ed2345671bae94ca8010e4e3721ac4ae`.
`provenance.json` records the exact exported files and hashes before package
adaptation. No dotfile history, authentication, live configuration, input
recordings or runtime metadata was copied into this project.

Adaptations rename the Python package and service to `superhold`, use a
separate XDG profile directory, add a version command and logind lock hint,
remove the original machine's Neovim mappings from the baseline, and provide
normal Python packaging and optional LXQt/Sway integration files. Recognition
of the original lock readiness marker remains for compatibility when present.
Human-readable labels for Oldbook helper commands are harmless optional
parsing rules; the helpers are not bundled or required.

The screenshot was exported from the source feature's disposable Sway test,
which displayed synthetic terminal text. The original runtime verification
JSON is intentionally not included because it contains machine/session paths
and identifiers. Standalone verification is recorded separately.

Shortcut baseline source URLs appear in `shortcut_profiles.py`. These are
documented defaults, not introspection of application menus. Source ownership
and the pending license decision are recorded in `LICENSE-STATUS.md`.
