# Pithos keyring on Sway

Installed Alpine `gnome-keyring` 50.0-r0 and its dependencies. Added
`gnome-keyring` and the already installed `pithos` to the desktop package list.
The packaged org.freedesktop.secrets D-Bus service starts the secrets component
on demand; the existing Sway session already supplies a user bus and graphical
activation environment, so no startup script or PAM changes were necessary.

Created a password-protected default collection labelled Login through the
GNOME secure desktop prompt. Keyring contents remain private under the user
HOME and are not archived in Fossil. Unlocking on subsequent logins may prompt
for the keyring password; automatic login-password unlocking was not configured.

## Validation

- Live D-Bus activation launched gnome-keyring-daemon with components=secrets.
- Default collection creation succeeded and reported unlocked.
- A randomly generated temporary secret was stored and read back successfully
  in the default collection, then deleted. No secret was printed or archived.
- Pithos 1.6.1's own SecretService.unlock_keyring callback succeeded and selected
  the persistent default collection, rather than falling back to session storage.
- Pithos was launched through the running Sway compositor.
- Snapshot 8ca6ff2e0e60e4427ae7 records the complete installed package closure;
  all 949 exact APK artifacts passed archive verification. This includes packages
  installed before this task, preserving the current host's recovery closure.
- Pandora account sign-in/playback and reboot/unlock behavior remain unverified.

## Recovery

Use alpine/bin/package-archive with alpine/packages/current-lock to restore the
archived APK closure (see alpine/packages/RESTORE.md). The keyring password and
Pandora credentials must be entered locally; restoring packages does not restore
private credentials. To remove this integration, remove gnome-keyring from the
APK world and desktop package list after confirming no other apps need it.
Do not delete the private keyring files as part of package removal.
