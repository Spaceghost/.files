# 1Password on Alpine

Installed on oldbook, 2026-09-07:

| Component | Version | Installation |
| --- | --- | --- |
| Desktop | 8.12.12 | User Flatpak `com.onepassword.OnePassword` from Flathub |
| CLI | 2.39.0-r1 | Official signed APK `1password-cli@1password`; command `op` |
| Firefox extension | 8.12.32.33 | Mozilla-signed XPI, one-time Firefox installation policy |

Open **1Password** in the launcher, or run
`flatpak run com.onepassword.OnePassword`. The native Wayland welcome/sign-in
window and a live HTTPS connection were observed. Sign in locally; no account
credentials are part of this installation record.

Close and reopen Firefox to apply the extension to the existing profile. Its
installation was tested in a disposable Firefox 154.0 profile: active, enabled,
and signed (`signedState=2`). The running personal browser was not restarted.

Alpine uses musl; the desktop app requires glibc. The Flatpak runtime supplies
glibc 2.42. Upstream documents that its Flatpak installation cannot integrate
desktop unlock with Firefox or the CLI, use system authentication, or provide
the SSH agent. Sign in to the browser extension and CLI separately. Flathub's
community package can lag the vendor's native release. Startup also reports
unavailable system D-Bus monitoring and global shortcuts in this environment;
the app itself renders successfully.

## Sources and artifacts

- [1Password Linux installation](https://support.1password.com/install-linux/)
- [CLI installation](https://developer.1password.com/docs/cli/get-started/)
- [Flathub desktop package](https://flathub.org/apps/com.onepassword.OnePassword)
- [Official Firefox extension](https://addons.mozilla.org/en-US/firefox/addon/1password-x-password-manager/)
- [Mozilla Extensions policy](https://firefox-admin-docs.mozilla.org/reference/policies/extensions/)

`cli.json` records the official repository, public key, APK identity, SHA256,
and Fossil artifact name. Full APK snapshot
`alpine/packages/locks/ae4f34e18c202f0b71c0.json` archives all 1007 installed
packages, including Flatpak and its Alpine dependencies. Snapshot validation
checked APK signatures and installed identities. The complete lock reflects
the current machine, including packages installed before this task. Comparing
the previous 984-package snapshot found exactly 23 additions and no removed
packages, changed versions, or changed binary identities.

`firefox.json` records the Mozilla API hash and successful isolated runtime
check. Its XPI is archived in Fossil unversioned storage; exporting it and
rechecking the Mozilla SHA256 passed. The root-owned runtime copy is
`/usr/local/share/1password/firefox/1password-firefox-8.12.32.33.xpi`.
`/etc/firefox/policies/policies.json` contains only `Extensions.Install` with
that local path. It does not lock the extension against disabling/removal.

`gui.json` records every installed Flatpak commit, the vendor tarball checksum,
and executable hash. `flatpak.metadata` records the signed package metadata.
The Flathub remote verifies both commits and repository summaries. Flatpak
application/runtime objects are installed under `~/.local/share/flatpak`;
a complete offline Flatpak restore has not been archived or verified.

For this already-running desktop session, links in `~/.local/share/applications`
and `~/.local/share/icons/hicolor/512x512/apps` expose the exported desktop entry
and icon. The Flatpak APK supplies `/etc/profile.d/flatpak.sh` for later logins.
The desktop entry passed `desktop-file-validate` (only a category hint).

## Network rules

`firewall/` records six added OpenSnitch rules and their verification: UID 1000,
exact `/usr/bin/flatpak` or `/usr/bin/op`, supplemental executable MD5, TCP443,
and TCP/UDP DNS only to the two current resolvers. Existing rules and defaults
were retained. All 14 bootstrap unit tests and 13 isolated namespace checks
passed before installation. The live watcher loaded the rules; Flatpak then
downloaded successfully and the credential-free `op update` check succeeded.

These rules are specific to the installed executable hashes and DNS servers.
After updates or a resolver change, regenerate/review the relevant rules with
`alpine/security/firewall/bootstrap-rules`; test in isolation before applying.
Use the firewall README's direct-write procedure for an existing rule, because
atomic replacement does not trigger the current daemon's watcher correctly.
Do not assume a supplemental MD5 operand is a cryptographic identity boundary.

## Updates and recovery

Update the desktop with `flatpak --user update com.onepassword.OnePassword`.
Update the CLI through its tagged APK repository. Firefox handles extension
updates normally after installation; the local XPI records the initial version.
Regenerate package snapshots after package changes.

Use the repository's package-archive restore procedure for exact APK recovery.
To install the desktop online on a restored machine, run as the normal user:

```sh
flatpak --user remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak --user install flathub com.onepassword.OnePassword
```

Recreate the Firefox policy by merging the local XPI path into
`policies.Extensions.Install`; preserve other policies if present. Export the
XPI from the Fossil artifact named in `firefox.json` and verify its SHA256 first.

To remove the desktop, use
`flatpak --user uninstall com.onepassword.OnePassword` without `--delete-data`.
Remove its two launcher/icon links if present. Remove the CLI with
`doas apk del 1password-cli`, and remove only its tagged repository line and
public key if no longer needed. Remove only this extension's `Install` entry
from Firefox policy, restart Firefox, then remove the add-on in `about:addons`.
After removing that policy entry, the runtime XPI under
`/usr/local/share/1password/firefox/` can be deleted. Delete the policy file only
if it contains no other policies.
The six exact firewall filenames are recorded in `firewall/manifest.json`;
remove those rules if these programs no longer need network access.

Account authentication, vault operations, reboot persistence, and full offline
Flatpak recovery remain untested. Private installation logs stay under
`~/.local/share/oldbook/1password` and `~/.local/share/1password-install`.
