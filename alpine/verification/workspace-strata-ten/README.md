# Workspace ten typography — 2026-09-07

The empty `10: STRATA` workspace receives the same emphasis as the other named
workspaces. Both digits remain bold; the active name is bold and bright, while
the inactive name is regular. Legacy `0: STRATA` recognition is retained during
the live migration. Application suffix styling is unchanged.

The updated native GTK fixture first failed against installed r6 because the
active STRATA name had weight 400 instead of 700. All 49 checks then passed
against the library extracted from the signed r7 APK, with fatal GTK warnings
in private Xvfb, D-Bus, HOME and XDG directories. The retained logs include both
results. The fixture covers both workspace digits, focus transitions, label
replacement, legacy zero recognition and normal application suffixes.

Two builds from a frozen source copy ran with networking disabled. Both signed
APKs are byte-identical and pass `apk verify`. The content-addressed Fossil
unversioned archive was exported and compared byte for byte. `art.c` is unchanged;
earlier gallery gesture and Waybar integration evidence remains explicitly
historical in the package verification record.

- APK: `oldbook-waybar-art-1.0.0-r7.apk`
- APK SHA-256: `4b10d6fc6a62f130c977f768d0e26045bad02d099c2d6c1e3013b3f6fda5385b`
- Library SHA-256: `eab5f93adda44e85b6729f8c7cedd5ba6b49a0ed515da317f46c9ce9e4bf45f5`
- APK identity: `Q1zaxuiP8v8BCbkE4QJoIcoU4kxg0=`

The offline install changed only this package among 1,119 installed identities.
The immutable lock `alpine/packages/locks/2866c8caaa0d133d4cc2.json` matches the
installed package closure and updated world identity pin. The preceding r6
lock and artifact remain available. Waybar was restarted with its original environment and maps the installed r7
library. A targeted stylesheet reload and subsequent repaint produced the
verified workspace-strip screenshot; focus and windows were preserved. Runtime
evidence is in `activation.json`. A separate Sway configuration notice below
the bar is being handled with the compositor configuration change.

![Live workspace strip with STRATA numbered 10](workspace-ten-live.png)

For recovery, reinstall the archived signed r6 APK and restart only Waybar.
This recovers the previous helper; the workspace numbering is managed separately
by Sway and the STRATA service.
