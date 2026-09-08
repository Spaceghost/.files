# Resume: every application must follow the selected desktop theme

Paused at the user's explicit request on 2026-09-07: wrap up quickly and leave
findings to continue when capacity improves. The original issue is unresolved;
this checkpoint changes documentation only, with no live restarts or theme switch.

## Confirmed observations

- Selected theme during investigation: `vespersteel-archive-968881e8a08a`.
  `~/.config/gtk-3.0/gtk.css` points to that theme's profile in `alpine/themes/`.
- The running service is the GTK project `projects/superhold-guide`, not the
  alternative Qt Superhold. PID was 23106 (rediscover before acting).
- `~/.local/bin/superhold` launches
  `~/.local/share/superhold/versions/0.2.0.dev0-70e5051/bin/superhold`.
  Its Python package lives below that prefix at
  `lib/python3.14/site-packages/superhold/`.
- Installed `shortcut_overlay.py:695-700` reads `active_palette()` and loads CSS
  once during window construction. No theme refresh is present there.
  Installed `theme.py` is absent. Installed `shortcut_window.py` and `settings.py`
  differ from checkout copies.
- The checkout already contains a newer implementation:
  `projects/superhold-guide/src/superhold/theme.py` defines `DesktopTheme`, which
  polls GTK user CSS every second and handles symlink replacement;
  `shortcut_overlay.py:659-660` and `settings.py:35-36` attach it to windows.
  This implementation has NOT been validated or installed in this task.
  Existing design and tests: that project's
  `docs/superpowers/2026-09-07-desktop-themes.md` and `tests/test_theme.py`.
- `alpine/desktop/.local/bin/oldbook-theme:197` refreshes several running clients,
  but has no Superhold refresh. Lines 246-251 explicitly leave running Firefox,
  btop and Neovim on their previous styling. These are outstanding against the
  user's requirement that all things stay updated with the selected theme.

## Resume here

1. Re-read repository instructions and current status. The checkout is Fossil,
   branch `alpine-oldbook`, with substantial unrelated pending work. Another
   operation advanced the checkout during this investigation; inspect current
   files rather than assuming the recorded revision or theme still applies.
2. Compare installed Superhold against the source, especially hold/dismiss fixes
   documented in `alpine/PROGRESS.md` under the 2026-09-07 Super-key work. Preserve
   those behaviors when packaging the newer theme code. Do not blindly replace
   only a few modules or assume an existing source fix has been deployed.
3. Run Superhold's existing theme/unit tests, then reproduce and verify in a
   private compositor: change between strongly different complete themes while
   the SAME guide/settings window stays alive. Check reopen, selected rows,
   search, release overlay and typography. Capture screenshots/runtime evidence.
4. Build/install a fresh versioned prefix, retain the old prefix for recovery,
   update the launcher and restart only Superhold after validation. Confirm the
   actual running interpreter/package paths and live theme change afterward.
5. Audit the other application refresh gaps and repair supported live update
   paths without destroying user sessions. Test both built-in and generated
   complete themes. Track any genuinely unsupported cases explicitly.
6. Update PROGRESS with validation/recovery evidence, review exact changed paths
   and commit locally in Fossil. Remote publication still requires authorization.

## Validation in this checkpoint

Read-only source/live package inspection, launcher/process inspection and GTK
symlink inspection only. No test suite or visual verification ran. No fix is
claimed. Runtime palette refresh is missing from the inspected installed guide;
source/install drift is the leading cause to confirm with the live reproduction.

## Additional read-only audit leads (runtime confirmation pending)

- Qt/LXQt: `desktop_theme.py:104-115` derives profiles from Gruvbox files, which
  include qt6ct but not LXQt configuration/palettes. `test_lxqt_theme.py` describes
  LXQt as the actual Qt integration; check this against the live environment and
  extend theme profiles to the actual Qt consumer. Current completeness tests
  require qt6ct files without covering that LXQt path.
- Existing profiles: `ensure_profile()` at `desktop_theme.py:168-180` fills missing
  files but keeps existing ones. Compare generated files against `render_profile()`
  after descriptor updates, while preserving intentional authored overrides.
- Other GTK clients: `oldbook-gtk-settings` updates desktop settings, but arbitrary
  persistent GTK clients may retain loaded user CSS when its symlink changes.
  Scripture and decoration have their own polling; validate other consumers.
- Expand integration coverage to check deployed selection and observed running
  consumers together; existing profile completeness tests primarily check files.
