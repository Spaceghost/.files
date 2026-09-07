# Release preparation

The current version is `0.1.0.dev0`. This branch is for review, with no tag,
GitHub release or package registry publication performed automatically.

Before a first distributable release:

1. Choose the project license and add its text and package metadata.
2. Decide whether to move the standalone project into a dedicated repository.
3. Complete the LXQt with Sway and physical input checks in `VALIDATION.md`.
4. Review app baseline coverage and the keyboard-device access requirement.
5. Set the intended version in `pyproject.toml` and `src/superhold/__init__.py`.
6. Run the tests, parser checks and wheel/sdist build from a clean checkout.
7. Install the wheel into an isolated environment with system GI bindings;
   verify the executable, menu entry, preview, daemon lifecycle and status.
8. Record artifact SHA-256 hashes and attach the wheel, sdist and checksums to
   a draft GitHub release. Publish only after the remaining checks are resolved.

Build commands:

```sh
python3 -m unittest discover -s tests -v
python3 -m build --no-isolation
sha256sum dist/*.whl dist/*.tar.gz > dist/SHA256SUMS
```

The development CI runs tests and builds archives without requiring graphical
or input access. The preparation workflow builds the archives and records checksums in its
logs. It uses plain commands in Python containers to respect the parent
repository policy allowing only actions owned by Spaceghost. It does not
upload artifacts, publish a release or install into a user's active session;
local release candidates are available under `dist/`.
