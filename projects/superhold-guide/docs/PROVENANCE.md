# Source provenance

The standalone package begins with the contextual shortcut feature in
`Spaceghost/.files`, Fossil check-in
`4fcdfda1f5caf45ef834688ab13225c7ed2345671bae94ca8010e4e3721ac4ae`.
`provenance.json` records the exported files and hashes before adaptation.
No dotfile history, authentication, live configuration, or recorded input was
copied into the project.

The first extraction renamed the package and service to `superhold`, separated
its XDG paths, added a version command and logind lock hint, removed the original
machine's Neovim mappings from the baseline, and supplied Python packaging and
optional LXQt/Sway integration. MBP Intel lock readiness recognition remains an
optional compatibility check. Human-readable MBP Intel command labels are parser
rules; those helper programs are neither bundled nor required.

The `0.2.0.dev0` work makes this a separate interactive application: a searchable
and clickable guide, native shortcut delivery through `wtype`, a persistent
normal GTK window, an independent GTK settings screen, versioned JSON settings,
and optional hold-to-release presentation. Its Git checkout is independent of
the contributor Fossil checkout. The intended standalone destination is
`Spaceghost/superhold`; dedicated remote publication remains pending repository
access. The original installed overlay and its configuration were not changed.

`docs/screenshot.png` is inherited from the original feature's disposable Sway
terminal fixture. `docs/guide.png` and `docs/settings.png` document the standalone
application in disposable graphical sessions. `runtime-focus-validation.json`
contains isolated focus events, settings results, and implementation findings;
it excludes host environment dumps and live application data. The original
host runtime verification JSON was not exported because it contained machine
and session details. Final standalone checks are recorded in `VALIDATION.md`.

Baseline source URLs appear in `shortcut_profiles.py`. These profiles describe
partial documented defaults, not live introspection of app menus. AT-SPI
feasibility evidence is historical and explicitly separate from the current
native keyboard activation backend. Source ownership and the unresolved license
choice remain documented in `LICENSE-STATUS.md`.
