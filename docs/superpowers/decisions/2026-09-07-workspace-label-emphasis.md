# Workspace label emphasis

The focused workspace number and name use bold bright text. Inactive numbers
remain bold with regular names. Process suffixes stay regular and subdued. A
soft accent tint behind the active label keeps the bright text legible in both
desktop themes.

The existing native Waybar helper applies Pango attribute ranges while keeping
labels and Sway workspace names plain. Focus and label changes update the
ranges, and layout discovery covers buttons that Waybar replaces during a
rename. Finalized bindings are released, and deinit restores original attributes.

The r5 package passed two identical offline builds, signature and archived-byte
verification, 38 GTK checks, six real Waybar states and four tooltip checks.
See [synthetic screenshots and native attributes](../../../alpine/verification/workspace-emphasis/README.md).
Only Waybar was restarted. Its loaded installed library matches the tested APK.
The restoration lock matches all 1117 installed package identities and includes
18 already installed Pylast dependencies omitted by the preceding lock.

Recovery: reinstall the archived r4 APK, restore the three Waybar stylesheets
from the parent check-in, and restart Waybar. Workspace names require no rollback.
