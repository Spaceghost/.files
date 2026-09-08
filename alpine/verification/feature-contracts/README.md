# Feature preservation baseline

The user asked to pin desktop behavior after repeated feature loss. The 30
contracts in `alpine/FEATURES.md` preserve the latest choices, record intentional
replacements, and distinguish desired behavior from historical test evidence.
`alpine/AGENTS.md` requires affected contracts to be read before changes; a new
explicit user instruction may update a pin, while an unresolved conflict needs
the user's decision. Existing repository instructions remain intact.

`alpine/bin/check-features` maps proposed paths or current Fossil changes to
overlapping features and existing unittest files. `--run` executes each selected
check once and returns failure if any fails. Unknown feature IDs are rejected;
unmapped paths and manual-only contracts remain visible. Safe project-relative
paths cover the installed guide's separate source directory as well as Alpine.
The JSON index and Markdown contract must contain exactly the same stable IDs.

Nine focused checks pass. They cover cross-feature theme impact, keyboard-mode
impact, deleted profiles, external project source, unmapped changes, invalid
feature selection, path safety, index integrity, and deduplicated execution with
failure propagation. `impact-examples.json` retains representative reports;
`evidence.json` pins the exact source hashes used by these checks.

This verifies the preservation workflow. It does not rerun every underlying
feature suite or establish physical frame rate, fresh boot, live application
refresh or hardware input. Each contract links the relevant narrower tests and
native evidence. A review must still inspect source/install drift and user
settings before activation.

Reproduce from the checkout:

```sh
python3 -m unittest discover -s alpine/tests -p test_feature_contracts.py -v
alpine/bin/check-features alpine/wallpapers/desktop_theme.py
alpine/bin/check-features --feature GHOST-BRAND --run
```

The checker only reads files unless `--run` is requested, in which case it runs
the selected existing tests. It never deploys, commits, publishes, changes a pin
or approves a conflict automatically.
