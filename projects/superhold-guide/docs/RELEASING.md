# Release preparation

The standalone application is version `0.2.0.dev1`. It has its own Git checkout
and Python package. The intended GitHub destination is `Spaceghost/superhold`;
at preparation time that destination returned HTTP 404 to the available
publisher. Create the repository or provide access before pushing the
standalone history. These changes have not been pushed back into a nested
project in `Spaceghost/.files`.

No release tag, GitHub release, package registry publication, or installation
into the existing desktop is performed by the build workflow.

## Release blockers

- Select a license, add its full text, and update package metadata. See
  `LICENSE-STATUS.md`; extraction did not assign a license.
- Resolve persistent-window behavior over fullscreen applications. The normal
  floating guide currently maps behind them. Sway's explicit focus command
  disables the target's fullscreen state, and an ON_DEMAND layer loses initial
  focus. The current application does not silently change fullscreen state.
- Complete full LXQt-with-Sway testing, physical keyboard checks, and the
  remaining matrix in `VALIDATION.md`.
- Make the dedicated repository accessible and verify its own CI against the
  exact standalone revision before tagging.

## Candidate checks

1. Review partial app coverage, unsupported shortcut reasons, and the keyboard
   access requirement. Confirm that no unavailable row can trigger guessed input.
2. Check settings Save, Cancel, Reset, malformed-file preservation, explicit
   config paths, and the daemon's idle configuration reload.
3. Test one-shot `show`, opening through an existing daemon, menu focus capture,
   hold/release and focus-loss behavior, filtering, click and Enter activation,
   original-target restoration, key-release waits, cancellation, and cleanup.
4. Run lock/session, compositor shutdown, hotplug, monitor scaling, fullscreen,
   and fresh-login checks in isolated sessions before the full desktop matrix.
5. Set matching versions in `pyproject.toml` and `src/superhold/__init__.py` and
   update the changelog for the final scope.
6. Run tests, desktop-file validation, and wheel/sdist builds from a clean
   checkout. Install the wheel into an isolated environment with system GI
   bindings; verify both menu entries and optional startup examples.
7. Record artifact SHA-256 hashes and validation evidence. Prepare a draft
   release containing the wheel, sdist, and checksums only after the blockers
   above have been resolved; then review that concrete candidate for publication.

```sh
python3 -m unittest discover -s tests -v
desktop-file-validate share/applications/superhold.desktop
desktop-file-validate share/applications/superhold-settings.desktop
desktop-file-validate integrations/lxqt/superhold.desktop
python3 -m build --no-isolation
sha256sum dist/*.whl dist/*.tar.gz > dist/SHA256SUMS
```

The development workflow tests Python 3.10 and 3.14 in Alpine containers and
builds archives without graphical or input access. It fetches the public
source revision with plain Git commands and records checksums in its log.
A private repository would need an authenticated checkout configuration. CI
does not prove physical input, native graphical delivery, or full LXQt support,
and does not upload artifacts or publish releases. Local candidates are under
`dist/`; final counts and runtime results belong in `VALIDATION.md`.
