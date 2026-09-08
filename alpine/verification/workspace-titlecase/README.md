# Empty workspace Titlecase typography

The native helper now recognizes reserved empty workspace names without regard
to ASCII letter case. Active numbers and names remain bold and bright; inactive
numbers remain bold while names use regular weight. Process suffixes keep their
existing subdued style. Legacy uppercase spelling and workspace 0/10 recognition
are retained. The gallery implementation is unchanged.

The updated native GTK fixture failed against the unchanged r7 helper: an active
Titlecase name had weight 400 instead of 700. With the one-line fix it passed all
126 checks under fatal GTK warnings in private Xvfb and D-Bus sessions. The same
126 checks passed when linked directly to the library extracted from the signed
r8 APK. Logs and source hashes accompany this record.

Two builds from frozen inputs ran with networking disabled and produced
byte-identical signed APKs. Both signatures and the local Fossil unversioned
archive readback were verified. A fakeroot diagnostic appears in the build logs;
both builds succeeded, and every payload entry's ownership and mode was checked
in the signed archive. The package metadata records the exact hashes.

The exact r8 APK was installed with networking disabled. All 1119 packages
remain installed and every unrelated package identity is unchanged. The new
immutable restoration lock is `alpine/packages/locks/368a9c51ce0830f4e791.json`;
it matches current installed identities, world constraints, repositories and
public keys. The completed r7 metadata is retained here as a historical record.

Live Waybar was restarted with its original desktop environment. PID 26778
maps the installed r8 library inode, with no deleted mapping, and the installed
SHA-256 matches the extracted signed APK. See `activation.json`.
